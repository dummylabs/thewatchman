"""Test the get_entity_state function in utils."""
import pytest
from homeassistant.core import HomeAssistant

from custom_components.watchman.const import STATELESS_DOMAINS
from custom_components.watchman.utils.utils import get_entity_state


async def test_get_entity_state_missing(hass: HomeAssistant) -> None:
    """Test Scenario A: Entity is completely missing from the State Machine."""
    # Ensure entity does not exist
    assert hass.states.get("sensor.non_existent") is None

    state, _ = get_entity_state(hass, "sensor.non_existent")
    assert state == "missing"


@pytest.mark.parametrize("domain", STATELESS_DOMAINS)
async def test_get_entity_state_stateless_unknown(hass: HomeAssistant, domain: str) -> None:
    """Test that stateless domains return 'available' when state is 'unknown'."""
    entity_id = f"{domain}.test_entity"
    hass.states.async_set(entity_id, "unknown")
    
    state, _ = get_entity_state(hass, entity_id)
    assert state == "available", f"Domain {domain} should be available when unknown"


@pytest.mark.parametrize("domain", STATELESS_DOMAINS)
async def test_get_entity_state_stateless_unavailable(hass: HomeAssistant, domain: str) -> None:
    """Test that stateless domains return 'unavail' when state is 'unavailable'."""
    entity_id = f"{domain}.test_entity"
    hass.states.async_set(entity_id, "unavailable")
    
    state, _ = get_entity_state(hass, entity_id)
    assert state == "unavail", f"Domain {domain} should be unavail when unavailable"


async def test_get_entity_state_valid_timestamp(hass: HomeAssistant) -> None:
    """Test Scenario E: Entity scene.test_scene exists with a valid timestamp state."""
    timestamp = "2024-02-15T12:00:00+00:00"
    hass.states.async_set("scene.test_scene", timestamp)
    
    state, _ = get_entity_state(hass, "scene.test_scene")
    assert state == timestamp


async def test_get_entity_state_friendly_name(hass: HomeAssistant) -> None:
    """Test retrieving friendly name."""
    hass.states.async_set(
        "sensor.test_sensor", 
        "on", 
        attributes={"friendly_name": "Test Sensor Friendly"}
    )
    
    # Test without friendly_names flag
    state, name = get_entity_state(hass, "sensor.test_sensor", friendly_names=False)
    assert state == "on"
    assert name is None

    # Test with friendly_names flag
    state, name = get_entity_state(hass, "sensor.test_sensor", friendly_names=True)
    assert state == "on"
    assert name == "Test Sensor Friendly"
