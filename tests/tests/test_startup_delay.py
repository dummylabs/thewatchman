"""Tests for Watchman startup delay logic."""
import pytest
from unittest.mock import patch
from homeassistant.core import HomeAssistant
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from custom_components.watchman.const import (
    DOMAIN,
    CONF_STARTUP_DELAY,
    DEFAULT_DELAY,
)
from tests import async_init_integration

@pytest.mark.asyncio
async def test_startup_delay_on_ha_start(hass: HomeAssistant):
    """Test that configured startup delay is used when HA starts."""
    
    # Mock HA state to NOT running, so it waits for event
    hass.is_running = False
    
    # Mock coordinator.request_parser_rescan to inspect arguments
    with patch("custom_components.watchman.WatchmanCoordinator.request_parser_rescan") as mock_rescan:
        
        await async_init_integration(
            hass, 
            add_params={CONF_STARTUP_DELAY: 30}
        )
        
        # Should not be called yet
        mock_rescan.assert_not_called()
        
        # Fire event
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()
        
        # Check call
        # We expect at least one call with reason="startup"
        # Since async_init_integration waits for idle, other calls might happen (like 'service_call' if services registered)
        # But we look for the one with reason="startup"
        
        calls = mock_rescan.call_args_list
        startup_call = None
        for call in calls:
            if call.kwargs.get("reason") == "startup":
                startup_call = call
                break
        
        assert startup_call is not None
        assert startup_call.kwargs["delay"] == 30

@pytest.mark.asyncio
async def test_startup_delay_when_ha_running(hass: HomeAssistant):
    """Test that default delay is used when HA is already running."""
    
    # Mock HA state to RUNNING
    hass.is_running = True
    
    with patch("custom_components.watchman.WatchmanCoordinator.request_parser_rescan") as mock_rescan:
        
        await async_init_integration(
            hass, 
            add_params={CONF_STARTUP_DELAY: 30}
        )
        
        await hass.async_block_till_done()
        
        calls = mock_rescan.call_args_list
        startup_call = None
        for call in calls:
            if call.kwargs.get("reason") == "startup":
                startup_call = call
                break
        
        assert startup_call is not None
        # async_init_integration patches DEFAULT_DELAY to 0 for speed
        assert startup_call.kwargs["delay"] == 0
