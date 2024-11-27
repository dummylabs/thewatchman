"""Watchman parser funcions."""

import fnmatch
import os
import re
import time
import anyio
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .logger import INDENT, _LOGGER
from .utils import async_get_next_file, get_config
from ..const import (
    BUNDLED_IGNORED_ITEMS,
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_INCLUDED_FOLDERS,
    DEFAULT_HA_DOMAINS,
    DOMAIN,
    HASS_DATA_FILES_IGNORED,
    HASS_DATA_FILES_PARSED,
    HASS_DATA_PARSE_DURATION,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    PARSER_STOP_WORDS,
)


async def parse_config(hass: HomeAssistant, reason=None):
    """Parse home assistant configuration files."""

    start_time = time.time()

    included_folders = get_included_folders(hass)
    ignored_files = get_config(hass, CONF_IGNORED_FILES, None)
    _LOGGER.debug(
        f"::parse_config:: called due to {reason} IGNORED_FILES={ignored_files}"
    )

    parsed_entity_list, parsed_service_list, files_parsed, files_ignored = await parse(
        hass, included_folders, ignored_files, hass.config.config_dir
    )
    hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST] = parsed_entity_list
    hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST] = parsed_service_list
    hass.data[DOMAIN][HASS_DATA_FILES_PARSED] = files_parsed
    hass.data[DOMAIN][HASS_DATA_FILES_IGNORED] = files_ignored
    hass.data[DOMAIN][HASS_DATA_PARSE_DURATION] = time.time() - start_time
    _LOGGER.debug(
        f"{INDENT}Parsing took {hass.data[DOMAIN][HASS_DATA_PARSE_DURATION]:.2f}s."
    )


async def async_get_short_path(yaml_file, root):
    """Provide short path for unit test mocking."""
    return os.path.relpath(yaml_file, root)


async def parse(hass, folders, ignored_files, root_path=None):
    """Parse a yaml or json file for entities/services."""
    parsed_files_count = 0
    entity_pattern = re.compile(
        r"(?:(?<=\s)|(?<=^)|(?<=\")|(?<=\'))([A-Za-z_0-9]*\s*:)?(?:\s*)?(?:states.)?"
        rf"(({"|".join([*Platform, *DEFAULT_HA_DOMAINS])})\.[A-Za-z_*0-9]+)"
    )
    service_pattern = re.compile(
        r"(?:service|action):\s*([A-Za-z_0-9]*\.[A-Za-z_0-9]+)"
    )
    comment_pattern = re.compile(
        rf"(^\s*(?:{"|".join([*PARSER_STOP_WORDS])}):.*)|(\s*#.*)"
    )
    parsed_entity_list = {}
    parsed_service_list = {}
    parsed_files = []
    effectively_ignored_files = []
    async for yaml_file, ignored in async_get_next_file(folders, ignored_files):
        short_path = await async_get_short_path(yaml_file, root_path)
        if ignored:
            effectively_ignored_files.append(short_path)
            continue

        try:
            lineno = 1
            async with await anyio.open_file(
                yaml_file, mode="r", encoding="utf-8"
            ) as f:
                async for line in f:
                    line = re.sub(comment_pattern, "", line)
                    for match in re.finditer(entity_pattern, line):
                        typ, val = match.group(1), match.group(2)
                        if (
                            typ != "service:"
                            and "*" not in val
                            and not val.endswith(".yaml")
                        ):
                            add_entry(parsed_entity_list, val, short_path, lineno)
                    for match in re.finditer(service_pattern, line):
                        val = match.group(1)
                        add_entry(parsed_service_list, val, short_path, lineno)
                    lineno += 1
            parsed_files_count += 1
            parsed_files.append(short_path)
        except OSError as exception:
            _LOGGER.error("Unable to parse %s: %s", yaml_file, exception)
        except UnicodeDecodeError as exception:
            _LOGGER.error(
                "Unable to parse %s: %s. Use UTF-8 encoding to avoid this error",
                yaml_file,
                exception,
            )
    # remove ignored entities and services from resulting lists
    ignored_items = get_config(hass, CONF_IGNORED_ITEMS, [])
    ignored_items = list(set(ignored_items + BUNDLED_IGNORED_ITEMS))
    excluded_entities = []
    excluded_services = []
    for itm in ignored_items:
        if itm:
            excluded_entities.extend(fnmatch.filter(parsed_entity_list, itm))
            excluded_services.extend(fnmatch.filter(parsed_service_list, itm))

    parsed_entity_list = {
        k: v for k, v in parsed_entity_list.items() if k not in excluded_entities
    }
    parsed_service_list = {
        k: v for k, v in parsed_service_list.items() if k not in excluded_services
    }

    _LOGGER.debug(f"{INDENT}Parsed {parsed_files_count} files: {parsed_files}")
    _LOGGER.debug(
        f"{INDENT}Ignored {len(effectively_ignored_files)} files: {effectively_ignored_files}",
    )
    _LOGGER.debug(
        f"{INDENT}Found {len(parsed_entity_list)} entities and {len(parsed_service_list)} actions"
    )

    return (
        parsed_entity_list,
        parsed_service_list,
        parsed_files_count,
        len(effectively_ignored_files),
    )


def add_entry(_list, entry, yaml_file, lineno):
    """Add entry to list of missing entities/services with line number information."""
    if entry in _list:
        if yaml_file in _list[entry]:
            _list[entry].get(yaml_file, []).append(lineno)
    else:
        _list[entry] = {yaml_file: [lineno]}


def get_included_folders(hass):
    """Gather the list of folders to parse."""
    folders = []

    for fld in get_config(hass, CONF_INCLUDED_FOLDERS, None):
        folders.append((fld, "**/*.yaml"))

    if get_config(hass, CONF_CHECK_LOVELACE):
        folders.append((hass.config.config_dir, ".storage/**/lovelace*"))

    return folders
