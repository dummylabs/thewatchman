"""https://github.com/dummylabs/thewatchman§"""

from datetime import timedelta
import time
import asyncio
from dataclasses import dataclass
from typing import Any
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.components import persistent_notification
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.exceptions import HomeAssistantError
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

from .coordinator import WatchmanCoordinator
from .utils.logger import _LOGGER, INDENT

from .utils.utils import (
    async_get_report_path,
    is_action,
    report,
    parse,
    table_renderer,
    text_renderer,
    get_config,
)

from .const import (
    CONF_ACTION_NAME,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_OPTIONS,
    DOMAIN,
    DOMAIN_DATA,
    DEFAULT_HEADER,
    CONF_IGNORED_FILES,
    CONF_HEADER,
    CONF_REPORT_PATH,
    CONF_IGNORED_ITEMS,
    CONF_SERVICE_NAME,
    CONF_SERVICE_DATA,
    CONF_INCLUDED_FOLDERS,
    CONF_CHECK_LOVELACE,
    CONF_IGNORED_STATES,
    CONF_CHUNK_SIZE,
    CONF_CREATE_FILE,
    CONF_SEND_NOTIFICATION,
    CONF_PARSE_CONFIG,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONF_FRIENDLY_NAMES,
    CONF_ALLOWED_SERVICE_PARAMS,
    CONF_TEST_MODE,
    CONF_SECTION_APPEARANCE_LOCATION,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    HASS_DATA_CANCEL_HANDLERS,
    HASS_DATA_COORDINATOR,
    HASS_DATA_FILES_IGNORED,
    HASS_DATA_FILES_PARSED,
    HASS_DATA_PARSE_DURATION,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    TRACKED_EVENT_DOMAINS,
    MONITORED_STATES,
    PLATFORMS,
    VERSION,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_REPORT_PATH): cv.string,
                vol.Optional(CONF_IGNORED_FILES): cv.ensure_list,
                vol.Optional(CONF_IGNORED_ITEMS): cv.ensure_list,
                vol.Optional(CONF_HEADER, default=DEFAULT_HEADER): cv.string,
                vol.Optional(CONF_SERVICE_DATA): vol.Schema({}, extra=vol.ALLOW_EXTRA),
                vol.Optional(CONF_INCLUDED_FOLDERS): cv.ensure_list,
                vol.Optional(CONF_CHECK_LOVELACE, default=False): cv.boolean,
                vol.Optional(CONF_IGNORED_STATES): MONITORED_STATES,
                vol.Optional(CONF_COLUMNS_WIDTH): cv.ensure_list,
                vol.Optional(CONF_STARTUP_DELAY, default=0): cv.positive_int,
                vol.Optional(CONF_FRIENDLY_NAMES, default=False): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

type WMConfigEntry = ConfigEntry[WMData]
parser_lock = asyncio.Lock()


@dataclass
class WMData:
    included_folders: list[str]
    ignored_items: list[str]
    ignored_states: list[str]
    ignored_files: list[str]
    check_lovelace: bool
    startup_delay: int
    service: str
    service_data: str
    chunk_size: int
    report_header: str
    report_path: str
    columns_width: list[int]
    friendly_names: bool


async def async_setup_entry(hass: HomeAssistant, entry: WMConfigEntry):
    """Set up this integration using UI"""
    _LOGGER.debug(
        f"::async_setup_entry:: Integration setup in progress. Home assistant path: {hass.config.path("")}"
    )

    coordinator = WatchmanCoordinator(hass, _LOGGER, name=entry.title)
    coordinator.async_set_updated_data(None)
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    hass.data[DOMAIN][HASS_DATA_COORDINATOR] = coordinator
    hass.data[DOMAIN_DATA] = {"config_entry_id": entry.entry_id}
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(update_listener))
    await add_services(hass)
    await add_event_handlers(hass)
    if hass.is_running:
        # integration reloaded or options changed via UI
        await parse_config(hass, reason="changes in watchman configuration")
        await coordinator.async_config_entry_first_refresh()
    else:
        # first run, home assistant is loading
        # parse_config will be scheduled once HA is fully loaded
        _LOGGER.info("Watchman started [%s]", VERSION)
    return True


