import pytest
import os
from pathlib import Path
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.mark.asyncio
async def test_regex_false_positive_with_custom_domains(tmp_path):
    """
    Test that false positives like image paths are not detected as entities
    when custom_domains are provided to async_scan.
    """
    # 1. Setup: Create a temporary configuration file with a false positive
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    test_file = config_dir / "test_config.yaml"
    # This string should NOT be detected as sensor.png
    test_file.write_text("image: /local/vacume/sensor.png", encoding="utf-8")
    
    db_path = str(tmp_path / "watchman.db")
    parser = WatchmanParser(db_path)
    
    # 2. Execute: Scan with custom_domains provided
    # This triggers the problematic re.compile in async_scan
    await parser.async_scan(
        root_path=str(config_dir),
        ignored_files=[],
        custom_domains=["sensor"]
    )
    
    # 3. Verify: Check found items in the database
    found_items = parser.get_found_items(item_type="entity")
    
    # Assert that no entities were found. 
    # If the bug exists, it will find "sensor.png" because "/" is not in the exclusion group.
    entities = [item[0] for item in found_items]
    assert "sensor.png" not in entities
    assert len(entities) == 0
