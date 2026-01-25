"""Text entity for Watchman ignored labels."""
from homeassistant.components.text import TextEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers import label_registry as lr
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from .const import DOMAIN, VERSION
from .coordinator import WatchmanCoordinator

class WatchmanIgnoredLabelsText(RestoreEntity, TextEntity):
    """Text entity to manage ignored labels."""

    _attr_has_entity_name = False
    _attr_name = "Watchman Ignored Labels"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:label-off"

    def __init__(self, hass: HomeAssistant, coordinator: WatchmanCoordinator):
        """Initialize the entity."""
        self.hass = hass
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.name}_ignored_labels"
        self._attr_native_value = ""
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "watchman_unique_id")},
            manufacturer="dummylabs",
            model="Watchman",
            name="Watchman",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/dummylabs/thewatchman",
        )

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        await super().async_added_to_hass()
        if (state := await self.async_get_last_state()) is not None:
            self._attr_native_value = state.state
            # Push restored state to coordinator
            self.coordinator.update_ignored_labels(self._parse_labels(state.state))

    async def async_set_value(self, value: str) -> None:
        """Set the text value."""
        valid_labels, invalid_labels = self._validate_labels(value)
        
        if invalid_labels:
            await self.hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "title": "Watchman: Invalid Labels",
                    "message": f"The following labels were not found and ignored: {', '.join(invalid_labels)}",
                    "notification_id": "watchman_invalid_labels",
                },
            )

        # Update state with valid labels only
        clean_value = ", ".join(valid_labels)
        self._attr_native_value = clean_value
        self.async_write_ha_state()
        
        # Update coordinator
        self.coordinator.update_ignored_labels(valid_labels)

    def _parse_labels(self, value: str) -> list[str]:
        """Parse comma-separated string to list."""
        if not value:
            return []
        return [x.strip() for x in value.split(",") if x.strip()]

    def _validate_labels(self, value: str) -> tuple[list[str], list[str]]:
        """Validate labels against registry."""
        registry = lr.async_get(self.hass)
        existing_labels = {l.label_id for l in registry.async_list_labels()}
        
        input_labels = self._parse_labels(value)
        valid = []
        invalid = []
        
        for label in input_labels:
            if label in existing_labels:
                valid.append(label)
            else:
                invalid.append(label)
                
        return valid, invalid

async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the text platform."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([WatchmanIgnoredLabelsText(hass, coordinator)])
