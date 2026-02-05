"""Tests for database schema integrity.

check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md
"""
import sqlite3
from custom_components.watchman.const import CURRENT_DB_SCHEMA_VERSION
from custom_components.watchman.utils.parser_core import WatchmanParser

def test_db_schema_integrity(tmp_path, snapshot):
    """Test that SQLite schema matches the snapshot and version."""
    db_path = tmp_path / "integrity_test.db"
    parser = WatchmanParser(str(db_path))

    # Initialize DB
    conn = parser._init_db(str(db_path))

    cursor = conn.cursor()
    # Extract DDL for all tables, sorted by name for determinism
    cursor.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    tables = cursor.fetchall()
    conn.close()

    schema_dump = "\n".join([f"Table: {name}\n{sql}" for name, sql in tables])

    # Snapshot contains (Version, Schema)
    # If schema changes, Version MUST be bumped to pass the test (after updating snapshot)
    #
    assert (CURRENT_DB_SCHEMA_VERSION, schema_dump) == snapshot, "Help: check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md"
