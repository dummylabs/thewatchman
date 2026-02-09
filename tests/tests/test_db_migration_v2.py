"""Test database wipe-on-mismatch strategy."""
import sqlite3
import pytest
from custom_components.watchman.const import DB_FILENAME, CURRENT_DB_SCHEMA_VERSION
from custom_components.watchman.utils.parser_core import WatchmanParser

"""Test database wipe-on-mismatch strategy."""
import sqlite3
import pytest
from custom_components.watchman.const import DB_FILENAME, CURRENT_DB_SCHEMA_VERSION
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.mark.asyncio
async def test_upgrade_wipes_old_db(tmp_path):
    """
    Test Upgrade Scenario (CURRENT-1 -> CURRENT).
    
    1. Create DB with previous version.
    2. Populate with some data.
    3. Initialize Parser.
    4. Assert DB is wiped (data gone) and version is CURRENT.
    """
    db_path = tmp_path / DB_FILENAME
    
    # Ensure we have a valid previous version (handle case if current is 1)
    old_version = max(1, CURRENT_DB_SCHEMA_VERSION - 1)
    # If current is 1, we can't test upgrade from 0 effectively if 0 is treated as "no file", 
    # but pragmas default to 0. 
    # Let's assume strategy works for mismatches. If current=old, we force a mismatch artificially 
    # just for the logic test, or skip if version is 1.
    
    if CURRENT_DB_SCHEMA_VERSION == 1:
        # If version is 1, this test is effectively checking fresh install, or we simulate v0
        old_version = 0

    # 1. Create DB with old version
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA user_version = {old_version}")
    cursor.execute("CREATE TABLE old_table (id INTEGER)")
    cursor.execute("INSERT INTO old_table VALUES (1)")
    conn.commit()
    conn.close()
    
    # 2. Initialize Parser
    parser = WatchmanParser(str(db_path))
    # This triggers _init_db
    conn = parser._init_db(str(db_path))
    
    # 3. Verify Version
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == CURRENT_DB_SCHEMA_VERSION
    
    # 4. Verify Wipe (old_table should be gone)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_table'")
    assert cursor.fetchone() is None
    
    conn.close()

@pytest.mark.asyncio
async def test_downgrade_wipes_future_db(tmp_path):
    """
    Test Downgrade Scenario (CURRENT+1 -> CURRENT).
    
    1. Create DB with future version.
    2. Populate with future data.
    3. Initialize Parser.
    4. Assert DB is wiped and version is CURRENT.
    """
    db_path = tmp_path / DB_FILENAME
    
    future_version = CURRENT_DB_SCHEMA_VERSION + 1
    
    # 1. Create DB with future version
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA user_version = {future_version}")
    cursor.execute("CREATE TABLE future_table (id INTEGER)")
    conn.commit()
    conn.close()
    
    # 2. Initialize Parser
    parser = WatchmanParser(str(db_path))
    conn = parser._init_db(str(db_path))
    
    # 3. Verify Version
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == CURRENT_DB_SCHEMA_VERSION
    
    # 4. Verify Wipe
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='future_table'")
    assert cursor.fetchone() is None
    
    conn.close()

@pytest.mark.asyncio
async def test_fresh_db_initialization(tmp_path):
    """
    Test Fresh DB Initialization.
    
    1. No DB file.
    2. Initialize Parser.
    3. Assert Version is 3.
    """
    db_path = tmp_path / DB_FILENAME
    
    parser = WatchmanParser(str(db_path))
    conn = parser._init_db(str(db_path))
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version")
    assert cursor.fetchone()[0] == CURRENT_DB_SCHEMA_VERSION
    conn.close()