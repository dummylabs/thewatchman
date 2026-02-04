from datetime import timedelta
from unittest.mock import patch

from custom_components.watchman.const import CONF_INCLUDED_FOLDERS
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from tests import async_init_integration

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.util import dt as dt_util


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
        # We need to spy on subscribe_to_events to see if it gets called
        with patch("custom_components.watchman.coordinator.WatchmanCoordinator.subscribe_to_events") as mock_add_handlers:

            # Initialize integration
            await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: [str(config_dir)]})

            # Since hass is NOT running, handlers should NOT be added yet
            mock_add_handlers.assert_not_called()

            # Fire startup event
            hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
            await hass.async_block_till_done()

            # Advance time to trigger delayed refresh
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
            await hass.async_block_till_done()

            # Now handlers SHOULD be added
            mock_add_handlers.assert_called_once()
