"""The Watchman integration."""

from datetime import timedelta
import asyncio
from dataclasses import dataclass
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_utc_time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
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

from custom_components.watchman.services import WatchmanServicesSetup

from .coordinator import WatchmanCoordinator
from .utils.logger import _LOGGER

from .utils.utils import (
    get_entry,
    get_config,
)


from .const import (
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_OPTIONS,
    DEFAULT_REPORT_FILENAME,
    DOMAIN,
    DOMAIN_DATA,
    CONF_IGNORED_FILES,
    CONF_HEADER,
    CONF_REPORT_PATH,
    CONF_IGNORED_ITEMS,
    CONF_INCLUDED_FOLDERS,
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_STATES,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONF_FRIENDLY_NAMES,
    CONF_SECTION_APPEARANCE_LOCATION,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    HASS_DATA_CANCEL_HANDLERS,
    HASS_DATA_COORDINATOR,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    REPORT_SERVICE_NAME,
    TRACKED_EVENT_DOMAINS,
    MONITORED_STATES,
    PLATFORMS,
    VERSION,
)


type WMConfigEntry = ConfigEntry[WMData]
parser_lock = asyncio.Lock()


@dataclass
class WMData:
    """Watchman runtime data."""

    coordinator: WatchmanCoordinator
    force_parsing: bool
    parse_reason: str | None


async def async_setup_entry(hass: HomeAssistant, config_entry: WMConfigEntry):
    """Set up this integration using UI."""
    _LOGGER.debug(
        f"::async_setup_entry:: Integration setup in progress. Home assistant path: {hass.config.path("")}"
    )

    coordinator = WatchmanCoordinator(hass, _LOGGER, name=config_entry.title)
    # parsing shouldn't be done if HA is not running yet
    config_entry.runtime_data = WMData(
        coordinator, force_parsing=False, parse_reason=None
    )

    hass.data[DOMAIN_DATA] = {"config_entry_id": config_entry.entry_id}
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator
    hass.data[DOMAIN][HASS_DATA_COORDINATOR] = coordinator
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    WatchmanServicesSetup(hass, config_entry)
    await add_event_handlers(hass)

    await coordinator.async_config_entry_first_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    if not hass.is_running:
        # first run, home assistant is loading
        # parse_config will be scheduled once HA is fully loaded
        _LOGGER.info("Watchman started [%s]", VERSION)
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Reload integration when options changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry):  # pylint: disable=unused-argument
    """Handle integration unload."""
    for cancel_handle in hass.data[DOMAIN].get(HASS_DATA_CANCEL_HANDLERS, []):
        if cancel_handle:
            cancel_handle()

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


