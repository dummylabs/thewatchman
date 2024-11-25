"""Miscellaneous support functions for watchman"""

import anyio
import re
import fnmatch

import os
from typing import Any
from types import MappingProxyType

from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant
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
    DEFAULT_REPORT_FILENAME,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    DEFAULT_OPTIONS,
)


def get_val(
    options: MappingProxyType[str, Any], key: str, section: str | None = None
) -> Any:
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
    val = get_val(options, key, section)
    return [x.strip() for x in val.split(",") if x.strip()]


def to_listi(options, key, section=None):
    val = get_val(options, key, section)
    return [int(x) for x in val.split(",") if x.strip()]


def get_entry(hass: HomeAssistant) -> Any:
    return hass.config_entries.async_get_entry(
        hass.data[DOMAIN_DATA]["config_entry_id"]
    )


def get_config(hass: HomeAssistant, key: str, default: Any | None = None) -> Any:
    """get configuration value from ConfigEntry"""
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


async def async_get_report_path(hass, path):
    """if path not specified, create report in config directory with default filename"""
    out_path = path
    if not path:
        out_path = hass.config.path(DEFAULT_REPORT_FILENAME)
    folder, _ = os.path.split(out_path)
    if not await anyio.Path(folder).exists():
        raise HomeAssistantError(f"Incorrect report_path: {out_path}.")
    _LOGGER.debug(
        "::async_get_report_path:: input path [%s], output path [%s]", path, out_path
    )
    return out_path


async def async_get_next_file(folder_tuples, ignored_files):
    """Returns next file for scan"""
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
    """check whether config entry is an action"""
    if not isinstance(entry, str):
        return False
    domain, service = entry.split(".")[0], ".".join(entry.split(".")[1:])
    return hass.services.has_service(domain, service)


def get_entity_state(hass, entry, friendly_names=False):
    """returns entity state or missing if entity does not extst"""
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

    return state, name


def check_services(hass):
    """check if entries from config file are services"""
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


def check_entitites(hass):
    """check if entries from config file are entities with an active state"""
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
