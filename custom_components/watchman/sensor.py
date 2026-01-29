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
    STATE_SAFE_MODE,
)

SENSORS_CONFIGURATION = [
    SensorEntityDescription(
        key=SENSOR_LAST_UPDATE,
        translation_key="last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key=SENSOR_MISSING_ENTITIES,
        translation_key="missing_entities",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:shield-half-full",
        native_unit_of_measurement="items",
    ),
    SensorEntityDescription(
        key=SENSOR_MISSING_ACTIONS,
        translation_key="missing_actions",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:shield-half-full",
        native_unit_of_measurement="items",
    ),
    SensorEntityDescription(
        key=SENSOR_STATUS,
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        entity_category=EntityCategory.DIAGNOSTIC,
        options=[STATE_WAITING_HA, STATE_PARSING, STATE_IDLE, STATE_SAFE_MODE],
    ),
    SensorEntityDescription(
        key=SENSOR_PARSE_DURATION,
        translation_key="parse_duration",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:timer-outline",
    ),
    SensorEntityDescription(
        key=SENSOR_LAST_PARSE,
        translation_key="last_parse",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
    ),
    SensorEntityDescription(
        key=SENSOR_PROCESSED_FILES,
        translation_key="processed_files",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:file-document-check",
    ),
    SensorEntityDescription(
        key=SENSOR_IGNORED_FILES,
        translation_key="ignored_files",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:file-remove",
    ),
]


async def async_setup_entry(hass, entry, async_add_devices):
    """Set up sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    ent_reg = er.async_get(hass)
    entities = []

    for description in SENSORS_CONFIGURATION:
        # Migration logic
        old_uid = f"{entry.entry_id}_{description.key}"
        new_uid = f"{DOMAIN}_{description.key}"

        if entity_id := ent_reg.async_get_entity_id("sensor", DOMAIN, old_uid):
            ent_reg.async_update_entity(entity_id, new_unique_id=new_uid)

        # Instantiate sensor classes
        if description.key == SENSOR_LAST_UPDATE:
            entities.append(LastUpdateSensor(coordinator, description))
        elif description.key == SENSOR_MISSING_ENTITIES:
            entities.append(MissingEntitiesSensor(coordinator, description))
        elif description.key == SENSOR_MISSING_ACTIONS:
            entities.append(MissingActionsSensor(coordinator, description))
        elif description.key == SENSOR_STATUS:
            entities.append(StatusSensor(coordinator, description))
        elif description.key == SENSOR_PARSE_DURATION:
            entities.append(ParseDurationSensor(coordinator, description))
        elif description.key == SENSOR_LAST_PARSE:
            entities.append(LastParseSensor(coordinator, description))
        elif description.key == SENSOR_PROCESSED_FILES:
            entities.append(ProcessedFilesSensor(coordinator, description))
        elif description.key == SENSOR_IGNORED_FILES:
            entities.append(IgnoredFilesSensor(coordinator, description))

    async_add_devices(entities)


class LastUpdateSensor(WatchmanEntity, SensorEntity):
    """Timestamp sensor for last watchman update time."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_LAST_UPDATE)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_LAST_UPDATE)
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class MissingEntitiesSensor(WatchmanEntity, SensorEntity):
    """Number of missing entities from watchman report."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({MATCH_ALL})

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_MISSING_ENTITIES)
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data:
            return {"entities": self.coordinator.data.get(COORD_DATA_ENTITY_ATTRS, [])}
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_MISSING_ENTITIES)
            self._attr_extra_state_attributes = {
                "entities": self.coordinator.data.get(COORD_DATA_ENTITY_ATTRS, [])
            }
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class MissingActionsSensor(WatchmanEntity, SensorEntity):
    """Number of missing services from watchman report."""

    _attr_should_poll = False
    _attr_has_entity_name = True
    _unrecorded_attributes = frozenset({MATCH_ALL})

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_MISSING_ACTIONS)
        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data:
            return {"entities": self.coordinator.data.get(COORD_DATA_SERVICE_ATTRS, [])}
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_MISSING_ACTIONS)
            self._attr_extra_state_attributes = {
                "services": self.coordinator.data.get(COORD_DATA_SERVICE_ATTRS, [])
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
        if self.coordinator.status == STATE_SAFE_MODE:
            return "mdi:shield-alert"
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

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_PARSE_DURATION)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_PARSE_DURATION)
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class LastParseSensor(WatchmanEntity, SensorEntity):
    """Timestamp sensor for last parse time."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_LAST_PARSE)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_LAST_PARSE)
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class ProcessedFilesSensor(WatchmanEntity, SensorEntity):
    """Sensor for number of processed files."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_PROCESSED_FILES)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_PROCESSED_FILES)
            self.async_write_ha_state()
        super()._handle_coordinator_update()


class IgnoredFilesSensor(WatchmanEntity, SensorEntity):
    """Sensor for number of ignored files."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def native_value(self):
        """Return the native value of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get(COORD_DATA_IGNORED_FILES)
        return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            self._attr_native_value = self.coordinator.data.get(COORD_DATA_IGNORED_FILES)
            self.async_write_ha_state()
        super()._handle_coordinator_update()