async def add_event_handlers(hass: HomeAssistant):
    """Add event handlers."""

    async def async_schedule_refresh_states(hass, delay):
        """Schedule delayed refresh of the sensors state."""
        now = dt_util.utcnow()
        next_interval = now + timedelta(seconds=delay)
        async_track_point_in_utc_time(hass, async_delayed_refresh_states, next_interval)

    async def async_delayed_refresh_states(timedate):  # pylint: disable=unused-argument
        """Refresh sensors state."""
        hass.data.get(DOMAIN_DATA)
        entry = get_entry(hass)
        entry.runtime_data.force_parsing = True
        entry.runtime_data.parse_reason = "HA restart"
        await entry.runtime_data.coordinator.async_refresh()

    async def async_on_home_assistant_started(event):  # pylint: disable=unused-argument
        startup_delay = get_config(hass, CONF_STARTUP_DELAY, 0)
        await async_schedule_refresh_states(hass, startup_delay)

    async def async_on_configuration_changed(event):
        entry = get_entry(hass)
        event_type = event.event_type
        if event_type == EVENT_CALL_SERVICE:
            domain = event.data.get("domain", None)
            service = event.data.get("service", None)
            if domain in TRACKED_EVENT_DOMAINS and service in [
                SERVICE_RELOAD_CORE_CONFIG,
                SERVICE_RELOAD,
                SERVICE_RELOAD_ALL,
            ]:
                entry.runtime_data.force_parsing = True
                entry.runtime_data.parse_reason = f"{domain}.{service} call"
                await entry.runtime_data.coordinator.async_refresh()

        elif event_type in [EVENT_AUTOMATION_RELOADED, EVENT_SCENE_RELOADED]:
            entry.runtime_data.force_parsing = True
            entry.runtime_data.parse_reason = f"event: {event_type}"
            await entry.runtime_data.coordinator.async_refresh()

    async def async_on_service_changed(event):
        service = f"{event.data['domain']}.{event.data['service']}"
        if service in hass.data[DOMAIN].get(HASS_DATA_PARSED_SERVICE_LIST, []):
            _LOGGER.debug("Monitored service changed: %s", service)
            coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
            await coordinator.async_refresh()

    async def async_on_state_changed(event):
        """Refresh monitored entities on state change."""

        def state_or_missing(state_id):
            """Return missing state if entity not found."""
            return "missing" if not event.data[state_id] else event.data[state_id].state

        if event.data["entity_id"] in hass.data[DOMAIN].get(
            HASS_DATA_PARSED_ENTITY_LIST, []
        ):
            ignored_states: list[str] = get_config(hass, CONF_IGNORED_STATES, [])
            old_state = state_or_missing("old_state")
            new_state = state_or_missing("new_state")
            checked_states = set(MONITORED_STATES) - set(ignored_states)
            if new_state in checked_states or old_state in checked_states:
                _LOGGER.debug("Monitored entity changed: %s", event.data["entity_id"])
                coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
                await coordinator.async_refresh()

    # hass is not started yet, schedule config parsing once it loaded
    if not hass.is_running:
        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED, async_on_home_assistant_started
        )

    hdlr = []
    hdlr.append(
        # track service calls which update HA configuration
        hass.bus.async_listen(EVENT_CALL_SERVICE, async_on_configuration_changed)
    )
    hdlr.append(
        hass.bus.async_listen(EVENT_AUTOMATION_RELOADED, async_on_configuration_changed)
    )
    hdlr.append(
        hass.bus.async_listen(EVENT_SCENE_RELOADED, async_on_configuration_changed)
    )
    hdlr.append(
        hass.bus.async_listen(EVENT_SERVICE_REGISTERED, async_on_service_changed)
    )
    hdlr.append(hass.bus.async_listen(EVENT_SERVICE_REMOVED, async_on_service_changed))
    hdlr.append(hass.bus.async_listen(EVENT_STATE_CHANGED, async_on_state_changed))
    hass.data[DOMAIN][HASS_DATA_CANCEL_HANDLERS] = hdlr


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate ConfigEntry persistent data to a new version."""
    if config_entry.version > 1:
        # This means the user has downgraded from a future version
        _LOGGER.error(
            "Unable to migratre Watchman entry from version %d.%d. If integration version was downgraded, use backup to restore its data.",
            config_entry.version,
            config_entry.minor_version,
        )
        return False
    else:
        # migrate from ConfigEntry.options to ConfigEntry.data
        _LOGGER.info(
            "Start Watchman configuration entry migration to version 2. Source data: %s",
            config_entry.options,
        )
        data = DEFAULT_OPTIONS

        data[CONF_INCLUDED_FOLDERS] = (
            hass.config.path()
            if CONF_INCLUDED_FOLDERS not in config_entry.options
            else ",".join(str(x) for x in config_entry.options[CONF_INCLUDED_FOLDERS])
        )

        data[CONF_IGNORED_STATES] = config_entry.options.get(CONF_IGNORED_STATES, [])
        data[CONF_CHECK_LOVELACE] = config_entry.options.get(CONF_CHECK_LOVELACE, False)

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
