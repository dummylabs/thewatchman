"""Tests for Lovelace dashboard discovery in .storage."""
import shutil
from pathlib import Path
import pytest
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

@pytest.mark.asyncio
async def test_lovelace_dynamic_discovery(parser_client, tmp_path):
    """Test that lovelace* files and core.config_entries in .storage are discovered, and junk is ignored."""
    
    # 1. Setup .storage directory in tmp_path
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    
    # 2. Copy ALL files from tests/data/.storage to tmp_path/.storage
    source_dir = Path("tests/data/.storage")
    for file_path in source_dir.iterdir():
        if file_path.is_file():
            shutil.copy(file_path, storage_dir / file_path.name)
    
    # 3. Run Parser on the tmp_path
    parsed_entities, _, _, _, _, _ = await parser_client.async_parse(str(tmp_path), [])
    
    # 4. Assertions for Lovelace Files (Dynamic Discovery)
    assert "sensor.test_main" in parsed_entities, "Should find entity in 'lovelace'"
    assert "sensor.test_legacy" in parsed_entities, "Should find entity in 'lovelace_dashboards'"
    assert "sensor.test_new" in parsed_entities, "Should find entity in 'lovelace.dashboard_test'"
    
    # 5. Assertions for Whitelisted Files
    assert "light.kitchen_ceiling" in parsed_entities, "Should find entity in 'core.config_entries'"
    
    # 6. Assertions for Junk Files (Should be Ignored)
    assert "sensor.junk_sensor" not in parsed_entities, "Should NOT find entity in 'junk_file.json'"
    assert "sensor.junk_no_ext" not in parsed_entities, "Should NOT find entity in 'junk_file'"
    assert "sensor.junk_yaml" not in parsed_entities, "Should NOT find entity in 'junk_file.yaml'"
