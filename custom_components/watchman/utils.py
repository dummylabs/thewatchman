"""Miscellaneous support functions for watchman"""
import glob
import re
import fnmatch
import time
import logging
from datetime import datetime
from textwrap import wrap
import os
import pytz
from prettytable import PrettyTable
from homeassistant.exceptions import HomeAssistantError
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    DOMAIN_DATA,
    DEFAULT_HEADER,
    DEFAULT_CHUNK_SIZE,
    CONF_HEADER,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_CHUNK_SIZE,
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    BUNDLED_IGNORED_ITEMS,
)

_LOGGER = logging.getLogger(__name__)

def get_config(hass: HomeAssistant, key, default):
    """get configuration value"""
    if DOMAIN_DATA not in hass.data:
        return default
    return hass.data[DOMAIN_DATA].get(key, default)

def get_columns_width(user_width):
    """define width of the report columns"""
    default_width = [30, 7, 60]
    if not user_width:
        return default_width
    try:
        return [7 if user_width[i] < 7 else user_width[i] for i in range(3)]
    except (TypeError, IndexError):
        _LOGGER.error(
            "Invalid configuration for table column widths, default values"
            " used %s", default_width
        )
    return default_width


def table_renderer(hass, entry_type):
    """Render ASCII tables in the report"""
    table = PrettyTable()
    cw = get_config(hass, CONF_COLUMNS_WIDTH, None)
    cw = get_columns_width(cw)
    if entry_type == "service_list":
        services_missing = hass.data[DOMAIN]["services_missing"]
        service_list = hass.data[DOMAIN]["service_list"]
        table.field_names = ["Service ID", "State", "Location"]
        for service in services_missing:
            row = [
                fill(service, cw[0]),
                fill("missing", cw[1]),
                fill(service_list[service], cw[2]),
            ]
            table.add_row(row)
        table.align = "l"
        return table.get_string()
    elif entry_type == "entity_list":
        entities_missing = hass.data[DOMAIN]["entities_missing"]
        entity_list = hass.data[DOMAIN]["entity_list"]
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        header = ["Entity ID", "State", "Location"]
        table.field_names = header
        for entity in entities_missing:
            state, name = get_entity_state(hass, entity, friendly_names)
            table.add_row(
                [
                    fill(entity, cw[0], name),
                    fill(state, cw[1]),
                    fill(entity_list[entity], cw[2]),
                ]
            )

        table.align = "l"
        return table.get_string()

    else:
        return f"Table render error: unknown entry type: {entry_type}"


def text_renderer(hass, entry_type):
    """Render plain lists in the report"""
    result = ""
    if entry_type == "service_list":
        services_missing = hass.data[DOMAIN]["services_missing"]
        service_list = hass.data[DOMAIN]["service_list"]
        for service in services_missing:
            result += f"{service} in {fill(service_list[service], 0)}\n"
        return result
    elif entry_type == "entity_list":
        entities_missing = hass.data[DOMAIN]["entities_missing"]
        entity_list = hass.data[DOMAIN]["entity_list"]
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        for entity in entities_missing:
            state, name = get_entity_state(hass, entity, friendly_names)
            entity_col = entity if not name else f"{entity} ('{name}')"
            result += f"{entity_col} [{state}] in: {fill(entity_list[entity], 0)}\n"

        return result
    else:
        return f"Text render error: unknown entry type: {entry_type}"


def get_next_file(folder_list, ignored_files, logger):
    """Returns next file for scan"""
    if not ignored_files:
        ignored_files = ""
    else:
        ignored_files = "|".join([f"({fnmatch.translate(f)})" for f in ignored_files])
    ignored_files_re = re.compile(ignored_files)
    for folder in folder_list:
        for filename in glob.iglob(folder, recursive=True):
            yield (filename, (ignored_files and ignored_files_re.match(filename)))


def add_entry(_list, entry, yaml_file, lineno):
    """Add entry to list of missing entities/services with line number information"""
    if entry in _list:
        if yaml_file in _list[entry]:
            _list[entry].get(yaml_file, []).append(lineno)
    else:
        _list[entry] = {yaml_file: [lineno]}


