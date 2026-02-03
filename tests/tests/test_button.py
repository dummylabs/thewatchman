"""Test Watchman button entity."""
from unittest.mock import patch
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.helpers import entity_registry as er
from custom_components.watchman.const import DOMAIN, REPORT_SERVICE_NAME
from tests import async_init_integration

async def test_button_press_triggers_report(hass: HomeAssistant):
    """Test that pressing the button triggers the report service."""
    
    await async_setup_component(hass, "persistent_notification", {})
    await async_init_integration(hass)
    
    # Verify button entity exists
    entity_registry = er.async_get(hass)
    entry = entity_registry.async_get("button.watchman_create_report_file")
    assert entry
    assert entry.platform == DOMAIN
    
    # Patch the service call to verify it's called
    # Also patch async_report_to_file to prevent actual file writing failure (due to empty path in defaults)
    # And patch button.get_config so notification gets a path
    with patch(
        "homeassistant.core.ServiceRegistry.async_call", 
        wraps=hass.services.async_call
    ) as mock_service_call, \
         patch("custom_components.watchman.services.async_report_to_file") as mock_write_file, \
         patch("custom_components.watchman.button.get_config", return_value="/tmp/report.txt"):
        
        # Press the button
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.watchman_create_report_file"}, blocking=True
        )
        await hass.async_block_till_done()
        
        # Verify watchman.report was called with correct parameters
        # mock_service_call captures all service calls.
        
        found_call = False
        found_notify = False
        
        for call in mock_service_call.mock_calls:
            domain = call.args[0] if call.args else call.kwargs.get('domain')
            service = call.args[1] if len(call.args) > 1 else call.kwargs.get('service')
            
            if domain == DOMAIN and service == REPORT_SERVICE_NAME:
                service_data = call.args[2] if len(call.args) > 2 else call.kwargs.get('service_data')
                if service_data == {"parse_config": True}:
                    found_call = True
            
            if domain == "persistent_notification" and service == "create":
                service_data = call.args[2] if len(call.args) > 2 else call.kwargs.get('service_data')
                if service_data and service_data.get("title") == "Watchman":
                    found_notify = True

        assert found_call, "watchman.report service was not called with parse_config=True"
        assert found_notify, "persistent_notification.create was not called with title='Watchman'"
