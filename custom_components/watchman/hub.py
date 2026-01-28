"""Watchman Hub - Asynchronous wrapper for WatchmanParser."""
import os
import fnmatch
import sqlite3
from typing import List, Dict, Any, Tuple, Callable

from homeassistant.core import HomeAssistant
from .utils.parser_core import WatchmanParser, get_domains
from .utils.logger import _LOGGER
from .const import BUNDLED_IGNORED_ITEMS

class WatchmanHub:
    """Asynchronous wrapper (Adapter) for the synchronous parser."""

    def __init__(self, hass: HomeAssistant, db_path: str):
        self.hass = hass
        self.db_path = db_path

        # inject Home Assistant's executor to run process config files asynchronously
        async def ha_executor(func: Callable, *args: Any):
            return await self.hass.async_add_executor_job(func, *args)

        self._parser = WatchmanParser(db_path, executor=ha_executor)
        self.cached_items = {}
        
        # Verify DB integrity on startup
        self.hass.async_add_executor_job(self._parser.check_and_fix_db)

    async def async_get_parsed_entities(self) -> Dict[str, Any]:
        """Return a dictionary of parsed entities and their locations."""
        return await self.hass.async_add_executor_job(
            self._get_parsed_items_sync, 'entity'
        )

    async def async_get_parsed_services(self) -> Dict[str, Any]:
        """Return a dictionary of parsed services and their locations."""
        return await self.hass.async_add_executor_job(
            self._get_parsed_items_sync, 'service'
        )

    def _get_parsed_items_sync(self, item_type: str) -> Dict[str, Any]:
        """Fetch and filter parsed items from the database."""
        from .utils.utils import get_config
        from .const import CONF_IGNORED_ITEMS

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
                result_dict[entity_id] = {"locations": {}, "automations": set()}

            if path not in result_dict[entity_id]["locations"]:
                result_dict[entity_id]["locations"][path] = []
            result_dict[entity_id]["locations"][path].append(line)

            # item[6] is parent_id
            parent_id = item[6]
            if parent_id:
                result_dict[entity_id]["automations"].add(parent_id)

        return result_dict

    async def async_parse(
        self,
        ignored_files: List[str],
        force: bool = False
    ) -> None:
        """Asynchronous wrapper for the parse method."""
        custom_domains = get_domains(self.hass)

        await self._parser.async_parse(
            self.hass.config.config_dir,
            ignored_files,
            force,
            custom_domains,
            base_path=self.hass.config.config_dir
        )

        self.cached_items = {}

    async def async_get_last_parse_info(self) -> Dict[str, Any]:
        """Return the duration and timestamp of the last successful scan."""
        return await self.hass.async_add_executor_job(self._get_last_parse_info_sync)

    def _get_last_parse_info_sync(self) -> Dict[str, Any]:
        """Return the duration and timestamp of the last successful scan."""
        try:
            return self._parser.get_last_parse_info()
        except sqlite3.OperationalError as e:
            _LOGGER.warning(f"Database busy (get_last_parse_info), returning default: {e}")
            return {"duration": 0.0, "timestamp": None, "ignored_files_count": 0, "processed_files_count": 0}
