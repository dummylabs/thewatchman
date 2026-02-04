"""Tests for advanced parser heuristics."""
import asyncio
import os

from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest


@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

import shutil


def test_ignored_patterns(parser_client, new_test_data_dir, tmp_path):
    """Test ignoring of variables, function calls, concatenation, and wildcards."""
    # H:1, H:2, H:6, H:7, H:15

    source_file = os.path.join(new_test_data_dir, "yaml_config", "patterns_ignored.yaml")
    dest_dir = tmp_path / "config"
    dest_dir.mkdir()
    dest_file = dest_dir / "patterns_ignored.yaml"
    shutil.copy(source_file, dest_file)

    # Scan the temp directory which contains ONLY the file we want to test
    entities, _, _, _, _ = asyncio.run(parser_client.async_parse(str(dest_dir), []))

    # H:1 Underscore Suffix
    assert "sensor.temp_var_" not in entities

    # H:2 Function Calls
    assert "sensor.valid_one" in entities
    # sensor.ignored_func_call is followed by ')', so it IS an entity (argument to float), not a function call.
    assert "sensor.ignored_func_call" in entities
    assert "sensor.function" not in entities

    # H:6 String Concatenation
    assert "sensor.constructed_id" not in entities
    assert "light.living_room" not in entities
    assert "sensor.placeholder" not in entities

    # H:7 Wildcards
    assert "light.*" not in entities
    assert "sensor.temperature_*" not in entities

    # H:15 Bundled Ignores
    assert "timer.finished" not in entities # Explicitly ignored
    assert "date.pixel_update" not in entities # date.* ignored
    assert "timer.kitchen" in entities # Valid timer

def test_ignored_keys(parser_client, new_test_data_dir):
    """Test ignoring content under specific keys."""
    # H:8 Ignored Keys (url, example, description)

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "keys_ignored.yaml")
    yaml_dir = os.path.dirname(yaml_file)

    entities, services, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    assert "light.example_entity" not in entities
    assert "sensor.test" not in entities
    assert "switch.demo_service" not in services
    assert "notify.telegram" in services # Valid

def test_custom_tags(parser_client, new_test_data_dir):
    """Test handling of custom YAML tags."""
    # H:12 Custom Tags

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "custom_tags.yaml")
    yaml_dir = os.path.dirname(yaml_file)

    entities, _, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    # !secret http_password resolves to string "http_password", not an entity.
    # !secret "sensor.secret_sensor" resolves to string "sensor.secret_sensor".
    # The parser implementation in parser_core explicitly SKIPS values that are tags (is_tag=True).
    assert "sensor.secret_sensor" not in entities

def test_templates_and_prefixes(parser_client, new_test_data_dir):
    """Test embedded services in templates and states prefix stripping."""
    # H:11 Embedded Services
    # H:16 States Prefix

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "templates.yaml")
    yaml_dir = os.path.dirname(yaml_file)

    entities, services, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    # H:11 Embedded Services
    assert "light.turn_on" in services
    assert "light.hallway" in entities
    assert "switch.toggle" in services # Embedded 'action:'

    # H:16 States Prefix
    assert "sun.sun" in entities # extracted from states.sun.sun
    assert "binary_sensor.garage" in entities # extracted from states.binary_sensor.garage
