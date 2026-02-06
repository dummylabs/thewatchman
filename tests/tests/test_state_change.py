"""Test Watchman reaction to entity state changes."""
from datetime import timedelta

from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    SENSOR_MISSING_ENTITIES,
)
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from tests import async_init_integration

from homeassistant.util import dt as dt_util


@pytest.mark.asyncio
async def test_entity_state_change_tracking(hass, tmp_path):
    """Test that Watchman updates missing entities sensor when a tracked entity becomes unavailable."""
    # 1. Setup: Create a config file with a monitored entity
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "test_sensors.yaml"

    # We define usage of 'sensor.test_monitored_sensor' so parser detects it
    config_file.write_text("monitored_usage:\n  entity_id: sensor.test_monitored_sensor", encoding="utf-8")

    # Set initial state to valid (ON) BEFORE setup, or right after
    hass.states.async_set("sensor.test_monitored_sensor", "on")

    # Initialize integration pointing to our temp config
    await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: str(config_dir),
            CONF_IGNORED_STATES: [], # Ensure unavailable is NOT ignored
        },
    )

    # Allow initial scan to complete
    await hass.async_block_till_done()

    # 2. Verify Initial State
    # Watchman should have parsed the file and found 'sensor.test_monitored_sensor'
    # Since state is 'on', missing entities should be 0.

    from homeassistant.helpers import entity_registry as er
    entity_registry = er.async_get(hass)
    entity_id = next(e.entity_id for e in entity_registry.entities.values() if e.unique_id.endswith(SENSOR_MISSING_ENTITIES))

    missing_sensor = hass.states.get(entity_id)
    assert missing_sensor is not None
    assert missing_sensor.state == "0", "Initial missing count should be 0"

    # 3. Trigger: Change state to unavailable
    hass.states.async_set("sensor.test_monitored_sensor", "unavailable")

    # Allow event processing and debounced refresh (10s default cooldown)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()

    # 4. Verify Updated State
    # Watchman should detect the state change for the monitored entity and trigger a refresh
    missing_sensor = hass.states.get(entity_id)
    assert missing_sensor.state == "1", "Missing count should update to 1 after entity becomes unavailable"

    # Verify attributes
    assert "sensor.test_monitored_sensor" in str(missing_sensor.attributes), \
        "The unavailable sensor should be listed in attributes"

    # 5. Recovery: Change state back to on
    hass.states.async_set("sensor.test_monitored_sensor", "on")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()

    missing_sensor = hass.states.get(entity_id)
    assert missing_sensor.state == "0", "Missing count should return to 0 after entity recovers"

    # 6. Removal: Remove the state entirely
    # Watchman should treat a missing state as 'missing' and increment the counter
    hass.states.async_remove("sensor.test_monitored_sensor")
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()

    missing_sensor = hass.states.get(entity_id)
    assert missing_sensor.state == "1", "Missing count should become 1 after entity state is removed"
    assert "sensor.test_monitored_sensor" in str(missing_sensor.attributes)
