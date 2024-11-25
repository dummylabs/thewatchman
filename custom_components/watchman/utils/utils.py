"""Miscellaneous support functions for watchman"""

import anyio
import re
import fnmatch
import time
from datetime import datetime
from textwrap import wrap
import os
from typing import Any
from types import MappingProxyType
import pytz
from prettytable import PrettyTable
from homeassistant.exceptions import HomeAssistantError
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry


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
    DEFAULT_HEADER,
    CONF_HEADER,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    BUNDLED_IGNORED_ITEMS,
    DEFAULT_REPORT_FILENAME,
    HASS_DATA_CHECK_DURATION,
    HASS_DATA_FILES_IGNORED,
    HASS_DATA_FILES_PARSED,
    HASS_DATA_MISSING_ENTITIES,
    HASS_DATA_MISSING_SERVICES,
    HASS_DATA_PARSE_DURATION,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    REPORT_ENTRY_TYPE_ENTITY,
    REPORT_ENTRY_TYPE_SERVICE,
    DEFAULT_OPTIONS,
    DEFAULT_HA_DOMAINS,
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


def get_config(hass: HomeAssistant, key: str, default: Any | None = None) -> Any:
    """get configuration value"""
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


def get_columns_width(user_width):
    """define width of the report columns"""
    default_width = [30, 7, 60]
    if not user_width:
        return default_width
    try:
        return [7 if user_width[i] < 7 else user_width[i] for i in range(3)]
    except (TypeError, IndexError):
        _LOGGER.error(
            "Invalid configuration for table column widths, default values" " used %s",
            default_width,
        )
    return default_width


def table_renderer(hass, entry_type):
    """Render ASCII tables in the report"""
    table = PrettyTable()
    columns_width = get_config(hass, CONF_COLUMNS_WIDTH, None)
    columns_width = get_columns_width(columns_width)
    if entry_type == REPORT_ENTRY_TYPE_SERVICE:
        services_missing = hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]
        service_list = hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST]
        table.field_names = ["Action ID", "State", "Location"]
        for service in services_missing:
            row = [
                fill(service, columns_width[0]),
                fill("missing", columns_width[1]),
                fill(service_list[service], columns_width[2]),
            ]
            table.add_row(row)
        table.align = "l"
        return table.get_string()
    elif entry_type == REPORT_ENTRY_TYPE_ENTITY:
        entities_missing = hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]
        parsed_entity_list = hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST]
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        header = ["Entity ID", "State", "Location"]
        table.field_names = header
        for entity in entities_missing:
            state, name = get_entity_state(hass, entity, friendly_names)
            table.add_row(
                [
                    fill(entity, columns_width[0], name),
                    fill(state, columns_width[1]),
                    fill(parsed_entity_list[entity], columns_width[2]),
                ]
            )

        table.align = "l"
        return table.get_string()

    else:
        return f"Table render error: unknown entry type: {entry_type}"


def text_renderer(hass, entry_type):
    """Render plain lists in the report"""
    result = ""
    if entry_type == REPORT_ENTRY_TYPE_SERVICE:
        services_missing = hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]
        service_list = hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST]
        for service in services_missing:
            result += f"{service} in {fill(service_list[service], 0)}\n"
        return result
    elif entry_type == REPORT_ENTRY_TYPE_ENTITY:
        entities_missing = hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]
        entity_list = hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST]
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        for entity in entities_missing:
            state, name = get_entity_state(hass, entity, friendly_names)
            entity_col = entity if not name else f"{entity} ('{name}')"
            result += f"{entity_col} [{state}] in: {fill(entity_list[entity], 0)}\n"

        return result
    else:
        return f"Text render error: unknown entry type: {entry_type}"


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


def add_entry(_list, entry, yaml_file, lineno):
    """Add entry to list of missing entities/services with line number information"""
    if entry in _list:
        if yaml_file in _list[entry]:
            _list[entry].get(yaml_file, []).append(lineno)
    else:
        _list[entry] = {yaml_file: [lineno]}


def is_action(hass, entry):
    """check whether config entry is a service"""
    if not isinstance(entry, str):
        return False
    domain, service = entry.split(".")[0], ".".join(entry.split(".")[1:])
    return hass.services.has_service(domain, service)


def get_entity_state(hass, entry, friendly_names=False):
    """returns entity state or missing if entity does not extst"""
    entity = hass.states.get(entry)
    name = None
    if entity and entity.attributes.get("friendly_name", None):
        if friendly_names:
            name = entity.name
    # fix for #75, some integrations return non-string states
    state = (
        "missing" if not entity else str(entity.state).replace("unavailable", "unavail")
    )
    return state, name


