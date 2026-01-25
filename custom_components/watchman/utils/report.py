"Reporting function of Watchman."

from datetime import datetime
from typing import Any
import pytz
from textwrap import wrap
import time
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from prettytable import PrettyTable
from .utils import get_config, get_entity_state, get_entry, is_action
from .logger import _LOGGER
from ..const import (
    CONF_ACTION_NAME,
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    DEFAULT_HEADER,
    CONF_HEADER,
    REPORT_ENTRY_TYPE_ENTITY,
    REPORT_ENTRY_TYPE_SERVICE,
)


async def parsing_stats(hass, start_time):
    """Separate func for test mocking."""

    def get_timezone(hass):
        return pytz.timezone(hass.config.time_zone)

    timezone = await hass.async_add_executor_job(get_timezone, hass)
    coordinator = get_entry(hass).runtime_data.coordinator
    parse_duration = await coordinator.async_get_last_parse_duration()
    return (
        datetime.now(timezone).strftime("%d %b %Y %H:%M:%S"),
        parse_duration,
        coordinator.last_check_duration,
        time.time() - start_time,
    )


async def report(
    hass,
    render=None,
    chunk_size=None,
    parse_config=None,
):
    """Generate a report of missing entities and services."""
    from ..coordinator import renew_missing_items_list

    from ..const import CONF_EXCLUDE_DISABLED_AUTOMATION

    start_time = time.time()
    entry = get_entry(hass)
    coordinator = entry.runtime_data.coordinator

    if parse_config:
        await coordinator.async_parse_config(reason="watchman.report service call")

    service_list = await coordinator.async_get_parsed_services()

    exclude_disabled_automations = get_config(
        hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
    )

    missing_services = renew_missing_items_list(
        hass, service_list, exclude_disabled_automations, coordinator.ignored_labels, "action"
    )
    entity_list = await coordinator.async_get_parsed_entities()

    missing_entities = renew_missing_items_list(
        hass, entity_list, exclude_disabled_automations, coordinator.ignored_labels, "entity"
    )

    header = get_config(hass, CONF_HEADER, DEFAULT_HEADER)
    info = await coordinator.hub.async_get_last_parse_info()
    files_parsed = info.get("processed_files_count", 0)
    files_ignored = info.get("ignored_files_count", 0)

    rep = f"{header} \n"
    if missing_services:
        rep += f"\n-== Missing {len(missing_services)} action(s) from "
        rep += f"{len(service_list)} found in your config:\n"
        if render:
            rep += render(hass, REPORT_ENTRY_TYPE_SERVICE, missing_services, service_list)
        rep += "\n"
    elif len(service_list) > 0:
        rep += f"\n-== Congratulations, all {len(service_list)} actions from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No actions found in configuration files!\n"

    if missing_entities:
        rep += f"\n-== Missing {len(missing_entities)} entity(ies) from "
        rep += f"{len(entity_list)} found in your config:\n"
        if render:
            rep += render(hass, REPORT_ENTRY_TYPE_ENTITY, missing_entities, entity_list)
        rep += "\n"

    elif len(entity_list) > 0:
        rep += f"\n-== Congratulations, all {len(entity_list)} entities from "
        rep += "your config are available!\n"
    else:
        rep += "\n-== No entities found in configuration files!\n"

    (
        report_datetime,
        parse_duration,
        check_duration,
        render_duration,
    ) = await parsing_stats(hass, start_time)

    rep += f"\n-== Report created on {report_datetime}\n"
    rep += (
        f"-== Parsed {files_parsed} files in {parse_duration:.2f}s., "
        f"ignored {files_ignored} files \n"
    )
    rep += f"-== Generated in: {render_duration:.2f}s. Validated in: {check_duration:.2f}s."
    report_chunks = []
    chunk = ""
    chunk_size = chunk_size or 0
    for line in iter(rep.splitlines()):
        chunk += f"{line}\n"
        if chunk_size > 0 and len(chunk) > chunk_size:
            report_chunks.append(chunk)
            chunk = ""
    if chunk:
        report_chunks.append(chunk)
    return report_chunks


