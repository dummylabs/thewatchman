import asyncio
from collections.abc import Iterable
import contextlib
import logging
from pathlib import Path
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .hub import WatchmanHub

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_CALL_SERVICE,
    EVENT_SERVICE_REGISTERED,
    EVENT_SERVICE_REMOVED,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    CONF_IGNORED_FILES,
    CONF_IGNORED_STATES,
    COORD_DATA_ENTITY_ATTRS,
    COORD_DATA_IGNORED_FILES,
    COORD_DATA_LAST_PARSE,
    COORD_DATA_LAST_UPDATE,
    COORD_DATA_MISSING_ACTIONS,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_PARSE_DURATION,
    COORD_DATA_PROCESSED_FILES,
    COORD_DATA_SERVICE_ATTRS,
    DEFAULT_DELAY,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    LOCK_FILENAME,
    MONITORED_STATES,
    PARSE_COOLDOWN,
    STATE_IDLE,
    STATE_PARSING,
    STATE_PENDING,
    STATE_SAFE_MODE,
    STATE_WAITING_HA,
    STORAGE_KEY,
    STORAGE_VERSION,
    WATCHED_EVENTS,
    WATCHED_SERVICES,
)
from .utils.logger import _LOGGER, INDENT
from .utils.parser_core import ParseResult
from .utils.report import fill
from .utils.utils import (
    get_config,
    get_entity_state,
    is_action,
    obfuscate_id,
)

parser_lock = asyncio.Lock()


def _get_automation_map(hass: HomeAssistant) -> dict[str, str]:
    """Build a map of unique_id -> entity_id for automations."""
    ent_reg = er.async_get(hass)
    return {
        entry.unique_id: entry.entity_id
        for entry in ent_reg.entities.values()
        if entry.domain == "automation"
    }


def _get_disabled_automations(hass: HomeAssistant, *, exclude_disabled_automations: bool) -> set[str]:
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


def _resolve_automations(
    hass: HomeAssistant, raw_automations: Iterable[str], automation_map: dict[str, str]
) -> set[str]:
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


def renew_missing_items_list(
    hass: HomeAssistant,
    parsed_list: dict[str, Any],
    *,
    exclude_disabled_automations: bool,
    ignored_labels: set[str],
    item_type: str,
) -> dict[str, Any]:
    """Refresh list of missing items (entities or actions)."""
    missing_items = {}
    is_entity = item_type == "entity"
    type_label = "entity" if is_entity else "action"
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

    disabled_automations = _get_disabled_automations(
        hass, exclude_disabled_automations=exclude_disabled_automations
    )
    automation_map = _get_automation_map(hass)
    ent_reg = er.async_get(hass)

    for entry, data in parsed_list.items():
        occurrences = data["locations"]
        raw_automations = data["automations"]
        automations = _resolve_automations(hass, raw_automations, automation_map)

        if is_entity:
            # Check if this is a valid HA action misidentified as a sensor/other entity
            if is_action(hass, entry):
                continue

            # Check ignored labels
            if ignored_labels:
                reg_entry = ent_reg.async_get(entry)
                if (
                    reg_entry
                    and hasattr(reg_entry, "labels")
                    and set(reg_entry.labels) & ignored_labels
                ):
                    continue

            state, _ = get_entity_state(hass, entry)
            if state in ignored_states:
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
                _LOGGER.debug(
                    f"{INDENT} {type_label} {entry} is used both by enabled and disabled automations {automations}, added to the report ({occurrences})"
                )

            missing_items[entry] = data["occurrences"]

            # Entity-specific warning logic
            if is_entity and automations:
                auto_id = next(iter(automations))
                if not hass.states.get(auto_id):
                    _LOGGER.warning(f"Automation with id {auto_id} not found.")

    return missing_items


