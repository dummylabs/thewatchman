"""Button entity for Watchman."""
from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_REPORT_PATH, DOMAIN, REPORT_SERVICE_NAME
from .utils.utils import get_config


class WatchmanReportButton(ButtonEntity):
    """Button entity to trigger Watchman report."""

    _attr_has_entity_name = True
    _attr_translation_key = "create_report_file"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:file-document-outline"

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the entity."""
        self.hass = hass
        self._attr_unique_id = f"{DOMAIN}_report_button"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "watchman_unique_id")},
            manufacturer="dummylabs",
            model="Watchman",
            name="Watchman",
            sw_version=config_entry.runtime_data.coordinator.version,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/dummylabs/thewatchman",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(
            DOMAIN,
            REPORT_SERVICE_NAME,
            {"parse_config": True},
            blocking=True
        )
        report_path = get_config(self.hass, CONF_REPORT_PATH)
        await self.hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "🛡️Watchman",
                "message": f"Watchman Report is ready: {report_path}"
            }
        )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the button platform."""
    async_add_entities([WatchmanReportButton(hass, config_entry)])
