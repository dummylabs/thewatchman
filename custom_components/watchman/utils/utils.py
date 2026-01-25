"""Miscellaneous support functions for Watchman."""

import fnmatch
import os
import re
from types import MappingProxyType
from typing import Any

import anyio
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.helpers import entity_registry as er

from ..const import (
    CONF_COLUMNS_WIDTH,
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    CONF_FRIENDLY_NAMES,
    CONF_HEADER,
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_LABELS,
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_STARTUP_DELAY,
    DEFAULT_OPTIONS,
    DOMAIN_DATA,
)
from .logger import _LOGGER, INDENT


def get_val(
    options: MappingProxyType[str, Any], key: str, section: str | None = None
) -> Any:
    """Return value of a key."""
    val = None
    if section:
        try:
            val = options[section][key]
        except KeyError:
            _LOGGER.error(
                "Key %s is missing in secion %s, return default value", key, section
            )
            val = DEFAULT_OPTIONS[section][key]
    else:
        val = options.get(key, DEFAULT_OPTIONS[key])
    return val


def to_lists(options, key, section=None):
    """Transform configuration value to the list of strings."""
    val = get_val(options, key, section)
    if isinstance(val, list):
        return val
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]


def to_listi(options, key, section=None):
    """Transform configuration value to the list of integers."""
    val = get_val(options, key, section)
    return [int(x) for x in val.split(",") if x.strip()]


def get_entry(hass: HomeAssistant) -> Any:
    """Return Watchman's ConfigEntry instance."""
    return hass.config_entries.async_get_entry(
        hass.data[DOMAIN_DATA]["config_entry_id"]
    )


def get_config(hass: HomeAssistant, key: str, default: Any | None = None) -> Any:
    """Get configuration value from ConfigEntry."""
    assert hass.data.get(DOMAIN_DATA)
    entry = hass.config_entries.async_get_entry(
        hass.data[DOMAIN_DATA]["config_entry_id"]
    )

    assert isinstance(entry, ConfigEntry)

    if key in [
        CONF_INCLUDED_FOLDERS,
        CONF_IGNORED_ITEMS,
        CONF_IGNORED_FILES,
        CONF_IGNORED_LABELS,
    ]:
        return to_lists(entry.data, key)

    if key in [
        CONF_IGNORED_STATES,
        CONF_EXCLUDE_DISABLED_AUTOMATION,
        CONF_STARTUP_DELAY,
    ]:
        return get_val(entry.data, key)

    if key in [CONF_HEADER, CONF_REPORT_PATH, CONF_COLUMNS_WIDTH, CONF_FRIENDLY_NAMES]:
        section_name = CONF_SECTION_APPEARANCE_LOCATION
        if key == CONF_COLUMNS_WIDTH:
            return to_listi(entry.data, CONF_COLUMNS_WIDTH, section_name)
        else:
            return get_val(entry.data, key, section_name)

    assert False, "Unknown key {}".format(key)


async def async_is_valid_path(path) -> bool:
    """Validate the report path."""
    folder, f_name = os.path.split(path)
    if is_valid := (
        folder.strip() and f_name.strip() and await anyio.Path(folder).exists()
    ):
        is_valid = not await anyio.Path(path).is_dir()
    return is_valid


async def async_get_next_file(folder_tuples, ignored_files):
    """Return next file from scan queue."""
    if not ignored_files:
        ignored_files = ""
    else:
        ignored_files = "|".join([f"({fnmatch.translate(f)})" for f in ignored_files])
    ignored_files_re = re.compile(ignored_files)
    for folder_name, glob_pattern in folder_tuples:
        _LOGGER.debug(
            f"{INDENT}Scan folder {folder_name} with pattern {glob_pattern} for configuration files"
        )
        async for filename in anyio.Path(folder_name).glob(glob_pattern):
            yield (
                str(filename),
                (ignored_files and ignored_files_re.match(str(filename))),
            )


def get_included_folders(hass):
    """Gather the list of folders to parse."""
    folders = []

    included = get_config(hass, CONF_INCLUDED_FOLDERS, None)
    if not included:
        # Default to config dir if nothing specified
        folders.append((hass.config.config_dir, "**"))
    else:
        for fld in included:
            folders.append((fld, "**"))

    return folders


def is_action(hass, entry):
    """Check whether config entry is an action."""
    if not isinstance(entry, str):
        return False
    domain, service = entry.split(".")[0], ".".join(entry.split(".")[1:])
    return hass.services.has_service(domain, service)


def get_entity_state(hass, entry, friendly_names=False):
    """Return entity state or 'missing' if entity does not extst."""
    entity_state = hass.states.get(entry)
    entity_registry = er.async_get(hass)
    name = None
    if entity_state and entity_state.attributes.get("friendly_name", None):
        if friendly_names:
            name = entity_state.name

    if not entity_state:
        state = "missing"
        if regentry := entity_registry.async_get(entry):
            if regentry.disabled_by:
                state = "disabled"
    else:
        state = str(entity_state.state).replace("unavailable", "unavail")
        if split_entity_id(entry)[0] == "input_button" and state == "unknown":
            state = "available"

    return state, name
