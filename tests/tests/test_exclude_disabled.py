"""Test for excluding disabled automations functionality."""
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

from custom_components.watchman.const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
)
from custom_components.watchman.coordinator import WatchmanCoordinator
import pytest


@pytest.mark.asyncio
async def test_exclude_disabled_automations(hass):
    """Test excluding entities from disabled automations."""
    # Mock Hub using AsyncMock for async methods
    hub = MagicMock()

    # Mock parsed entities
    # sensor.sensor_1 and automation.automation_1 are found in config files
    parsed_entities = {
        "sensor.sensor_1": {
            "locations": {"config/automations.yaml": [10]},
            "automations": {"automation.automation_2"},
            "occurrences": []
        },
        "automation.automation_1": {
            "locations": {"config/automations.yaml": [12]},
            "automations": {"automation.automation_2"},
            "occurrences": []
        },
        "sensor.shared_sensor": {
            "locations": {"config/scripts.yaml": [5]},
            "automations": {"script.active_script", "script.disabled_script"},
            "occurrences": []
        }
    }

    # Mock parsed services
    # service.test_service is in disabled automation
    parsed_services = {
        "service.test_service": {
            "locations": {"config/automations.yaml": [15]},
            "automations": {"automation.automation_2"},
            "occurrences": []
        }
    }

    hub.async_get_all_items = AsyncMock(return_value={
        "entities": parsed_entities,
        "services": parsed_services
    })

    hub.async_parse = AsyncMock(return_value=None)    
    # Ensure is_scanning is False so coordinator doesn't skip update

    type(hub).is_scanning = PropertyMock(return_value=False)

    # Set states
    # automation.automation_2: OFF (disabled)
    hass.states.async_set("automation.automation_2", "off")
    # script.active_script: ON (active)
    hass.states.async_set("script.active_script", "on")
    # script.disabled_script: OFF (disabled)
    hass.states.async_set("script.disabled_script", "off")

    # sensor.sensor_1, automation.automation_1, sensor.shared_sensor, service.test_service are NOT set (missing)

    # Mock Config Entry
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.title = "Watchman Test"
    entry.runtime_data = MagicMock()
    entry.runtime_data.force_parsing = False

    # Setup Coordinator
    coordinator = WatchmanCoordinator(hass, None, entry, hub, version="0.0.0")

    # Step 1: Flag is FALSE
    # Mock get_config to return False for CONF_EXCLUDE_DISABLED_AUTOMATION
    # We need to patch get_config imported in coordinator
    with patch("custom_components.watchman.coordinator.get_config") as mock_get_config:
        def get_config_side_effect(hass, key, default=None):
            if key == CONF_EXCLUDE_DISABLED_AUTOMATION:
                return False
            # Allow other configs to return default
            return default
        mock_get_config.side_effect = get_config_side_effect

        # Step 2: Update Data
        await coordinator._async_update_data()

        # Verify missing entities
        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]

        service_attrs = coordinator.data.get("service_attrs", [])
        missing_service_ids = [s["id"] for s in service_attrs]

        assert "sensor.sensor_1" in missing_entity_ids, "sensor.sensor_1 should be missing when exclusion is OFF"
        assert "automation.automation_1" in missing_entity_ids, "automation.automation_1 should be missing when exclusion is OFF"
        assert "sensor.shared_sensor" in missing_entity_ids, "sensor.shared_sensor should be missing when exclusion is OFF"
        assert "service.test_service" in missing_service_ids, "service.test_service should be missing when exclusion is OFF"

    # Step 3: Set Flag to TRUE
    with patch("custom_components.watchman.coordinator.get_config") as mock_get_config:
        def get_config_side_effect(hass, key, default=None):
            if key == CONF_EXCLUDE_DISABLED_AUTOMATION:
                return True
            return default
        mock_get_config.side_effect = get_config_side_effect

        # Trigger update again
        await coordinator._async_update_data()

        # Step 4: Verify results
        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]

        service_attrs = coordinator.data.get("service_attrs", [])
        missing_service_ids = [s["id"] for s in service_attrs]

        # sensor_1 and automation_1 only in disabled automation -> Should be EXCLUDED (NOT in missing_ids)
        assert "sensor.sensor_1" not in missing_entity_ids, "sensor.sensor_1 should be excluded"
        assert "automation.automation_1" not in missing_entity_ids, "automation.automation_1 should be excluded"

        # shared_sensor is in one active script -> Should be INCLUDED (in missing_ids)
        assert "sensor.shared_sensor" in missing_entity_ids, "sensor.shared_sensor should be included because it is used by an active script"

        # test_service is only in disabled automation -> Should be EXCLUDED
        assert "service.test_service" not in missing_service_ids, "service.test_service should be excluded"