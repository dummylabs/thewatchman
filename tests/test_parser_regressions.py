"""Tests for parser regressions."""
import asyncio
import os
from pathlib import Path

from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest


@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

def test_template_false_positive(parser_client, new_test_data_dir):
    """Test that template files with trigger/action are NOT identified as automations."""
    yaml_file = Path(new_test_data_dir) / "yaml_config" / "template_false_positive.yaml"
    yaml_dir = str(yaml_file.parent)

    # Parse just this file (but scanning dir scans all, so rely on specific entity checks)
    asyncio.run(parser_client.async_parse(yaml_dir, []))
    items = parser_client.get_found_items(item_type='all')
    entities = [item[0] for item in items if item[3] == 'entity']

    # Check entity in action target
    # NOTE: todo.cleaning is in 'action' block.
    assert "todo.cleaning" in entities

    context = parser_client.get_automation_context("todo.cleaning")
    assert context
    # Should be False because it's a template file, not an automation
    assert context["is_automation_context"] is False, "Template file incorrectly identified as automation"

def test_automation_context_regression(parser_client, new_test_data_dir):
    """Test that entities in automation triggers are correctly identified in context."""
    yaml_file = Path(new_test_data_dir) / "yaml_config" / "automation_context_regression.yaml"
    yaml_dir = str(yaml_file.parent)

    asyncio.run(parser_client.async_parse(yaml_dir, []))
    items = parser_client.get_found_items(item_type='all')
    entities = [item[0] for item in items if item[3] == 'entity']

    entity_id = "input_boolean.mode_cleaning_house"
    assert entity_id in entities

    context = parser_client.get_automation_context(entity_id)
    assert context
    assert context["is_automation_context"] is True, "Automation context lost for trigger entity"
    assert context["parent_id"] == "c2153826-fa86-4448-91a5-53791f86a5f5"
    assert context["parent_alias"] == "Attic Ventilation"

def test_root_automation(parser_client, new_test_data_dir):
    """Test that a root-level automation dictionary is correctly detected."""
    yaml_file = Path(new_test_data_dir) / "yaml_config" / "root_automation.yaml"
    yaml_dir = str(yaml_file.parent)

    asyncio.run(parser_client.async_parse(yaml_dir, []))
    items = parser_client.get_found_items(item_type='all')
    entities = [item[0] for item in items if item[3] == 'entity']

    entity_id = "sensor.root_trigger"
    assert entity_id in entities

    context = parser_client.get_automation_context(entity_id)
    assert context
    assert context["is_automation_context"] is True, "Root automation context missing"
    assert context["parent_id"] == "root_auto_123"
    assert context["parent_alias"] == "Root Automation"
