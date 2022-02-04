"""Miscellaneous support functions for watchman"""
import glob
import re
import fnmatch
import time
import logging
from datetime import datetime
import pytz
from prettytable import PrettyTable
from textwrap import wrap
import os

from .const import (
    DOMAIN,
    DEFAULT_REPORT_FILENAME,
    DEFAULT_HEADER,
    CONF_IGNORED_FILES,
    CONF_HEADER,
    CONF_REPORT_PATH,
    CONF_IGNORED_ITEMS,
    CONF_SERVICE_NAME,
    CONF_SERVICE_DATA,
    CONF_INCLUDED_FOLDERS,
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_STATES,
    CONF_CHUNK_SIZE,
    CONF_CREATE_FILE,
    CONF_SEND_NITIFICATION,
    CONF_COLUMNS_WIDTH,
)

_LOGGER = logging.getLogger(__name__)


def get_columns_width(config):
    default_width = [30, 7, 60]
    if CONF_COLUMNS_WIDTH in config[DOMAIN]:
        config_width = config[DOMAIN].get(CONF_COLUMNS_WIDTH)
        try:
            return [7 if config_width[i] < 7 else config_width[i] for i in range(3)]
        except Exception:
            _LOGGER.error(
                f"Invalid configuration for table column widths, default values used {default_width}"
            )
            return default_width
    else:
        return default_width


def table_renderer(hass, config, entry_type):
    """Render ASCII tables in the report"""
    table = PrettyTable()
    cw = get_columns_width(config)
    if entry_type == "service_list":
        services_missing = hass.data[DOMAIN]["services_missing"]
        service_list = hass.data[DOMAIN]["service_list"]
        table.field_names = ["Service", "State", "Location"]
        for service in services_missing:
            table.add_row(
                [
                    fill(service, cw[0]),
                    fill("missing", cw[1]),
                    fill(service_list[service], cw[2]),
                ]
            )
        table.align = "l"
        return table.get_string()
    elif entry_type == "entity_list":
        entities_missing = hass.data[DOMAIN]["entities_missing"]
        entity_list = hass.data[DOMAIN]["entity_list"]
        table.field_names = ["Entity", "State", "Location"]
        for entity in entities_missing:
            state = get_entity_state(hass, entity)
            table.add_row(
                [
                    fill(entity, cw[0]),
                    fill(state, cw[1]),
                    fill(entity_list[entity], cw[2]),
                ]
            )
        table.align = "l"
        return table.get_string()

    else:
        return f"Table render error: unknown entry type: {entry_type}"


def text_renderer(hass, config, entry_type):
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
        for entity in entities_missing:
            state = get_entity_state(hass, entity)
            result += f"{entity}[{state}] in: {fill(entity_list[entity], 0)}\n"

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


def get_entity_state(hass, entry):
    """returns entity state or missing if entity does not extst"""
    entity = hass.states.get(entry)
    return "missing" if not entity else entity.state.replace("unavailable", "unavail")


def check_services(hass, config):
    """check if entries from config file are services"""
    ignored_items = config[DOMAIN].get(CONF_IGNORED_ITEMS, [])
    if DOMAIN not in hass.data or "service_list" not in hass.data[DOMAIN]:
        _LOGGER.error("Service list not found")
        raise Exception("Service list not found")
    service_list = hass.data[DOMAIN]["service_list"]
    excluded_services = []
    services_missing = {}
    for itm in ignored_items:
        if itm:
            excluded_services.extend(fnmatch.filter(service_list, itm))
    for entry, occurences in service_list.items():
        if not is_service(hass, entry):
            if entry in excluded_services:
                # self.debug(f"Ignored service: {service}")
                continue
            else:
                services_missing[entry] = occurences
    return services_missing


