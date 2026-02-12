import contextlib
import os
from pathlib import Path

from custom_components.watchman.const import (
    CONF_INCLUDED_FOLDERS,
    COORD_DATA_PROCESSED_FILES,
    DOMAIN,
)
import pytest
from tests import async_init_integration


@pytest.mark.asyncio
async def test_symlink_handling(hass, tmp_path, caplog):
    """Test parser handling of valid and broken symlinks."""
    # Setup directory structure
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # 1. Real file with content
    target_file = config_dir / "target_file.yaml"
    # Create a simple sensor usage that Watchman will detect as a missing entity
    target_file.write_text("automation:\n  - trigger:\n      platform: state\n      entity_id: sensor.target_sensor_missing", encoding="utf-8")

    # 2. Valid symlink to target_file
    valid_link = config_dir / "valid_link.yaml"
    try:
        valid_link.symlink_to(target_file)
    except OSError:
        pytest.skip("Symlinks not supported on this OS/filesystem")

    # 3. Broken symlink
    broken_link = config_dir / "broken_link.yaml"
    with contextlib.suppress(OSError):
        broken_link.symlink_to(config_dir / "non_existent.yaml")

    # Initialize integration
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: [str(config_dir)]
        }
    )

    try:
        await hass.async_block_till_done()

        # Retrieve coordinator
        entries = hass.config_entries.async_entries(DOMAIN)
        coordinator = entries[0].runtime_data.coordinator

        # Verify:
        # 1. Broken link warning in logs
        assert "Skipping broken symlink" in caplog.text

        # 2. Target file parsed correctly (via valid link)
        parsed_items = await coordinator.hub.async_get_all_items()
        parsed_entities = parsed_items["entities"]
        assert "sensor.target_sensor_missing" in parsed_entities
        assert "valid_link.yaml" in parsed_entities["sensor.target_sensor_missing"]["locations"]

        # Check if we parsed 2 files (target + link) or 1 (if parser handles deduplication by real path, which it doesn't seem to do yet, but `processed_files` uses path as key)
        # processed_files_count should be at least 1. If symlink is followed as a separate file, it might be 2.
        assert coordinator.data.get(COORD_DATA_PROCESSED_FILES) >= 1
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
