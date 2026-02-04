"""Tests for ESPHome configuration parsing."""
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

def test_esphome_context(parser_client, new_test_data_dir):
    """Test strict parsing for ESPHome files."""
    # H:9 ESPHOME Context

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "esphome", "device.yaml")
    yaml_dir = os.path.dirname(yaml_file)

    entities, services, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    # Allowed: keys are 'service', 'action', 'entity_id'
    assert "light.turn_on" in services
    assert "light.living_room_esp" in entities
    assert "sensor.outside_temp" in entities

    # Ignored: Looks like entity/service but key is not allowed
    assert "uptime_sensor" not in entities # Inside lambda
    assert "light.fake_light" not in entities # Inside random key
