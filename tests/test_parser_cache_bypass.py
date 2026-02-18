"""Test parser cache bypass logic."""
import os
import asyncio
import time
import pytest
import sqlite3
from custom_components.watchman.utils.parser_core import WatchmanParser
from custom_components.watchman.const import DB_FILENAME

@pytest.fixture
def parser(hass):
    """Initialize parser with temporary DB."""
    db_path = hass.config.path(DB_FILENAME)
    return WatchmanParser(db_path)

def get_file_scan_date(parser, file_path):
    """Helper to get scan_date for a file from DB."""
    with parser._db_session() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT scan_date FROM processed_files WHERE path = ?", 
            (file_path,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

async def test_parser_ignore_mtime_bypass(hass, parser):
    """Test that ignore_mtime=True bypasses mtime cache check."""
    # 1. Setup: Create a test file
    test_file = hass.config.path("test_bypass.yaml")
    with open(test_file, "w") as f:
        f.write("sensor:\n  - platform: template\n")

    # Set mtime to the past to prevent Docker host/container clock skew from causing false positives
    past_time = time.time() - 10
    os.utime(test_file, (past_time, past_time))
    
    try:
        # 2. Initial Parse
        await parser.async_parse(hass.config.config_dir, [])
        initial_scan_date = get_file_scan_date(parser, test_file)
        assert initial_scan_date is not None
        
        # Ensure some time passes for mtime granularity
        await asyncio.sleep(1.1)
        
        # 3. Phase 1: No Bypass (mtime unchanged)
        # Calling parse again without modifying file should NOT update scan_date
        await parser.async_parse(hass.config.config_dir, [], ignore_mtime=False)
        phase1_scan_date = get_file_scan_date(parser, test_file)
        
        # Should be identical because file was skipped
        assert phase1_scan_date == initial_scan_date
        
        # 4. Phase 2: Bypass (mtime still unchanged)
        # Calling parse with ignore_mtime=True SHOULD update scan_date
        await parser.async_parse(hass.config.config_dir, [], ignore_mtime=True)
        phase2_scan_date = get_file_scan_date(parser, test_file)
        
        assert phase2_scan_date != initial_scan_date
        assert phase2_scan_date > initial_scan_date
        
    finally:
        if os.path.exists(test_file):
            os.remove(test_file)
