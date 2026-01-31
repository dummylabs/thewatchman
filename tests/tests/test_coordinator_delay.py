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




async def test_smart_debounce_priority(hass: HomeAssistant, mock_hub_parse):
    """Test that the longest delay takes precedence (Smart Debounce)."""
    config_entry = await async_init_integration(hass)
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    mock_hub_parse.reset_mock()
    if coordinator.safe_mode:
        coordinator.update_status(STATE_IDLE)
    coordinator._last_parse_time = 0 
    
    # 1. Request rescan with LONG delay (e.g. startup)
    long_delay = 10
    coordinator.request_parser_rescan(reason="startup", delay=long_delay)
    
    # 2. Advance time slightly (e.g. 1s)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    
    # 3. Request rescan with SHORT delay (e.g. config change)
    short_delay = 1
    coordinator.request_parser_rescan(reason="config_change", delay=short_delay)
    
    # 4. Advance time by short_delay + buffer (e.g. +2s total from step 3)
    # Total time from start = 1 + 2 = 3s.
    # Current naive implementation would fire here (1s after step 3).
    # Desired logic: Should NOT fire yet, because we should respect the 10s delay.
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=3))
    await hass.async_block_till_done()
    
    # Assert NOT called yet
    assert mock_hub_parse.call_count == 0
    
    # 5. Advance time to cover the full long_delay relative to the LAST request?
    # Requirement: "отложить парсинг ещё на 10 секунд с момента регистрации второго запроса"
    # So we need to wait 10s from step 3.
    # We are at T=3s (relative to start). Step 3 happened at T=1s.
    # We need to reach T = 1s + 10s = 11s.
    # So advance by another 8s + buffer.
    
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=12))
    await hass.async_block_till_done()
    
    import asyncio
    for _ in range(5):
        if mock_hub_parse.call_count == 1:
            break
        await asyncio.sleep(0.1)
        
    mock_hub_parse.assert_called_once()