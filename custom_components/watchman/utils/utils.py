"""Miscellaneous support functions for Watchman."""

import anyio
import re
import fnmatch

import os
from typing import Any
from types import MappingProxyType

from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant, split_entity_id
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

from .logger import _LOGGER, INDENT
from ..const import (
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_FILES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_STARTUP_DELAY,
    DOMAIN,
    DOMAIN_DATA,
    CONF_HEADER,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    DEFAULT_OPTIONS,
)


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

    if key in [CONF_INCLUDED_FOLDERS, CONF_IGNORED_ITEMS, CONF_IGNORED_FILES]:
        return to_lists(entry.data, key)

    if key in [CONF_IGNORED_STATES, CONF_CHECK_LOVELACE, CONF_STARTUP_DELAY]:
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
    _LOGGER.debug(f"@@@[{folder}] [{f_name}] [{path}]")
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


def renew_missing_actions_list(hass):
    """Update list of missing actions when an action gets registered or removed."""
    services_missing = {}
    _LOGGER.debug("::check_services:: Triaging list of found actions")
    if "missing" in get_config(hass, CONF_IGNORED_STATES, []):
        _LOGGER.debug(
            f"{INDENT}MISSING state set as ignored in config, so final list of reported actions is empty."
        )
        return services_missing
    if (
        DOMAIN not in hass.data
        or HASS_DATA_PARSED_SERVICE_LIST not in hass.data[DOMAIN]
    ):
        raise HomeAssistantError("Service list not found")
    parsed_service_list = hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST]
    for entry, occurrences in parsed_service_list.items():
        if not is_action(hass, entry):
            services_missing[entry] = occurrences
            _LOGGER.debug(f"{INDENT}service {entry} added to the report")
    return services_missing


def renew_missing_entities_list(hass):
    """Update list of missing entities when a service from a config file changed its state."""
    _LOGGER.debug("::check_entities:: Triaging list of found entities")

    ignored_states = [
        "unavail" if s == "unavailable" else s
        for s in get_config(hass, CONF_IGNORED_STATES, [])
    ]
    if DOMAIN not in hass.data or HASS_DATA_PARSED_ENTITY_LIST not in hass.data[DOMAIN]:
        _LOGGER.error(f"{INDENT}Entity list not found")
        raise Exception("Entity list not found")
    parsed_entity_list = hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST]
    entities_missing = {}
    for entry, occurrences in parsed_entity_list.items():
        if is_action(hass, entry):  # this is a service, not entity
            _LOGGER.debug(f"{INDENT}entry {entry} is service, skipping")
            continue
        state, _ = get_entity_state(hass, entry)
        if state in ignored_states:
            _LOGGER.debug(
                f"{INDENT}entry {entry} with state {state} skipped due to ignored_states"
            )
            continue
        if state in ["missing", "unknown", "unavail", "disabled"]:
            entities_missing[entry] = occurrences
            _LOGGER.debug(f"{INDENT}entry {entry} added to the report")
    return entities_missing
