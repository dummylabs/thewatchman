"""Watchman sensors definition"""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.components.sensor.const import (
    SensorDeviceClass,
    SensorStateClass,
)

from homeassistant.helpers import entity_registry as er
from homeassistant.core import callback
from homeassistant.const import MATCH_ALL
from .entity import WatchmanEntity
from .utils.logger import _LOGGER

from .const import (
    COORD_DATA_ENTITY_ATTRS,
    COORD_DATA_LAST_UPDATE,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_MISSING_SERVICES,
    COORD_DATA_SERVICE_ATTRS,
    DOMAIN,
    SENSOR_LAST_UPDATE,
    SENSOR_MISSING_ACTIONS,
    SENSOR_MISSING_ENTITIES,
    SENSOR_MISSING_SERVICES,
)


async def async_setup_entry(hass, entry, async_add_devices):
    """Setup sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # if sensor.watchman_missing_sensor exists in entity registry - this is an existing
    # user and we don't want to break compatibility by changing sensor name to actions
    entity_registry = er.async_get(hass)
    action_sensor_name = (
        SENSOR_MISSING_SERVICES
        if entity_registry.async_get(f"sensor.{SENSOR_MISSING_SERVICES}")
        else SENSOR_MISSING_ACTIONS
    )
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
                    key=action_sensor_name,
                    name=action_sensor_name,
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
            return self.coordinator.data[COORD_DATA_LAST_UPDATE]
        else:
            return self._attr_native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_LAST_UPDATE]
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class MissingEntitiesSensor(WatchmanEntity, SensorEntity):
    """Number of missing entities from watchman report"""

    _attr_should_poll = False
    _attr_icon = "mdi:shield-half-full"
    _attr_native_unit_of_measurement = "items"
    _unrecorded_attributes = frozenset({MATCH_ALL})

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[COORD_DATA_MISSING_ENTITIES]
        else:
            return self._attr_native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data:
            return {"entities": self.coordinator.data[COORD_DATA_ENTITY_ATTRS]}
        else:
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_MISSING_ENTITIES]
            self._attr_extra_state_attributes = {
                "entities": self.coordinator.data[COORD_DATA_ENTITY_ATTRS]
            }
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class MissingServicesSensor(WatchmanEntity, SensorEntity):
    """Number of missing services from watchman report"""

    _attr_should_poll = False
    _attr_icon = "mdi:shield-half-full"
    _attr_native_unit_of_measurement = "items"
    _unrecorded_attributes = frozenset({MATCH_ALL})

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[COORD_DATA_MISSING_SERVICES]
        else:
            return self._attr_native_value

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data:
            return {"entities": self.coordinator.data[COORD_DATA_SERVICE_ATTRS]}
        else:
            return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_MISSING_SERVICES]
            self._attr_extra_state_attributes = {
                "services": self.coordinator.data[COORD_DATA_SERVICE_ATTRS]
            }
        self.async_write_ha_state()
        super()._handle_coordinator_update()
