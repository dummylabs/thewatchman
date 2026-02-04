"""Test parser handling of service_template."""
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

def test_service_template(parser_client, new_test_data_dir):
    """Test that service_template values are identified as services."""
    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "service_template.yaml")
    yaml_dir = os.path.dirname(yaml_file)
    
    entities, services, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))
    
    # light.living_room is entity
    assert "light.living_room" in entities
    
    # light.unique_service should be service
    assert "light.unique_service" in services
    assert "light.unique_service" not in entities
