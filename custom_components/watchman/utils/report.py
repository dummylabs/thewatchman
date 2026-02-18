"""Reporting function of Watchman."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
import time
from typing import Any

from prettytable import PrettyTable
import pytz

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    CONF_ACTION_NAME,
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    CONF_HEADER,
    DEFAULT_HEADER,
    REPORT_ENTRY_TYPE_ENTITY,
    REPORT_ENTRY_TYPE_SERVICE,
)
from .logger import _LOGGER
from .utils import (
    format_column_text,
    format_occurrences,
    format_state,
    get_config,
    get_entity_state,
    is_action,
)


async def parsing_stats(hass: HomeAssistant, parse_duration: float, last_check_duration: float, start_time: float) -> tuple[str, float, float, float]:
    """Separate func for test mocking."""

    def get_timezone(hass: HomeAssistant) -> Any:
        return pytz.timezone(hass.config.time_zone)

    timezone = await hass.async_add_executor_job(get_timezone, hass)
    return (
        datetime.now(timezone).strftime("%d %b %Y %H:%M:%S"),
        parse_duration,
        last_check_duration,
        time.time() - start_time,
    )


async def report(
    hass: HomeAssistant,
    missing_entities: dict[str, Any],
    missing_services: dict[str, Any],
    parsed_entity_list: dict[str, Any],
    parsed_service_list: dict[str, Any],
    files_parsed: int,
    files_ignored: int,
    parse_duration: float,
    last_check_duration: float,
    *,
    render: Callable[[HomeAssistant, str, dict[str, Any], dict[str, Any]], str]
    | None = None,
    chunk_size: int | None = None,
) -> list[str]:
    """Generate a report of missing entities and services."""
    start_time = time.time()
    service_list = parsed_service_list
    entity_list = parsed_entity_list

    header = get_config(hass, CONF_HEADER, DEFAULT_HEADER)

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
    ) = await parsing_stats(hass, parse_duration, last_check_duration, start_time)

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


def table_renderer(
    hass: HomeAssistant,
    entry_type: str,
    missing_items: dict[str, Any],
    parsed_list: dict[str, Any],
) -> str:
    """Render ASCII tables in the report."""
    table = PrettyTable()
    columns_width = get_config(hass, CONF_COLUMNS_WIDTH, None)
    columns_width = get_columns_width(columns_width)
    if entry_type == REPORT_ENTRY_TYPE_SERVICE:
        table.field_names = ["Action ID", "State", "Location"]
        for service in missing_items:
            row = [
                format_column_text(service, columns_width[0]),
                format_column_text("missing", columns_width[1]),
                format_occurrences(parsed_list[service]["occurrences"], columns_width[2]),
            ]
            table.add_row(row)
        table.align = "l"
        return table.get_string()
    if entry_type == REPORT_ENTRY_TYPE_ENTITY:
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        header = ["Entity ID", "State", "Location"]
        table.field_names = header
        for entity in missing_items:
            state, name = get_entity_state(hass, entity, friendly_names=friendly_names)
            table.add_row(
                [
                    format_column_text(entity, columns_width[0], name),
                    format_column_text(format_state(state), columns_width[1]),
                    format_occurrences(parsed_list[entity]["occurrences"], columns_width[2]),
                ]
            )

        table.align = "l"
        return table.get_string()

    return f"Table render error: unknown entry type: {entry_type}"


def text_renderer(
    hass: HomeAssistant,
    entry_type: str,
    missing_items: dict[str, Any],
    parsed_list: dict[str, Any],
) -> str:
    """Render plain lists in the report."""
    result = ""
    if entry_type == REPORT_ENTRY_TYPE_SERVICE:
        for service in missing_items:
            loc = format_occurrences(parsed_list[service]["occurrences"], 0)
            result += f"{service} in {loc}\n"
        return result
    if entry_type == REPORT_ENTRY_TYPE_ENTITY:
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        for entity in missing_items:
            state, name = get_entity_state(hass, entity, friendly_names=friendly_names)
            entity_col = entity if not name else f"{entity} ('{name}')"
            loc = format_occurrences(parsed_list[entity]["occurrences"], 0)
            result += f"{entity_col} [{format_state(state)}] in: {loc}\n"

        return result
    return f"Text render error: unknown entry type: {entry_type}"


def get_columns_width(user_width: list[int] | None) -> list[int]:
    """Define width of the report columns."""
    default_width = [30, 7, 60]
    if not user_width:
        return default_width
    try:
        return [max(user_width[i], 7) for i in range(3)]
    except (TypeError, IndexError):
        _LOGGER.error(
            "Invalid configuration for table column widths, default values" " used %s",
            default_width,
        )
    return default_width


async def async_report_to_file(hass: HomeAssistant, path: str, report_data: dict[str, Any]) -> None:
    """Save report to a file."""
    report_chunks = await report(hass, **report_data, render=table_renderer, chunk_size=0)

    def write(path: str) -> None:
        with Path(path).open("w", encoding="utf-8") as report_file:
            report_file.writelines(report_chunks)

    await hass.async_add_executor_job(write, path)
    _LOGGER.debug(f"Report saved to {path}")


async def async_report_to_notification(
    hass: HomeAssistant,
    action_str: str,
    service_data: dict[str, Any],
    chunk_size: int,
    report_data: dict[str, Any],
) -> None:
    """Send report via notification action."""
    if not action_str:
        raise HomeAssistantError(f"Missing `{CONF_ACTION_NAME}` parameter.")

    if action_str and not isinstance(action_str, str):
        raise HomeAssistantError(
            f"`action` parameter should be a string, got {action_str}"
        )

    if not is_action(hass, action_str):
        raise HomeAssistantError(f"{action_str} is not a valid action for notification")

    domain = action_str.split(".", maxsplit=1)[0]
    action = ".".join(action_str.split(".")[1:])

    data = {} if service_data is None else service_data.copy()
    # only inject notification_id for persistent_notification service
    if domain == "persistent_notification" and "notification_id" not in data:
        data["notification_id"] = "watchman_report"

    _LOGGER.debug(f"SERVICE_DATA {data}")

    report_chunks = await report(hass, **report_data, render=text_renderer, chunk_size=chunk_size)
    for msg_chunk in report_chunks:
        data["message"] = msg_chunk
        # blocking=True ensures send order
        await hass.services.async_call(domain, action, data, blocking=True)
