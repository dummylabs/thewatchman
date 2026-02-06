"""Tests for control flow structures parsing.

These tests must verify that entities and services defined inside nested control flow blocks
are correctly attributed to their parent automation ID, rather than being isolated as anonymous scripts.
"""
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

def test_control_flow_structures(parser_client, tmp_path):
    """Test context tracking in choose, repeat, if/then, and parallel blocks."""

    # Setup config dir
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    source_file = Path("tests/data/control_flow.yaml")
    dest_file = config_dir / "control_flow.yaml"
    dest_file.write_text(source_file.read_text())

    # Parse
    asyncio.run(parser_client.async_parse(str(config_dir), []))

    # Fetch all items
    # Format: (entity_id, path, line, item_type, parent_type, parent_alias, parent_id)
    all_items = parser_client.get_found_items('all')

    # Convert to a more accessible format: dict of list of contexts by ID
    item_map = {}
    for item in all_items:
        item_id = item[0]
        context = {
            "parent_type": item[4],
            "parent_alias": item[5],
            "parent_id": item[6]
        }
        if item_id not in item_map:
            item_map[item_id] = []
        item_map[item_id].append(context)

    # Helper to verify
    def verify(item_id, expected_parent_id):
        assert item_id in item_map, f"{item_id} not found"
        for ctx in item_map[item_id]:
            assert ctx["parent_type"] == "automation", f"{item_id}: Expected parent_type 'automation', got '{ctx['parent_type']}'"
            assert ctx["parent_id"] == expected_parent_id, f"{item_id}: Expected parent_id '{expected_parent_id}', got '{ctx['parent_id']}'"

    # Verify Choose
    # light.living_room_1 is in 'choose' sequence
    verify("light.living_room_1", "test_choose")
    # switch.kitchen_fan is in 'default' sequence
    verify("switch.kitchen_fan", "test_choose")

    verify("light.turn_on", "test_choose")
    verify("switch.turn_off", "test_choose")

    # Verify Repeat
    verify("notify.mobile_app_phone", "test_repeat")

    # Verify If/Then/Else
    # light.hallway appears in both then and else
    verify("light.hallway", "test_if_then")
    verify("light.turn_on_hallway", "test_if_then")
    verify("light.turn_off_hallway", "test_if_then")

    # Verify Parallel
    verify("script.perform_cleanup", "test_parallel")
    verify("notify.admin", "test_parallel")
