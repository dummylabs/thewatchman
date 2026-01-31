"""Test Watchman Status Sensor."""
from unittest.mock import patch, AsyncMock
from homeassistant.core import HomeAssistant, CoreState
from homeassistant.helpers import entity_registry as er
from custom_components.watchman.const import (
    DOMAIN, 
    SENSOR_STATUS, 
    STATE_PARSING, 
    STATE_IDLE,
    STATE_PENDING,
    STATE_SAFE_MODE,
    LOCK_FILENAME,
    CONF_INCLUDED_FOLDERS
)
from tests import async_init_integration
import asyncio
import os
from datetime import timedelta
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

async def test_status_sensor_states(hass: HomeAssistant):
    """Test the status sensor transitions through all states."""
    
    # 1. Initialize integration
    # In this test environment, setup completes and fires startup events usually,
    # so we expect it to settle at IDLE.
    await async_init_integration(hass)
    
    # Get the sensor entity ID dynamically
    entity_registry = list(er.async_get(hass).entities.values())
    entity_id = next(e.entity_id for e in entity_registry if e.unique_id.endswith(SENSOR_STATUS))
    
    # Verify Initial State (Idle after startup)
    state = hass.states.get(entity_id)
    assert state.state == STATE_IDLE, f"State after startup should be {STATE_IDLE}"
    
    # 2. Transition to PARSING: Trigger a scan
    coordinator = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]
    
    # We use an event to coordinate the check during the 'parsing' phase
    parsing_event = asyncio.Event()
    
    # Mock the hub.async_parse to pause so we can check the state
    original_parse = coordinator.hub.async_parse
    
    async def mocked_async_parse(*args, **kwargs):
        # Notify test that we are inside parsing
        parsing_event.set()
        # Wait a tiny bit to ensure the test loop has a chance to run if needed, 
        # though event set is enough for us to assert.
        # But we actually want to HOLD here until we verify the state.
        
        # We can just return immediately, but we need to check the state "during" this call.
        # Since we can't pause the test execution easily in the main loop while this runs 
        # (because both run on the loop), we can check the state HERE inside the mock.
        
        # Check state inside the execution context
        current_state = hass.states.get(entity_id)
        assert current_state.state == STATE_PARSING, f"State during parsing should be {STATE_PARSING}"
        
        # Call original if needed or just return (we mock it completely)
        return
        
    with patch.object(coordinator.hub, 'async_parse', side_effect=mocked_async_parse) as mock_parse, \
            patch("custom_components.watchman.coordinator.PARSE_COOLDOWN", 0):
        # Request a rescan to ensure parsing logic is triggered
        coordinator.request_parser_rescan("Test")

        # Trigger an update
        task = asyncio.create_task(coordinator.async_request_refresh())

        # Wait for the parsing to trigger
        await parsing_event.wait()

        # Wait for the update to finish
        await task
        await hass.async_block_till_done()

        # Verify the mock assertion passed (implicitly by no exception)
        mock_parse.assert_called()

    # 3. Transition back to IDLE: After update finishes
    # Use a loop to wait for state change as it happens in background task
    async def wait_for_idle():
        while True:
            state = hass.states.get(entity_id)
            if state.state == STATE_IDLE:
                return
            await asyncio.sleep(0.1)

    try:
        await asyncio.wait_for(wait_for_idle(), timeout=2.0)
    except asyncio.TimeoutError:
        pass

    state = hass.states.get(entity_id)
    print(f"DEBUG: Final state is {state.state}")
    assert state.state == STATE_IDLE, f"State after parsing should return to {STATE_IDLE}"

    # 4. Transition to PENDING
    # Now that we are IDLE, if we request another scan within cooldown, it should go to PENDING.
    # We need to ensure cooldown is > 0. The previous patch context has exited.
    
    # We assume default PARSE_COOLDOWN is 60s (defined in const.py).
    # Since we just finished a parse, last_parse_time is set to now.
    
    coordinator.request_parser_rescan("Test Pending")
    await hass.async_block_till_done()
    
    state = hass.states.get(entity_id)
    assert state.state == STATE_PENDING, f"State should be {STATE_PENDING} when requesting scan inside cooldown"


async def test_status_sensor_safe_mode(hass: HomeAssistant):
    """Test the status sensor reports safe mode when lock file exists."""
    
    # Create lock file to simulate previous crash
    lock_path = hass.config.path(".storage", LOCK_FILENAME)
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    
    with open(lock_path, "w") as f:
        f.write("1")
        
    try:
        # Initialize integration
        # Pass CONF_INCLUDED_FOLDERS=None to prevent async_init_integration from changing hass.config.config_dir
        # so that our lock file remains in the correct place.
        await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: None})
        
        # Get the sensor entity ID dynamically
        entity_registry = list(er.async_get(hass).entities.values())
        entity_id = next(e.entity_id for e in entity_registry if e.unique_id.endswith(SENSOR_STATUS))
        
        # Verify Safe Mode State
        state = hass.states.get(entity_id)
        assert state.state == STATE_SAFE_MODE, f"State should be {STATE_SAFE_MODE} due to lock file"
        
        # Verify lock file is removed
        assert not os.path.exists(lock_path), "Lock file should be removed after safe mode startup"
        
    finally:
        # Cleanup if test fails
        if os.path.exists(lock_path):
            os.remove(lock_path)