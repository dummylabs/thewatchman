"""Tests for file size limit."""
import asyncio

from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest


@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

def test_large_file_skipped(parser_client, tmp_path, caplog):
    """Test that files larger than MAX_FILE_SIZE are skipped."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # Create a large file (> 500KB)
    large_file = config_dir / "large_file.yaml"
    # 500KB = 512000 bytes. Let's make it 500*1024 + 10 bytes.
    large_content = "#" * (500 * 1024 + 10)
    large_file.write_text(large_content, encoding="utf-8")

    # Create a normal file
    normal_file = config_dir / "normal.yaml"
    normal_file.write_text("sensor:\n  - platform: template\n    sensors:\n      test: \n        value_template: '{{ states.sensor.valid }}'", encoding="utf-8")

    # Parse
    entities, _, _, _, _, _ = asyncio.run(parser_client.async_parse(str(config_dir), []))

    # Verify normal file parsed
    assert "sensor.valid" in entities

    # Verify large file skipped (log message)
    assert "is too large" in caplog.text
    assert str(large_file) in caplog.text
