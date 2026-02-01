import asyncio
from typing import Any
import os
import logging
from homeassistant.core import callback, CALLBACK_TYPE
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.const import (
    EVENT_SERVICE_REGISTERED,
    EVENT_SERVICE_REMOVED,
    EVENT_CALL_SERVICE,
)
from homeassistant.components.homeassistant import (
    SERVICE_RELOAD_CORE_CONFIG,
    SERVICE_RELOAD,
    SERVICE_RELOAD_ALL,
)

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
    STATE_PENDING,
    STATE_IDLE,
    STATE_SAFE_MODE,
    PARSE_COOLDOWN,
    LOCK_FILENAME,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    TRACKED_EVENT_DOMAINS,
    MONITORED_STATES,
    DEFAULT_DELAY,
)
from .utils.utils import (
    get_entity_state,
    get_config,
    is_action,
    obfuscate_id,
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

    #_LOGGER.debug(f"## Triaging list of found {type_label}s. exclude_disabled_automations={exclude_disabled_automations}")

    ignored_states = []
    if is_entity:
        ignored_states = [
            "unavail" if s == "unavailable" else s
            for s in get_config(hass, CONF_IGNORED_STATES, [])
        ]
    elif "missing" in get_config(hass, CONF_IGNORED_STATES, []):
        # Specific check for actions if 'missing' is ignored
        _LOGGER.info("MISSING state set as ignored in config, so watchman ignores missing actions.")
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
#                _LOGGER.debug(f"{INDENT}⚪ {entry} is a HA action, skipped ({occurrences})")
                continue

            # Check ignored labels
            if ignored_labels:
                reg_entry = ent_reg.async_get(entry)
                if (
                    reg_entry
                    and hasattr(reg_entry, "labels")
                    and set(reg_entry.labels) & ignored_labels
                ):
                    # _LOGGER.debug(
                    #     f"{INDENT}⚪ {entry} has ignored label(s), skipped ({occurrences})"
                    # )
                    continue

            state, _ = get_entity_state(hass, entry)
            if state in ignored_states:
                # _LOGGER.debug(
                #     f"{INDENT}⚪ {entry} has ignored state {state}, skipped ({occurrences})"
                # )
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
                        f"{INDENT} {type_label} {entry} is only used by disabled automations {automations}, skipped ({occurrences})"
                    )
                    continue
                else:
                    _LOGGER.debug(
                        f"{INDENT} {type_label} {entry} is used both by enabled and disabled automations {automations}, added to the report ({occurrences})"
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

            # log_msg = f"{INDENT}🔴 {type_label} {entry} added to the report"
            # if is_entity:
            #     log_msg += f" {missing_auto_warning}"
            # log_msg += f" ({occurrences})"
            # _LOGGER.debug(log_msg)

    return missing_items


class WatchmanCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, logger, name, hub):
        """Initialize watchmman coordinator."""
        debouncer = Debouncer(
                    hass,
                    _LOGGER,
                    cooldown=15.0,
                    immediate=False
                )

        super().__init__(
            hass,
            _LOGGER,
            name=name,  # Name of the data. For logging purposes.
            always_update=False,
            request_refresh_debouncer=debouncer
        )

        self.hass = hass
        self.hub = hub
        self.last_check_duration = 0.0
        self.ignored_labels = set()
        self.checked_states = set()
        self._status = STATE_WAITING_HA
        self._needs_parse = False
        self._parse_task: asyncio.Task | None = None
        self._cooldown_unsub = None
        self._delay_unsub = None
        self._unsub_state_listener: CALLBACK_TYPE | None = None
        self._last_parse_time = 0.0
        self._current_delay = 0

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

    def _update_checked_states(self):
        """Update the set of states that trigger a refresh."""
        ignored_states = get_config(self.hass, CONF_IGNORED_STATES, [])
        self.checked_states = set(MONITORED_STATES) - set(ignored_states)
        _LOGGER.debug(f"Checked states updated: {self.checked_states}")

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

    async def async_get_detailed_report_data(self):
        """Return detailed report data with missing items lists."""
        parsed_services = await self.async_get_parsed_services()
        parsed_entities = await self.async_get_parsed_entities()
        exclude_disabled = get_config(
            self.hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
        )

        missing_services = renew_missing_items_list(
            self.hass,
            parsed_services,
            exclude_disabled,
            self.ignored_labels,
            "action",
        )
        missing_entities = renew_missing_items_list(
            self.hass,
            parsed_entities,
            exclude_disabled,
            self.ignored_labels,
            "entity",
        )

        def flatten_locations(item_id, locations, state):
            results = []
            for file_path, lines in locations.items():
                for line in lines:
                    results.append(
                        {
                            "id": item_id,
                            "state": state,
                            "file": file_path,
                            "line": line,
                        }
                    )
            return results

        entities_list = []
        for entity_id, locations in missing_entities.items():
            state, _ = get_entity_state(self.hass, entity_id)
            entities_list.extend(flatten_locations(entity_id, locations, state))

        actions_list = []
        for service_id, locations in missing_services.items():
            actions_list.extend(flatten_locations(service_id, locations, "missing"))

        parse_info = await self.hub.async_get_last_parse_info()
        info = {}
        info["last_parse_date"] = parse_info["timestamp"]
        info["parse_duration"] = parse_info["duration"]
        info["ignored_files_count"] = parse_info["ignored_files_count"]
        info["processed_files_count"] = parse_info["processed_files_count"]
        info["missing_entities"] = entities_list
        info["missing_actions"] = actions_list
        return info

    def request_parser_rescan(self, reason=None, force=False, delay=DEFAULT_DELAY):
        """
        Request a background scan.
        If force=True, ignore cooldown and delay.
        """
        self._needs_parse = True
        print(f"DEBUG: request_parser_rescan reason={reason} needs_parse={self._needs_parse}")
        _LOGGER.debug(f"Parser rescan requested. Reason: {reason}, Force: {force}, Delay: {delay}")

        if self.hub.is_scanning or (self._parse_task and not self._parse_task.done()):
            _LOGGER.debug("Scan in progress, request queued.")
            return

        if force:
            # if forcing, cancel any pending cooldown and delay and execute immediately
            if self._cooldown_unsub:
                self._cooldown_unsub.cancel()
                self._cooldown_unsub = None

            if self._delay_unsub:
                self._delay_unsub.cancel()
                self._delay_unsub = None

            self._current_delay = 0
            self._schedule_parse(force_immediate=True)
            return

        # if delayed parse already scheduled
        if self._delay_unsub:
            self._delay_unsub.cancel()
            self._delay_unsub = None
            _LOGGER.debug(f"Debouncing: previously scheduled parsing will be postponed for another {max(self._current_delay, delay)} sec")

        if self._cooldown_unsub:
            _LOGGER.debug("Debouncing: parser in cooldown, will be scheduled in 60 sec.")

        # Smart Debounce: use the maximum of current pending delay or new delay
        self._current_delay = max(self._current_delay, delay)
        self.update_status(STATE_PENDING)
        self._delay_unsub = self.hass.loop.call_later(self._current_delay, self._on_timer_finished, "delay")

    @callback
    def _on_timer_finished(self, timer_type: str):
        """Callback when a scheduled timer (delay or cooldown) finishes."""
        if timer_type == "delay":
            self._delay_unsub = None
            self._current_delay = 0
        elif timer_type == "cooldown":
            self._cooldown_unsub = None
        self._schedule_parse()

    def _schedule_parse(self, force_immediate=False):
        """Schedule the parse task based on state and cooldown."""

        if self.hub.is_scanning or (self._parse_task and not self._parse_task.done()):
            #  do nothing as parsing is already running
            # _needs_parse=True will trigger next parsing request with cooldown
            # after current parsing is finished
            _LOGGER.debug("⏳ Scheduling parse: Scan in progress, parsing request queued.")
            return

        # 2. Check cooldown
        now = time.time()
        time_since_last = now - self._last_parse_time

        if not force_immediate and time_since_last < PARSE_COOLDOWN:
            remaining = PARSE_COOLDOWN - time_since_last
            if self._cooldown_unsub:
                # Timer already running
                _LOGGER.debug(f"⏳ Scheduling parse: parser in cooldown and will run again in {remaining:.1f}s")
                return

            _LOGGER.debug(f"⏳ Scheduling parse: parser in cooldown. Scheduling in {remaining:.1f}s")
            self.update_status(STATE_PENDING)
            self._cooldown_unsub = self.hass.loop.call_later(
                remaining, self._on_timer_finished, "cooldown"
            )
            return

        # 3. Start background task
        _LOGGER.debug(f"🚀 Start parse: force_immediate={force_immediate}")
        self._cooldown_unsub = None
        self._parse_task = self.hass.async_create_background_task(
            self._execute_parse(), "watchman_parse"
        )

    async def async_force_parse(self):
        """
        Execute a blocking parse for the report service.
        Returns a Task/Coroutine that finishes when parsing is complete.
        """
        # Cancel pending cooldown
        if self._cooldown_unsub:
            self._cooldown_unsub.cancel()
            self._cooldown_unsub = None

        # Cancel pending delay
            if self._delay_unsub:
                self._delay_unsub.cancel()
                self._delay_unsub = None

        # If already running, return the running task
        if self._parse_task and not self._parse_task.done():
            _LOGGER.debug("Force parse requested, but parser is already running. Waiting to reuse its results.")
            return await self._parse_task

        # Otherwise, run immediately
        _LOGGER.debug("Force parse requested. Starting immediately.")
        return await self._execute_parse()

    async def _execute_parse(self):
        """Execute the heavy parsing logic."""
        if self.safe_mode:
            _LOGGER.warning("_execute_parse: Watchman is in Safe Mode. Skipping parse.")
            return

        self._needs_parse = False
        self.update_status(STATE_PARSING)

        # Create lock file
        lock_path = self.hass.config.path(".storage", LOCK_FILENAME)
        await self.hass.async_add_executor_job(lambda: open(lock_path, "w").write("1"))

        try:
            ignored_files = get_config(self.hass, CONF_IGNORED_FILES, None)

            # Perform the scan
            await self.hub.async_parse(ignored_files)

            self._last_parse_time = time.time()

            # Refresh data and notify sensors
            await self.async_refresh()
            self.async_update_entity_tracking()

        except Exception as err:
            _LOGGER.exception(f"Error during watchman parse: {err}")

        finally:
            # Cleanup
            await self.hass.async_add_executor_job(
                lambda: os.remove(lock_path) if os.path.exists(lock_path) else None
            )
            self.update_status(STATE_IDLE)
            self._parse_task = None
            _LOGGER.debug("🏁 Background parse finished.")

            # Check if another parse was requested during execution
            if self._needs_parse:
                _LOGGER.debug(f"Another request occured during parser execution, will be repeated after cooldown ({PARSE_COOLDOWN} sec)")
                self._schedule_parse()

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

    @callback
    def _handle_state_change_event(self, event):
        """Handle state change event for monitored entities."""
        if self.hub.is_scanning:
            _LOGGER.debug("Scan in progress, skipping state change event.")
            return

        def state_or_missing(state_id):
            """Return missing state if entity not found."""
            return "missing" if not event.data[state_id] else event.data[state_id].state

        old_state = state_or_missing("old_state")
        new_state = state_or_missing("new_state")

        if new_state in self.checked_states or old_state in self.checked_states:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(f"Monitored entity changed: {obfuscate_id(event.data['entity_id'])} from {old_state} to {new_state}")
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def async_update_entity_tracking(self):
        """Update the state change listener with the current list of monitored entities."""
        self._update_checked_states()
        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

        if self.hub._monitored_entities:
            _LOGGER.debug("Updating monitored entities listener with %s entities", len(self.hub._monitored_entities))
            self._unsub_state_listener = async_track_state_change_event(
                self.hass, list(self.hub._monitored_entities), self._handle_state_change_event
            )
        else:
            _LOGGER.debug("No entities to monitor.")

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
                    self.request_parser_rescan(reason=f"{domain}.{service}")

            elif event_type in [EVENT_AUTOMATION_RELOADED, EVENT_SCENE_RELOADED]:
                self.request_parser_rescan(reason=event_type)

        async def async_on_service_changed(event):
            if self.hub.is_scanning:
                _LOGGER.debug("Scan in progress, skipping service change event.")
                return

            service = f"{event.data['domain']}.{event.data['service']}"
            if self.hub.is_monitored_service(service):
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Monitored service changed: %s", obfuscate_id(service))
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
        # Entity state change monitoring is now handled by async_track_state_change_event
        # triggered via async_update_entity_tracking in _execute_parse


    async def _async_update_data(self) -> dict[str, Any]:
        """
        Update Watchman sensors.
        Reactive: Read from Hub/DB without triggering a parse.
        """
        _LOGGER.debug("Coordinator: refresh watchman sensors requested")
        if self.safe_mode:
            _LOGGER.debug("Watchman in safe mode, async_update_data will return {}")
            return {}

        # concurrency check
        if self.hub.is_scanning:
            _LOGGER.debug("Coordinator: Hub is scanning. Use cached data for sensors to avoid race conditions.")
            return self.data

        # 2. Read Phase
        try:
            parsed_service_list = await self.async_get_parsed_services()
            parsed_entity_list = await self.async_get_parsed_entities()

            new_data = await self.async_process_parsed_data(
                parsed_entity_list, parsed_service_list
            )
            self.data = new_data
            _LOGGER.debug(
                f"Sensors refreshed from DB. Actions: {new_data[COORD_DATA_MISSING_ACTIONS]}, "
                f"Entities: {new_data[COORD_DATA_MISSING_ENTITIES]}"
            )
            return new_data

        except Exception as err:
            _LOGGER.error(f"Error reading watchman data: {err}")
            return self.data
