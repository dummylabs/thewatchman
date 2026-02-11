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
    services = [i["entity_id"] for i in items if i["item_type"] == "service"]

    # 'input_boolean.mode' is definitely an entity
    assert "input_boolean.mode" in entities

    # 'light.turn_on' and 'script.notify_error' are services and now
    # correctly identified as such by the new action template logic.
    assert "light.turn_on" in services
    assert "script.notify_error" in services

def test_multiline_action_template():
    """Test multiline action templates with mixed services and entities."""
    content = """
- alias: system_start_stop_flag_set 
  id: system_start_stop_flag_set 
  initial_state: true 
  triggers: 
    - trigger: homeassistant 
      event: start 
      id: "homeassistant_start" 
    - trigger: homeassistant 
      event: shutdown 
  actions: 
    - action: > 
        {% if trigger.id == 'homeassistant_start' -%} 
            input_boolean.turn_off 
        {% else -%} 
            input_boolean.turn_on 
        {% endif %} 
      data: 
        entity_id: input_boolean.ha_shutdown 
    - action: > 
        {% if trigger.id == 'homeassistant_start' -%} 
            automation.turn_on 
        {% else -%} 
            automation.turn_off 
        {% endif %}
    """
    items = _parse_content(content, "yaml")
    
    services = [i["entity_id"] for i in items if i["item_type"] == "service"]
    entities = [i["entity_id"] for i in items if i["item_type"] == "entity"]

    # Verify precise line numbers
    # Line 13: action: >
    # Line 14: {% if trigger.id == 'homeassistant_start' -%}
    # Line 15:     input_boolean.turn_off
    # Line 16: {% else -%}
    # Line 17:     input_boolean.turn_on
    # Line 18: {% endif %}
    
    # We need to find the items to check their line numbers
    item_off = next(i for i in items if i["entity_id"] == "input_boolean.turn_off")
    item_on = next(i for i in items if i["entity_id"] == "input_boolean.turn_on")
    item_shutdown = next(i for i in items if i["entity_id"] == "input_boolean.ha_shutdown")
    
    # Debug output showed (before fix):
    # line_no=12 for the first action block
    # input_boolean.turn_off: offset=1 -> line 13
    # input_boolean.turn_on: offset=3 -> line 15
    # input_boolean.ha_shutdown: line 19
    
    # After fix (+1 for block scalar):
    # input_boolean.turn_off: 12 + 1 + 1 = 14
    # input_boolean.turn_on: 12 + 3 + 1 = 16
    # input_boolean.ha_shutdown: line 19 (remains unchanged as it is not a block scalar)
    
    assert item_off["line"] == 14
    assert item_on["line"] == 16
    assert item_shutdown["line"] == 19

    # These should be detected as services because they match _STRICT_SERVICE_PATTERN 
    # and are in an action template on lines that DON'T have template markers.
    assert "input_boolean.turn_off" in services
    assert "input_boolean.turn_on" in services
    assert "automation.turn_on" in services
    assert "automation.turn_off" in services

    # This is a standard entity in data block
    assert "input_boolean.ha_shutdown" in entities

    # trigger.id should NOT be detected as anything
    assert "trigger.id" not in entities
    assert "trigger.id" not in services

