"""Watchman Hub - Asynchronous wrapper for WatchmanParser."""
from collections.abc import Callable
import fnmatch
import sqlite3
from typing import Any

from homeassistant.core import HomeAssistant

from .const import BUNDLED_IGNORED_ITEMS
from .utils.logger import _LOGGER
from .utils.parser_core import ParseResult, WatchmanParser, get_domains


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

    async def async_init(self) -> None:
        """Initialize the hub and verify DB."""
        # Verify DB integrity on startup
        await self.hass.async_add_executor_job(self._parser.check_and_fix_db)

    @property
    def is_scanning(self) -> bool:
        """Return True if a scan is currently in progress."""
        return self._is_scanning

    def is_monitored_service(self, service_id: str) -> bool:
        """Check if service is monitored (fast cache check)."""
        if self._monitored_services is None:
            return False
        return service_id in self._monitored_services

    async def async_get_parsed_entities(self) -> dict[str, Any]:
        """Return a dictionary of parsed entities and their locations."""
        return await self.hass.async_add_executor_job(
            self._get_parsed_items_sync, 'entity'
        )

    async def async_get_parsed_services(self) -> dict[str, Any]:
        """Return a dictionary of parsed services and their locations."""
        return await self.hass.async_add_executor_job(
            self._get_parsed_items_sync, 'service'
        )

    def _get_parsed_items_sync(self, item_type: str) -> dict[str, Any]:
        """Fetch and filter parsed items from the database."""
        from .const import CONF_IGNORED_ITEMS
        from .utils.utils import get_config

        ignored_items = get_config(self.hass, CONF_IGNORED_ITEMS, [])
        final_ignored_items = list(set((ignored_items or []) + BUNDLED_IGNORED_ITEMS))

        try:
            if item_type not in self.cached_items:
                self.cached_items[item_type] = self._parser.get_found_items(item_type)

            raw_items = self.cached_items[item_type]
        except sqlite3.OperationalError as e:
            _LOGGER.warning(f"Database busy during read, returning cached/empty data: {e}")
            raw_items = self.cached_items.get(item_type, [])

        result_dict = {}
        for item in raw_items:
            entity_id, path, line = item[0], item[1], item[2]

            # Filter ignored items
            is_ignored = False
            for pattern in final_ignored_items:
                if fnmatch.fnmatch(entity_id, pattern):
                    is_ignored = True
                    break

            if is_ignored:
                continue

            if entity_id not in result_dict:
                result_dict[entity_id] = {"locations": {}, "automations": set(), "occurrences": []}

            if path not in result_dict[entity_id]["locations"]:
                result_dict[entity_id]["locations"][path] = []
            result_dict[entity_id]["locations"][path].append(line)

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

            result_dict[entity_id]["occurrences"].append({
                "path": path,
                "line": line,
                "context": context
            })

            if parent_id and parent_type in ("automation", "script"):
                result_dict[entity_id]["automations"].add(parent_id)

        # Update fast lookups
        if item_type == 'entity':
            self._monitored_entities = set(result_dict.keys())
        elif item_type == 'service':
            self._monitored_services = set(result_dict.keys())

        return result_dict

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
