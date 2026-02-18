"""Test reproduction of context loss in nested blocks."""
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

def test_nested_context_loss(parser_client, tmp_path):
    """Test that entities in nested choose blocks retain parent automation context."""
    
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    source_file = Path("tests/data/context_bug.yaml")
    dest_file = config_dir / "context_bug.yaml"
    dest_file.write_text(source_file.read_text())
    
    # Parse
    asyncio.run(parser_client.async_parse(str(config_dir), []))
    
    # Verify entity presence
    entities = parser_client.get_found_items('entity')
    
    found = False
    for item in entities:
        # item: (entity_id, path, line, item_type, p_type, p_alias, p_id)
        if item[0] == "light.living_room":
            found = True
            parent_type = item[4]
            parent_alias = item[5]
            parent_id = item[6]
            
            # Expectation: Automation context
            # If the bug exists, this assertion should FAIL
            assert parent_type == "automation", f"Expected parent_type 'automation', got '{parent_type}'"
            assert parent_id == "123456789", f"Expected parent_id '123456789', got '{parent_id}'"
            
    assert found, "Entity light.living_room not found in parser results"
