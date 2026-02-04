"""Tests for basic parser functionality."""
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

def test_basic_yaml_parsing(parser_client, new_test_data_dir):
    """Test parsing of a standard YAML file with valid and invalid domains."""
    # Heuristic 13: Valid Domains
    # Heuristic 4: Comments
    # Heuristic 3: Service Keys

    yaml_file = Path(new_test_data_dir) / "yaml_config" / "basic_config.yaml"
    yaml_dir = str(yaml_file.parent)

    # Parse the directory
    entities, services, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

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

    json_file = Path(new_test_data_dir) / "json_config" / "dashboard.json"
    json_dir = str(json_file.parent)

    # We pass the file path, but the scanner internal filter should reject it based on extension
    # Scan the directory
    entities, services, files_parsed, _, _ = asyncio.run(parser_client.async_parse(json_dir, []))

    # dashboard.json is ignored. .storage/lovelace_dashboards is whitelisted and parsed.
    # But wait, this test expects everything to be ignored?
    # "Test that .json files are explicitly ignored by the parser."
    # With the rename, .storage/lovelace_dashboards IS parsed.
    # I should adjust the test expectation or use a directory that really has only ignored files.
    # Since I cannot easily isolate, I will accept that files_parsed > 0 if lovelace_dashboards is found.
    # However, dashboard.json MUST be ignored.

    # assert files_parsed == 0  <-- This might fail now.
    # assert "sensor.dashboard_sensor" not in entities
    # assert "light.dashboard_toggle" not in services

    # Let's see. If I renamed the file, it will be found.
    # I should separate dashboard.json test from storage test if possible.
    # But they are in the same tree.
    # I will remove the assertion on files_parsed count being 0, or check specifically for dashboard.json being ignored.
    # But async_parse returns aggregates.

    # If I want to verify dashboard.json is ignored, I check entities from it.
    # "sensor.dashboard_sensor" comes from dashboard.json.

    assert "sensor.dashboard_sensor" not in entities, "Should not parse entities from ignored .json file"
    assert "light.dashboard_toggle" not in services

def test_extensionless_json_parsing(parser_client, new_test_data_dir):
    """Test parsing of extensionless files detected as JSON."""
    # Heuristic 14: File Type Detection (Extensionless JSON)

    # Renamed file to match whitelist
    storage_file = (
        Path(new_test_data_dir) / "json_config" / ".storage" / "lovelace_dashboards"
    )
    root_dir = str(Path(new_test_data_dir) / "json_config")

    entities, _, _, _, _ = asyncio.run(parser_client.async_parse(root_dir, []))

    assert "sensor.storage_sensor_1" in entities
    assert "sensor.storage_sensor_2" in entities

def test_invalid_file_extension(parser_client, new_test_data_dir):
    """Test that files with invalid extensions are ignored."""
    # Heuristic 14: File Type Detection

    txt_file = Path(new_test_data_dir) / "yaml_config" / "invalid_file.txt"
    yaml_dir = str(txt_file.parent)

    entities, services, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    assert "sensor.invalid_file_test" not in entities
    assert "light.invalid_file_test" not in services
