import sqlite3
from unittest.mock import patch

from custom_components.watchman.const import COORD_DATA_MISSING_ENTITIES, DOMAIN
from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest
from tests import async_init_integration


@pytest.mark.asyncio
async def test_coordinator_resilience_read_timeout(hass, tmp_path):
    """Test coordinator handles DB read timeout (locking) gracefully."""
    # Setup integration normally first
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    await async_init_integration(hass, add_params={"included_folders": [str(config_dir)]})
    coordinator = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]

    # Mock parser.get_found_items to raise OperationalError (database locked)
    with patch.object(WatchmanParser, 'get_found_items', side_effect=sqlite3.OperationalError("database is locked")):

        # Trigger refresh
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Verify coordinator did NOT fail
        assert coordinator.last_update_success is True, "Coordinator should succeed even if DB read fails"

        # Verify data gracefully degraded (empty results -> 0 missing)
        # Note: If cache was empty, it returns empty list -> 0 missing.
        assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 0

@pytest.mark.asyncio
async def test_coordinator_resilience_parse_timeout(hass, tmp_path):
    """Test coordinator handles DB write timeout during parsing gracefully."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    await async_init_integration(hass, add_params={"included_folders": [str(config_dir)]})
    coordinator = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]

    # Mock _init_db to raise OperationalError
    # This allows scan() code to run and its try-except block to catch the error
    with patch.object(WatchmanParser, '_init_db', side_effect=sqlite3.OperationalError("database is locked")):

        # Request parsing
        await coordinator._async_update_data()
        # Should not raise exception (test passes if no unhandled exception)

@pytest.mark.asyncio
async def test_coordinator_resilience_info_timeout(hass, tmp_path):
    """Test coordinator handles DB timeout when fetching last parse info."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    await async_init_integration(hass, add_params={"included_folders": [str(config_dir)]})
    coordinator = hass.data[DOMAIN][hass.config_entries.async_entries(DOMAIN)[0].entry_id]

    # Mock get_last_parse_info to raise OperationalError
    with patch.object(
        WatchmanParser,
        "get_last_parse_info",
        side_effect=sqlite3.OperationalError("database is locked"),
    ):
        info = await coordinator.hub.async_get_last_parse_info()

        # Verify default values returned
        assert info["duration"] == 0.0
        assert info["processed_files_count"] == 0
