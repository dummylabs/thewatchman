from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir, label_registry as lr

from .const import (
    CONF_ACTION_NAME,
    CONF_ALLOWED_SERVICE_PARAMS,
    CONF_CHUNK_SIZE,
    CONF_CREATE_FILE,
    CONF_FORCE_PARSING,
    CONF_IGNORED_LABELS,
    CONF_PARSE_CONFIG,
    CONF_REPORT_PATH,
    CONF_SEND_NOTIFICATION,
    CONF_SERVICE_DATA,
    CONF_SERVICE_NAME,
    DOMAIN,
    LABELS_SERVICE_NAME,
    REPORT_SERVICE_NAME,
)
from .utils.logger import _LOGGER
from .utils.report import async_report_to_file, async_report_to_notification
from .utils.utils import get_config


class WatchmanServicesSetup:
    """Class to handle Integration Services."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialise services."""
        self.hass = hass
        self.config_entry = config_entry
        self.coordinator = config_entry.runtime_data.coordinator

        self.setup_services()

    def setup_services(self) -> None:
        """Initialise the services in Hass."""
        self.hass.services.async_register(
            DOMAIN,
            REPORT_SERVICE_NAME,
            self.async_handle_report,
            supports_response=SupportsResponse.OPTIONAL
        )
        self.hass.services.async_register(
            DOMAIN,
            LABELS_SERVICE_NAME,
            self.async_handle_set_ignored_labels,
        )

    async def async_handle_set_ignored_labels(self, call: ServiceCall) -> None:
        """Set ignored labels."""
        labels = call.data.get("labels", [])
        registry = lr.async_get(self.hass)
        existing_labels = {l.label_id for l in registry.async_list_labels()}

        invalid_labels = [l for l in labels if l not in existing_labels]
        if invalid_labels:
            raise ServiceValidationError(
                f"The following labels do not exist: {', '.join(invalid_labels)}"
            )

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_IGNORED_LABELS: labels}
        )

    async def async_handle_report(self, call: ServiceCall) -> dict[str, Any]:
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

        if action_data and not action_name:
            raise ServiceValidationError(
                f"Missing [{CONF_ACTION_NAME}] parameter. The [{CONF_SERVICE_DATA}] parameter can only be used "
                f"in conjunction with [{CONF_ACTION_NAME}] parameter."
            )

        _LOGGER.debug(f"User requested report params={call.data}")

        if CONF_PARSE_CONFIG in call.data:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                "deprecated_parse_config_parameter",
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="deprecated_service_param",
                translation_placeholders={
                    "deprecated_param": CONF_PARSE_CONFIG,
                },
            )

        force_parsing = call.data.get(CONF_FORCE_PARSING, call.data.get(CONF_PARSE_CONFIG, False))

        # Always trigger a parser run (default: incremental, unless forced)
        await self.coordinator.async_force_parse(ignore_mtime=force_parsing)

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

        return await self.coordinator.async_get_detailed_report_data()
