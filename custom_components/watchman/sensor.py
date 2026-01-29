"""Watchman sensors definition."""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.components.sensor.const import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import EntityCategory

from homeassistant.helpers import entity_registry as er
from homeassistant.core import callback
from homeassistant.const import MATCH_ALL
from .entity import WatchmanEntity

from .const import (
    COORD_DATA_ENTITY_ATTRS,
    COORD_DATA_LAST_UPDATE,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_MISSING_ACTIONS,
    COORD_DATA_SERVICE_ATTRS,
    COORD_DATA_PARSE_DURATION,
    COORD_DATA_LAST_PARSE,
    COORD_DATA_PROCESSED_FILES,
    COORD_DATA_IGNORED_FILES,
    DOMAIN,
    SENSOR_LAST_UPDATE,
    SENSOR_MISSING_ACTIONS,
    SENSOR_MISSING_ENTITIES,
    SENSOR_STATUS,
    SENSOR_PARSE_DURATION,
    SENSOR_LAST_PARSE,
    SENSOR_PROCESSED_FILES,
    SENSOR_IGNORED_FILES,
    STATE_WAITING_HA,
    STATE_PARSING,
    STATE_IDLE,
)


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_devices(
        [
            LastUpdateSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_LAST_UPDATE,
                    translation_key="last_updated",
                    device_class=SensorDeviceClass.TIMESTAMP,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            MissingEntitiesSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_MISSING_ENTITIES,
                    translation_key="missing_entities",
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            MissingActionsSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_MISSING_ACTIONS,
                    translation_key="missing_actions",
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            StatusSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_STATUS,
                    translation_key="status",
                    device_class=SensorDeviceClass.ENUM,
                    entity_category=EntityCategory.DIAGNOSTIC,
                    options=[STATE_WAITING_HA, STATE_PARSING, STATE_IDLE],
                ),
            ),
            ParseDurationSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_PARSE_DURATION,
                    translation_key="parse_duration",
                    device_class=SensorDeviceClass.DURATION,
                    state_class=SensorStateClass.MEASUREMENT,
                    native_unit_of_measurement="s",
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            LastParseSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_LAST_PARSE,
                    translation_key="last_parse",
                    device_class=SensorDeviceClass.TIMESTAMP,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            ProcessedFilesSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_PROCESSED_FILES,
                    translation_key="processed_files",
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
            IgnoredFilesSensor(
                coordinator=coordinator,
                entity_description=SensorEntityDescription(
                    key=SENSOR_IGNORED_FILES,
                    translation_key="ignored_files",
                    state_class=SensorStateClass.MEASUREMENT,
                    entity_category=EntityCategory.DIAGNOSTIC,
                ),
            ),
        ]
    )


class LastUpdateSensor(WatchmanEntity, SensorEntity):
    """Timestamp sensor for last watchman update time."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

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
    """Number of missing entities from watchman report."""

    _attr_should_poll = False
    _attr_has_entity_name = True
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


class MissingActionsSensor(WatchmanEntity, SensorEntity):
    """Number of missing services from watchman report."""

    _attr_should_poll = False
    _attr_has_entity_name = True
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
            return self.coordinator.data[COORD_DATA_MISSING_ACTIONS]
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
            self._attr_native_value = self.coordinator.data[COORD_DATA_MISSING_ACTIONS]
            self._attr_extra_state_attributes = {
                "services": self.coordinator.data[COORD_DATA_SERVICE_ATTRS]
            }
        self.async_write_ha_state()
        super()._handle_coordinator_update()


class StatusSensor(WatchmanEntity, SensorEntity):
    """Diagnostic sensor for Watchman status."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        return self.coordinator.status

    @property
    def icon(self):
        """Return dynamic icon based on status."""
        if self.coordinator.status == STATE_PARSING:
            return "mdi:progress-clock"
        if self.coordinator.status == STATE_IDLE:
            return "mdi:sleep"
        return "mdi:timer-sand"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = self.coordinator.status
        self.async_write_ha_state()
        super()._handle_coordinator_update()


class ParseDurationSensor(WatchmanEntity, SensorEntity):
    """Sensor for last parse duration."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:timer-outline"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[COORD_DATA_PARSE_DURATION]
        else:
            return self._attr_native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_PARSE_DURATION]
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class LastParseSensor(WatchmanEntity, SensorEntity):
    """Timestamp sensor for last parse time."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:calendar-clock"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[COORD_DATA_LAST_PARSE]
        else:
            return self._attr_native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_LAST_PARSE]
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class ProcessedFilesSensor(WatchmanEntity, SensorEntity):
    """Sensor for number of processed files."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:file-document-check"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[COORD_DATA_PROCESSED_FILES]
        else:
            return self._attr_native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_PROCESSED_FILES]
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class IgnoredFilesSensor(WatchmanEntity, SensorEntity):
    """Sensor for number of ignored files."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_icon = "mdi:file-remove"

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data[COORD_DATA_IGNORED_FILES]
        else:
            return self._attr_native_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data[COORD_DATA_IGNORED_FILES]
            self.async_write_ha_state()
        super()._handle_coordinator_update()
