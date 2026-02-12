import asyncio
from collections.abc import Iterable
import contextlib
from dataclasses import dataclass
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
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    CONF_IGNORED_FILES,
    CONF_IGNORED_LABELS,
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


@dataclass
class FilterContext:
    """Context object holding data for filtering missing items."""

    entity_registry: er.EntityRegistry
    disabled_automations: set[str]
    automation_map: dict[str, str]
    ignored_states: set[str]
    ignored_labels: set[str]
    exclude_disabled: bool


def _resolve_automations(
    hass: HomeAssistant,
    raw_automations: Iterable[str],
    automation_map: dict[str, str],
    ent_reg: er.EntityRegistry,
) -> set[str]:
    """Resolve parser parent IDs to Home Assistant entity IDs."""
    automations = set()

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


def _is_safe_to_report(
    hass: HomeAssistant,
    entry: str,
    data: dict[str, Any],
    ctx: FilterContext,
    is_entity_check: bool
) -> bool:
    """Check context (automations) to decide if item should be reported.

    Returns True if item should be reported, False if it is excluded.
    """
    occurrences = data["locations"]
    raw_automations = data["automations"]
    automations = _resolve_automations(hass, raw_automations, ctx.automation_map, ctx.entity_registry)

    if ctx.exclude_disabled and automations:
        all_parents_disabled = True
        for parent_id in automations:
            if parent_id not in ctx.disabled_automations:
                all_parents_disabled = False
                break

        if all_parents_disabled:
            return False

    if is_entity_check and automations:
        auto_id = next(iter(automations))
        if not hass.states.get(auto_id):
             reg_entry = ctx.entity_registry.async_get(auto_id)
             if not (reg_entry and reg_entry.disabled_by):
                 _LOGGER.warning(
                     f"? Unable to locate automation: {obfuscate_id(auto_id)} for {obfuscate_id(entry)}. "
                     f"Occurrences: {occurrences}"
                 )

    return True


def _is_available(state: Any) -> bool:
    """Check if state is available/active.

    Missing/Unavailable: None, "unavailable", "unknown", "missing"
    Active: Any other state
    """
    if state is None:
        return False
    val = state.state if hasattr(state, "state") else str(state)
    return val not in ("unavailable", "unknown", "missing", "None")


def check_single_entity_status( # noqa: PLR0911
    hass: HomeAssistant,
    entry: str,
    data: dict[str, Any],
    ctx: FilterContext,
    item_type: str,
) -> list[dict[str, Any]] | None:
    """Check status of a single entity with cross-validation logic.

    Returns occurrences list if missing/invalid, None otherwise.
    """
    is_entity_check = item_type == "entity"
    # reg_entry used for: disabled check, label filtering, and cross-check logic.
    reg_entry = None
    # --- PHASE 1: STATUS RESOLUTION ---
    if is_entity_check:
        # fetch reg_entry to re-use below in code
        reg_entry = ctx.entity_registry.async_get(entry)
        current_state, _ = get_entity_state(hass, entry, registry_entry=reg_entry)

        # Fast exit for healthy entities
        if current_state not in ("missing", "unknown", "unavail", "disabled"):
            return None

        # Cross-validation: If missing, check if it's actually an action
        if is_action(hass, entry):
            return None
    else: # item_type == "action"
        if is_action(hass, entry):
            return None

        # Cross-validation: If missing, check if it's actually an entity.
        # Check 1: State Machine
        # Check 2: Registry
        # fetch reg_entry to re-use below in code
        reg_entry = ctx.entity_registry.async_get(entry)
        if hass.states.get(entry) or reg_entry:
            return None
    # --- PHASE 2: CONFIGURATION FILTERS ---
    # 2. Check Ignored Labels (Applies to BOTH entities and actions)
    # Use the pre-fetched reg_entry
    if ctx.ignored_labels and reg_entry and hasattr(reg_entry, "labels") and \
        not ctx.ignored_labels.isdisjoint(reg_entry.labels):
            return None
    # --- PHASE 3: CONTEXT ANALYSIS ---
    # Expensive checks (parsing automations) only if everything else failed
    if not _is_safe_to_report(hass, entry, data, ctx, is_entity_check):
        return None

    return data["occurrences"]


