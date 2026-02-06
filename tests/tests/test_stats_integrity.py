"""Tests for stats structure integrity.

check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md
"""
from dataclasses import fields
from custom_components.watchman.const import STORAGE_VERSION
from custom_components.watchman.utils.parser_core import ParseResult

def test_stats_structure_integrity(snapshot):
    """Test that ParseResult dataclass structure matches the snapshot and version."""
    # Get sorted field names from ParseResult
    field_names = sorted([f.name for f in fields(ParseResult)])

    # Snapshot contains (Version, Fields)
    # If fields change, STORAGE_VERSION should be bumped if it's a breaking change
    assert (STORAGE_VERSION, field_names) == snapshot, "Help: check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md"
