"""Test Watchman Safe Mode."""
import os
import pytest
from unittest.mock import patch
from homeassistant.core import HomeAssistant
from custom_components.watchman.const import (
    DOMAIN,
    LOCK_FILENAME,
    STATE_SAFE_MODE,
    SENSOR_STATUS,
    CONF_INCLUDED_FOLDERS,
)
from tests import async_init_integration

async def test_safe_mode_activates(hass: HomeAssistant, tmp_path):
    """Test that safe mode activates when lock file exists."""
    
    # Setup config dir
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir()
    
    # Create lock file
    lock_file = storage_dir / LOCK_FILENAME
    lock_file.write_text("1")
    
    # Mock hass.config.path to ensure the integration finds our lock file
    with patch.object(hass.config, "path", side_effect=lambda *args: str(config_dir.joinpath(*args))):
        # Initialize integration
        await async_init_integration(
            hass,
            add_params={
                CONF_INCLUDED_FOLDERS: str(config_dir),
            },
        )
    
    # Get coordinator
    coordinator = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]
    
    # Verify Safe Mode
    assert coordinator.safe_mode is True
    assert coordinator.status == STATE_SAFE_MODE
    
    # Verify Status Sensor
    from homeassistant.helpers import entity_registry as er
    ent_reg = er.async_get(hass)
    status_entity_id = next(e.entity_id for e in ent_reg.entities.values() if e.unique_id.endswith(SENSOR_STATUS))
    
    state = hass.states.get(status_entity_id)
    assert state.state == STATE_SAFE_MODE

async def test_safe_mode_prevents_parsing(hass: HomeAssistant, tmp_path):
    """Test that safe mode prevents parsing."""
    
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir()
    (storage_dir / LOCK_FILENAME).write_text("1")

    with patch("custom_components.watchman.hub.WatchmanHub.async_parse") as mock_parse, \
         patch.object(hass.config, "path", side_effect=lambda *args: str(config_dir.joinpath(*args))):
        
        # Initialize integration
        await async_init_integration(hass)
        
        # Verify status is safe mode
        coordinator = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]
        assert coordinator.safe_mode

        # Ensure parse was NOT called
        mock_parse.assert_not_called()
