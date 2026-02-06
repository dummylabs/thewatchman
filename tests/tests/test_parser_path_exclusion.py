"""Test for parser path exclusion heuristic."""
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

def test_path_exclusion(parser_client, new_test_data_dir):
    """Test that file paths looking like entities are ignored."""
    # Heuristic 17: Path Separation

    yaml_file = Path(new_test_data_dir) / "yaml_config" / "path_exclusion.yaml"
    yaml_dir = str(yaml_file.parent)

    # We scan the directory, but filtering by file might not be supported by async_parse directly (it scans dir)
    # But since we put it in yaml_config, it might parse other files too.
    # We should filter results or check just for our specific entities.

    entities, services, _, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    assert "person.valid_entity" in entities
    assert "person.space_preceded" in entities
    assert "person.colon_preceded" in entities
    assert "person.quoted_entity" in entities

    assert "person.jpg" not in entities, "Should ignore person.jpg preceded by / or \\"
