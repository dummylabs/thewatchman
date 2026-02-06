"""Test deduplication of results from YAML anchors.

Before this fix parser produced duplicate entries in its report when processing YAML files
that utilize Anchors (&) and Aliases (*). This happens because the parser traverses the fully expanded YAML tree.
If an alias is used multiple times, the parser visits the underlying entity multiple times.
However, the YAML loader assigns the line number of the anchor definition to all instances.
This results in the final report showing the same Entity ID, on the same Line Number, with the same Context,
multiple times (e.g., fan.turn_off on line 79 appearing 3 times).
The test parses test file and asserts that the count of found items is greater than 1 for that specific entity
(confirming the duplication exists)
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

def test_anchor_duplication(parser_client, tmp_path):
    """Test that YAML anchors produce duplicate entries initially."""

    config_dir = tmp_path / "config"
    config_dir.mkdir()

    source_file = Path("tests/data/anchors.yaml")
    dest_file = config_dir / "anchors.yaml"
    dest_file.write_text(source_file.read_text())

    # Parse
    asyncio.run(parser_client.async_parse(str(config_dir), []))

    # Verify entity presence
    entities = parser_client.get_found_items('entity')

    target_entity = "light.anchored_light"
    occurrences = [e for e in entities if e[0] == target_entity]

    # After fix, we expect NO duplicates because context and line number are identical
    assert len(occurrences) == 1, f"Expected 1 occurrence for {target_entity} after deduplication, found {len(occurrences)}"
