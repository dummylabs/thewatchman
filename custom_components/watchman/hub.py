"""Watchman Hub - Asynchronous wrapper for WatchmanParser."""
from collections.abc import Callable
import fnmatch
import sqlite3
from typing import Any

from homeassistant.core import HomeAssistant

from .const import BUNDLED_IGNORED_ITEMS, CONF_IGNORED_ITEMS
from .utils.logger import _LOGGER
from .utils.parser_core import ParseResult, WatchmanParser, get_domains
from .utils.utils import get_config


class WatchmanHub:
    """Asynchronous wrapper (Adapter) for the synchronous parser."""

    def __init__(self, hass: HomeAssistant, db_path: str) -> None:
        self.hass = hass
        self.db_path = db_path
        self._is_scanning = False

        # inject Home Assistant's executor to run process config files asynchronously
        async def ha_executor(func: Callable, *args: Any) -> Any:
            return await self.hass.async_add_executor_job(func, *args)

        self._parser = WatchmanParser(db_path, executor=ha_executor)
        self.cached_items = {}
        self._monitored_entities = None
        self._monitored_services = None

    @property
    def is_scanning(self) -> bool:
        """Return True if a scan is currently in progress."""
        return self._is_scanning

    def is_monitored_service(self, service_id: str) -> bool:
        """Check if service is monitored (fast cache check)."""
        if self._monitored_services is None:
            return False
        return service_id in self._monitored_services

    async def async_get_all_items(self) -> dict[str, dict[str, Any]]:
        """Return all parsed items (entities and services) in one pass."""
        return await self.hass.async_add_executor_job(self._get_all_items_sync)

    def _get_all_items_sync(self) -> dict[str, dict[str, Any]]:
        """Fetch ALL items in one go and split them in memory."""
        ignored_items = get_config(self.hass, CONF_IGNORED_ITEMS, [])
        final_ignored_items = list(set((ignored_items or []) + BUNDLED_IGNORED_ITEMS))

        entities = {}
        services = {}

        try:
            raw_items = self._parser.get_found_items(item_type='all')
        except sqlite3.OperationalError as e:
            _LOGGER.warning(f"Database busy during read, returning cached/empty data: {e}")
            # Try to return cached data if available, else empty
            # Note: cached_items is now structured differently?
            # For simplicity in this refactor, if DB fails, return empty structure.
            # Ideally we should cache the full 'entities'/'services' structure.
            return {"entities": {}, "services": {}}

        for item in raw_items:
            entity_id, path, line, item_type = item[0], item[1], item[2], item[3]

            # Filter ignored items
            is_ignored = False
            for pattern in final_ignored_items:
                if fnmatch.fnmatch(entity_id, pattern):
                    is_ignored = True
                    break

            if is_ignored:
                continue

            target_dict = entities if item_type == 'entity' else services

            if entity_id not in target_dict:
                target_dict[entity_id] = {"locations": {}, "automations": set(), "occurrences": []}

            if path not in target_dict[entity_id]["locations"]:
                target_dict[entity_id]["locations"][path] = []
            target_dict[entity_id]["locations"][path].append(line)

            parent_type = item[4]
            parent_alias = item[5]
            parent_id = item[6]

            context = None
            if parent_type or parent_alias or parent_id:
                context = {
                    "parent_type": parent_type,
                    "parent_alias": parent_alias,
                    "parent_id": parent_id
                }

            target_dict[entity_id]["occurrences"].append({
                "path": path,
                "line": line,
                "context": context
            })

            if parent_id and parent_type in ("automation", "script"):
                target_dict[entity_id]["automations"].add(parent_id)

        # Update fast lookups
        self._monitored_entities = set(entities.keys())
        self._monitored_services = set(services.keys())

        return {"entities": entities, "services": services}

    async def async_parse(
        self, ignored_files: list[str], *, force: bool = False
    ) -> ParseResult | None:
        """Asynchronous wrapper for the parse method."""
        if self._is_scanning:
            _LOGGER.debug("Scan already in progress, skipping request.")
            return None

        self._is_scanning = True
        try:
            custom_domains = get_domains(self.hass)

            (
                _entities,
                _services,
                _files_parsed,
                _files_ignored,
                _ent_to_auto,
                parse_result,
            ) = await self._parser.async_parse(
                self.hass.config.config_dir,
                ignored_files,
                force=force,
                custom_domains=custom_domains,
                base_path=self.hass.config.config_dir,
            )

            self.cached_items = {}
            # Reset fast cache so it's rebuilt on next access
            self._monitored_entities = None
            self._monitored_services = None
            return parse_result
        finally:
            self._is_scanning = False

    async def async_get_last_parse_info(self) -> dict[str, Any]:
        """Return the duration and timestamp of the last successful scan."""
        return await self.hass.async_add_executor_job(self._get_last_parse_info_sync)

    def _get_last_parse_info_sync(self) -> dict[str, Any]:
        """Return the duration and timestamp of the last successful scan."""
        try:
            return self._parser.get_last_parse_info()
        except sqlite3.OperationalError as e:
            _LOGGER.warning(f"Database busy (get_last_parse_info), returning default: {e}")
            return {"duration": 0.0, "timestamp": None, "ignored_files_count": 0, "processed_files_count": 0}
