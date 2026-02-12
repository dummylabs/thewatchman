"""Test Watchman services."""
from unittest.mock import MagicMock, patch
import pytest
from custom_components.watchman.const import DOMAIN, CONF_IGNORED_LABELS, CONF_STARTUP_DELAY
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

@pytest.mark.asyncio
async def test_set_ignored_labels_service(hass: HomeAssistant):
    """Test set_ignored_labels service."""
    
    # 1. Setup Config Entry
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry",
        version=2,
        minor_version=4,
        data={
            CONF_IGNORED_LABELS: [],
            CONF_STARTUP_DELAY: 0
        }
    )
    config_entry.add_to_hass(hass)
    
    # 2. Setup Label Registry
    mock_registry = MagicMock()
    label1 = MagicMock()
    label1.label_id = "test"
    label2 = MagicMock()
    label2.label_id = "private"
    mock_registry.async_list_labels.return_value = [label1, label2]
    
    with patch("homeassistant.helpers.label_registry.async_get", return_value=mock_registry), \
         patch("custom_components.watchman.DEFAULT_DELAY", 0):
        # Setup integration (registers service)
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        
        try:
            # Test 1: Valid labels
            await hass.services.async_call(
                DOMAIN,
                "set_ignored_labels",
                {"labels": ["test", "private"]},
                blocking=True
            )
            await hass.async_block_till_done() # Wait for possible reload
            
            # Verify config updated
            assert config_entry.data[CONF_IGNORED_LABELS] == ["test", "private"]
            
            # Test 2: Invalid labels -> Exception
            with pytest.raises(ServiceValidationError) as excinfo:
                await hass.services.async_call(
                    DOMAIN,
                    "set_ignored_labels",
                    {"labels": ["test", "invalid_one"]},
                    blocking=True
                )
            await hass.async_block_till_done()
            
            assert "The following labels do not exist: invalid_one" in str(excinfo.value)
            
            # Verify config NOT updated
            assert config_entry.data[CONF_IGNORED_LABELS] == ["test", "private"]
        finally:
            await hass.config_entries.async_unload(config_entry.entry_id)
            await hass.async_block_till_done()