def is_service(hass, entry):
    """check whether config entry is a service"""
    domain, service = entry.split(".")[0], ".".join(entry.split(".")[1:])
    return hass.services.has_service(domain, service)


def get_entity_state(hass, entry, friendly_names=False):
    """returns entity state or missing if entity does not extst"""
    entity = hass.states.get(entry)
    name = None
    if entity and entity.attributes.get("friendly_name", None):
        if friendly_names:
            name = entity.name
    state = "missing" if not entity else entity.state.replace("unavailable", "unavail")
    return state, name


def check_services(hass):
    """check if entries from config file are services"""
    excluded_services = []
    services_missing = {}

    if "missing" in get_config(hass, CONF_IGNORED_STATES, []):
        return services_missing

    ignored_items = get_config(hass, CONF_IGNORED_ITEMS, [])
    ignored_items = list(set(ignored_items + BUNDLED_IGNORED_ITEMS))

    if DOMAIN not in hass.data or "service_list" not in hass.data[DOMAIN]:
        raise HomeAssistantError("Service list not found")

    service_list = hass.data[DOMAIN]["service_list"]
    _LOGGER.debug("::check_services")

    for itm in ignored_items:
        if itm:
            excluded_services.extend(fnmatch.filter(service_list, itm))

    for entry, occurences in service_list.items():
        if not is_service(hass, entry):
            if entry in excluded_services:
                _LOGGER.debug("service %s ignored due to ignored_items", entry)
                continue
            else:
                services_missing[entry] = occurences
                _LOGGER.debug("service %s added to missing list", entry)

    return services_missing


def check_entitites(hass):
    """check if entries from config file are entities with an active state"""
    ignored_states = [
        "unavail" if s == "unavailable" else s
        for s in get_config(hass, CONF_IGNORED_STATES, [])
    ]
    ignored_items = get_config(hass, CONF_IGNORED_ITEMS, [])
    ignored_items = list(set(ignored_items + BUNDLED_IGNORED_ITEMS))
    if DOMAIN not in hass.data or "entity_list" not in hass.data[DOMAIN]:
        _LOGGER.error("Entity list not found")
        raise Exception("Entity list not found")
    entity_list = hass.data[DOMAIN]["entity_list"]
    excluded_entities = []
    entities_missing = {}
    for itm in ignored_items:
        if itm:
            excluded_entities.extend(fnmatch.filter(entity_list, itm))
    _LOGGER.debug("::check_entities")
    for entry, occurences in entity_list.items():
        if is_service(hass, entry):  # this is a service, not entity
            _LOGGER.debug("entry %s is service, skipping", entry)
            continue
        state, _ = get_entity_state(hass, entry)
        if state in ignored_states:
            _LOGGER.debug("entry %s ignored due to ignored_states", entry)
            continue
        if state in ["missing", "unknown", "unavail"]:
            if entry in excluded_entities:
                _LOGGER.debug("entry %s ignored due to ignored_items", entry)
                continue
            else:
                entities_missing[entry] = occurences
                _LOGGER.debug("entry %s added to missing list", entry)
    return entities_missing