def renew_missing_items_list(
    hass: HomeAssistant,
    parsed_list: dict[str, Any],
    ctx: FilterContext,
    item_type: str,
) -> dict[str, Any]:
    """Refresh list of missing items using the provided FilterContext."""
    missing_items = {}
    is_entity = item_type == "entity"

    # Specific check for actions if 'missing' is ignored
    if not is_entity and "missing" in ctx.ignored_states:
        _LOGGER.info("MISSING state set as ignored in config, so watchman ignores missing actions.")
        return missing_items

    for entry, data in parsed_list.items():
        result = check_single_entity_status(hass, entry, data, ctx, item_type)
        if result is not None:
            missing_items[entry] = result

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
        self.debouncer = debouncer
        self.last_check_duration = 0.0
        self.checked_states = set()
        self._status = STATE_WAITING_HA
        self._needs_parse = False
        self._parse_task: asyncio.Task | None = None
        self._cooldown_unsub = None
        self._delay_unsub = None
        self._unsub_state_listener: CALLBACK_TYPE | None = None
        self._unsub_automation_listener: CALLBACK_TYPE | None = None
        self._last_parse_time = 0.0
        self._current_delay = 0
        self._version = version
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._filter_context_cache: FilterContext | None = None

        # Optimization: Dirty set tracking
        self._dirty_entities: set[str] = set()
        self._missing_entities_cache: dict[str, Any] = {}
        self._missing_actions_cache: dict[str, Any] = {}
        self._force_full_rescan: bool = True

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

    def invalidate_filter_context(self) -> None:
        """Invalidate the cached filter context."""
        self._filter_context_cache = None
        # Invalidate filter context implies global rules changed, so force full rescan
        self._force_full_rescan = True

    def _build_filter_context(self) -> FilterContext:
        """Build the context object for filtering operations."""
        if self._filter_context_cache:
            return self._filter_context_cache

        _LOGGER.debug("Build FilterContext object for filtering operations")
        ent_reg = er.async_get(self.hass)
        exclude_disabled = get_config(self.hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False)
        ignored_states = get_config(self.hass, CONF_IGNORED_STATES, [])
        ignored_labels = set(self.config_entry.data.get(CONF_IGNORED_LABELS, []))

        automation_map = {}
        disabled_automations = set()


        # 1. Registry Pass: Map unique_id and check disabled_by
        for entry in ent_reg.entities.values():
            if entry.domain != "automation":
                continue

            # Map unique_id to entity_id
            automation_map[entry.unique_id] = entry.entity_id

            if exclude_disabled and entry.disabled_by:
                disabled_automations.add(entry.entity_id)

        num_disabled_auto = len(disabled_automations)
        num_off_auto = 0
        # 2. State Pass: Check for 'off' state (covers both registry and non-registry automations)
        if exclude_disabled:
            for state in self.hass.states.async_all("automation"):
                if state.state == "off":
                    num_off_auto += 1
                    disabled_automations.add(state.entity_id)

        if exclude_disabled:
            _LOGGER.debug(f"Found {num_off_auto} automations in 'off' state and {num_disabled_auto} registry-disabled automations.")
            _LOGGER.debug("They will be excluded from report due to user settings.")

        # Normalize ignored states (e.g. unavail -> unavailable if needed, or handle in loop)
        # For now, we pass raw config list and handle mapping in the loop for backward compatibility
        ignored_states_mapped = set()
        for s in ignored_states:
             if s == "unavailable":
                 ignored_states_mapped.add("unavail")
             else:
                 ignored_states_mapped.add(s)

        self._filter_context_cache = FilterContext(
            entity_registry=ent_reg,
            disabled_automations=disabled_automations,
            automation_map=automation_map,
            ignored_states=ignored_states_mapped,
            ignored_labels=ignored_labels,
            exclude_disabled=exclude_disabled,
        )
        return self._filter_context_cache

    @callback
    def _handle_automation_state_change(self, event: Event) -> None:
        """Handle state changes for automations (toggles)."""
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        # Filter noise (attribute changes)
        if old_state and new_state and old_state.state != new_state.state:
            _LOGGER.debug(f"Automation state changed: {obfuscate_id(event.data['entity_id'])}")
            self.invalidate_filter_context()
            self.hass.async_create_task(self.async_request_refresh())

    @callback
    def _update_automation_listener(self) -> None:
        """Update subscription to automation state changes."""
        if self._unsub_automation_listener:
            self._unsub_automation_listener()
            self._unsub_automation_listener = None

        automation_ids = self.hass.states.async_entity_ids("automation")
        if automation_ids:
            _LOGGER.debug(f"Subscribing to state changes for {len(automation_ids)} automations")
            self._unsub_automation_listener = async_track_state_change_event(
                self.hass, automation_ids, self._handle_automation_state_change
            )
        else:
            _LOGGER.debug("No automations found to subscribe to.")

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
        return (await self.hub.async_get_all_items())["entities"]

    async def async_get_parsed_services(self) -> dict[str, Any]:
        """Return a dictionary of parsed services and their locations."""
        return (await self.hub.async_get_all_items())["services"]

    async def async_process_parsed_data(
        self, parsed_entity_list: dict[str, Any], parsed_service_list: dict[str, Any]
    ) -> dict[str, Any]:
        """Process parsed data to calculate missing items and build sensor attributes.

        This is separated to allow 'priming' the coordinator from cache without a full scan.
        """
        # Build optimized Home Assistant data context once
        ctx = self._build_filter_context()

        services_missing = renew_missing_items_list(
            self.hass,
            parsed_service_list,
            ctx,
            item_type="action",
        )
        entities_missing = renew_missing_items_list(
            self.hass,
            parsed_entity_list,
            ctx,
            item_type="entity",
        )

        # Initialize internal cache
        self._missing_entities_cache = entities_missing
        self._missing_actions_cache = services_missing
        self._force_full_rescan = False
        self._dirty_entities.clear()

        # build entity attributes map for missing_entities sensor
        entity_attrs = []
        for entity in entities_missing:
            reg_entry = ctx.entity_registry.async_get(entity)
            state, name = get_entity_state(
                self.hass, entity, friendly_names=True, registry_entry=reg_entry
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
        service_attrs = [
            {
                "id": service,
                "occurrences": fill(parsed_service_list[service]["locations"], 0),
            }
            for service in services_missing
        ]

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
        all_items = await self.hub.async_get_all_items()
        parsed_services = all_items["services"]
        parsed_entities = all_items["entities"]

        ctx = self._build_filter_context()

        missing_services = renew_missing_items_list(
            self.hass,
            parsed_services,
            ctx,
            item_type="action",
        )
        missing_entities = renew_missing_items_list(
            self.hass,
            parsed_entities,
            ctx,
            item_type="entity",
        )

        def flatten_occurrences(
            item_id: str, occurrences: list[dict[str, Any]], state: str
        ) -> list[dict[str, Any]]:
            return [
                {
                    "id": item_id,
                    "state": state,
                    "file": occ["path"],
                    "line": occ["line"],
                    "context": occ.get("context"),
                }
                for occ in occurrences
            ]


        entities_list = []
        for entity_id, occurrences in missing_entities.items():
            reg_entry = ctx.entity_registry.async_get(entity_id)
            state, _ = get_entity_state(self.hass, entity_id, registry_entry=reg_entry)
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
                # After scan, we definitely need full rescan of items status
                self._force_full_rescan = True

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

    @callback
    def _handle_state_change_event(self, event: Event) -> None:
        """Handle state change event for monitored entities."""
        if self.hub.is_scanning:
            _LOGGER.debug("Scan in progress, skipping state change event.")
            return

        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")

        # 1. Ignore Attribute Changes (same state value)
        if old_state and new_state and old_state.state == new_state.state:
            return

        # 2. Availability Check
        if _is_available(old_state) == _is_available(new_state):
            # Status quo regarding availability (Active->Active or Missing->Missing), ignore.
            return

        entity_id = event.data["entity_id"]
        # Track dirty entities
        self._dirty_entities.add(entity_id)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            old_s = old_state.state if old_state else "None"
            new_s = new_state.state if new_state else "None"
            _LOGGER.debug(f"⚡{obfuscate_id(entity_id)} ({old_s}->{new_s}), queued for refresh. Dirty: {len(self._dirty_entities)}")

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
                if event_type == EVENT_AUTOMATION_RELOADED:
                    _LOGGER.debug("Invalidating FilterContext cache due to EVENT_AUTOMATION_RELOADED")
                    self.invalidate_filter_context()
                    self._update_automation_listener()
                self.request_parser_rescan(reason=str(event_type))

        async def async_on_service_changed(event: Event) -> None:
            if self.hub.is_scanning:
                _LOGGER.debug("Scan in progress, skipping service change event.")
                return

            service = f"{event.data['domain']}.{event.data['service']}"
            if self.hub.is_monitored_service(service):
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug("Monitored service changed: %s", obfuscate_id(service))
                self._force_full_rescan = True
                await self.async_request_refresh()

        async def async_on_registry_updated(event: Event) -> None:
            if event.data.get("action") in ("create", "remove", "update"):
                entity_id = event.data.get("entity_id")

                # 1. Automation changes -> Invalidate Context -> Full Rescan
                if entity_id and entity_id.startswith("automation."):
                    _LOGGER.debug("Invalidating FilterContext cache due to a CRUD op. for an automation")
                    self.invalidate_filter_context()
                    self._update_automation_listener()
                    await self.async_request_refresh()
                    return

                # 2. Monitored Entity changes -> Full Rescan
                if entity_id and entity_id in self.hub._monitored_entities:
                    # Optimization Note: While we could technically use incremental update here
                    # (by adding to dirty_entities), we opt for a full rescan to guarantee
                    # consistency when metadata changes. This covers low-frequency administrative
                    # actions like changing labels, disabling entities, or renaming IDs.
                    _LOGGER.debug(f"⚡Registry update for monitored entity {obfuscate_id(entity_id)} -> Force Full Rescan")
                    self._force_full_rescan = True
                    await self.async_request_refresh()

        # Config/Service/Reload events
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

        # Entity Registry Updates
        entry.async_on_unload(
            self.hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED, async_on_registry_updated)
        )

        # Initial subscription to existing automations
        self._update_automation_listener()

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

        if self._unsub_automation_listener:
            self._unsub_automation_listener()
            self._unsub_automation_listener = None

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
            # OPTIMIZATION: One-Pass Data Retrieval
            all_items = await self.hub.async_get_all_items()
            parsed_service_list = all_items["services"]
            parsed_entity_list = all_items["entities"]

            ctx = self._build_filter_context()

            # Logic Fork: Full vs Partial
            if self._force_full_rescan:
                _LOGGER.debug("Coordinator: performing FULL status check.")
                self._missing_entities_cache = renew_missing_items_list(
                    self.hass, parsed_entity_list, ctx, item_type="entity"
                )
                self._missing_actions_cache = renew_missing_items_list(
                    self.hass, parsed_service_list, ctx, item_type="action"
                )
                self._force_full_rescan = False
                self._dirty_entities.clear()

            elif self._dirty_entities:
                _LOGGER.debug(f"Coordinator: performing PARTIAL status check for {len(self._dirty_entities)} entities.")
                updates = self._dirty_entities.copy()
                self._dirty_entities.clear()

                for entity_id in updates:
                    if entity_id in parsed_entity_list:
                        # Re-check this entity
                        result = check_single_entity_status(
                            self.hass, entity_id, parsed_entity_list[entity_id], ctx, item_type="entity"
                        )
                        if result is not None:
                            # It is missing/invalid
                            self._missing_entities_cache[entity_id] = result
                        else:
                            # It is valid/available -> remove from missing cache
                            self._missing_entities_cache.pop(entity_id, None)

            # Construct result from cache
            entities_missing = self._missing_entities_cache
            services_missing = self._missing_actions_cache

            # build entity attributes map for missing_entities sensor
            entity_attrs = []
            for entity in entities_missing:
                reg_entry = ctx.entity_registry.async_get(entity)
                state, name = get_entity_state(
                    self.hass, entity, friendly_names=True, registry_entry=reg_entry
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
            service_attrs = [
                {
                    "id": service,
                    "occurrences": fill(parsed_service_list[service]["locations"], 0),
                }
                for service in services_missing
            ]

            new_data = {
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
            self.data = new_data
            _LOGGER.debug(
                f"Coordinator: sensors refreshed. Actions: {new_data[COORD_DATA_MISSING_ACTIONS]}, "
                f"Entities: {new_data[COORD_DATA_MISSING_ENTITIES]}"
            )
            return new_data

        except Exception as err:
            _LOGGER.exception(f"Error reading watchman data: {err}")
            return self.data