def check_entitites(hass, config):
    """check if entries from config file are entities with an active state"""
    ignored_states = config[DOMAIN].get(CONF_IGNORED_STATES, [])
    ignored_items = config[DOMAIN].get(CONF_IGNORED_ITEMS, [])
    if DOMAIN not in hass.data or "entity_list" not in hass.data[DOMAIN]:
        _LOGGER.error("Entity list not found")
        raise Exception("Entity list not found")
    entity_list = hass.data[DOMAIN]["entity_list"]
    excluded_entities = []
    entities_missing = {}
    # ignored_states = ignored_states or []
    for itm in ignored_items:
        if itm:
            excluded_entities.extend(fnmatch.filter(entity_list, itm))

    for entry, occurences in entity_list.items():
        if is_service(hass, entry):  # this is a service, not entity
            continue
        state = get_entity_state(hass, entry)
        if state in ignored_states:
            continue
        if state in ["missing", "unknown", "unavail"]:
            if entry in excluded_entities:
                # self.debug(f"Ignored entity: {entity}")
                continue
            else:
                entities_missing[entry] = occurences
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
    for yaml_file, ignored in get_next_file(folders, ignored_files, logger):
        # s = len(root) if root and yaml_file.startswith(root) else 0
        # short_path = yaml_file[s:]
        short_path = os.path.relpath(yaml_file, root)
        if ignored:
            effectively_ignored.append(short_path)
            continue
        files_parsed += 1
        for i, line in enumerate(open(yaml_file, encoding="utf-8")):
            line = re.sub(comment_pattern, "", line)
            for match in re.finditer(entity_pattern, line):
                typ, val = match.group(1), match.group(2)
                if typ != "service:" and "*" not in val and not val.endswith(".yaml"):
                    add_entry(entity_list, val, short_path, i + 1)
            for match in re.finditer(service_pattern, line):
                val = match.group(1)
                add_entry(service_list, val, short_path, i + 1)
    if logger:
        logger.log(f"::parse:: Parsed files: {files_parsed} ")
        logger.log(f"::parse:: Ignored files: {effectively_ignored}")
    return (entity_list, service_list, files_parsed, len(effectively_ignored))


def fill(t, width):
    if t and isinstance(t, dict):
        key, val = next(iter(t.items()))
        s = f"{key}:{','.join([str(v) for v in val])}"
    else:
        s = str(t)

    return "\n".join([s.ljust(width) for s in wrap(s, width)]) if width > 0 else s


def report(hass, config, render, chunk_size):
    """generates watchman report either as a table or as a list"""
    if not DOMAIN in hass.data:
        _LOGGER.error(f"No data for report, refresh required.")
        return None

    start_time = time.time()
    header = config[DOMAIN].get(CONF_HEADER)
    services_missing = hass.data[DOMAIN]["services_missing"]
    service_list = hass.data[DOMAIN]["service_list"]
    entities_missing = hass.data[DOMAIN]["entities_missing"]
    entity_list = hass.data[DOMAIN]["entity_list"]
    files_parsed = hass.data[DOMAIN]["files_parsed"]
    files_ignored = hass.data[DOMAIN]["files_ignored"]
    parse_duration = hass.data[DOMAIN]["parse_duration"]
    check_duration = hass.data[DOMAIN]["check_duration"]
    chunk_size = (
        config[DOMAIN].get(CONF_CHUNK_SIZE) if chunk_size is None else chunk_size
    )

    rep = f"{header} \n"
    if services_missing:
        rep += f"\n-== Missing {len(services_missing)} service(-s) from "
        rep += f"{len(service_list)} found in your config:\n"
        rep += render(hass, config, "service_list")
        rep += "\n"
    elif len(service_list) > 0:
        rep += f"\n-== Congratulations, all {len(service_list)} services from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No services found in configuration files!\n"

    if entities_missing:
        rep += f"\n-== Missing {len(entities_missing)} entity(-es) from "
        rep += f"{len(entity_list)} found in your config:\n"
        rep += render(hass, config, "entity_list")
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
