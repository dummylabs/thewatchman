"""Test for parser false positives due to suffix matching."""
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

def test_false_positives_suffix(parser_client, new_test_data_dir):
    """Test that entity IDs are not matched if followed by - or ."""
    # Heuristic 18: Word Boundary Check

    yaml_file = Path(new_test_data_dir) / "yaml_config" / "false_positives_suffix.yaml"
    yaml_dir = str(yaml_file.parent)

    asyncio.run(parser_client.async_parse(yaml_dir, []))
    items = parser_client.get_found_items(item_type='all')
    entities = [item[0] for item in items if item[3] == 'entity']

    # Valid entities should be present
    assert "sensor.camera_1" in entities
    assert "sensor.doorbell" in entities

    # False positives should be absent
    assert "sensor.example" not in entities, "Should ignore partial match from 'sensor.example-host.org'"
    assert "sensor.stunnel" not in entities, "Should ignore partial match from 'sensor.stunnel.status'"
