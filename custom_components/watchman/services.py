from custom_components.watchman.const import (
    CONF_ACTION_NAME,
    CONF_ALLOWED_SERVICE_PARAMS,
    CONF_CHUNK_SIZE,
    CONF_CREATE_FILE,
    CONF_PARSE_CONFIG,
    CONF_REPORT_PATH,
    CONF_SEND_NOTIFICATION,
    CONF_SERVICE_DATA,
    CONF_SERVICE_NAME,
    DOMAIN,
    REPORT_SERVICE_NAME,
)
from .utils.report import async_report_to_file, async_report_to_notification
from .utils.utils import get_config

from homeassistant.exceptions import ServiceValidationError
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry


class WatchmanServicesSetup:
    """Class to handle Integration Services."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise services."""
        self.hass = hass
        self.config_entry = config_entry
        self.coordinator = config_entry.runtime_data.coordinator

        self.setup_services()

    def setup_services(self):
        """Initialise the services in Hass."""

        self.hass.services.async_register(
            DOMAIN, REPORT_SERVICE_NAME, self.async_handle_report
        )

    async def async_handle_report(self, call):
        """Handle the action call."""
        path = get_config(self.hass, CONF_REPORT_PATH)
        send_notification = call.data.get(CONF_SEND_NOTIFICATION, False)
        create_file = call.data.get(CONF_CREATE_FILE, True)
        action_data = call.data.get(CONF_SERVICE_DATA, None)
        chunk_size = call.data.get(CONF_CHUNK_SIZE, 0)

        # validate action params
        for param in call.data:
            if param not in CONF_ALLOWED_SERVICE_PARAMS:
                raise ServiceValidationError(f"Unknown action parameter: `{param}`.")

        action_name = call.data.get(
            CONF_ACTION_NAME, call.data.get(CONF_SERVICE_NAME, None)
        )

        if not (action_name or create_file):
            raise ServiceValidationError(
                f"Either [{CONF_ACTION_NAME}] or [{CONF_CREATE_FILE}] should be specified."
            )

        if action_data and not action_name:
            raise ServiceValidationError(
                f"Missing [{CONF_ACTION_NAME}] parameter. The [{CONF_SERVICE_DATA}] parameter can only be used "
                f"in conjunction with [{CONF_ACTION_NAME}] parameter."
            )

        if call.data.get(CONF_PARSE_CONFIG, False):
            await self.coordinator.async_parse_config(reason="service call")
            await self.coordinator.async_refresh()

        # call notification action even when send notification = False
        if send_notification or action_name:
            await async_report_to_notification(
                self.hass, action_name, action_data, chunk_size
            )

        if create_file:
            try:
                await async_report_to_file(self.hass, path)
            except OSError as exception:
                raise ServiceValidationError(
                    f"Unable to write report to file '{exception.filename}': {exception.strerror} [Error:{exception.errno}]"
                )