"""Tests for Watchman configuration migration."""
import pytest
from unittest.mock import MagicMock
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from custom_components.watchman import async_migrate_entry
from custom_components.watchman.const import (
    DOMAIN,
    CONF_STARTUP_DELAY,
    CONF_IGNORED_LABELS,
    CONFIG_ENTRY_VERSION,
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_OPTIONS,
)

@pytest.mark.asyncio
async def test_migrate_v1_to_v2(hass: HomeAssistant):
    """Test migration from version 1 (options) to version 2 (data)."""
    
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 1
    mock_entry.minor_version = 1
    mock_entry.data = {}
    mock_entry.options = {
        CONF_STARTUP_DELAY: 15  # Custom value from v1
    }
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    # Mock async_update_entry to capture the result
    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    
    # Check that update was called with migrated data
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_entry = args[0]
    updated_data = kwargs["data"]
    
    assert updated_data[CONF_STARTUP_DELAY] == 15
    assert kwargs["version"] == CONFIG_ENTRY_VERSION
    assert kwargs["minor_version"] == CONFIG_ENTRY_MINOR_VERSION

@pytest.mark.asyncio
async def test_migrate_v2_minor_upgrade_forces_delay(hass: HomeAssistant):
    """Test minor version upgrade enforces minimum startup delay."""
    
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 1 # Previous minor version
    mock_entry.data = {
        CONF_STARTUP_DELAY: 5  # Too small, should be bumped
    }
    mock_entry.options = {}
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check update call
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_data = kwargs["data"]
    
    # Should be updated to default (30)
    assert updated_data[CONF_STARTUP_DELAY] == DEFAULT_OPTIONS[CONF_STARTUP_DELAY]
    assert updated_data[CONF_IGNORED_LABELS] == "" # Should add default labels if missing
    assert kwargs["minor_version"] == 2

@pytest.mark.asyncio
async def test_migrate_v2_minor_upgrade_preserves_valid_delay(hass: HomeAssistant):
    """Test minor version upgrade preserves valid startup delay."""
    
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 1 
    mock_entry.data = {
        CONF_STARTUP_DELAY: 60  # Valid custom value
    }
    mock_entry.options = {}
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check update call
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_data = kwargs["data"]
    
    assert updated_data[CONF_STARTUP_DELAY] == 60
    assert kwargs["minor_version"] == 2

@pytest.mark.asyncio
async def test_migrate_v2_current_version_no_op(hass: HomeAssistant):
    """Test no migration needed if version is current."""
    
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 2 # Already current
    mock_entry.data = {
        CONF_STARTUP_DELAY: 5, # Should remain 5 as migration logic won't run
        CONF_IGNORED_LABELS: ""
    }
    mock_entry.options = {}

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    # Should not be called
    hass.config_entries.async_update_entry.assert_not_called()
