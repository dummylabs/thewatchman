"""The Watchman integration."""

import os
from datetime import timedelta
from dataclasses import dataclass
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_utc_time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_SERVICE_REGISTERED,
    EVENT_SERVICE_REMOVED,
    EVENT_STATE_CHANGED,
    EVENT_CALL_SERVICE,
    SERVICE_RELOAD,
)
from homeassistant.components.homeassistant import (
    SERVICE_RELOAD_CORE_CONFIG,
    SERVICE_RELOAD_ALL,
)

from .services import WatchmanServicesSetup
from .coordinator import WatchmanCoordinator
from .utils.logger import _LOGGER
from .utils.utils import get_config
from .hub import WatchmanHub


from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_OPTIONS,
    DEFAULT_REPORT_FILENAME,
    DB_FILENAME,
    LOCK_FILENAME,
    DOMAIN,
    DOMAIN_DATA,
    CONF_IGNORED_FILES,
    CONF_HEADER,
    CONF_REPORT_PATH,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_LABELS,
    CONF_IGNORED_STATES,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONF_FRIENDLY_NAMES,
    CONF_SECTION_APPEARANCE_LOCATION,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    REPORT_SERVICE_NAME,
    STATE_WAITING_HA,
    STATE_SAFE_MODE,
    TRACKED_EVENT_DOMAINS,
    MONITORED_STATES,
    PLATFORMS,
    VERSION
)


type WMConfigEntry = ConfigEntry[WMData]


@dataclass
class WMData:
    """Watchman runtime data."""

    coordinator: WatchmanCoordinator
    hub: WatchmanHub

async def async_setup_entry(hass: HomeAssistant, config_entry: WMConfigEntry):
    """Set up this integration using UI."""

    async def async_on_home_assistant_started(event):  # pylint: disable=unused-argument
        """
        update watchman sensors anf start listening to HA events when Home Assistant started
        """

        async def async_delayed_refresh_states(timedate):  # pylint: disable=unused-argument
            """Refresh sensors state."""
            hass.data.get(DOMAIN_DATA)
            config_entry.runtime_data.coordinator.request_parser_rescan("HA restart")
            await config_entry.runtime_data.coordinator.async_request_refresh()

        async def async_schedule_refresh_states(delay):
            """Schedule delayed refresh of the sensors state."""
            now = dt_util.utcnow()
            next_interval = now + timedelta(seconds=delay)
            async_track_point_in_utc_time(hass, async_delayed_refresh_states, next_interval)

        startup_delay = get_config(hass, CONF_STARTUP_DELAY, 0)

        if not config_entry.runtime_data.coordinator.safe_mode:
            await async_schedule_refresh_states(startup_delay)
            await add_event_handlers(hass, config_entry)
            _LOGGER.debug("Subscribed to HA events to keep actual state of sensors.")
        else:
            _LOGGER.info("Watchman is in Safe Mode. Skipping event subscriptions and initial scan.")

    db_path = hass.config.path(".storage", DB_FILENAME)
    hub = WatchmanHub(hass, db_path)
    coordinator = WatchmanCoordinator(hass, _LOGGER, name=config_entry.title, hub=hub)
    # parsing shouldn't occur if HA is not running yet
    config_entry.runtime_data = WMData(coordinator, hub)

    # Check for previous crash
    lock_path = hass.config.path(".storage", LOCK_FILENAME)
    if await hass.async_add_executor_job(os.path.exists, lock_path):
        _LOGGER.error("Previous crash detected (lock file found). Watchman is starting in Safe Mode.")
        coordinator.update_status(STATE_SAFE_MODE)

    hass.data[DOMAIN_DATA] = {"config_entry_id": config_entry.entry_id}
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    WatchmanServicesSetup(hass, config_entry)

    coordinator.request_parser_rescan(reason="initial_setup")

    if hass.is_running:
        # HA is already up and running (e.g. integration was installed)
        # don't need to wait until it is booted
        await async_on_home_assistant_started(None)
    else:
        # integration started during HA startup, wait until it is fully loaded
        if not coordinator.safe_mode:
            config_entry.runtime_data.coordinator.update_status(STATE_WAITING_HA)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, async_on_home_assistant_started)

    config_entry.async_create_background_task(
        hass, coordinator._async_update_data(), "watchman_initial_parse"
    )

    _LOGGER.info("Watchman started [%s]", VERSION)
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Reload integration when options changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry):  # pylint: disable=unused-argument
    """Handle integration unload."""

    if hass.services.has_service(DOMAIN, REPORT_SERVICE_NAME):
        hass.services.async_remove(DOMAIN, REPORT_SERVICE_NAME)

    unload_ok = await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    )

    if DOMAIN_DATA in hass.data:
        hass.data.pop(DOMAIN_DATA)
    if DOMAIN in hass.data:
        hass.data.pop(DOMAIN)

    if unload_ok:
        _LOGGER.info("Watchman integration successfully unloaded.")
    else:
        _LOGGER.error("Having trouble unloading watchman integration")

    return unload_ok