def check_services(hass):
    """check if entries from config file are services"""
    services_missing = {}
    _LOGGER.debug(f"::check_services:: Triaging list of found actions")
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
    _LOGGER.debug(f"::check_entities:: Triaging list of found entities")

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
        if state in ["missing", "unknown", "unavail"]:
            entities_missing[entry] = occurrences
            _LOGGER.debug(f"{INDENT}entry {entry} added to the report")
    return entities_missing


async def parse(hass, folders, ignored_files, root=None):
    """Parse a yaml or json file for entities/services"""
    parsed_files_count = 0
    entity_pattern = re.compile(
        r"(?:(?<=\s)|(?<=^)|(?<=\")|(?<=\'))([A-Za-z_0-9]*\s*:)?(?:\s*)?(?:states.)?"
        rf"(({ "|".join([*Platform, *DEFAULT_HA_DOMAINS]) })\.[A-Za-z_*0-9]+)"
    )
    service_pattern = re.compile(
        r"(?:service|action):\s*([A-Za-z_0-9]*\.[A-Za-z_0-9]+)"
    )
    comment_pattern = re.compile(r"(^\s*(?:description|example):.*)|(\s*#.*)")
    parsed_entity_list = {}
    parsed_service_list = {}
    parsed_files = []
    effectively_ignored_files = []
    async for yaml_file, ignored in async_get_next_file(folders, ignored_files):
        short_path = os.path.relpath(yaml_file, root)
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


def fill(data, width, extra=None):
    """arrange data by table column width"""
    if data and isinstance(data, dict):
        key, val = next(iter(data.items()))
        out = f"{key}:{','.join([str(v) for v in val])}"
    else:
        out = str(data) if not extra else f"{data} ('{extra}')"

    return (
        "\n".join([out.ljust(width) for out in wrap(out, width)]) if width > 0 else out
    )


async def report(hass, render, chunk_size, test_mode=False):
    """generates watchman report either as a table or as a list"""
    if DOMAIN not in hass.data:
        raise HomeAssistantError("No data for report, refresh required.")

    start_time = time.time()
    header = get_config(hass, CONF_HEADER, DEFAULT_HEADER)
    services_missing = hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]
    service_list = hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST]
    entities_missing = hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]
    entity_list = hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST]
    files_parsed = hass.data[DOMAIN][HASS_DATA_FILES_PARSED]
    files_ignored = hass.data[DOMAIN][HASS_DATA_FILES_IGNORED]

    rep = f"{header} \n"
    if services_missing:
        rep += f"\n-== Missing {len(services_missing)} action(s) from "
        rep += f"{len(service_list)} found in your config:\n"
        rep += render(hass, REPORT_ENTRY_TYPE_SERVICE)
        rep += "\n"
    elif len(service_list) > 0:
        rep += f"\n-== Congratulations, all {len(service_list)} actions from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No actions found in configuration files!\n"

    if entities_missing:
        rep += f"\n-== Missing {len(entities_missing)} entity(ies) from "
        rep += f"{len(entity_list)} found in your config:\n"
        rep += render(hass, REPORT_ENTRY_TYPE_ENTITY)
        rep += "\n"

    elif len(entity_list) > 0:
        rep += f"\n-== Congratulations, all {len(entity_list)} entities from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No entities found in configuration files!\n"

    def get_timezone(hass):
        return pytz.timezone(hass.config.time_zone)

    timezone = await hass.async_add_executor_job(get_timezone, hass)

    if not test_mode:
        report_datetime = datetime.now(timezone).strftime("%d %b %Y %H:%M:%S")
        parse_duration = hass.data[DOMAIN][HASS_DATA_PARSE_DURATION]
        check_duration = hass.data[DOMAIN][HASS_DATA_CHECK_DURATION]
        render_duration = time.time() - start_time
    else:
        report_datetime = "01 Jan 1970 00:00:00"
        parse_duration = 0.01
        check_duration = 0.105
        render_duration = 0.0003

    rep += f"\n-== Report created on {report_datetime}\n"
    rep += (
        f"-== Parsed {files_parsed} files in {parse_duration:.2f}s., "
        f"ignored {files_ignored} files \n"
    )
    rep += f"-== Generated in: {render_duration:.2f}s. Validated in: {check_duration:.2f}s."
    report_chunks = []
    chunk = ""
    for line in iter(rep.splitlines()):
        chunk += f"{line}\n"
        if chunk_size > 0 and len(chunk) > chunk_size:
            report_chunks.append(chunk)
            chunk = ""
    if chunk:
        report_chunks.append(chunk)
    return report_chunks