def parse(folders, ignored_files, root=None, logger=None):
    """Parse a yaml or json file for entities/services"""
    if logger:
        logger.log(f"::parse:: ignored_files={ignored_files}")
    files_parsed = 0
    entity_pattern = re.compile(
        r"(?:(?<=\s)|(?<=^)|(?<=\")|(?<=\'))([A-Za-z_0-9]*\s*:)?(?:\s*)?"
        r"((air_quality|alarm_control_panel|alert|automation|binary_sensor|button|calendar|camera|"
        r"climate|counter|device_tracker|fan|group|humidifier|input_boolean|input_datetime|"
        r"input_number|input_select|light|lock|media_player|number|person|plant|proximity|remote|"
        r"scene|script|select|sensor|sun|switch|timer|vacuum|weather|zone)\.[A-Za-z_*0-9]+)"
    )
    service_pattern = re.compile(r"service:\s*([A-Za-z_0-9]*\.[A-Za-z_0-9]+)")
    comment_pattern = re.compile(r"#.*")
    entity_list = {}
    service_list = {}
    effectively_ignored = []
    _LOGGER.debug("::parse")
    for yaml_file, ignored in get_next_file(folders, ignored_files, logger):
        short_path = os.path.relpath(yaml_file, root)
        if ignored:
            effectively_ignored.append(short_path)
            _LOGGER.debug("%s ignored", yaml_file)
            continue
        files_parsed += 1
        _LOGGER.debug("%s parsed", yaml_file)
        for i, line in enumerate(open(yaml_file, encoding="utf-8")):
            line = re.sub(comment_pattern, "", line)
            for match in re.finditer(entity_pattern, line):
                typ, val = match.group(1), match.group(2)
                if typ != "service:" and "*" not in val and not val.endswith(".yaml"):
                    add_entry(entity_list, val, short_path, i + 1)
            for match in re.finditer(service_pattern, line):
                val = match.group(1)
                add_entry(service_list, val, short_path, i + 1)

    _LOGGER.debug("Parsed files: %s", files_parsed)
    _LOGGER.debug("Ignored files: %s", effectively_ignored)
    return (entity_list, service_list, files_parsed, len(effectively_ignored))


def fill(t, width, extra=None):
    """arrange data by table column width"""
    if t and isinstance(t, dict):
        key, val = next(iter(t.items()))
        s = f"{key}:{','.join([str(v) for v in val])}"
    else:
        s = str(t) if not extra else f"{t} ('{extra}')"

    return "\n".join([s.ljust(width) for s in wrap(s, width)]) if width > 0 else s


def report(hass, render, chunk_size):
    """generates watchman report either as a table or as a list"""
    if not DOMAIN in hass.data:
        raise HomeAssistantError("No data for report, refresh required.")

    start_time = time.time()
    header = get_config(hass, CONF_HEADER, DEFAULT_HEADER)
    services_missing = hass.data[DOMAIN]["services_missing"]
    service_list = hass.data[DOMAIN]["service_list"]
    entities_missing = hass.data[DOMAIN]["entities_missing"]
    entity_list = hass.data[DOMAIN]["entity_list"]
    files_parsed = hass.data[DOMAIN]["files_parsed"]
    files_ignored = hass.data[DOMAIN]["files_ignored"]
    parse_duration = hass.data[DOMAIN]["parse_duration"]
    check_duration = hass.data[DOMAIN]["check_duration"]
    chunk_size = get_config(hass, CONF_CHUNK_SIZE, DEFAULT_CHUNK_SIZE) \
        if chunk_size is None else chunk_size

    rep = f"{header} \n"
    if services_missing:
        rep += f"\n-== Missing {len(services_missing)} service(s) from "
        rep += f"{len(service_list)} found in your config:\n"
        rep += render(hass, "service_list")
        rep += "\n"
    elif len(service_list) > 0:
        rep += f"\n-== Congratulations, all {len(service_list)} services from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No services found in configuration files!\n"

    if entities_missing:
        rep += f"\n-== Missing {len(entities_missing)} entity(ies) from "
        rep += f"{len(entity_list)} found in your config:\n"
        rep += render(hass, "entity_list")
        rep += "\n"

    elif len(entity_list) > 0:
        rep += f"\n-== Congratulations, all {len(entity_list)} entities from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No entities found in configuration files!\n"
    tz = pytz.timezone(hass.config.time_zone)
    rep += f"\n-== Report created on {datetime.now(tz).strftime('%d %b %Y %H:%M:%S')}\n"
    rep += f"-== Parsed {files_parsed} files in {parse_duration:.2f}s., ignored {files_ignored} files \n"
    rep += f"-== Generated in: {(time.time()-start_time):.2f}s. Validated in: {check_duration:.2f}s."
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
