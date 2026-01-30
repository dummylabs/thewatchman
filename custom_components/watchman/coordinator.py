import asyncio
from typing import Any
import os
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import entity_registry as er
from homeassistant.const import (
    EVENT_SERVICE_REGISTERED,
    EVENT_SERVICE_REMOVED,
    EVENT_STATE_CHANGED,
    EVENT_CALL_SERVICE,
)
from homeassistant.components.homeassistant import (
    SERVICE_RELOAD_CORE_CONFIG,
    SERVICE_RELOAD,
    SERVICE_RELOAD_ALL,
)
import logging

from .utils.report import fill
from .const import (
    COORD_DATA_ENTITY_ATTRS,
    COORD_DATA_LAST_UPDATE,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_MISSING_ACTIONS,
    COORD_DATA_SERVICE_ATTRS,
    COORD_DATA_PARSE_DURATION,
    COORD_DATA_LAST_PARSE,
    COORD_DATA_PROCESSED_FILES,
    COORD_DATA_IGNORED_FILES,
    CONF_IGNORED_FILES,
    CONF_IGNORED_STATES,
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    STATE_WAITING_HA,
    STATE_PARSING,
    STATE_IDLE,
    STATE_SAFE_MODE,
    LOCK_FILENAME,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    TRACKED_EVENT_DOMAINS,
    MONITORED_STATES,
)
from .utils.utils import (
    get_entity_state,
    get_config,
    is_action,
)
from .utils.logger import _LOGGER, INDENT
import time

parser_lock = asyncio.Lock()


def _get_automation_map(hass):
    """Build a map of unique_id -> entity_id for automations."""
    ent_reg = er.async_get(hass)
    return {
        entry.unique_id: entry.entity_id
        for entry in ent_reg.entities.values()
        if entry.domain == "automation"
    }


def _get_disabled_automations(hass, exclude_disabled_automations):
    """Return a set of disabled automation entity IDs."""
    if not exclude_disabled_automations:
        return set()

    disabled = {
        a.entity_id
        for a in hass.states.async_all("automation")
        if not a.state or a.state == "off"
    }
    _LOGGER.debug(f"{INDENT}Found {len(disabled)} disabled automations")
    return disabled


def _resolve_automations(hass, raw_automations, automation_map):
    """Resolve parser parent IDs to Home Assistant entity IDs."""
    automations = set()
    ent_reg = er.async_get(hass)

    for p_id in raw_automations:
        # 1. Automation Unique ID match
        if p_id in automation_map:
            automations.add(automation_map[p_id])
            continue

        # 2. Script ID match (by key)
        script_id = f"script.{p_id}"
        if hass.states.get(script_id) or ent_reg.async_get(script_id):
            automations.add(script_id)
            continue

        # 3. Fallback
        automations.add(p_id)
    return automations


def renew_missing_items_list(hass, parsed_list, exclude_disabled_automations, ignored_labels, item_type):
    """Refresh list of missing items (entities or actions)."""
    missing_items = {}
    is_entity = item_type == "entity"
    type_label = "entity" if is_entity else "action"

    _LOGGER.debug(f"## Triaging list of found {type_label}s. exclude_disabled_automations={exclude_disabled_automations}")

    ignored_states = []
    if is_entity:
        ignored_states = [
            "unavail" if s == "unavailable" else s
            for s in get_config(hass, CONF_IGNORED_STATES, [])
        ]
    elif "missing" in get_config(hass, CONF_IGNORED_STATES, []):
        # Specific check for actions if 'missing' is ignored
        _LOGGER.debug(
            f"{INDENT}MISSING state set as ignored in config, so final list of reported actions is empty."
        )
        return missing_items

    disabled_automations = _get_disabled_automations(hass, exclude_disabled_automations)
    automation_map = _get_automation_map(hass)
    ent_reg = er.async_get(hass)

    for entry, data in parsed_list.items():
        occurrences = data["locations"]
        raw_automations = data["automations"]
        automations = _resolve_automations(hass, raw_automations, automation_map)

        if is_entity:
            # Check if this is a valid HA action misidentified as a sensor/other entity
            if is_action(hass, entry):
                _LOGGER.debug(f"{INDENT}⚪ {entry} is a HA action, skipped ({occurrences})")
                continue

            # Check ignored labels
            if ignored_labels:
                reg_entry = ent_reg.async_get(entry)
                if (
                    reg_entry
                    and hasattr(reg_entry, "labels")
                    and set(reg_entry.labels) & ignored_labels
                ):
                    _LOGGER.debug(
                        f"{INDENT}⚪ {entry} has ignored label(s), skipped ({occurrences})"
                    )
                    continue

            state, _ = get_entity_state(hass, entry)
            if state in ignored_states:
                _LOGGER.debug(
                    f"{INDENT}⚪ {entry} has ignored state {state}, skipped ({occurrences})"
                )
                continue

            # Entities are reported if they are missing/unknown/etc.
            should_report = state in ["missing", "unknown", "unavail", "disabled"]
        else:
            # Actions are reported if they don't exist
            should_report = not is_action(hass, entry)

        if should_report:
            # Shared exclusion logic
            if exclude_disabled_automations and automations:
                all_parents_disabled = True
                for parent_id in automations:
                    if parent_id not in disabled_automations:
                        all_parents_disabled = False
                        break

                if all_parents_disabled:
                    _LOGGER.debug(
                        f"{INDENT}⚪ {type_label} {entry} is only used by disabled automations {automations}, skipped ({occurrences})"
                    )
                    continue
                else:
                    _LOGGER.debug(
                        f"{INDENT}🔴 {type_label} {entry} is used both by enabled and disabled automations {automations}, added to the report ({occurrences})"
                    )

            missing_items[entry] = occurrences

            # Entity-specific warning logic
            missing_auto_warning = ""
            if is_entity and automations:
                auto_id = list(automations)[0]
                auto_state = hass.states.get(auto_id)
                missing_auto_warning = (
                    "" if auto_state else "❌: automation not found"
                )

            log_msg = f"{INDENT}🔴 {type_label} {entry} added to the report"
            if is_entity:
                log_msg += f" {missing_auto_warning}"
            log_msg += f" ({occurrences})"
            _LOGGER.debug(log_msg)

    return missing_items


class WatchmanCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, logger, name, hub):
        """Initialize watchmman coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,  # Name of the data. For logging purposes.
            always_update=False,
        )

        self.hass = hass
        self.hub = hub
        self.last_check_duration = 0.0
        self.ignored_labels = set()
        self._status = STATE_WAITING_HA
        self.data = {
            COORD_DATA_MISSING_ENTITIES: 0,
            COORD_DATA_MISSING_ACTIONS: 0,
            COORD_DATA_LAST_UPDATE: dt_util.now(),
            COORD_DATA_SERVICE_ATTRS: "",
            COORD_DATA_ENTITY_ATTRS: "",
            COORD_DATA_PARSE_DURATION: 0.0,
            COORD_DATA_LAST_PARSE: None,
            COORD_DATA_PROCESSED_FILES: 0,
            COORD_DATA_IGNORED_FILES: 0,
        }

    @property
    def status(self):
        """Return the current status of the integration."""
        return self._status

    @property
    def safe_mode(self):
        """Return True if integration is in safe mode."""
        return self._status == STATE_SAFE_MODE

    def update_status(self, new_status):
        """Update the status and notify listeners."""
        self._status = new_status
        self.async_update_listeners()

    async def async_get_parsed_entities(self):
        """Return a dictionary of parsed entities and their locations."""
        return await self.hub.async_get_parsed_entities()

    async def async_get_parsed_services(self):
        """Return a dictionary of parsed services and their locations."""
        return await self.hub.async_get_parsed_services()

    async def async_process_parsed_data(self, parsed_entity_list, parsed_service_list):
        """
        Process parsed data to calculate missing items and build sensor attributes.
        This is separated to allow 'priming' the coordinator from cache without a full scan.
        """
        exclude_disabled_automations = get_config(
            self.hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
        )

        services_missing = renew_missing_items_list(
            self.hass, parsed_service_list, exclude_disabled_automations, self.ignored_labels, "action"
        )
        entities_missing = renew_missing_items_list(
            self.hass, parsed_entity_list, exclude_disabled_automations, self.ignored_labels, "entity"
        )

        parse_info = await self.hub.async_get_last_parse_info()

        last_parse_dt = None
        if parse_info.get("timestamp"):
                try:
                    last_parse_dt = dt_util.parse_datetime(parse_info["timestamp"])
                    if last_parse_dt and last_parse_dt.tzinfo is None:
                        last_parse_dt = last_parse_dt.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
                except Exception:
                    pass

        # build entity attributes map for missing_entities sensor
        entity_attrs = []
        for entity in entities_missing:
            state, name = get_entity_state(
                self.hass, entity, friendly_names=True
            )
            entity_attrs.append(
                {
                    "id": entity,
                    "state": state,
                    "friendly_name": name or "",
                    "occurrences": fill(parsed_entity_list[entity]["locations"], 0),
                }
            )

        # build service attributes map for missing_services sensor
        service_attrs = []
        for service in services_missing:
            service_attrs.append(
                {
                    "id": service,
                    "occurrences": fill(parsed_service_list[service]["locations"], 0),
                }
            )

        return {
            COORD_DATA_MISSING_ENTITIES: len(entities_missing),
            COORD_DATA_MISSING_ACTIONS: len(services_missing),
            COORD_DATA_LAST_UPDATE: dt_util.now(),
            COORD_DATA_SERVICE_ATTRS: service_attrs,
            COORD_DATA_ENTITY_ATTRS: entity_attrs,
            COORD_DATA_PARSE_DURATION: parse_info.get("duration", 0.0),
            COORD_DATA_LAST_PARSE: last_parse_dt,
            COORD_DATA_PROCESSED_FILES: parse_info.get("processed_files_count", 0),
            COORD_DATA_IGNORED_FILES: parse_info.get("ignored_files_count", 0),
        }

    # request_parser_rescan is removed as automatic mtime checking in Hub handles it.

    def request_parser_rescan(self, reason=None):
         # Stub for compatibility if anything external calls it
         pass

    async def async_get_last_parse_duration(self):
        """Return duration of the last parsing."""
        info = await self.hub.async_get_last_parse_info()
        return info.get("duration", 0.0)

    def update_ignored_labels(self, labels: list[str]) -> None:
        """Update ignored labels list and refresh data."""
        self.ignored_labels = set(labels)
        # Only trigger refresh if we are not waiting for HA startup
        if self._status != STATE_WAITING_HA:
            self.hass.async_create_task(self.async_request_refresh())

    def subscribe_to_events(self, entry):
        """Subscribe to Home Assistant events."""
        async def async_on_configuration_changed(event):
            event_type = event.event_type
            if event_type == EVENT_CALL_SERVICE:
                domain = event.data.get("domain", None)
                service = event.data.get("service", None)
                if domain in TRACKED_EVENT_DOMAINS and service in [
                    SERVICE_RELOAD_CORE_CONFIG,
                    SERVICE_RELOAD,
                    SERVICE_RELOAD_ALL,
                ]:
                    await self.async_request_refresh()

            elif event_type in [EVENT_AUTOMATION_RELOADED, EVENT_SCENE_RELOADED]:
                await self.async_request_refresh()

        async def async_on_service_changed(event):
            service = f"{event.data['domain']}.{event.data['service']}"
            parsed_services = await self.async_get_parsed_services()
            if service in parsed_services:
                _LOGGER.debug("Monitored service changed: %s", service)
                await self.async_request_refresh()

        async def async_on_state_changed(event):
            """Refresh monitored entities on state change."""
            def state_or_missing(state_id):
                """Return missing state if entity not found."""
                return "missing" if not event.data[state_id] else event.data[state_id].state

            parsed_entities = await self.async_get_parsed_entities()
            if event.data["entity_id"] in parsed_entities:
                ignored_states: list[str] = get_config(self.hass, CONF_IGNORED_STATES, [])
                old_state = state_or_missing("old_state")
                new_state = state_or_missing("new_state")
                checked_states = set(MONITORED_STATES) - set(ignored_states)
                if new_state in checked_states or old_state in checked_states:
                    _LOGGER.debug("Monitored entity changed: %s", event.data["entity_id"])
                    await self.async_request_refresh()

        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_CALL_SERVICE, async_on_configuration_changed)
        )
        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_AUTOMATION_RELOADED, async_on_configuration_changed)
        )
        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_SCENE_RELOADED, async_on_configuration_changed)
        )
        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_SERVICE_REGISTERED, async_on_service_changed)
        )
        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_SERVICE_REMOVED, async_on_service_changed)
        )
        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_STATE_CHANGED, async_on_state_changed)
        )


    async def _async_update_data(self) -> dict[str, Any]:
        """Update Watchman sensors."""

        if self.safe_mode:
            _LOGGER.warning("Watchman is in Safe Mode. Skipping update.")
            return {}

        # Check concurrency guard in Hub
        if self.hub.is_scanning:
            _LOGGER.debug("Hub is currently scanning. Skipping overlapping update request.")
            # returning self.data ensures sensors don't go unavailable/empty.
            return self.data

        _LOGGER.debug("_async_update_data: update sensor data with actual state of entities and actions")

        self.update_status(STATE_PARSING)

        # Create lock file to signal parsing in progress (crash detection)
        lock_path = self.hass.config.path(".storage", LOCK_FILENAME)
        await self.hass.async_add_executor_job(lambda: open(lock_path, "w").write("1"))

        try:
            ignored_files = get_config(self.hass, CONF_IGNORED_FILES, None)

            # only parses if needed, handled by hub
            await self.hub.async_parse(ignored_files)
            parsed_service_list = await self.async_get_parsed_services()
            parsed_entity_list = await self.async_get_parsed_entities()

            self.data = await self.async_process_parsed_data(parsed_entity_list, parsed_service_list)

            _LOGGER.debug(
                f"Sensors updated, actions: {self.data[COORD_DATA_MISSING_ACTIONS]}, entities: {self.data[COORD_DATA_MISSING_ENTITIES]}"
            )

            return self.data

        finally:
            # Remove lock file
            await self.hass.async_add_executor_job(lambda: os.remove(lock_path) if os.path.exists(lock_path) else None)
            self.update_status(STATE_IDLE)
