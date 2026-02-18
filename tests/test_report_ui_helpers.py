from unittest.mock import MagicMock, patch
from custom_components.watchman.const import REPORT_ENTRY_TYPE_ENTITY
from custom_components.watchman.utils.report import table_renderer, text_renderer

def test_report_ui_helpers_renderer():
    """Test that UI helpers are reported with friendly names instead of file paths."""
    hass = MagicMock()
    
    # Data structure simulating what comes from coordinator/hub
    parsed_list = {
        "light.missing_light": {
            "locations": {
                ".storage/core.config_entries": [42]
            },
            "occurrences": [
                {
                    "path": ".storage/core.config_entries",
                    "line": 42,
                    "context": {
                        "parent_type": "helper_group",
                        "parent_alias": "My Light Group",
                        "parent_id": "entry_id_123"
                    }
                }
            ]
        },
        "sensor.missing_template": {
            "locations": {
                ".storage/core.config_entries": [100]
            },
            "occurrences": [
                {
                    "path": ".storage/core.config_entries",
                    "line": 100,
                    "context": {
                        "parent_type": "helper_template",
                        "parent_alias": "My Template",
                        "parent_id": "entry_id_456"
                    }
                }
            ]
        },
        "switch.missing_file": {
            "locations": {
                "automations.yaml": [227]
            },
            "occurrences": [
                {
                    "path": "automations.yaml",
                    "line": 227,
                    "context": None
                }
            ]
        }
    }
    
    missing_items = ["light.missing_light", "sensor.missing_template", "switch.missing_file"]
    
    # Mock configuration retrieval
    def mock_get_config(hass, key, default=None):
        return default

    # Mock entity state retrieval
    with (
        patch("custom_components.watchman.utils.report.get_entity_state") as mock_state,
        patch("custom_components.watchman.utils.report.get_config", side_effect=mock_get_config),
    ):
        
        mock_state.return_value = ("missing", None)
        
        # Test Text Renderer
        text_output = text_renderer(hass, REPORT_ENTRY_TYPE_ENTITY, missing_items, parsed_list)
        
        # Check for the expected output format
        assert '👥 Group: "My Light Group"' in text_output
        assert '🧩 Template: "My Template"' in text_output
        assert "📄 automations.yaml:227" in text_output
        assert ".storage/core.config_entries" not in text_output

        # Test Table Renderer
        table_output = table_renderer(hass, REPORT_ENTRY_TYPE_ENTITY, missing_items, parsed_list)
        assert '👥 Group: "My Light Group"' in table_output
        assert '🧩 Template: "My Template"' in table_output
        assert "📄 automations.yaml:227" in table_output
