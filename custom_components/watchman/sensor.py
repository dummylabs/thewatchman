"""Watchman sensors definition"""
import logging
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import callback
from .entity import WatchmanEntity

from .const import (
    DOMAIN,
    SENSOR_LAST_UPDATE,
    SENSOR_MISSING_ENTITIES,
    SENSOR_MISSING_SERVICES,
)


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        [
            LastUpdateSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_LAST_UPDATE,
                    name=SENSOR_LAST_UPDATE,
                    device_class=SensorDeviceClass.TIMESTAMP,
                ),
            ),
            MissingEntitiesSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_MISSING_ENTITIES,
                    name=SENSOR_MISSING_ENTITIES,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
            ),
            MissingServicesSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_MISSING_SERVICES,
                    name=SENSOR_MISSING_SERVICES,
                    state_class=SensorStateClass.MEASUREMENT,
                ),
            ),
        ]
    )


class LastUpdateSensor(WatchmanEntity, SensorEntity):
    """Timestamp sensor for last watchman update time"""

    _attr_should_poll = False
    _attr_icon = "mdi:shield-half-full"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data["last_update"]
        else:
            return self._attr_native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data["last_update"]
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class MissingEntitiesSensor(WatchmanEntity, SensorEntity):
    """Number of missing entities from watchman report"""

    _attr_should_poll = False
    _attr_icon = "mdi:shield-half-full"
    _attr_native_unit_of_measurement = "items"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data["entities_missing"]
        else:
            return self._attr_native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data:
            return {"entities": self.coordinator.data["entity_attrs"]}
        else:
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data["entities_missing"]
            self._attr_extra_state_attributes = {
                "entities": self.coordinator.data["entity_attrs"]
            }
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class MissingServicesSensor(WatchmanEntity, SensorEntity):
    """Number of missing services from watchman report"""

    _attr_should_poll = False
    _attr_icon = "mdi:shield-half-full"
    _attr_native_unit_of_measurement = "items"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data["services_missing"]
        else:
            return self._attr_native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data:
            return {"entities": self.coordinator.data["service_attrs"]}
        else:
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data["services_missing"]
            self._attr_extra_state_attributes = {
                "services": self.coordinator.data["service_attrs"]
            }
        self.async_write_ha_state()
        super()._handle_coordinator_update()