async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Reload integration when options changed"""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, config_entry):  # pylint: disable=unused-argument
    """Handle integration unload"""
    for cancel_handle in hass.data[DOMAIN].get(HASS_DATA_CANCEL_HANDLERS, []):
        if cancel_handle:
            cancel_handle()

    if hass.services.has_service(DOMAIN, "report"):
        hass.services.async_remove(DOMAIN, "report")

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


async def add_services(hass: HomeAssistant):
    """adds report service"""

    async def async_handle_report(call):
        """Handle the action call"""
        path = get_config(hass, CONF_REPORT_PATH)
        send_notification = call.data.get(CONF_SEND_NOTIFICATION, False)
        create_file = call.data.get(CONF_CREATE_FILE, True)
        test_mode = call.data.get(CONF_TEST_MODE, False)
        action_data = call.data.get(CONF_SERVICE_DATA, None)
        chunk_size = call.data.get(CONF_CHUNK_SIZE, 0)

        # validate action params
        for param in call.data:
            if param not in CONF_ALLOWED_SERVICE_PARAMS:
                raise HomeAssistantError(f"Unknown action parameter: `{param}`.")

        action_name = call.data.get(
            CONF_ACTION_NAME, call.data.get(CONF_SERVICE_NAME, None)
        )

        if not (action_name or create_file):
            raise HomeAssistantError(
                f"Either [{CONF_ACTION_NAME}] or [{CONF_CREATE_FILE}] should be specified."
            )

        if action_data and not action_name:
            raise HomeAssistantError(
                f"Missing [{CONF_ACTION_NAME}] parameter. The [{CONF_SERVICE_DATA}] parameter can only be used "
                f"in conjunction with [{CONF_ACTION_NAME}] parameter."
            )

        if call.data.get(CONF_PARSE_CONFIG, False):
            await parse_config(hass, reason="service call")

        # call notification action even when send notification = False
        if send_notification or action_name:
            await async_report_to_notification(
                hass, action_name, action_data, chunk_size
            )

        if create_file:
            try:
                await async_report_to_file(hass, path, test_mode=test_mode)
            except OSError as exception:
                raise HomeAssistantError(f"Unable to write report: {exception}")

    hass.services.async_register(DOMAIN, "report", async_handle_report)


async def add_event_handlers(hass: HomeAssistant):
    """add event handlers"""

    async def async_schedule_refresh_states(hass, delay):
        """schedule refresh of the sensors state"""
        now = dt_util.utcnow()
        next_interval = now + timedelta(seconds=delay)
        async_track_point_in_utc_time(hass, async_delayed_refresh_states, next_interval)

    async def async_delayed_refresh_states(timedate):  # pylint: disable=unused-argument
        """refresh sensors state"""
        # parse_config should be invoked beforehand
        coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
        await coordinator.async_refresh()

    async def async_on_home_assistant_started(event):  # pylint: disable=unused-argument
        await parse_config(hass, reason="HA restart")
        startup_delay = get_config(hass, CONF_STARTUP_DELAY, 0)
        await async_schedule_refresh_states(hass, startup_delay)

    async def async_on_configuration_changed(event):
        # prevent multiple parse attempts when several events triggered simultaneously
        if not parser_lock.locked():
            async with parser_lock:
                event_type = event.event_type
                if event_type == EVENT_CALL_SERVICE:
                    domain = event.data.get("domain", None)
                    service = event.data.get("service", None)
                    if domain in TRACKED_EVENT_DOMAINS and service in [
                        SERVICE_RELOAD_CORE_CONFIG,
                        SERVICE_RELOAD,
                        SERVICE_RELOAD_ALL,
                    ]:
                        await parse_config(hass, reason=f"{domain}.{service} call")
                        coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
                        await coordinator.async_refresh()

                elif event_type in [EVENT_AUTOMATION_RELOADED, EVENT_SCENE_RELOADED]:
                    await parse_config(hass, reason=f"event: {event_type}")
                    coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
                    await coordinator.async_refresh()

    async def async_on_service_changed(event):
        service = f"{event.data['domain']}.{event.data['service']}"
        if service in hass.data[DOMAIN].get(HASS_DATA_PARSED_SERVICE_LIST, []):
            _LOGGER.debug("Monitored service changed: %s", service)
            coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
            await coordinator.async_refresh()

    async def async_on_state_changed(event):
        """refresh monitored entities on state change"""

        def state_or_missing(state_id):
            """return missing state if entity not found"""
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


async def parse_config(hass: HomeAssistant, reason=None):
    """parse home assistant configuration files"""

    start_time = time.time()

    included_folders = get_included_folders(hass)
    ignored_files = get_config(hass, CONF_IGNORED_FILES, None)
    _LOGGER.debug(
        f"::parse_config:: called due to {reason} IGNORED_FILES={ignored_files}"
    )

    parsed_entity_list, parsed_service_list, files_parsed, files_ignored = await parse(
        hass, included_folders, ignored_files, hass.config.config_dir
    )
    hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST] = parsed_entity_list
    hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST] = parsed_service_list
    hass.data[DOMAIN][HASS_DATA_FILES_PARSED] = files_parsed
    hass.data[DOMAIN][HASS_DATA_FILES_IGNORED] = files_ignored
    hass.data[DOMAIN][HASS_DATA_PARSE_DURATION] = time.time() - start_time
    _LOGGER.debug(
        f"{INDENT}Parsing took {hass.data[DOMAIN][HASS_DATA_PARSE_DURATION]:.2f}s."
    )


def get_included_folders(hass):
    """gather the list of folders to parse"""
    folders = []

    for fld in get_config(hass, CONF_INCLUDED_FOLDERS, None):
        folders.append((fld, "**/*.yaml"))

    if get_config(hass, CONF_CHECK_LOVELACE):
        folders.append((hass.config.config_dir, ".storage/**/lovelace*"))

    return folders


async def async_report_to_file(hass, path, test_mode):
    """save report to a file"""
    coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
    await coordinator.async_refresh()
    report_chunks = await report(
        hass, table_renderer, chunk_size=0, test_mode=test_mode
    )

    def write(path):
        with open(path, "w", encoding="utf-8") as report_file:
            for chunk in report_chunks:
                report_file.write(chunk)

    await hass.async_add_executor_job(write, path)


async def async_report_to_notification(
    hass: HomeAssistant, action_str: str, service_data: dict[str, Any], chunk_size: int
):
    """send report via notification action"""

    if not action_str:
        raise HomeAssistantError(f"Missing `{CONF_ACTION_NAME}` parameter.")

    if action_str and not isinstance(action_str, str):
        raise HomeAssistantError(
            f"`action` parameter should be a string, got {action_str}"
        )

    if not is_action(hass, action_str):
        raise HomeAssistantError(f"{action_str} is not a valid action for notification")

    domain = action_str.split(".")[0]
    action = ".".join(action_str.split(".")[1:])

    data = {} if service_data is None else service_data

    _LOGGER.debug(f"SERVICE_DATA {data}")

    coordinator = hass.data[DOMAIN][HASS_DATA_COORDINATOR]
    await coordinator.async_refresh()
    report_chunks = await report(hass, text_renderer, chunk_size)
    for msg_chunk in report_chunks:
        data["message"] = msg_chunk
        # blocking=True ensures send order
        await hass.services.async_call(domain, action, data, blocking=True)


async def async_notification(hass, title, message, error=False, n_id="watchman"):
    """Show a persistent notification"""
    persistent_notification.async_create(
        hass,
        message,
        title=title,
        notification_id=n_id,
    )
    if error:
        raise HomeAssistantError(message.replace("`", ""))


async def async_migrate_entry(hass, config_entry: ConfigEntry):
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
                CONF_REPORT_PATH, await async_get_report_path(hass, None)
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
