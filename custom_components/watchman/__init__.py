"""https://github.com/dummylabs/thewatchman§"""
import json
import time
import os
import logging
from datetime import datetime, timedelta
import pytz
from .utils import (
    is_service,
    check_entitites,
    check_services,
    report,
    parse,
    table_renderer,
    text_renderer,
)
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.components import persistent_notification
from homeassistant.util import dt as dt_util
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.helpers.event import track_point_in_utc_time
from homeassistant.exceptions import HomeAssistantError

from homeassistant.const import (
    EVENT_CORE_CONFIG_UPDATE,
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_CALL_SERVICE,
    STATE_UNKNOWN,
)
from .const import (
    DOMAIN,
    DEFAULT_REPORT_FILENAME,
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
    CONF_SEND_NITIFICATION,
    CONF_PARSE_CONFIG,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONF_FRIENDLY_NAMES,
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED,
    SENSOR_LAST_UPDATE,
    SENSOR_MISSING_ENTITIES,
    SENSOR_MISSING_SERVICES,
    TRACKED_EVENT_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_REPORT_PATH): cv.string,
                vol.Optional(CONF_IGNORED_FILES): cv.ensure_list,
                vol.Optional(CONF_IGNORED_ITEMS): cv.ensure_list,
                vol.Optional(CONF_HEADER, default=DEFAULT_HEADER): cv.string,
                vol.Optional(CONF_SERVICE_NAME): cv.string,
                vol.Optional(CONF_SERVICE_DATA): vol.Schema({}, extra=vol.ALLOW_EXTRA),
                vol.Optional(CONF_INCLUDED_FOLDERS): cv.ensure_list,
                vol.Optional(CONF_CHECK_LOVELACE, default=False): cv.boolean,
                vol.Optional(CONF_CHUNK_SIZE, default=3500): cv.positive_int,
                vol.Optional(CONF_IGNORED_STATES): [
                    "missing",
                    "unavailable",
                    "unknown",
                ],
                vol.Optional(CONF_COLUMNS_WIDTH): cv.ensure_list,
                vol.Optional(CONF_STARTUP_DELAY, default=0): cv.positive_int,
                vol.Optional(CONF_FRIENDLY_NAMES, default=False): cv.boolean,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


