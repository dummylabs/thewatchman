"""Test report generation using snapshots."""
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


# Mock stats to ensure deterministic output for snapshots
async def mock_stats(hass, parse_duration, last_check_duration, start_time):
    """Mock function for report stats."""
    return ("01 Jan 2026 12:00:00", 1.23, 5, 0.1234)

@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
@pytest.mark.asyncio
async def test_report_generation_snapshot(hass, new_test_data_dir, tmp_path, snapshot):
    """Test full report generation matching a snapshot."""
    # Define source config directory
    config_dir = str(Path(new_test_data_dir) / "reports" / "test_report_generation")

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
        # Set some states so they are NOT reported as missing (to reduce noise or verify filtering)
        # But leave many missing so the report is populated.
        hass.states.async_set("sensor.outside_temp", "25.0") # Exists
        hass.states.async_set("light.living_room", "on") # Exists
        hass.states.async_set("binary_sensor.motion_sensor", "unavailable") # Unavailable
        hass.states.async_set("input_boolean.unknown_boolean", "unknown") # Unknown

        # Register dummy services for standard domains so they are detected as "available"
        # This mimics a real HA instance where these integrations are loaded.
        for domain in ["light", "switch", "alarm_control_panel", "vacuum", "script", "notify", "automation"]:
            hass.services.async_register(domain, "turn_on", lambda x: None)
            hass.services.async_register(domain, "turn_off", lambda x: None)
            hass.services.async_register(domain, "toggle", lambda x: None)
            # Add specific services used in test data

        hass.services.async_register("alarm_control_panel", "arm_home", lambda x: None)
        hass.services.async_register("vacuum", "start", lambda x: None)
        hass.services.async_register("notify", "telegram", lambda x: None)
        hass.services.async_register("notify", "persistent_notification", lambda x: None)
        hass.services.async_register("notify", "mobile_app_phone", lambda x: None)
        #hass.services.async_register("script", "cleanup_routine", lambda x: None)

        # Run report
        await hass.services.async_call(DOMAIN, "report")
        await hass.async_block_till_done()

        # Verify report created
        assert report_file.exists()

        # Read content
        content = report_file.read_text(encoding="utf-8")

        # Assert match snapshot
        # We replace the absolute temp path in the report header if it appears there
        # The header usually contains "Report created..."
        # Check if absolute paths leak in the body. mock_get_short_path should handle file paths.

        assert content == snapshot
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
