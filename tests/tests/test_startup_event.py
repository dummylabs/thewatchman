import pytest
from unittest.mock import patch
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from custom_components.watchman.const import CONF_INCLUDED_FOLDERS
from tests import async_init_integration

@pytest.mark.asyncio
async def test_startup_event_listener(hass, tmp_path):
    """Test that startup event listener is registered correctly and works."""
    
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # Mock hass.is_running to False initially to force event subscription
    # We patch it on the instance provided by fixture
    
    # Note: async_init_integration calls async_setup_entry.
    # Inside async_setup_entry, hass.is_running is checked.
    
    with patch.object(type(hass), "is_running", property(lambda self: False)):
        # We need to spy on add_event_handlers to see if it gets called
        with patch("custom_components.watchman.add_event_handlers") as mock_add_handlers:
            await async_init_integration(
                hass,
                add_params={CONF_INCLUDED_FOLDERS: str(config_dir)}
            )
            
            # At this point, setup is done, but startup event hasn't fired.
            assert not mock_add_handlers.called
            
            # Fire the startup event
            hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
            await hass.async_block_till_done()
            
            # If the signature of async_on_home_assistant_started is wrong, 
            # the event bus will log an error and NOT execute the inner logic properly,
            # or it might execute but crash.
            # Ideally we want to verify it didn't crash and called the handler.
            
            assert mock_add_handlers.called, "add_event_handlers should be called after EVENT_HOMEASSISTANT_STARTED"
