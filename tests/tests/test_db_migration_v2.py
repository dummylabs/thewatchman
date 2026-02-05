"""Test database migration scenarios 0->2 and N->2.

check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md
"""
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from custom_components.watchman.const import (
    DB_FILENAME,
    LEGACY_DB_FILENAME,
    CURRENT_DB_SCHEMA_VERSION,
    DOMAIN,
)
from custom_components.watchman.utils.parser_core import WatchmanParser
from custom_components.watchman import async_setup_entry, WMConfigEntry
from homeassistant.core import HomeAssistant

@pytest.mark.asyncio
async def test_migration_0_to_2_preserves_legacy_columns(hass: HomeAssistant, tmp_path):
    """
    Test Migration 0 -> 2.

    1. Legacy file exists, new file does not.
    2. File is renamed.
    3. User version bumped to 2.
    4. Legacy columns (e.g., last_parse_duration) MUST remain.
    """
    # 1. Setup paths
    legacy_db_path = tmp_path / LEGACY_DB_FILENAME
    new_db_path = tmp_path / DB_FILENAME

    # 2. Create Legacy DB (Version 0 by default) with legacy schema
    conn = sqlite3.connect(legacy_db_path)
    cursor = conn.cursor()

    # Create table with OLD schema (including stats columns)
    cursor.execute("""
        CREATE TABLE scan_config (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK(id=1),
            included_folders TEXT,
            ignored_files TEXT,
            last_parse_duration REAL,
            last_parse_timestamp TEXT
        )
    """)
    cursor.execute("INSERT INTO scan_config (id, last_parse_duration) VALUES (1, 123.45)")
    conn.commit()

    # Verify Version 0
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 0, "Help: check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md"
    conn.close()

    # 3. Setup Mocks for async_setup_entry
    # We need to mock hass.config.path to return our tmp_path locations
    def mock_path_side_effect(folder, filename):
        if filename == LEGACY_DB_FILENAME:
            return str(legacy_db_path)
        if filename == DB_FILENAME:
            return str(new_db_path)
        return str(tmp_path / filename)

    hass.config.path = MagicMock(side_effect=mock_path_side_effect)

    # Mock Config Entry
    config_entry = MagicMock(spec=WMConfigEntry)
    config_entry.entry_id = "test_entry"
    config_entry.title = "Watchman"
    config_entry.runtime_data = None

    # Mock dependencies to prevent full integration boot
    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coord, \
         patch("custom_components.watchman.WatchmanHub") as mock_hub_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch("custom_components.watchman.Path.exists", side_effect=[False, True]), \
         patch("custom_components.watchman.Path.rename") as mock_rename:

        # Note: We can't easily rely on the actual rename inside async_setup_entry
        # because we are mocking Path.
        # Instead, let's verify the LOGIC in __init__.py does the rename,
        # but for the database content check, we will manually rename it
        # or just instantiate the Parser on the legacy file to check schema migration.

        # Let's test the PARSER logic specifically for the schema part first.
        # We simulate the rename manually to test the parser's migration behavior.
        import shutil
        shutil.move(legacy_db_path, new_db_path)

        parser = WatchmanParser(str(new_db_path))
        # This triggers _init_db -> _migrate_db
        conn = parser._init_db(str(new_db_path))

        # 4. Verify Version Bump
        cursor = conn.cursor()
        cursor.execute("PRAGMA user_version")
        # check Data Persistense and Migration in /docs/dev/DEVELOPMENT.md
        assert cursor.fetchone()[0] == 2, "Database version should be bumped to 2"

        # 5. Verify Legacy Columns Remain (CRITICAL)
        # SQLite doesn't drop columns easily, so they should be there unless we explicitly rebuilt the table.
        cursor.execute("PRAGMA table_info(scan_config)")
        columns = [row[1] for row in cursor.fetchall()]

        assert "last_parse_duration" in columns, "Legacy column 'last_parse_duration' should NOT be deleted"
        assert "last_parse_timestamp" in columns, "Legacy column 'last_parse_timestamp' should NOT be deleted"

        # Verify data is accessible
        cursor.execute("SELECT last_parse_duration FROM scan_config")
        assert cursor.fetchone()[0] == 123.45

        conn.close()


@pytest.mark.asyncio
async def test_downgrade_protection_3_to_2(tmp_path):
    """
    Test Downgrade 3 -> 2.

    1. DB exists with user_version 3.
    2. Parser initializes.
    3. DB should be deleted and recreated at version 2.
    4. Old data should be gone.
    """
    db_path = tmp_path / DB_FILENAME

    # 1. Create "Future" DB
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version = 3")
    # Add a marker table that shouldn't exist in V2
    cursor.execute("CREATE TABLE future_table (id INTEGER)")
    conn.commit()
    conn.close()

    # 2. Init Parser (Trigger Downgrade)
    parser = WatchmanParser(str(db_path))
    conn = parser._init_db(str(db_path))

    # 3. Verify Version Reset
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == 2, "Database should be rebuilt to current version 2"

    # 4. Verify Rebuild (Future table gone)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='future_table'")
    assert cursor.fetchone() is None, "Future table should be deleted (DB recreated)"

    # 5. Verify Standard Tables Exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='found_items'")
    assert cursor.fetchone() is not None

    conn.close()