def setup(hass, config):
    """Set up is called when Home Assistant is loading our component."""

    def notification(title, message, n_id="watchman"):
        """Show a persistent notification"""
        persistent_notification.create(
            hass,
            message,
            title=title,
            notification_id=n_id,
        )

    def get_report_path(path):
        # if path not specified, create report in config directory with default filename
        if not path:
            path = os.path.join(hass.config.config_dir, DEFAULT_REPORT_FILENAME)
        folder, _ = os.path.split(path)
        if not os.path.exists(folder):
            # _LOGGER.error(f"Incorrect `report_path` {path}.")
            raise HomeAssistantError(f"Incorrect report_path: {path}.")
        return path

    def report_to_file(hass, config, path):
        """ "save report to a file"""
        delayed_refresh(0)
        report_chunks = report(hass, config, table_renderer, chunk_size=0)

        with open(path, "w", encoding="utf-8") as report_file:
            for chunk in report_chunks:
                report_file.write(chunk)

    def report_to_notification(hass, config, service_str, service_data, chunk_size):
        """send report via notification service"""
        if not service_str:
            service_str = config[DOMAIN].get(CONF_SERVICE_NAME, None)
            service_data = config[DOMAIN].get(CONF_SERVICE_DATA, {})

        if not service_str:
            notification(
                "Watchman Error",
                "You should specify `service` parameter (in configuration.yaml file or as `service` parameter) in order to send report via notification",
            )
            return

        if not is_service(hass, service_str):
            notification(
                "Watchman Error",
                f"{service_str} is not a valid service for notification",
            )
        domain = service_str.split(".")[0]
        service = ".".join(service_str.split(".")[1:])

        if service_data is None:
            service_data = {}

        delayed_refresh(0)
        report_chunks = report(hass, config, text_renderer, chunk_size)
        for chunk in report_chunks:
            service_data["message"] = chunk
            if not hass.services.call(domain, service, service_data, blocking=True):
                _LOGGER.error(
                    f"Unable to call service {domain}.{service} due to an error."
                )
                break

    def onboarding(service, path):
        service = service or config[DOMAIN].get(CONF_SERVICE_NAME, None)
        return not (service or os.path.exists(path))

    def handle_report(call):
        """Handle the service call"""

        if call.data.get(CONF_PARSE_CONFIG, False):
            parse_config()

        path = get_report_path(config[DOMAIN].get(CONF_REPORT_PATH, None))

        if call.data.get(CONF_SEND_NITIFICATION, True):
            chunk_size = call.data.get(CONF_CHUNK_SIZE, None)
            service = call.data.get(CONF_SERVICE_NAME, None)
            service_data = call.data.get(CONF_SERVICE_DATA, None)
            if onboarding(service, path):
                notification(
                    "🖖 Achievement unlocked: first report!",
                    f"Your first watchman report was stored in `{path}` \n\n "
                    "TIP: set `service` parameter in configuration.yaml file to "
                    "receive report via notification service of choice. \n\n "
                    "This is one-time message, it will not bother you in the future.",
                )
            else:
                report_to_notification(hass, config, service, service_data, chunk_size)

        if call.data.get(CONF_CREATE_FILE, True):
            report_to_file(hass, config, path)

    def get_included_folders(config):
        """gather the list of folders to parse"""
        folders = []
        for fld in config[DOMAIN].get("included_folders", [hass.config.config_dir]):
            folders.append(os.path.join(fld, "**/*.yaml"))
        if config[DOMAIN].get(CONF_CHECK_LOVELACE):
            folders.append(
                os.path.join(hass.config.config_dir, ".storage/**/lovelace*")
            )
        return folders

    def parse_config(reason=None):
        """parse home assistant configuration files"""
        start_time = time.time()
        included_folders = get_included_folders(config)
        ignored_files = config[DOMAIN].get(CONF_IGNORED_FILES, None)
        ignored_states = config[DOMAIN].get(CONF_IGNORED_STATES, [])

        entity_list, service_list, files_parsed, files_ignored = parse(
            included_folders, ignored_files, hass.config.config_dir, None
        )
        hass.data[DOMAIN]["entity_list"] = entity_list
        hass.data[DOMAIN]["service_list"] = service_list
        hass.data[DOMAIN]["files_parsed"] = files_parsed
        hass.data[DOMAIN]["files_ignored"] = files_ignored
        hass.data[DOMAIN]["parse_duration"] = time.time() - start_time
        _LOGGER.info(
            f"Configuration files parsed in {hass.data[DOMAIN]['parse_duration']:.2f}s. due to {reason}"
        )

    def refresh_states(time_date):
        # parse_config should be invoked beforehand
        start_time = time.time()
        services_missing = check_services(hass, config)
        entities_missing = check_entitites(hass, config)
        hass.data[DOMAIN]["check_duration"] = time.time() - start_time
        hass.data[DOMAIN]["entities_missing"] = entities_missing
        hass.data[DOMAIN]["services_missing"] = services_missing
        hass.states.set(
            SENSOR_MISSING_ENTITIES,
            len(entities_missing),
            {"unit_of_measurement": "items", "friendly_name": "Missing entities"},
            force_update=True,
        )
        hass.states.set(
            SENSOR_MISSING_SERVICES,
            len(services_missing),
            {"unit_of_measurement": "items", "friendly_name": "Missing services"},
            force_update=True,
        )
        hass.states.set(
            SENSOR_LAST_UPDATE,
            dt_util.now(),
            {
                "device_class": "timestamp",
                "friendly_name": "Watchman updated",
            },
        )
        _LOGGER.info("Watchman sensors updated")

    def delayed_refresh(delay):
        if delay == 0:
            refresh_states(None)
        else:
            now = dt_util.utcnow()
            next_interval = now + timedelta(seconds=delay)
            unsub = track_point_in_utc_time(hass, refresh_states, next_interval)

    def on_home_assistant_started(event):
        parse_config("HA restart")
        startup_delay = config[DOMAIN].get(CONF_STARTUP_DELAY)
        delayed_refresh(startup_delay)

    def on_configuration_changed(event):
        typ = event.event_type
        if typ == EVENT_CALL_SERVICE:
            domain = event.data.get("domain", None)
            service = event.data.get("service", None)
            if domain in TRACKED_EVENT_DOMAINS and service in [
                "reload_core_config",
                "reload",
            ]:
                parse_config("configuration changes")
                delayed_refresh(0)

        elif typ in [
            EVENT_AUTOMATION_RELOADED,
            EVENT_SCENE_RELOADED,
            # EVENT_HOMEASSISTANT_STARTED,
        ]:
            parse_config("configuration changes")
            delayed_refresh(0)

    if not DOMAIN in hass.data:
        hass.data[DOMAIN] = {}

    hass.states.set(
        SENSOR_MISSING_ENTITIES,
        STATE_UNKNOWN,
        {"unit_of_measurement": "items", "friendly_name": "Missing entities"},
    )
    hass.states.set(
        SENSOR_MISSING_SERVICES,
        STATE_UNKNOWN,
        {"unit_of_measurement": "items", "friendly_name": "Missing services"},
    )
    hass.states.set(
        SENSOR_LAST_UPDATE,
        STATE_UNKNOWN,
        {"device_class": "timestamp", "friendly_name": "Watchman updated"},
    )

    hass.bus.listen(EVENT_HOMEASSISTANT_STARTED, on_home_assistant_started)
    hass.bus.listen(EVENT_CALL_SERVICE, on_configuration_changed)
    hass.bus.listen(EVENT_AUTOMATION_RELOADED, on_configuration_changed)
    hass.bus.listen(EVENT_SCENE_RELOADED, on_configuration_changed)

    hass.services.register(DOMAIN, "report", handle_report)

    # Return boolean to indicate that initialization was successful.
    return True
