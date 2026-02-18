"""Test handling of disabled automations warnings."""
from unittest.mock import MagicMock, patch

from custom_components.watchman.const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    CONF_IGNORED_STATES,
)
from custom_components.watchman.coordinator import (
    FilterContext,
    WatchmanCoordinator,
    renew_missing_items_list,
)
from custom_components.watchman.utils.utils import set_obfuscation_config
import pytest
from homeassistant.helpers import entity_registry as er

@pytest.mark.asyncio
async def test_registry_disabled_automation_warning_suppression(hass):
    """Test that warnings are suppressed for registry-disabled automations."""
    # Disable obfuscation for clear assertions
    set_obfuscation_config(False)
    
    # Setup Entity Registry
    registry = er.async_get(hass)
    
    # Create a registry-disabled automation
    # We use async_get_or_create to add it
    entry = registry.async_get_or_create(
        "automation",
        "test",
        "disabled_auto",
        suggested_object_id="disabled_auto",
        disabled_by=er.RegistryEntryDisabler.USER
    )
    
    # Create an active automation (state 'on')
    registry.async_get_or_create(
        "automation",
        "test",
        "active_auto",
        suggested_object_id="active_auto",
    )
    hass.states.async_set("automation.active_auto", "on")
    
    # Create an automation that is missing from registry AND states (should warn)
    # No registry entry, no state
    
    # Mock Hub (minimal)
    hub = MagicMock()
    
    # Mock Config Entry
    config_entry = MagicMock()
    config_entry.data = {}
    config_entry.title = "Test"
    
    # Init Coordinator
    coordinator = WatchmanCoordinator(hass, None, config_entry, hub, "1.0")
    
    # Patch config to enable exclude_disabled (so build_filter_context logic runs fully)
    with patch("custom_components.watchman.coordinator.get_config", side_effect=lambda h, k, d=None: True if k == CONF_EXCLUDE_DISABLED_AUTOMATION else d):
        
        # 1. Verify _build_filter_context logic
        # It should identify automation.disabled_auto as disabled
        ctx = coordinator._build_filter_context()
        
        assert "automation.disabled_auto" in ctx.disabled_automations
        assert "automation.active_auto" not in ctx.disabled_automations
        
        # 2. Verify renew_missing_items_list logic
        # parsed_list simulates entities used by these automations
        parsed_list = {
            "sensor.test_disabled": {
                "automations": ["automation.disabled_auto"],
                "locations": {"test.yaml": [1]},
                "occurrences": []
            },
            "sensor.test_missing": {
                "automations": ["automation.missing_auto"],
                "locations": {"test.yaml": [2]},
                "occurrences": []
            }
        }
        
        # Capture logs
        with patch("custom_components.watchman.coordinator._LOGGER") as mock_logger:
            renew_missing_items_list(hass, parsed_list, ctx, "entity")
            
            # Should warn for missing_auto
            # We expect warning: "? Unable to locate automation: automation.missing_auto ..."
            
            # Should NOT warn for disabled_auto
            
            warnings = [call[0][0] for call in mock_logger.warning.call_args_list]
            
            # Check for missing_auto warning
            missing_warned = any("automation.missing_auto" in w for w in warnings)
            assert missing_warned, f"Should warn about truly missing automation. Warnings: {warnings}"
            
            # Check for disabled_auto warning
            disabled_warned = any("automation.disabled_auto" in w for w in warnings)
            assert not disabled_warned, "Should NOT warn about registry-disabled automation"
