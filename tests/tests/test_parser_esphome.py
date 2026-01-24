"""Tests for ESPHome configuration parsing."""
import os
import pytest
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    yield client

def test_esphome_context(parser_client, new_test_data_dir):
    """Test strict parsing for ESPHome files."""
    # H:9 ESPHOME Context

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "esphome", "device.yaml")

    entities, services, _, _, _ = parser_client.parse([yaml_file], [])

    # Allowed: keys are 'service', 'action', 'entity_id'
    assert "light.turn_on" in services
    assert "light.living_room_esp" in entities
    assert "sensor.outside_temp" in entities

    # Ignored: Looks like entity/service but key is not allowed
    assert "uptime_sensor" not in entities # Inside lambda
    assert "light.fake_light" not in entities # Inside random key
