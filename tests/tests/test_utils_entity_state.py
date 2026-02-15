"""Test the get_entity_state function in utils."""
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.watchman.utils.utils import get_entity_state


async def test_get_entity_state_missing(hass: HomeAssistant) -> None:
    """Test Scenario A: Entity is completely missing from the State Machine."""
    # Ensure entity does not exist
    assert hass.states.get("sensor.non_existent") is None

    state, _ = get_entity_state(hass, "sensor.non_existent")
    assert state == "missing"


async def test_get_entity_state_scene_unknown(hass: HomeAssistant) -> None:
    """Test Scenario B: Entity scene.test_scene exists with state unknown."""
    hass.states.async_set("scene.test_scene", "unknown")
    
    state, _ = get_entity_state(hass, "scene.test_scene")
    assert state == "available"


async def test_get_entity_state_button_unknown(hass: HomeAssistant) -> None:
    """Test Scenario C: Entity button.test_button exists with state unknown."""
    hass.states.async_set("button.test_button", "unknown")
    
    state, _ = get_entity_state(hass, "button.test_button")
    assert state == "available"


async def test_get_entity_state_input_button_unknown(hass: HomeAssistant) -> None:
    """Test Scenario C (extra): Entity input_button.test_button exists with state unknown."""
    hass.states.async_set("input_button.test_button", "unknown")
    
    state, _ = get_entity_state(hass, "input_button.test_button")
    assert state == "available"


async def test_get_entity_state_scene_unavailable(hass: HomeAssistant) -> None:
    """Test Scenario D: Entity scene.test_scene exists with state unavailable."""
    hass.states.async_set("scene.test_scene", "unavailable")
    
    state, _ = get_entity_state(hass, "scene.test_scene")
    assert state == "unavail"


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
