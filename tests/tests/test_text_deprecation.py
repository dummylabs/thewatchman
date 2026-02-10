"""Test Watchman Text Entity empty value logic."""
from unittest.mock import MagicMock, patch
import pytest
from custom_components.watchman.const import DOMAIN, CONF_IGNORED_LABELS
from custom_components.watchman.text import WatchmanIgnoredLabelsText
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

@pytest.mark.asyncio
async def test_text_entity_empty_clears_config(hass: HomeAssistant):
    """Test that setting text entity to empty string clears the config entry."""
    
    # 1. Setup Config Entry with existing labels
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry",
        version=2,
        minor_version=4,
        data={CONF_IGNORED_LABELS: ["kitchen", "living_room"]}
    )
    config_entry.add_to_hass(hass)
    
    # Mock Label Registry
    mock_registry = MagicMock()
    mock_registry.async_list_labels.return_value = [] 
    
    mock_coordinator = MagicMock()
    mock_coordinator.config_entry = config_entry
    mock_coordinator.version = "1.0"
    
    entity = WatchmanIgnoredLabelsText(hass, mock_coordinator)
    entity.entity_id = "text.watchman_ignored_labels"
    
    with patch("homeassistant.helpers.label_registry.async_get", return_value=mock_registry):
        # Call async_set_value with empty string
        await entity.async_set_value("")
        
        # Verify config entry updated to empty list
        assert config_entry.data[CONF_IGNORED_LABELS] == []
        
        # Verify native value is empty
        assert entity.native_value == ""
        
        # Verify deprecation issue created
        issue_registry = ir.async_get(hass)
        issue = issue_registry.async_get_issue(DOMAIN, "deprecated_ignored_labels_entity")
        assert issue is not None
        assert issue.severity == ir.IssueSeverity.WARNING
        assert issue.translation_key == "deprecated_text_entity"

@pytest.mark.asyncio
async def test_text_entity_invalid_label_behavior(hass: HomeAssistant):
    """Test behavior when invalid label is entered."""
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry_2",
        data={CONF_IGNORED_LABELS: ["existing"]}
    )
    config_entry.add_to_hass(hass)
    
    mock_coordinator = MagicMock()
    mock_coordinator.config_entry = config_entry
    mock_coordinator.version = "1.0"
    
    entity = WatchmanIgnoredLabelsText(hass, mock_coordinator)
    entity.entity_id = "text.watchman_ignored_labels"
    
    # Mock registry with "existing"
    mock_registry = MagicMock()
    label_existing = MagicMock()
    label_existing.label_id = "existing"
    mock_registry.async_list_labels.return_value = [label_existing]
    
    # Mock notification service call to verify it's called
    calls = async_mock_service(hass, "persistent_notification", "create")
    
    with patch("homeassistant.helpers.label_registry.async_get", return_value=mock_registry):
        # User inputs: "existing, invalid_one"
        # Expectation in CURRENT implementation: "existing" saved, "invalid_one" ignored (warned).
        
        await entity.async_set_value("existing, invalid_one")
        
        # Check config (should contain valid only)
        assert config_entry.data[CONF_IGNORED_LABELS] == ["existing"]
        assert entity.native_value == "existing"
        
        # Check warning notification
        assert len(calls) == 1
        assert calls[0].data["title"] == "Watchman: Invalid Labels"
        assert "invalid_one" in calls[0].data["message"]
        
        # Verify deprecation issue created
        issue_registry = ir.async_get(hass)
        issue = issue_registry.async_get_issue(DOMAIN, "deprecated_ignored_labels_entity")
        assert issue is not None