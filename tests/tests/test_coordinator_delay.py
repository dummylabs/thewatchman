import pytest
from unittest.mock import patch, AsyncMock
from datetime import timedelta
import time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from custom_components.watchman.const import DOMAIN, PARSE_COOLDOWN, STATE_PENDING, STATE_IDLE
from custom_components.watchman.coordinator import WatchmanCoordinator
from tests import async_init_integration

@pytest.fixture
def mock_hub_parse():
    with patch("custom_components.watchman.hub.WatchmanHub.async_parse", new_callable=AsyncMock) as mock_parse:
        yield mock_parse

async def test_debounce_rescan(hass: HomeAssistant, mock_hub_parse):
    """Test that multiple rescan requests are debounced."""
    config_entry = await async_init_integration(hass)
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Reset mock and coordinator state
    mock_hub_parse.reset_mock()
    if coordinator.safe_mode:
        coordinator.update_status(STATE_IDLE)
    coordinator._last_parse_time = 0 # Ensure no cooldown issues for this test
    
    # 1. Request rescan with delay
    coordinator.request_parser_rescan(reason="test1", delay=2)
    assert coordinator._delay_unsub is not None
    assert coordinator.status == STATE_PENDING
    
    # 2. Advance time by 1s (halfway)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    
    # Verify not parsed yet
    mock_hub_parse.assert_not_called()
    
    # 3. Request rescan again (should reset timer)
    coordinator.request_parser_rescan(reason="test2", delay=2)
    
    # 4. Advance time by 1.5s (original timer would have fired at 2.0s, now at 1.0+1.5=2.5s)
    # Total time from start: 2.5s.
    # First request was at T=0. Second at T=1.
    # If first request was active, it would fire at T=2.
    # Since we reset at T=1 with delay=2, it should fire at T=3.
    
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1.5))
    await hass.async_block_till_done()
    
    # Should still not be called (T=2.5 < T=3)
    mock_hub_parse.assert_not_called()
    
    # 5. Advance time to T=3.1
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=0.6))
    await hass.async_block_till_done()
    
    # Should be called now
    await hass.async_block_till_done()
    import asyncio
    await asyncio.sleep(0.1)
    mock_hub_parse.assert_called_once()


async def test_force_rescan(hass: HomeAssistant, mock_hub_parse):
    """Test that force=True bypasses delay."""
    config_entry = await async_init_integration(hass)
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    mock_hub_parse.reset_mock()
    if coordinator.safe_mode:
        coordinator.update_status(STATE_IDLE)
    coordinator._last_parse_time = 0

    # 1. Request rescan with delay
    coordinator.request_parser_rescan(reason="test_delay", delay=5)
    assert coordinator._delay_unsub is not None
    
    # 2. Immediately force rescan
    coordinator.request_parser_rescan(reason="test_force", force=True)
    
    assert coordinator._delay_unsub is None
    # Wait for background task
    await hass.async_block_till_done()
    import asyncio
    for _ in range(5):
        if mock_hub_parse.call_count == 1:
            break
        await asyncio.sleep(0.1)
    
    mock_hub_parse.assert_called_once()

async def test_force_rescan_during_cooldown(hass: HomeAssistant, mock_hub_parse):
    """Test that force=True correctly cancels a pending cooldown timer."""
    config_entry = await async_init_integration(hass)
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    mock_hub_parse.reset_mock()
    if coordinator.safe_mode:
        coordinator.update_status(STATE_IDLE)
    
    # 1. Simulate a completed parse recently
    coordinator._last_parse_time = time.time()
    
    # 2. Request rescan. It should hit cooldown logic.
    coordinator.request_parser_rescan(reason="test_trigger_cooldown", delay=1)
    
    # Advance time to expire the delay (1s) so it moves to cooldown state
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1.1))
    await hass.async_block_till_done()
    
    # Cooldown timer should be active now
    assert coordinator._cooldown_unsub is not None
    assert coordinator.status == STATE_PENDING
    
    # 3. Request force rescan. This should CANCEL the cooldown timer.
    # If the bug exists (trying to call the handle), this will raise TypeError.
    coordinator.request_parser_rescan(reason="test_force_cooldown", force=True)
    
    assert coordinator._cooldown_unsub is None
    await hass.async_block_till_done()
    
    import asyncio
    for _ in range(5):
        if mock_hub_parse.call_count == 1:
            break
        await asyncio.sleep(0.1)

    mock_hub_parse.assert_called_once()


async def test_delay_and_cooldown(hass: HomeAssistant, mock_hub_parse):
    """Test interaction between delay and cooldown."""
    config_entry = await async_init_integration(hass)
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # 1. Simulate a completed parse
    mock_hub_parse.reset_mock()
    if coordinator.safe_mode:
        coordinator.update_status(STATE_IDLE)
    
    # We need to manually invoke what _execute_parse does because calling it directly
    # will trigger the actual logic which we want, BUT we want to ensure it works
    # even if we are in safe mode (which we cleared).
    await coordinator._execute_parse()
    
    # Now _last_parse_time is set to approx current time
    # Force _last_parse_time to be exactly now to simplify calc
    coordinator._last_parse_time = time.time()
    
    mock_hub_parse.reset_mock()
    
    # 2. Request rescan with small delay
    delay = 1
    coordinator.request_parser_rescan(reason="test_cooldown", delay=delay)
    
    # 3. Advance time to pass the delay
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=delay + 0.1))
    await hass.async_block_till_done()
    
    # At this point, delay expired. But cooldown (60s) is active.
    # So it should NOT have parsed, but scheduled a cooldown wait.
    mock_hub_parse.assert_not_called() 
    
    # Now check
    assert coordinator._cooldown_unsub is not None
    assert coordinator.status == STATE_PENDING
    
    
    # 4. Advance time to past cooldown
    # We are at T=1.1s. Cooldown is 60s. Need to wait ~59s.
    # Instead of patching time.time, we artificially move the last parse time back
    # so that the current real time satisfies the cooldown check.
    coordinator._last_parse_time -= (PARSE_COOLDOWN + 5)

    # We still need to fire time changed to trigger the pending call_later callback
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=PARSE_COOLDOWN + 5))
    await hass.async_block_till_done()
    
    # Retry a few times to allow background task to complete
    import asyncio
    for _ in range(10):
        if mock_hub_parse.call_count == 1:
            break
        await asyncio.sleep(0.1)
    
    mock_hub_parse.assert_called_once()