"""Button entity for Watchman."""
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.core import HomeAssistant
from .const import DOMAIN, VERSION, REPORT_SERVICE_NAME


class WatchmanReportButton(ButtonEntity):
    """Button entity to trigger Watchman report."""

    _attr_has_entity_name = True
    _attr_name = "Report"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:file-document-outline"

    def __init__(self, hass: HomeAssistant, entry_id: str):
        """Initialize the entity."""
        self.hass = hass
        self._attr_unique_id = f"{entry_id}_report_button"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "watchman_unique_id")},
            manufacturer="dummylabs",
            model="Watchman",
            name="Watchman",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/dummylabs/thewatchman",
        )

    async def async_press(self) -> None:
        """Handle the button press."""
        await self.hass.services.async_call(DOMAIN, REPORT_SERVICE_NAME, {})


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the button platform."""
    async_add_entities([WatchmanReportButton(hass, config_entry.entry_id)])
