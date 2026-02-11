import pytest
from custom_components.watchman.utils.parser_core import _recursive_search, is_template
from custom_components.watchman.utils.parser_core import _parse_content

def test_is_template():
    """Test template detection logic."""
    assert is_template("[[[ code ]]]") is True
    assert is_template("  [[[ code ]]]") is True
    assert is_template("{{ state }}") is True
    assert is_template("{% if True %}") is True
    assert is_template("plain_string") is False
    assert is_template("service: light.turn_on") is False

def test_reproduction_case():
    """Test reproduction case for button card template."""
    with open("tests/data/lovelace_button_card.yaml", "r") as f:
        content = f.read()

    items = _parse_content(content, "yaml")
    
    entities = [i["entity_id"] for i in items if i["item_type"] == "entity"]
    services = [i["entity_id"] for i in items if i["item_type"] == "service"]

    assert "switch.pool_pump" in entities
    assert "light.turn_on" in services
    
    # Ensure switch.pool_pump is NOT in services
    assert "switch.pool_pump" not in services

def test_service_template_ambiguity():
    """Test that entities inside a service_template are correctly identified as entities."""
    with open("tests/data/complex_service_template.yaml", "r") as f:
        content = f.read()

    items = _parse_content(content, "yaml")

    entities = [i["entity_id"] for i in items if i["item_type"] == "entity"]
    
    # 'input_boolean.mode' is definitely an entity
    assert "input_boolean.mode" in entities
    
    # 'light.turn_on' and 'script.notify_error' are services but inside a template,
    # so parser should see them as 'entity' (because they are inside a template block).
    assert "light.turn_on" in entities
    assert "script.notify_error" in entities

