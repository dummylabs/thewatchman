"""Test filtering logic in WatchmanHub."""
from unittest.mock import MagicMock, patch

from custom_components.watchman.hub import WatchmanHub
import pytest


def test_hub_automations_filtering(hass):
    """Test that only automations and scripts are added to the automations set."""
    
    hub = WatchmanHub(hass, "dummy.db")
    
    # Mock Parser
    hub._parser = MagicMock()
    
    # Mock get_found_items return values
    # Format: (entity_id, path, line, item_type, parent_type, parent_alias, parent_id)
    mock_items = [
        ("sensor.in_automation", "config/automations.yaml", 10, "entity", "automation", "Auto 1", "automation.auto_1"),
        ("sensor.in_script", "config/scripts.yaml", 5, "entity", "script", "Script 1", "script.script_1"),
        ("sensor.in_group", "config/groups.yaml", 1, "entity", "group", "Group 1", "group.group_1"),
        ("sensor.in_template", "config/templates.yaml", 2, "entity", "template", "Template 1", "template.template_1"),
    ]
    
    hub._parser.get_found_items.return_value = mock_items
    
    # Run
    # We need to patch get_config to avoid errors
    with patch("custom_components.watchman.utils.utils.get_config", return_value=[]):
        all_items = hub._get_all_items_sync()
        parsed = all_items["entities"]
    
    # Verify Automation
    assert "automation.auto_1" in parsed["sensor.in_automation"]["automations"]
    
    # Verify Script
    assert "script.script_1" in parsed["sensor.in_script"]["automations"]
    
    # Verify Group (Should be excluded from automations set)
    assert "group.group_1" not in parsed["sensor.in_group"]["automations"]
    assert len(parsed["sensor.in_group"]["automations"]) == 0
    
    # Verify Template (Should be excluded from automations set)
    assert "template.template_1" not in parsed["sensor.in_template"]["automations"]
    assert len(parsed["sensor.in_template"]["automations"]) == 0
    
    # Verify Context is still preserved in occurrences
    assert parsed["sensor.in_group"]["occurrences"][0]["context"]["parent_type"] == "group"
    assert parsed["sensor.in_group"]["occurrences"][0]["context"]["parent_id"] == "group.group_1"