class WatchmanCoordinator(DataUpdateCoordinator):
    """Watchman coordinator."""

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        config_entry: ConfigEntry,
        hub: "WatchmanHub",
        version: str,
    ) -> None:
        """Initialize watchmman coordinator."""
        debouncer = Debouncer(
                    hass,
                    _LOGGER,
                    cooldown=5.0,
                    immediate=False
                )

        super().__init__(
            hass,
            _LOGGER,
            name=config_entry.title.lower(), # Name of the data. For logging purposes.
            config_entry=config_entry,
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
        self._version = version
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

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

    async def async_load_stats(self) -> None:
        """Load stats from storage."""
        if stats := await self._store.async_load():
            self._last_parse_time = stats.get("last_parse_time_monotonic", 0.0)
            self.data[COORD_DATA_PARSE_DURATION] = stats.get("duration", 0.0)
            self.data[COORD_DATA_PROCESSED_FILES] = stats.get("processed_files_count", 0)
            self.data[COORD_DATA_IGNORED_FILES] = stats.get("ignored_files_count", 0)
            if timestamp := stats.get("timestamp"):
                with contextlib.suppress(Exception):
                    last_parse_dt = dt_util.parse_datetime(timestamp)
                    if last_parse_dt and last_parse_dt.tzinfo is None:
                        last_parse_dt = last_parse_dt.replace(
                            tzinfo=dt_util.DEFAULT_TIME_ZONE
                        )
                    self.data[COORD_DATA_LAST_PARSE] = last_parse_dt

    async def async_save_stats(self, parse_result: ParseResult) -> None:
        """Save stats to storage and update in-memory data."""
        # Update in-memory data immediately so sensors are fresh
        self.data[COORD_DATA_PARSE_DURATION] = parse_result.duration
        self.data[COORD_DATA_PROCESSED_FILES] = parse_result.processed_files_count
        self.data[COORD_DATA_IGNORED_FILES] = parse_result.ignored_files_count

        if parse_result.timestamp:
            with contextlib.suppress(Exception):
                last_parse_dt = dt_util.parse_datetime(parse_result.timestamp)
                if last_parse_dt and last_parse_dt.tzinfo is None:
                    last_parse_dt = last_parse_dt.replace(
                        tzinfo=dt_util.DEFAULT_TIME_ZONE
                    )
                self.data[COORD_DATA_LAST_PARSE] = last_parse_dt

        stats = {
            "duration": parse_result.duration,
            "timestamp": parse_result.timestamp,
            "ignored_files_count": parse_result.ignored_files_count,
            "processed_files_count": parse_result.processed_files_count,
            "last_parse_time_monotonic": self._last_parse_time,
        }
        await self._store.async_save(stats)

    @property
    def version(self) -> str:
        """Return version of the integration from manifest file."""
        return self._version

    @property
    def status(self) -> str:
        """Return the current status of the integration."""
        return self._status

    @property
    def safe_mode(self) -> bool:
        """Return True if integration is in safe mode."""
        return self._status == STATE_SAFE_MODE

    def update_status(self, new_status: str) -> None:
        """Update the status and notify listeners."""
        self._status = new_status
        self.async_update_listeners()

    def _update_checked_states(self) -> None:
        """Update the set of states that trigger a refresh."""
        ignored_states = get_config(self.hass, CONF_IGNORED_STATES, [])
        self.checked_states = set(MONITORED_STATES) - set(ignored_states)
        _LOGGER.debug(f"Checked states updated: {self.checked_states}")

    async def async_get_parsed_entities(self) -> dict[str, Any]:
        """Return a dictionary of parsed entities and their locations."""
        return await self.hub.async_get_parsed_entities()

    async def async_get_parsed_services(self) -> dict[str, Any]:
        """Return a dictionary of parsed services and their locations."""
        return await self.hub.async_get_parsed_services()

    async def async_process_parsed_data(
        self, parsed_entity_list: dict[str, Any], parsed_service_list: dict[str, Any]
    ) -> dict[str, Any]:
        """Process parsed data to calculate missing items and build sensor attributes.

        This is separated to allow 'priming' the coordinator from cache without a full scan.
        """
        exclude_disabled_automations = get_config(
            self.hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
        )

        services_missing = renew_missing_items_list(
            self.hass,
            parsed_service_list,
            exclude_disabled_automations=exclude_disabled_automations,
            ignored_labels=self.ignored_labels,
            item_type="action",
        )
        entities_missing = renew_missing_items_list(
            self.hass,
            parsed_entity_list,
            exclude_disabled_automations=exclude_disabled_automations,
            ignored_labels=self.ignored_labels,
            item_type="entity",
        )

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
            COORD_DATA_PARSE_DURATION: self.data.get(COORD_DATA_PARSE_DURATION, 0.0),
            COORD_DATA_LAST_PARSE: self.data.get(COORD_DATA_LAST_PARSE),
            COORD_DATA_PROCESSED_FILES: self.data.get(COORD_DATA_PROCESSED_FILES, 0),
            COORD_DATA_IGNORED_FILES: self.data.get(COORD_DATA_IGNORED_FILES, 0),
        }

    async def async_get_detailed_report_data(self) -> dict[str, Any]:
        """Return detailed report data with missing items lists."""
        parsed_services = await self.async_get_parsed_services()
        parsed_entities = await self.async_get_parsed_entities()
        exclude_disabled = get_config(
            self.hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
        )

        missing_services = renew_missing_items_list(
            self.hass,
            parsed_services,
            exclude_disabled_automations=exclude_disabled,
            ignored_labels=self.ignored_labels,
            item_type="action",
        )
        missing_entities = renew_missing_items_list(
            self.hass,
            parsed_entities,
            exclude_disabled_automations=exclude_disabled,
            ignored_labels=self.ignored_labels,
            item_type="entity",
        )

        def flatten_occurrences(
            item_id: str, occurrences: list[dict[str, Any]], state: str
        ) -> list[dict[str, Any]]:
            results = []
            for occ in occurrences:
                results.append(
                    {
                        "id": item_id,
                        "state": state,
                        "file": occ["path"],
                        "line": occ["line"],
                        "context": occ.get("context"),
                    }
                )
            return results

        entities_list = []
        for entity_id, occurrences in missing_entities.items():
            state, _ = get_entity_state(self.hass, entity_id)
            entities_list.extend(flatten_occurrences(entity_id, occurrences, state))

        actions_list = []
        for service_id, occurrences in missing_services.items():
            actions_list.extend(flatten_occurrences(service_id, occurrences, "missing"))

        info = {}
        info["last_parse_date"] = self.data.get(COORD_DATA_LAST_PARSE)
        info["parse_duration"] = self.data.get(COORD_DATA_PARSE_DURATION)
        info["ignored_files_count"] = self.data.get(COORD_DATA_IGNORED_FILES)
        info["processed_files_count"] = self.data.get(COORD_DATA_PROCESSED_FILES)
        info["missing_entities"] = entities_list
        info["missing_actions"] = actions_list
        return info

    def request_parser_rescan(
        self,
        *,
        reason: str | None = None,
        force: bool = False,
        delay: float = DEFAULT_DELAY,
    ) -> None:
        """Request a background scan.

        If force=True, ignore cooldown and delay.
        """
        self._needs_parse = True
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
            _LOGGER.debug(f"⏳ Debouncing: previously scheduled parsing will be postponed for another {max(self._current_delay, delay)} sec")

        if self._cooldown_unsub:
            _LOGGER.debug("⏳ Debouncing: parser in cooldown, will be scheduled in 60 sec.")

        # Smart Debounce: use the maximum of current pending delay or new delay
        self._current_delay = max(self._current_delay, delay)
        self.update_status(STATE_PENDING)
        self._delay_unsub = self.hass.loop.call_later(self._current_delay, self._on_timer_finished, "delay")

    @callback
    def _on_timer_finished(self, timer_type: str) -> None:
        """Callback when a scheduled timer (delay or cooldown) finishes."""
        if timer_type == "delay":
            self._delay_unsub = None
            self._current_delay = 0
        elif timer_type == "cooldown":
            self._cooldown_unsub = None
        self._schedule_parse()

    def _schedule_parse(self, *, force_immediate: bool = False) -> None:
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
        _LOGGER.debug(f"🚀 Background parse started: force_immediate={force_immediate}")
        self._cooldown_unsub = None
        self._parse_task = self.hass.async_create_background_task(
            self._execute_parse(), "watchman_parse"
        )

    async def async_force_parse(self) -> Any:
        """Execute a blocking parse for the report service.

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

    async def _execute_parse(self) -> None:
        """Execute the heavy parsing logic."""
        if self.safe_mode:
            _LOGGER.warning("_execute_parse: Watchman is in Safe Mode. Skipping parse.")
            return

        self._needs_parse = False
        self.update_status(STATE_PARSING)

        # Create lock file
        lock_path = self.hass.config.path(".storage", LOCK_FILENAME)
        await self.hass.async_add_executor_job(
            lambda: Path(lock_path).write_text("1", encoding="utf-8")
        )

        try:
            ignored_files = get_config(self.hass, CONF_IGNORED_FILES, [])

            # Perform the scan
            if parse_result := await self.hub.async_parse(ignored_files):
                self._last_parse_time = time.time()
                await self.async_save_stats(parse_result)

            # Refresh data and notify sensors
            await self.async_refresh()
            self.async_update_entity_tracking()

        except Exception as err:
            _LOGGER.exception(f"Error during watchman parse: {err}")

        finally:
            # Cleanup
            await self.hass.async_add_executor_job(
                lambda: Path(lock_path).unlink(missing_ok=True)
            )
            self.update_status(STATE_IDLE)
            self._parse_task = None
            _LOGGER.debug("🏁 Background parse finished.")

            # Check if another parse was requested during execution
            if self._needs_parse:
                _LOGGER.debug(f"⏳ Another request occured during parser execution, will be repeated after cooldown ({PARSE_COOLDOWN} sec)")
                self._schedule_parse()

    async def async_get_last_parse_duration(self) -> float:
        """Return duration of the last parsing."""
        return self.data.get(COORD_DATA_PARSE_DURATION, 0.0)

    def update_ignored_labels(self, labels: list[str]) -> None:
        """Update ignored labels list and refresh data."""
        self.ignored_labels = set(labels)
        # Only trigger refresh if we are not waiting for HA startup
        if self._status != STATE_WAITING_HA:
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _handle_state_change_event(self, event: Event) -> None:
        """Handle state change event for monitored entities."""
        if self.hub.is_scanning:
            _LOGGER.debug("Scan in progress, skipping state change event.")
            return

        def state_or_missing(state_id: str) -> str:
            """Return missing state if entity not found."""
            return "missing" if not event.data[state_id] else event.data[state_id].state

        old_state = state_or_missing("old_state")
        new_state = state_or_missing("new_state")

        if new_state in self.checked_states or old_state in self.checked_states:
            if _LOGGER.isEnabledFor(logging.DEBUG):
                _LOGGER.debug(f"Monitored entity changed: {obfuscate_id(event.data['entity_id'])} from {old_state} to {new_state}")
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def async_update_entity_tracking(self) -> None:
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

    def subscribe_to_events(self, entry: ConfigEntry) -> None:
        """Subscribe to Home Assistant events."""

        async def async_on_configuration_changed(event: Event) -> None:
            event_type = event.event_type
            if event_type == EVENT_CALL_SERVICE:

                service = event.data.get("service", None)
                if service in WATCHED_SERVICES:
                    domain = event.data.get("domain", None)
                    self.request_parser_rescan(reason=f"{domain}.{service}")

            elif event_type in WATCHED_EVENTS:
                self.request_parser_rescan(reason=event_type)

        async def async_on_service_changed(event: Event) -> None:
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

    async def async_shutdown(self) -> None:
        """Cancel any scheduled tasks and listeners."""
        await super().async_shutdown()
        if self._cooldown_unsub:
            self._cooldown_unsub.cancel()
            self._cooldown_unsub = None

        if self._delay_unsub:
            self._delay_unsub.cancel()
            self._delay_unsub = None

        if self._unsub_state_listener:
            self._unsub_state_listener()
            self._unsub_state_listener = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Update Watchman sensors.

        Read from Hub/DB without triggering a parse.
        """
        _LOGGER.debug("Coordinator: refresh watchman sensors requested")
        if self.safe_mode:
            _LOGGER.debug("Watchman in safe mode, async_update_data will return {}")
            return {}

        if self.hub.is_scanning:
            _LOGGER.debug("Coordinator: Hub is scanning. Use cached data for sensors to avoid race conditions.")
            return self.data

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
