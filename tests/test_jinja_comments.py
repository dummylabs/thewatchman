"""Test parsing of Jinja2 comments."""
import asyncio
from pathlib import Path
import pytest
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

def test_jinja_comments_ignored(parser_client, tmp_path):
    """Test that entities inside Jinja2 comments are ignored."""
    yaml_content = """
sensor:
  - platform: template
    sensors:
      test_sensor:
        value_template: >
          {# sensor.should_be_ignored #}
          {{ states('sensor.valid_entity') }}
          {#
            sensor.ignored_one
            sensor.ignored_two
          #}
          {{ states('sensor.another_valid_entity') }}
"""
    test_file = tmp_path / "test_jinja_comments.yaml"
    test_file.write_text(yaml_content, encoding="utf-8")
    
    # Parse the directory
    asyncio.run(parser_client.async_parse(str(tmp_path), []))
    
    # Get results from DB
    items = parser_client.get_found_items(item_type='all')
    entities = [item[0] for item in items if item[3] == 'entity']
    
    # Assertions
    assert "sensor.valid_entity" in entities, "Should find valid entity 1"
    assert "sensor.another_valid_entity" in entities, "Should find valid entity 2"
    
    assert "sensor.should_be_ignored" not in entities, "Should ignore single-line comment"
    assert "sensor.ignored_one" not in entities, "Should ignore multi-line comment entity 1"
    assert "sensor.ignored_two" not in entities, "Should ignore multi-line comment entity 2"

def test_jinja_comments_line_numbers(parser_client, tmp_path):
    """Test that line numbers are preserved when ignoring comments."""
    yaml_content = """
action: |
  {#
    sensor.ignored_one
    sensor.ignored_two
  #}
  service: light.turn_on
  target:
    entity_id: light.valid_entity
"""
    # Line 1: empty (yaml starts at 2)
    # Line 2: action: |
    # Line 3:   {#
    # Line 4:     sensor.ignored_one
    # Line 5:     sensor.ignored_two
    # Line 6:   #}
    # Line 7:   service: light.turn_on
    # Line 8:   target:
    # Line 9:     entity_id: light.valid_entity

    test_file = tmp_path / "test_line_numbers.yaml"
    test_file.write_text(yaml_content, encoding="utf-8")

    # Run the parser to get detailed items
    # We need access to the found items directly, so we use async_scan then query DB or use get_found_items
    asyncio.run(parser_client.async_scan(str(tmp_path), []))

    items = parser_client.get_found_items(item_type='all')

    # Helper to find item
    def find_item(entity_id):
        for item in items:
            # item structure: (entity_id, path, line, item_type, parent_type, parent_alias, parent_id)
            if item[0] == entity_id:
                return item
        return None

    # Verify ignored
    assert find_item("sensor.ignored_one") is None
    assert find_item("sensor.ignored_two") is None

    # Verify valid service
    # Structure: (entity_id, path, line, item_type, ...)
    service_item = find_item("light.turn_on")
    assert service_item is not None
    
    # light.turn_on is on line 7 (1-based).
    # yaml_loader.py returns 1-based line numbers (start_mark.line + 1).
    assert service_item[2] == 7, f"Expected line 7 (1-based), got {service_item[2]}"
    
    # Verify valid entity
    entity_item = find_item("light.valid_entity")
    assert entity_item is not None
    # light.valid_entity is on line 9 (1-based).
    assert entity_item[2] == 9, f"Expected line 9 (1-based), got {entity_item[2]}"

