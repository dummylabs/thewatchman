"""Tests for watchman integration setup and removal."""
import os

from custom_components.watchman.const import DB_FILENAME
from tests import async_init_integration

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


async def test_integration_removal_cleanup(hass: HomeAssistant):
    """Test that the database file is removed when the integration is deleted."""
    # 1. Setup integration
    config_entry = await async_init_integration(hass)
    assert config_entry.state == ConfigEntryState.LOADED

    # 2. Verify DB file exists
    db_path = hass.config.path(".storage", DB_FILENAME)
    # Ensure directory exists for the test environment
    assert os.path.exists(db_path)

    # 3. Remove integration
    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    # 4. Verify DB file is removed
    assert not os.path.exists(db_path)
