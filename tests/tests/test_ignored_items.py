"""Test exclusion of items via CONF_IGNORED_ITEMS."""
import pytest
from custom_components.watchman.const import (
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    DOMAIN,
)
from tests import async_init_integration
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

@pytest.mark.asyncio
async def test_ignored_items_exact_match(hass: HomeAssistant):
    """Test ignoring specific entities and services by exact name."""
    # We use basic_config.yaml which has:
    # Entities: sensor.skylight, switch.skylight
    # Services: switch.turn_on, switch.turn_off
    
    # We ignore one of each
    ignored = ["sensor.skylight", "switch.turn_off"]
    
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_ITEMS: ignored,
            CONF_IGNORED_STATES: [], # Ensure everything is reported as missing
        },
    )
    
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Check Entities
    # sensor.skylight should be ignored
    # switch.skylight should be reported
    
    entity_attrs = coordinator.data.get("entity_attrs", [])
    missing_entity_ids = [e["id"] for e in entity_attrs]
    
    assert "sensor.skylight" not in missing_entity_ids, "sensor.skylight should be ignored"
    assert "switch.skylight" in missing_entity_ids, "switch.skylight should be reported"
    
    # Check Services
    # switch.turn_off should be ignored
    # switch.turn_on should be reported
    
    service_attrs = coordinator.data.get("service_attrs", [])
    missing_service_ids = [s["id"] for s in service_attrs]
    
    assert "switch.turn_off" not in missing_service_ids, "switch.turn_off should be ignored"
    assert "switch.turn_on" in missing_service_ids, "switch.turn_on should be reported"


@pytest.mark.asyncio
async def test_ignored_items_glob_match(hass: HomeAssistant):
    """Test ignoring items using glob patterns."""
    # We ignore all switches and all services starting with switch.
    ignored = ["switch.*"]
    
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_ITEMS: ignored,
            CONF_IGNORED_STATES: [],
        },
    )
    
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Check Entities
    # switch.skylight should be ignored (matches switch.*)
    # sensor.skylight should be reported
    
    entity_attrs = coordinator.data.get("entity_attrs", [])
    missing_entity_ids = [e["id"] for e in entity_attrs]
    
    assert "switch.skylight" not in missing_entity_ids, "switch.skylight should be ignored by glob"
    assert "sensor.skylight" in missing_entity_ids, "sensor.skylight should be reported"
    
    # Check Services
    # switch.turn_on and switch.turn_off should be ignored (matches switch.*)
    
    service_attrs = coordinator.data.get("service_attrs", [])
    missing_service_ids = [s["id"] for s in service_attrs]
    
    assert "switch.turn_on" not in missing_service_ids
    assert "switch.turn_off" not in missing_service_ids