async def add_event_handlers(hass: HomeAssistant, entry: WMConfigEntry):
    """Add event handlers."""
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
                entry.runtime_data.coordinator.request_parser_rescan(f"{domain}.{service} call")
                await entry.runtime_data.coordinator.async_request_refresh()

        elif event_type in [EVENT_AUTOMATION_RELOADED, EVENT_SCENE_RELOADED]:
            entry.runtime_data.coordinator.request_parser_rescan(f"event: {event_type}")
            await entry.runtime_data.coordinator.async_request_refresh()

    async def async_on_service_changed(event):
        service = f"{event.data['domain']}.{event.data['service']}"
        coordinator = entry.runtime_data.coordinator
        parsed_services = await coordinator.async_get_parsed_services()
        if service in parsed_services:
            _LOGGER.debug("Monitored service changed: %s", service)
            await coordinator.async_request_refresh()

    async def async_on_state_changed(event):
        """Refresh monitored entities on state change."""

        def state_or_missing(state_id):
            """Return missing state if entity not found."""
            return "missing" if not event.data[state_id] else event.data[state_id].state

        coordinator = entry.runtime_data.coordinator
        parsed_entities = await coordinator.async_get_parsed_entities()
        if event.data["entity_id"] in parsed_entities:
            ignored_states: list[str] = get_config(hass, CONF_IGNORED_STATES, [])
            old_state = state_or_missing("old_state")
            new_state = state_or_missing("new_state")
            checked_states = set(MONITORED_STATES) - set(ignored_states)
            if new_state in checked_states or old_state in checked_states:
                _LOGGER.debug("Monitored entity changed: %s", event.data["entity_id"])
                await coordinator.async_request_refresh()

    # event handlers will be automatically cancelled by HA on entry unload
    entry.async_on_unload(
        # track service calls which update HA configuration
        hass.bus.async_listen(EVENT_CALL_SERVICE, async_on_configuration_changed)
    )
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_AUTOMATION_RELOADED, async_on_configuration_changed)
    )
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_SCENE_RELOADED, async_on_configuration_changed)
    )
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_SERVICE_REGISTERED, async_on_service_changed)
    )
    entry.async_on_unload(hass.bus.async_listen(EVENT_SERVICE_REMOVED, async_on_service_changed))
    entry.async_on_unload(hass.bus.async_listen(EVENT_STATE_CHANGED, async_on_state_changed))


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate ConfigEntry persistent data to a new version."""
    if config_entry.version > CONFIG_ENTRY_VERSION:
        # the user has downgraded from a future version
        _LOGGER.error(
            "Unable to migratre Watchman entry from version %d.%d. If integration version was downgraded, use backup to restore its data.",
            config_entry.version,
            config_entry.minor_version,
        )
        return False
    if config_entry.version == 1:
        # migrate from ConfigEntry.options to ConfigEntry.data
        _LOGGER.info(
            "Start Watchman configuration entry migration to version 2. Source data: %s",
            config_entry.options,
        )
        data = DEFAULT_OPTIONS

        data[CONF_IGNORED_STATES] = config_entry.options.get(CONF_IGNORED_STATES, [])

        if CONF_IGNORED_ITEMS in config_entry.options:
            data[CONF_IGNORED_ITEMS] = ",".join(
                str(x) for x in config_entry.options[CONF_IGNORED_ITEMS]
            )

        if CONF_IGNORED_FILES in config_entry.options:
            data[CONF_IGNORED_FILES] = ",".join(
                str(x) for x in config_entry.options[CONF_IGNORED_FILES]
            )

        if CONF_FRIENDLY_NAMES in config_entry.options:
            data[CONF_SECTION_APPEARANCE_LOCATION][CONF_FRIENDLY_NAMES] = (
                config_entry.options[CONF_FRIENDLY_NAMES]
            )

        data[CONF_SECTION_APPEARANCE_LOCATION][CONF_REPORT_PATH] = (
            config_entry.options.get(
                CONF_REPORT_PATH, hass.config.path(DEFAULT_REPORT_FILENAME)
            )
        )

        if CONF_HEADER in config_entry.options:
            data[CONF_SECTION_APPEARANCE_LOCATION][CONF_HEADER] = config_entry.options[
                CONF_HEADER
            ]

        if CONF_COLUMNS_WIDTH in config_entry.options:
            data[CONF_SECTION_APPEARANCE_LOCATION][CONF_COLUMNS_WIDTH] = ",".join(
                str(x) for x in config_entry.options[CONF_COLUMNS_WIDTH]
            )

        if CONF_STARTUP_DELAY in config_entry.options:
            data[CONF_STARTUP_DELAY] = config_entry.options[CONF_STARTUP_DELAY]

        _LOGGER.info(
            "Successfully migrated Watchman configuration entry from version %d.%d. to version %d.%d",
            config_entry.version,
            config_entry.minor_version,
            CONFIG_ENTRY_VERSION,
            CONFIG_ENTRY_MINOR_VERSION,
        )
        hass.config_entries.async_update_entry(
            config_entry,
            data=data,
            options={},
            minor_version=CONFIG_ENTRY_MINOR_VERSION,
            version=CONFIG_ENTRY_VERSION,
        )
        return True
    if config_entry.version == CONFIG_ENTRY_VERSION and (
        config_entry.minor_version < CONFIG_ENTRY_MINOR_VERSION
    ):
        _LOGGER.info(
            "Start Watchman configuration entry migration to minor version %d. Source data: %s",
            CONFIG_ENTRY_MINOR_VERSION,
            config_entry.data,
        )
        data = {**config_entry.data}
        if CONF_IGNORED_LABELS not in data:
            data[CONF_IGNORED_LABELS] = DEFAULT_OPTIONS[CONF_IGNORED_LABELS]

        hass.config_entries.async_update_entry(
            config_entry,
            data=data,
            options={**config_entry.options},
            minor_version=CONFIG_ENTRY_MINOR_VERSION,
            version=CONFIG_ENTRY_VERSION,
        )
        _LOGGER.info(
            "Successfully migrated Watchman configuration entry to version %d.%d",
            config_entry.version,
            CONFIG_ENTRY_MINOR_VERSION,
        )
        return True
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    db_path = hass.config.path(".storage", DB_FILENAME)
    lock_path = hass.config.path(".storage", LOCK_FILENAME)

    def remove_files():
        if os.path.exists(db_path):
            os.remove(db_path)
        if os.path.exists(lock_path):
            os.remove(lock_path)

    await hass.async_add_executor_job(remove_files)
    _LOGGER.info("Watchman database file removed: %s", db_path)
