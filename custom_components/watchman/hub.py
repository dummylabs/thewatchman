"""Watchman Hub - Asynchronous wrapper for WatchmanParser."""
import os
import fnmatch
from typing import List, Dict, Any, Tuple

from homeassistant.core import HomeAssistant
from .utils.parser_core import WatchmanParser, get_domains
from .const import BUNDLED_IGNORED_ITEMS

class WatchmanHub:
    """Asynchronous wrapper (Adapter) for the synchronous parser."""

    def __init__(self, hass: HomeAssistant, db_path: str):
        self.hass = hass
        self.db_path = db_path
        self._parser = WatchmanParser(db_path)

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
        
        raw_items = self._parser.get_found_items(item_type)
            
        result_dict = {}
        for item in raw_items:
            # item is now (entity_id, path, line, item_type, parent_type, parent_alias, parent_id)
            if not isinstance(item, (list, tuple)) or len(item) < 3:
                continue
                
            entity_id, path, line = item[0], item[1], item[2]
            
            # Filter ignored items
            is_ignored = False
            for pattern in final_ignored_items:
                if fnmatch.fnmatch(entity_id, pattern):
                    is_ignored = True
                    break
            
            if is_ignored:
                continue

            # Ensure we have a valid path and config_dir before calling relpath
            if path and self.hass.config.config_dir:
                rel_path = os.path.relpath(path, self.hass.config.config_dir)
            else:
                rel_path = path or "unknown"

            if entity_id not in result_dict:
                result_dict[entity_id] = {"locations": {}, "automations": set()}
            
            if rel_path not in result_dict[entity_id]["locations"]:
                result_dict[entity_id]["locations"][rel_path] = []
            result_dict[entity_id]["locations"][rel_path].append(line)
            
            # item[6] is parent_id
            parent_id = item[6] if len(item) > 6 else None
            if parent_id:
                result_dict[entity_id]["automations"].add(parent_id)
                
        return result_dict

    async def async_parse(
        self, 
        included_folders: List[Tuple[str, str]], 
        ignored_files: List[str], 
        ignored_items: List[str] = None, 
        force: bool = False
    ) -> None:
        """Asynchronous wrapper for the parse method."""
        custom_domains = get_domains(self.hass)
        
        await self.hass.async_add_executor_job(
            self._run_parse_sync, 
            included_folders, 
            ignored_files, 
            ignored_items, 
            custom_domains, 
            force
        )

    def _run_parse_sync(
        self, 
        included_folders: List[Tuple[str, str]], 
        ignored_files: List[str], 
        ignored_items: List[str], 
        custom_domains: List[str], 
        force: bool
    ) -> None:
        """Run synchronous parsing logic in executor."""
        client = self._parser

        # Adapt included_folders (list of tuples [(path, glob)]) to list of strings for WatchmanParser
        folder_globs = []
        for path, pattern in included_folders:
            if pattern:
                if os.path.isabs(path):
                    full_glob = os.path.join(path, pattern)
                    folder_globs.append(full_glob)
                else:
                    folder_globs.append(os.path.join(self.hass.config.config_dir, path, pattern))
            else:
                folder_globs.append(path)

        # client.parse returns lists (which we ignore now)
        # Note: We do NOT close the parser here because it's a long-lived object in the hub
        client.parse(folder_globs, ignored_files, force, custom_domains)

    async def async_get_last_parse_info(self) -> Dict[str, Any]:
        """Return the duration and timestamp of the last successful scan."""
        return await self.hass.async_add_executor_job(self._get_last_parse_info_sync)

    def _get_last_parse_info_sync(self) -> Dict[str, Any]:
        """Return the duration and timestamp of the last successful scan."""
        return self._parser.get_last_parse_info()