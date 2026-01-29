"""Test Watchman Status Sensor."""
from unittest.mock import patch, AsyncMock
from homeassistant.core import HomeAssistant, CoreState
from homeassistant.helpers import entity_registry as er
from custom_components.watchman.const import (
    DOMAIN, 
    SENSOR_STATUS, 
    STATE_PARSING, 
    STATE_IDLE
)
from tests import async_init_integration
import asyncio
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
        
    with patch.object(coordinator.hub, 'async_parse', side_effect=mocked_async_parse) as mock_parse:
        # Request a rescan to ensure parsing logic is triggered
        coordinator.request_parser_rescan("Test")
        
        # Force debounce to fire
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=15))
        
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
    state = hass.states.get(entity_id)
    print(f"DEBUG: Final state is {state.state}")
    assert state.state == STATE_IDLE, f"State after parsing should return to {STATE_IDLE}"
        
        