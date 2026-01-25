import asyncio
from typing import Any
from homeassistant.util import dt as dt_util
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers import entity_registry as er

from .utils.report import fill
from .const import (
    COORD_DATA_ENTITY_ATTRS,
    COORD_DATA_LAST_UPDATE,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_MISSING_SERVICES,
    COORD_DATA_SERVICE_ATTRS,
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_EXCLUDE_DISABLED_AUTOMATION,
)
from .utils.utils import (
    get_entity_state,
    get_entry,
    get_config,
    get_included_folders,
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
        self.data = {
            COORD_DATA_MISSING_ENTITIES: 0,
            COORD_DATA_MISSING_SERVICES: 0,
            COORD_DATA_LAST_UPDATE: dt_util.now(),
            COORD_DATA_SERVICE_ATTRS: "",
            COORD_DATA_ENTITY_ATTRS: "",
        }

    async def async_get_parsed_entities(self):
        """Return a dictionary of parsed entities and their locations."""
        return await self.hub.async_get_parsed_entities()

    async def async_get_parsed_services(self):
        """Return a dictionary of parsed services and their locations."""
        return await self.hub.async_get_parsed_services()

    async def _async_setup(self) -> None:
        """Do initialization logic."""
        _LOGGER.debug("::coordinator._async_setup::")
        if self.hass.is_running:
            # integration reloaded or options changed via UI
            _LOGGER.debug(f"{INDENT} hass up and running, try to parse config")
            await self.async_parse_config(reason="changes in watchman configuration")
        else:
            _LOGGER.debug(f"{INDENT} hass is still loading, do nothing yet")
            # first run, home assistant still loading
            # parse_config will be scheduled once HA is fully loaded

    async def async_parse_config(self, reason=None):
        """Parse home assistant configuration files."""

        included_folders = get_included_folders(self.hass)
        ignored_files = get_config(self.hass, CONF_IGNORED_FILES, None)
        ignored_items = get_config(self.hass, CONF_IGNORED_ITEMS, [])

        _LOGGER.debug(
            f"::parse_config:: called due to {reason} IGNORED_FILES={ignored_files}"
        )

        await self.hub.async_parse(included_folders, ignored_files, ignored_items)

        info = await self.hub.async_get_last_parse_info()

        # We don't log parse duration here anymore as it is handled by the parser/hub
        _LOGGER.debug(f"{INDENT}Parsing finished in: {info.get('duration', 0.0)}")

    async def async_get_last_parse_duration(self):
        """Return duration of the last parsing."""
        info = await self.hub.async_get_last_parse_info()
        return info.get("duration", 0.0)

    def update_ignored_labels(self, labels: list[str]) -> None:
        """Update ignored labels list and refresh data."""
        self.ignored_labels = set(labels)
        self.hass.async_create_task(self.async_refresh())

    async def _async_update_data(self) -> dict[str, Any]:
        """Update Watchman sensors.

        Update will trigger parsing of configuration files if entry.runtime_data.force_parsing is set
        """

        if not parser_lock.locked():
            async with parser_lock:
                entry = get_entry(self.hass)
                _LOGGER.debug(
                    f"::coordinator._async_update_data:: force_parsing {entry.runtime_data.force_parsing}, parse_reason: {entry.runtime_data.parse_reason}"
                )

                if self.hass.is_running:
                    if entry.runtime_data.force_parsing:
                        await self.async_parse_config(
                            reason=entry.runtime_data.parse_reason
                        )
                        entry.runtime_data.force_parsing = False

                    start_time = time.time()

                    parsed_service_list = await self.async_get_parsed_services()
                    parsed_entity_list = await self.async_get_parsed_entities()

                    exclude_disabled_automations = get_config(
                        self.hass, CONF_EXCLUDE_DISABLED_AUTOMATION, False
                    )

                    services_missing = renew_missing_items_list(
                        self.hass, parsed_service_list, exclude_disabled_automations, self.ignored_labels, "action"
                    )
                    entities_missing = renew_missing_items_list(
                        self.hass, parsed_entity_list, exclude_disabled_automations, self.ignored_labels, "entity"
                    )

                    self.last_check_duration = (
                        time.time() - start_time
                    )

                    # build entity attributes map for missing_entities sensor
                    # FIXME: this may lead to enormous size of WM sensor attributes data and should be eventually removed
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
                    # FIXME: this may lead to enormous size of WM sensor attributes data and should be eventually removed
                    service_attrs = []
                    for service in services_missing:
                        service_attrs.append(
                            {
                                "id": service,
                                "occurrences": fill(parsed_service_list[service]["locations"], 0),
                            }
                        )

                    self.data = {
                        COORD_DATA_MISSING_ENTITIES: len(entities_missing),
                        COORD_DATA_MISSING_SERVICES: len(services_missing),
                        COORD_DATA_LAST_UPDATE: dt_util.now(),
                        COORD_DATA_SERVICE_ATTRS: service_attrs,
                        COORD_DATA_ENTITY_ATTRS: entity_attrs,
                    }
                    _LOGGER.debug(
                        f"Watchman sensors updated, actions: {self.data[COORD_DATA_MISSING_SERVICES]}, entities: {self.data[COORD_DATA_MISSING_ENTITIES]}"
                    )

                    return self.data
        return {}