def table_renderer(hass, entry_type, missing_items, parsed_list):
    """Render ASCII tables in the report."""
    table = PrettyTable()
    columns_width = get_config(hass, CONF_COLUMNS_WIDTH, None)
    columns_width = get_columns_width(columns_width)
    if entry_type == REPORT_ENTRY_TYPE_SERVICE:
        table.field_names = ["Action ID", "State", "Location"]
        for service in missing_items:
            row = [
                fill(service, columns_width[0]),
                fill("missing", columns_width[1]),
                fill(parsed_list[service]["locations"], columns_width[2]),
            ]
            table.add_row(row)
        table.align = "l"
        return table.get_string()
    elif entry_type == REPORT_ENTRY_TYPE_ENTITY:
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        header = ["Entity ID", "State", "Location"]
        table.field_names = header
        for entity in missing_items:
            state, name = get_entity_state(hass, entity, friendly_names)
            table.add_row(
                [
                    fill(entity, columns_width[0], name),
                    fill(state, columns_width[1]),
                    fill(parsed_list[entity]["locations"], columns_width[2]),
                ]
            )

        table.align = "l"
        return table.get_string()

    else:
        return f"Table render error: unknown entry type: {entry_type}"


def text_renderer(hass, entry_type, missing_items, parsed_list):
    """Render plain lists in the report."""
    result = ""
    if entry_type == REPORT_ENTRY_TYPE_SERVICE:
        for service in missing_items:
            result += f"{service} in {fill(parsed_list[service]['locations'], 0)}\n"
        return result
    elif entry_type == REPORT_ENTRY_TYPE_ENTITY:
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        for entity in missing_items:
            state, name = get_entity_state(hass, entity, friendly_names)
            entity_col = entity if not name else f"{entity} ('{name}')"
            result += f"{entity_col} [{state}] in: {fill(parsed_list[entity]['locations'], 0)}\n"

        return result
    else:
        return f"Text render error: unknown entry type: {entry_type}"


def fill(data, width, extra=None):
    """Arrange data by table column width."""
    if data and isinstance(data, dict):
        key, val = next(iter(data.items()))
        out = f"{key}:{','.join([str(v) for v in val])}"
    else:
        out = str(data) if not extra else f"{data} ('{extra}')"

    return (
        "\n".join([out.ljust(width) for out in wrap(out, width)]) if width > 0 else out
    )


def get_columns_width(user_width):
    """Define width of the report columns."""
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


async def async_report_to_file(hass, path):
    """Save report to a file."""
    report_chunks = await report(hass, table_renderer, chunk_size=0)

    def write(path):
        with open(path, "w", encoding="utf-8") as report_file:
            for chunk in report_chunks:
                report_file.write(chunk)

    await hass.async_add_executor_job(write, path)
    _LOGGER.debug(f"::async_report_to_file:: Repost saved to {path}")


async def async_report_to_notification(
    hass: HomeAssistant, action_str: str, service_data: dict[str, Any], chunk_size: int
):
    """Send report via notification action."""

    if not action_str:
        raise HomeAssistantError(f"Missing `{CONF_ACTION_NAME}` parameter.")

    if action_str and not isinstance(action_str, str):
        raise HomeAssistantError(
            f"`action` parameter should be a string, got {action_str}"
        )

    if not is_action(hass, action_str):
        raise HomeAssistantError(f"{action_str} is not a valid action for notification")

    domain = action_str.split(".")[0]
    action = ".".join(action_str.split(".")[1:])

    data = {} if service_data is None else service_data

    _LOGGER.debug(f"SERVICE_DATA {data}")

    report_chunks = await report(hass, text_renderer, chunk_size)
    for msg_chunk in report_chunks:
        data["message"] = msg_chunk
        # blocking=True ensures send order
        await hass.services.async_call(domain, action, data, blocking=True)
