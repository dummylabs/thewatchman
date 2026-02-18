"""Test report generation with context."""
from unittest.mock import AsyncMock, MagicMock, patch

from custom_components.watchman.const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
)
from custom_components.watchman.coordinator import WatchmanCoordinator
import pytest


@pytest.mark.asyncio
async def test_report_context_inclusion(hass):
    """Test that the report includes context information."""
    
    # Mock Hub
    hub = MagicMock()
    
    # Mock Parsed Entities with new structure
    parsed_entities = {
        "sensor.test_sensor": {
            "locations": {"config/automations.yaml": [10]},
            "automations": {"automation.kitchen_lights"},
            "occurrences": [
                {
                    "path": "config/automations.yaml",
                    "line": 10,
                    "context": {
                        "parent_type": "automation",
                        "parent_alias": "Kitchen Lights",
                        "parent_id": "auto_123"
                    }
                }
            ]
        },
        "light.living_room": {
            "locations": {"config/scripts.yaml": [5]},
            "automations": {"script.good_night"},
            "occurrences": [
                {
                    "path": "config/scripts.yaml",
                    "line": 5,
                    "context": {
                        "parent_type": "script",
                        "parent_alias": "Good Night",
                        "parent_id": "script_good_night"
                    }
                }
            ]
        },
        "sensor.no_context": {
            "locations": {"config/configuration.yaml": [20]},
            "automations": set(),
            "occurrences": [
                {
                    "path": "config/configuration.yaml",
                    "line": 20,
                    "context": None
                }
            ]
        }
    }
    
    hub.async_get_all_items = AsyncMock(return_value={
        "entities": parsed_entities,
        "services": {}
    })
    hub.async_parse = AsyncMock(return_value=None)
    
    # Setup Coordinator
    entry = MagicMock()
    entry.title = "Watchman"
    coordinator = WatchmanCoordinator(hass, None, entry, hub, version="1.0.0")
    
    try:
        # Mock get_config to allow everything
        def get_config_side_effect(hass, key, default=None):
            return default

        with patch("custom_components.watchman.coordinator.get_config", side_effect=get_config_side_effect):
            # By default hass.states.get returns None (missing) which is what we want
            
            report_data = await coordinator.async_get_detailed_report_data()
            
            missing_entities = report_data["missing_entities"]
            
            # Verify Sensor Context
            sensor_entry = next((e for e in missing_entities if e["id"] == "sensor.test_sensor"), None)
            assert sensor_entry is not None, "Sensor entry missing from report"
            assert sensor_entry["context"]["parent_type"] == "automation"
            assert sensor_entry["context"]["parent_alias"] == "Kitchen Lights"
            
            # Verify Light Context
            light_entry = next((e for e in missing_entities if e["id"] == "light.living_room"), None)
            assert light_entry is not None, "Light entry missing from report"
            assert light_entry["context"]["parent_type"] == "script"
            assert light_entry["context"]["parent_alias"] == "Good Night"
            
            # Verify No Context
            no_context_entry = next((e for e in missing_entities if e["id"] == "sensor.no_context"), None)
            assert no_context_entry is not None, "No context entry missing from report"
            assert no_context_entry["context"] is None
    finally:
        await coordinator.async_shutdown()
        await hass.async_block_till_done()
