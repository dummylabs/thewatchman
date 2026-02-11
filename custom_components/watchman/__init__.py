"""The Watchman integration."""

from dataclasses import dataclass
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
)
from homeassistant.core import Event, HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    CONF_HEADER,
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_LOG_OBFUSCATE,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_STARTUP_DELAY,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    CURRENT_DB_SCHEMA_VERSION,
    DEFAULT_DELAY,
    DEFAULT_OPTIONS,
    DEFAULT_REPORT_FILENAME,
    DOMAIN,
    DOMAIN_DATA,
    LOCK_FILENAME,
    PLATFORMS,
    REPORT_SERVICE_NAME,
    STATE_SAFE_MODE,
    STATE_WAITING_HA,
    STORAGE_VERSION,
)
from .coordinator import WatchmanCoordinator
from .hub import WatchmanHub
from .services import WatchmanServicesSetup
from .utils.logger import _LOGGER
from .utils.utils import get_config, set_obfuscation_config

type WMConfigEntry = ConfigEntry[WMData]


@dataclass
class WMData:
    """Watchman runtime data."""

    coordinator: WatchmanCoordinator
    hub: WatchmanHub

async def async_setup_entry(hass: HomeAssistant, config_entry: WMConfigEntry) -> bool:
    """Set up this integration using UI."""
    from .const import DB_FILENAME, LEGACY_DB_FILENAME

    legacy_db_path = Path(hass.config.path(".storage", LEGACY_DB_FILENAME))
    db_path = Path(hass.config.path(".storage", DB_FILENAME))

    # One-time migration: rename watchman.db to watchman_v2.db
    if not db_path.exists() and legacy_db_path.exists():
        _LOGGER.info(
            "Migrating legacy database %s to %s", LEGACY_DB_FILENAME, DB_FILENAME
        )
        legacy_db_path.rename(db_path)

    integration = await async_get_integration(hass, DOMAIN)

    # Configure obfuscation
    set_obfuscation_config(config_entry.data.get(CONF_LOG_OBFUSCATE, True))

    hub = WatchmanHub(hass, str(db_path))
    coordinator = WatchmanCoordinator(
        hass,
        _LOGGER,
        config_entry=config_entry,
        hub=hub,
        version=str(integration.version),
    )
    await coordinator.async_load_stats()
    config_entry.runtime_data = WMData(coordinator, hub)

    async def async_on_home_assistant_started(event: Event | None) -> None:  # pylint: disable=unused-argument
        """Update watchman sensors and start listening to HA events when Home Assistant started."""
        # Guard Clause: Check if integration is still loaded
        if DOMAIN_DATA not in hass.data or hass.data[DOMAIN_DATA].get("config_entry_id") != config_entry.entry_id:
            _LOGGER.debug("Skipping async_on_home_assistant_started: Integration unloaded.")
            return

        # prime the coordinator with cached data immediately to minimize startup delay
        try:
            _LOGGER.debug("HA is ready. Prime coordinator with cached data.")
            all_items = await hub.async_get_all_items()
            parsed_entities = all_items["entities"]
            parsed_services = all_items["services"]
            initial_data = await coordinator.async_process_parsed_data(
                parsed_entities, parsed_services
            )
            coordinator.async_set_updated_data(initial_data)
        except Exception as e:
            _LOGGER.error(f"Failed to prime coordinator with cached data: {e}")

        if coordinator.safe_mode:
            _LOGGER.info(
                "Watchman is in Safe Mode. Skipping event subscriptions and initial scan."
            )
            return

        coordinator.subscribe_to_events(config_entry)
        _LOGGER.debug("Subscribed to HA events.")

        if event:
            # integration started during HA startup
            # use startup delay to schedule initial parsing (usually longer)
            startup_delay = get_config(hass, CONF_STARTUP_DELAY, 0)
        else:
            # intergation started after installation from Devices&Services
            # use short delay to schedule initial parsing (usually longer)
            startup_delay = DEFAULT_DELAY

        _LOGGER.debug(
            f"Executing mandatory startup scan in: {startup_delay}s."
        )

        coordinator.request_parser_rescan(reason="integration reload", delay=startup_delay)

    _LOGGER.info(
        "Watchman integration started [%s], DB: %s, Stats: %s",
        coordinator.version,
        CURRENT_DB_SCHEMA_VERSION,
        STORAGE_VERSION,
    )

    # Check for previous crash
    lock_path = Path(hass.config.path(".storage", LOCK_FILENAME))

    def check_crash() -> bool:
        if lock_path.exists():
            _LOGGER.error(
                "Previous crash detected (lock file found). Watchman is starting in Safe Mode."
            )
            lock_path.unlink(missing_ok=True)
            return True
        return False

    if await hass.async_add_executor_job(check_crash):
        coordinator.update_status(STATE_SAFE_MODE)

    hass.data[DOMAIN_DATA] = {"config_entry_id": config_entry.entry_id}
    hass.data.setdefault(DOMAIN, {})[config_entry.entry_id] = coordinator
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

        # do not use async_listen_once here to make unsubscribe callback valid even after the event fires,
        # preventing the "unknown job listener" warning on entry unload.
        unsub = hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, async_on_home_assistant_started)
        config_entry.async_on_unload(unsub)

    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload integration when options changed."""
    set_obfuscation_config(entry.data.get(CONF_LOG_OBFUSCATE, True))
    if hasattr(entry, "runtime_data") and entry.runtime_data:
        _LOGGER.debug("Invalidating FilterContext cache due to update Watchman config_entry data")
        entry.runtime_data.coordinator.invalidate_filter_context()
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry: WMConfigEntry) -> bool:  # pylint: disable=unused-argument
    """Handle integration unload."""
    if hasattr(config_entry, "runtime_data") and config_entry.runtime_data:
        await config_entry.runtime_data.coordinator.async_shutdown()

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


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate ConfigEntry persistent data to a new version."""
    if config_entry.version > CONFIG_ENTRY_VERSION:
        # the user has downgraded from a future version
        _LOGGER.error(
            "Unable to migrate Watchman entry from version %d.%d. If integration version was downgraded, either reinstall or use backup to restore its data.",
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

        if current_minor < 3:
            _LOGGER.info("Migrating Watchman entry to minor version 3")
            # Default to True (enabled)
            data[CONF_LOG_OBFUSCATE] = DEFAULT_OPTIONS.get(CONF_LOG_OBFUSCATE, True)
            current_minor = 3

        if current_minor < 4:
            _LOGGER.info("Migrating Watchman entry to minor version 4")
            # Do not initialize ignored_labels here to allow text entity to restore state lazily
            current_minor = 4

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
    from .const import DB_FILENAME, LEGACY_DB_FILENAME, LOCK_FILENAME, STORAGE_KEY

    db_path = hass.config.path(".storage", DB_FILENAME)
    journal_path = f"{db_path}-journal"
    lock_path = hass.config.path(".storage", LOCK_FILENAME)
    stats_path = hass.config.path(".storage", STORAGE_KEY)

    # Legacy files
    legacy_db_path = hass.config.path(".storage", LEGACY_DB_FILENAME)
    legacy_wal_path = f"{legacy_db_path}-wal"
    legacy_shm_path = f"{legacy_db_path}-shm"

    def remove_files() -> None:
        Path(db_path).unlink(missing_ok=True)
        Path(journal_path).unlink(missing_ok=True)
        Path(lock_path).unlink(missing_ok=True)
        Path(stats_path).unlink(missing_ok=True)
        # Cleanup legacy
        Path(legacy_db_path).unlink(missing_ok=True)
        Path(legacy_wal_path).unlink(missing_ok=True)
        Path(legacy_shm_path).unlink(missing_ok=True)

    await hass.async_add_executor_job(remove_files)
    _LOGGER.info("Watchman database file removed: %s", db_path)
    _LOGGER.info("Watchman journal file removed: %s", journal_path)
    _LOGGER.info("Watchman stats file removed: %s", stats_path)
