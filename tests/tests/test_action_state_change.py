"""Test Watchman reaction to action state changes."""
from datetime import timedelta

from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    DOMAIN,
    SENSOR_MISSING_ACTIONS,
)
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from tests import async_init_integration

from homeassistant.util import dt as dt_util


@pytest.mark.asyncio
async def test_action_state_change_tracking(hass, tmp_path):
    """Test that Watchman updates missing services sensor when a tracked service is registered/removed."""
    # 1. Setup: Create a config file with a monitored service
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "test_actions.yaml"

    # Define usage of 'script.test_service'
    config_file.write_text("automation:\n  - action:\n      - service: script.test_service", encoding="utf-8")

    # Initialize integration pointing to our temp config
    await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: str(config_dir),
            CONF_IGNORED_STATES: [],
        },
    )

    # Allow initial scan to complete
    await hass.async_block_till_done()

    # 2. Verify Initial State
    # The service 'script.test_service' is NOT registered yet, so it should be reported as missing.
    # Note: New installations use watchman_missing_actions by default

    from homeassistant.helpers import entity_registry as er
    entity_registry = er.async_get(hass)
    entity_id = next(e.entity_id for e in entity_registry.entities.values() if e.unique_id.endswith(SENSOR_MISSING_ACTIONS))

    missing_sensor = hass.states.get(entity_id)
    assert missing_sensor is not None
    assert missing_sensor.state == "1", "Initial missing count should be 1 (service not registered)"
    assert "script.test_service" in str(missing_sensor.attributes)

    # 3. Trigger: Register the service
    def mock_service_handler(call):
        pass

    hass.services.async_register("script", "test_service", mock_service_handler)

    # Allow event processing and debounced refresh (10s default cooldown)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()

    # 4. Verify Updated State
    # Watchman should detect the service registration and update counter to 0
    missing_sensor = hass.states.get(f"sensor.{DOMAIN}_{SENSOR_MISSING_ACTIONS}")
    assert missing_sensor.state == "0", "Missing count should update to 0 after service is registered"

    # 5. Trigger: Remove the service
    hass.services.async_remove("script", "test_service")

    # Allow event processing and debounced refresh
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=11))
    await hass.async_block_till_done()

    # 6. Verify Final State
    # Watchman should detect service removal and increment counter back to 1
    missing_sensor = hass.states.get(f"sensor.{DOMAIN}_{SENSOR_MISSING_ACTIONS}")
    assert missing_sensor.state == "1", "Missing count should return to 1 after service is removed"
    assert "script.test_service" in str(missing_sensor.attributes)
