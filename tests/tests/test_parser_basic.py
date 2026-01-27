"""Tests for basic parser functionality."""
import os
import pytest
import asyncio
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    yield client

def test_basic_yaml_parsing(parser_client, new_test_data_dir):
    """Test parsing of a standard YAML file with valid and invalid domains."""
    # Heuristic 13: Valid Domains
    # Heuristic 4: Comments
    # Heuristic 3: Service Keys

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "basic_config.yaml")

    # Parse the file
    entities, services, _, _, _ = asyncio.run(parser_client.async_parse([yaml_file], []))

    # Check Entities
    assert "sensor.skylight" in entities, "Should detect entity in template"
    assert "switch.skylight" in entities, "Should detect entity in target"

    # Check Services
    assert "switch.turn_on" in services
    assert "switch.turn_off" in services

    # Check Ignored (H:4 Comments, H:13 Invalid Domains)
    assert "light.kitchen_ignored" not in entities, "Should ignore entities in comments (H:4)"
    assert "invalid_domain.test" not in entities, "Should ignore invalid domains (H:13)"

def test_json_files_ignored(parser_client, new_test_data_dir):
    """Test that .json files are explicitly ignored by the parser."""
    # Heuristic 14: File Type Detection
    # .json files are ignored to prevent false positives, even if they contain valid config.

    json_file = os.path.join(new_test_data_dir, "json_config", "dashboard.json")

    # We pass the file path, but the scanner internal filter should reject it based on extension
    entities, services, files_parsed, _, _ = asyncio.run(parser_client.async_parse([json_file], []))

    assert files_parsed == 0, "Should verify no files were processed"
    assert "sensor.dashboard_sensor" not in entities, "Should not parse entities from ignored .json file"
    assert "light.dashboard_toggle" not in services

def test_extensionless_json_parsing(parser_client, new_test_data_dir):
    """Test parsing of extensionless files detected as JSON."""
    # Heuristic 14: File Type Detection (Extensionless JSON)

    storage_file = os.path.join(new_test_data_dir, "json_config", ".storage", "lovelace_dash")

    entities, _, _, _, _ = asyncio.run(parser_client.async_parse([storage_file], []))

    assert "sensor.storage_sensor_1" in entities
    assert "sensor.storage_sensor_2" in entities

def test_invalid_file_extension(parser_client, new_test_data_dir):
    """Test that files with invalid extensions are ignored."""
    # Heuristic 14: File Type Detection

    txt_file = os.path.join(new_test_data_dir, "yaml_config", "invalid_file.txt")

    entities, services, _, _, _ = asyncio.run(parser_client.async_parse([txt_file], []))

    assert "sensor.invalid_file_test" not in entities
    assert "light.invalid_file_test" not in services
