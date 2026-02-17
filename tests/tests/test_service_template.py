"""Test parser handling of service_template."""
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

def test_service_template(parser_client, new_test_data_dir):
    """Test that service_template values are identified as services."""
    yaml_file = Path(new_test_data_dir) / "yaml_config" / "service_template.yaml"
    yaml_dir = str(yaml_file.parent)

    asyncio.run(parser_client.async_parse(yaml_dir, []))
    items = parser_client.get_found_items(item_type='all')
    entities = [item[0] for item in items if item[3] == 'entity']
    services = [item[0] for item in items if item[3] == 'service']

    # light.living_room is entity
    assert "light.living_room" in entities

    # light.unique_service should be service
    assert "light.unique_service" in services
    assert "light.unique_service" not in entities
