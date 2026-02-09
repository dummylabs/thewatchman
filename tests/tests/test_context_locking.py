"""Test Top-Down Context Locking strategy."""
import asyncio
from pathlib import Path
from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    return WatchmanParser(str(db_path))

def test_script_nested_context_locking(parser_client, new_test_data_dir):
    """Test that nested structures do not redefine active script context."""
    yaml_file = Path(new_test_data_dir) / "test_script_nested_context.yaml"
    
    # We need to run the parser on the specific file
    # async_parse usually takes a directory
    yaml_dir = str(yaml_file.parent)
    
    # Run parsing
    asyncio.run(parser_client.async_parse(yaml_dir, []))
    
    # Find light.inside_loop context
    # Note: get_automation_context returns context for an entity_id
    context = parser_client.get_automation_context('light.inside_loop')
    
    assert context is not None
    assert context["is_automation_context"] is True
    assert context["parent_alias"] == "Master Script"
    assert context["parent_type"] == "script"
    # Ensure it didn't use 'repeat' as parent_id (common bug where nested keys redefine context)
    assert context["parent_id"] != "repeat"
