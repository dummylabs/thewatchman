"""Represents Watchman service in the device registry of Home Assistant"""

from homeassistant.helpers.entity import DeviceInfo, EntityDescription
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)
from .const import DOMAIN, VERSION


class WatchmanEntity(CoordinatorEntity):
    """Representation of a Watchman entity."""

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize Watchman entity."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        # per sensor unique_id
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "watchman_unique_id")},
            manufacturer="dummylabs",
            model="Watchman",
            name="Watchman",
            sw_version=VERSION,
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://github.com/dummylabs/thewatchman",
        )
        self._attr_extra_state_attributes = {}
