"""Integration test for report exclusion logic."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

from custom_components.watchman.const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    DOMAIN,
)
import pytest
from tests import async_init_integration

from homeassistant.helpers import entity_registry as er


# Mock stats to ensure deterministic output for snapshots
async def mock_stats(hass, parse_duration, last_check_duration, start_time):
    """Mock function for report stats."""
    return ("01 Jan 2026 12:00:00", 1.23, 5, 0.1234)

@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
@pytest.mark.asyncio
async def test_report_exclusion_integration(hass, tmp_path, snapshot, new_test_data_dir):
    """Test report generation with disabled automation exclusion."""
    # Define source config directory
    # We point directly to the test data folder
    config_dir = str(Path(new_test_data_dir) / "reports" / "test_report_exclusion")

    # Mock hass.config.config_dir to the source dir so relative paths are calculated correctly
    hass.config.config_dir = config_dir

    # Mock hass.config.path to redirect .storage/watchman.db to tmp_path
    # This prevents creating .storage folder in tests/data
    def mock_path_side_effect(*args):
        return str(tmp_path.joinpath(*args))

    hass.config.path = MagicMock(side_effect=mock_path_side_effect)

    report_file = tmp_path / "report.txt"


    # 2. Setup HA States and Registry
    registry = er.async_get(hass)

    # Register automations with Unique IDs matching YAML IDs
    # Note: async_get_or_create returns the entity_entry.
    registry.async_get_or_create(
        "automation", "automation", "auto_disabled",
        suggested_object_id="auto_disabled"
    )
    registry.async_get_or_create(
        "automation", "automation", "auto_enabled",
        suggested_object_id="auto_enabled"
    )
    registry.async_get_or_create(
        "automation", "automation", "auto_disabled_2",
        suggested_object_id="auto_disabled_2"
    )

    # Set States (on/off for automations)
    hass.states.async_set("automation.auto_disabled", "off")
    hass.states.async_set("automation.auto_enabled", "on")
    hass.states.async_set("automation.auto_disabled_2", "off")

    # Register 'light.turn_on' so it's not reported as missing service
    hass.services.async_register("light", "turn_on", lambda x: None)

    # 3. Initialize Integration
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: str(config_dir),
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: str(report_file),
            },
            CONF_IGNORED_STATES: [],
            CONF_EXCLUDE_DISABLED_AUTOMATION: True,
        },
    )

    try:
        # 4. Generate Report
        await hass.services.async_call(DOMAIN, "report")
        await hass.async_block_till_done()

        # 5. Verify
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")

        # entity1 and action1 should be EXCLUDED as they are referenced by disabled automations
        # and CONF_EXCLUDE_DISABLED_AUTOMATION = True
        assert "sensor.entity1" not in content, "sensor.entity1 should be excluded"
        assert "service.action1" not in content, "service.action1 should be excluded"

        # entity3 should be INCLUDED (in report) because it is referenced both
        # active and disabled automation
        assert "sensor.entity3" in content, "sensor.entity3 should be included"

        # Verify snapshot
        assert content == snapshot
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
