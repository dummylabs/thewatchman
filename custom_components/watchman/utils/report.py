"""Reporting function of Watchman."""

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from textwrap import wrap
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
    COORD_DATA_IGNORED_FILES,
    COORD_DATA_PROCESSED_FILES,
    DEFAULT_HEADER,
    REPORT_ENTRY_TYPE_ENTITY,
    REPORT_ENTRY_TYPE_SERVICE,
)
from .logger import _LOGGER
from .utils import get_config, get_entity_state, get_entry, is_action


async def parsing_stats(hass: HomeAssistant, start_time: float) -> tuple[str, float, float, float]:
    """Separate func for test mocking."""

    def get_timezone(hass: HomeAssistant) -> Any:
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
    hass: HomeAssistant,
    *,
    render: Callable[[HomeAssistant, str, dict[str, Any], dict[str, Any]], str]
    | None = None,
    chunk_size: int | None = None,
    parse_config: bool | None = None,
) -> list[str]:
    """Generate a report of missing entities and services."""
    from ..const import CONF_EXCLUDE_DISABLED_AUTOMATION
    from ..coordinator import renew_missing_items_list

    start_time = time.time()
    entry = get_entry(hass)
    coordinator = entry.runtime_data.coordinator

    if parse_config:
        coordinator.request_parser_rescan(reason="service call")

    service_list = await coordinator.async_get_parsed_services()

    exclude_disabled_automations = get_config(
        hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
    )

    missing_services = renew_missing_items_list(
        hass,
        service_list,
        exclude_disabled_automations=exclude_disabled_automations,
        ignored_labels=coordinator.ignored_labels,
        item_type="action",
    )
    entity_list = await coordinator.async_get_parsed_entities()

    missing_entities = renew_missing_items_list(
        hass,
        entity_list,
        exclude_disabled_automations=exclude_disabled_automations,
        ignored_labels=coordinator.ignored_labels,
        item_type="entity",
    )

    header = get_config(hass, CONF_HEADER, DEFAULT_HEADER)
    files_parsed = coordinator.data.get(COORD_DATA_PROCESSED_FILES, 0)
    files_ignored = coordinator.data.get(COORD_DATA_IGNORED_FILES, 0)

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
                fill(service, columns_width[0]),
                fill("missing", columns_width[1]),
                fill(parsed_list[service]["locations"], columns_width[2]),
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
                    fill(entity, columns_width[0], name),
                    fill(state, columns_width[1]),
                    fill(parsed_list[entity]["locations"], columns_width[2]),
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
            result += f"{service} in {fill(parsed_list[service]['locations'], 0)}\n"
        return result
    if entry_type == REPORT_ENTRY_TYPE_ENTITY:
        friendly_names = get_config(hass, CONF_FRIENDLY_NAMES, False)
        for entity in missing_items:
            state, name = get_entity_state(hass, entity, friendly_names=friendly_names)
            entity_col = entity if not name else f"{entity} ('{name}')"
            result += f"{entity_col} [{state}] in: {fill(parsed_list[entity]['locations'], 0)}\n"

        return result
    return f"Text render error: unknown entry type: {entry_type}"


def fill(data: Any, width: int, extra: str | None = None) -> str:
    """Arrange data by table column width."""
    if data and isinstance(data, dict):
        key, val = next(iter(data.items()))
        out = f"{key}:{','.join([str(v) for v in val])}"
    else:
        out = str(data) if not extra else f"{data} ('{extra}')"

    return (
        "\n".join([out.ljust(width) for out in wrap(out, width)]) if width > 0 else out
    )


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


async def async_report_to_file(hass: HomeAssistant, path: str) -> None:
    """Save report to a file."""
    report_chunks = await report(hass, render=table_renderer, chunk_size=0)

    def write(path: str) -> None:
        with Path(path).open("w", encoding="utf-8") as report_file:
            report_file.writelines(report_chunks)

    await hass.async_add_executor_job(write, path)
    _LOGGER.debug(f"Report saved to {path}")


async def async_report_to_notification(
    hass: HomeAssistant, action_str: str, service_data: dict[str, Any], chunk_size: int
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

    data = {} if service_data is None else service_data

    _LOGGER.debug(f"SERVICE_DATA {data}")

    report_chunks = await report(hass, render=text_renderer, chunk_size=chunk_size)
    for msg_chunk in report_chunks:
        data["message"] = msg_chunk
        # blocking=True ensures send order
        await hass.services.async_call(domain, action, data, blocking=True)
