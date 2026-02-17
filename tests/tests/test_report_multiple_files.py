"""Test report generation with multiple files for the same missing item."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    DOMAIN,
)
import pytest
from tests import async_init_integration


# Mock stats to ensure deterministic output
async def mock_stats(hass, parse_duration, last_check_duration, start_time):
    """Mock function for report stats."""
    return ("01 Jan 2026 12:00:00", 1.23, 5, 0.1234)

@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
@pytest.mark.asyncio
async def test_report_multiple_files(hass, new_test_data_dir, tmp_path):
    """Test that all files are reported when an item is in multiple files."""
    # Define source config directory
    config_dir = str(Path(new_test_data_dir) / "reports" / "test_multiple_files")

    # Mock hass.config.config_dir to the source dir so relative paths are calculated correctly
    hass.config.config_dir = config_dir

    # Mock hass.config.path to redirect .storage/watchman.db to tmp_path
    def mock_path_side_effect(*args):
        return str(tmp_path.joinpath(*args))

    hass.config.path = MagicMock(side_effect=mock_path_side_effect)

    report_file = tmp_path / "watchman_report.txt"

    # Initialize integration pointing to our dedicated folder
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: config_dir,
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: str(report_file),
            },
            CONF_IGNORED_STATES: [], # Report everything
        },
    )

    try:
        # Run report
        await hass.services.async_call(DOMAIN, "report")
        await hass.async_block_till_done()

        # Verify report created
        assert report_file.exists()

        # Read content
        content = report_file.read_text(encoding="utf-8")

        # Check if both files are mentioned in the report
        assert "file1.yaml" in content
        assert "file2.yaml" in content

        # Verify that both files are associated with the missing entity
        # We check the block of text around the missing entity
        entity_section = content[content.find("sensor.missing_entity") : content.find("-==", content.find("sensor.missing_entity"))]
        assert "file1.yaml:5" in entity_section
        assert "file2.yaml:5" in entity_section

        # Verify that both files are associated with the missing service
        service_section = content[content.find("script.missing_service") : content.find("-==", content.find("script.missing_service"))]
        assert "file1.yaml:7" in service_section
        assert "file2.yaml:7" in service_section

    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
