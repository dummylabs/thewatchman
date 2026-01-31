"""The Watchman integration."""

import os
from dataclasses import dataclass
from homeassistant.util import dt as dt_util

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
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
    DEFAULT_DELAY,
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
    REPORT_SERVICE_NAME,
    STATE_WAITING_HA,
    STATE_SAFE_MODE,
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
        Update watchman sensors and start listening to HA events when Home Assistant started.
        """
        coordinator = config_entry.runtime_data.coordinator

        if coordinator.safe_mode:
            _LOGGER.info("Watchman is in Safe Mode. Skipping event subscriptions and initial scan.")
            return

        coordinator.subscribe_to_events(config_entry)
        _LOGGER.debug("Subscribed to HA events.")

        if event:
            startup_delay = get_config(hass, CONF_STARTUP_DELAY, 0)
            _LOGGER.debug(f"Watchman started during HA startup). Initial parse in: {startup_delay}s.")
        else:
            startup_delay = DEFAULT_DELAY
            _LOGGER.debug(f"Watchman installed (HA running). Initial parse in: {startup_delay}s.")

        coordinator.request_parser_rescan(reason="startup", delay=startup_delay)

    _LOGGER.info("Watchman integration started [%s]", VERSION)
    db_path = hass.config.path(".storage", DB_FILENAME)
    hub = WatchmanHub(hass, db_path)
    await hub.async_init()
    coordinator = WatchmanCoordinator(hass, _LOGGER, name=config_entry.title, hub=hub)
    config_entry.runtime_data = WMData(coordinator, hub)

    # Check for previous crash
    lock_path = hass.config.path(".storage", LOCK_FILENAME)
    if await hass.async_add_executor_job(os.path.exists, lock_path):
        _LOGGER.error("Previous crash detected (lock file found). Watchman is starting in Safe Mode.")
        coordinator.update_status(STATE_SAFE_MODE)
        # We must clean up the lock file so next restart isn't safe mode unless it crashes again
        await hass.async_add_executor_job(os.remove, lock_path)

    hass.data[DOMAIN_DATA] = {"config_entry_id": config_entry.entry_id}
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator


    # prime the coordinator with cached data immediately to minimize startup delay
    try:
        _LOGGER.debug("Prime coordinator with cached data.")
        parsed_entities = await hub.async_get_parsed_entities()
        parsed_services = await hub.async_get_parsed_services()
        initial_data = await coordinator.async_process_parsed_data(parsed_entities, parsed_services)
        coordinator.async_set_updated_data(initial_data)
    except Exception as e:
        _LOGGER.error(f"Failed to prime coordinator with cached data: {e}")

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    config_entry.async_on_unload(config_entry.add_update_listener(update_listener))
    WatchmanServicesSetup(hass, config_entry)

    if hass.is_running:
        # HA is already up and running, don't need to wait until it is booted
        _LOGGER.debug("Home assistant is up, proceed with async_on_home_assistant_started")
        await async_on_home_assistant_started(None)
    else:
        # integration started during HA startup, wait until it is fully loaded
        _LOGGER.debug("Waiting for Home Assistant to be up and running...")
        if not coordinator.safe_mode:
            config_entry.runtime_data.coordinator.update_status(STATE_WAITING_HA)
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, async_on_home_assistant_started)

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


async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate ConfigEntry persistent data to a new version."""
    if config_entry.version > CONFIG_ENTRY_VERSION:
        # the user has downgraded from a future version
        _LOGGER.error(
            "Unable to migratre Watchman entry from version %d.%d. If integration version was downgraded, either reinstall or use backup to restore its data.",
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

    if config_entry.version == CONFIG_ENTRY_VERSION:
        data = {**config_entry.data}
        current_minor = config_entry.minor_version

        # Sequential migration logic for minor versions
        if current_minor < 2:
            _LOGGER.info("Migrating Watchman entry to minor version 2")

            if CONF_IGNORED_LABELS not in data:
                data[CONF_IGNORED_LABELS] = DEFAULT_OPTIONS[CONF_IGNORED_LABELS]

            # Enforce minimum startup delay
            current_delay = data.get(CONF_STARTUP_DELAY, 0)
            min_delay = DEFAULT_OPTIONS[CONF_STARTUP_DELAY]
            if current_delay < min_delay:
                _LOGGER.info(
                    "Enforcing minimum startup delay of %ss (was %ss)",
                    min_delay,
                    current_delay,
                )
                data[CONF_STARTUP_DELAY] = min_delay

            current_minor = 2

        if current_minor != config_entry.minor_version:
            hass.config_entries.async_update_entry(
                config_entry,
                data=data,
                minor_version=current_minor,
                version=CONFIG_ENTRY_VERSION,
            )
            _LOGGER.info(
                "Successfully migrated Watchman configuration entry to version %d.%d",
                config_entry.version,
                current_minor,
            )

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
