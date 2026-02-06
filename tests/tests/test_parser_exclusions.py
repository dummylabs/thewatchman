"""Tests for parser exclusions logic."""
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

def test_trigger_false_positives(parser_client, tmp_path):
    """Test that triggers are ignored as values but recursed into."""
    
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    source_file = Path("tests/data/test_trigger_false_positives.yaml")
    dest_file = config_dir / "test_trigger.yaml"
    dest_file.write_text(source_file.read_text())
    
    # Parse
    asyncio.run(parser_client.async_parse(str(config_dir), []))
    
    # Get entities
    entities_data = parser_client.get_found_items('entity')
    entities = [item[0] for item in entities_data]
    
    # Assertions
    # 1. False Positive Scenario
    assert "light.turn_on" not in entities, "Trigger shorthand value should be ignored"
    
    # 2. Valid Recursion Scenario
    assert "sensor.real_entity" in entities, "Nested entity inside triggers should be found"