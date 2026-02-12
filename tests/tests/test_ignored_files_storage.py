"""Test ignored files in .storage directory."""
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

def test_storage_ignored_files(parser_client, tmp_path):
    """Test that ignored files in .storage are respected."""
    
    # 1. Setup Mock Directory Structure
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir()
    
    # Create a standard whitelisted file
    (storage_dir / "core.config_entries").write_text("{}")
    
    # Create a lovelace file that we want to IGNORE
    (storage_dir / "lovelace.dashboard_test").write_text("{}")
    
    # Create a lovelace file that we want to KEEP
    (storage_dir / "lovelace.dashboard_keep").write_text("{}")
    
    # 2. Run Parser with ignored pattern
    ignored_patterns = ["*dashboard_test*"]
    
    # We use async_parse but we are interested in the side effect (DB content)
    asyncio.run(parser_client.async_parse(
        str(config_dir),
        ignored_patterns
    ))
    
    # 3. Verify Results
    processed_files = parser_client.get_processed_files()
    processed_paths = [f[1] for f in processed_files]
    
    # Debug info
    print(f"Processed paths: {processed_paths}")
    
    # Check that core.config_entries is present (baseline)
    # The path in DB is relative to where parser ran or absolute?
    # parser_core.py says:
    # if base_path: path_for_db = relpath
    # In async_parse call above, we didn't provide base_path, so it stores absolute path usually,
    # or whatever _scan_files_sync returns.
    # _scan_files_sync returns absolute paths.
    
    # Let's check for substring presence to be safe
    assert any("core.config_entries" in p for p in processed_paths), "core.config_entries should be scanned"
    assert any("lovelace.dashboard_keep" in p for p in processed_paths), "lovelace.dashboard_keep should be scanned"
    
    # THIS SHOULD FAIL INITIALLY
    assert not any("lovelace.dashboard_test" in p for p in processed_paths), "lovelace.dashboard_test should be IGNORED"
