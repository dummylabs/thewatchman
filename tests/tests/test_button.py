"""Test Watchman button entity."""
from unittest.mock import patch
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from custom_components.watchman.const import DOMAIN, REPORT_SERVICE_NAME
from tests import async_init_integration

async def test_button_press_triggers_report(hass: HomeAssistant):
    """Test that pressing the button triggers the report service."""
    
    await async_init_integration(hass)
    
    # Verify button entity exists
    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("button.watchman_report")
    assert entry
    assert entry.platform == DOMAIN
    
    # Patch the service call to verify it's called
    with patch(
        "homeassistant.core.ServiceRegistry.async_call", 
        wraps=hass.services.async_call
    ) as mock_service_call:
        
        # Press the button
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.watchman_report"}, blocking=True
        )
        await hass.async_block_till_done()
        
        # Verify watchman.report was called
        # mock_service_call captures all service calls.
        # One of them should be (DOMAIN, REPORT_SERVICE_NAME, {})
        
        called_services = [
            (call.args[0] if call.args else call.kwargs.get('domain'), 
             call.args[1] if len(call.args) > 1 else call.kwargs.get('service'))
            for call in mock_service_call.mock_calls
        ]
        
        assert (DOMAIN, REPORT_SERVICE_NAME) in called_services
