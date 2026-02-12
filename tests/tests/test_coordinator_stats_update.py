"""Test Coordinator stats update logic."""
import pytest
from tests import async_init_integration
from custom_components.watchman.const import (
    DOMAIN,
    COORD_DATA_PARSE_DURATION,
    COORD_DATA_LAST_PARSE,
    COORD_DATA_PROCESSED_FILES,
    COORD_DATA_IGNORED_FILES,
)
from custom_components.watchman.utils.parser_core import ParseResult
from homeassistant.util import dt as dt_util

@pytest.mark.asyncio
async def test_async_save_stats_updates_memory(hass):
    """Test that async_save_stats updates the coordinator's in-memory data."""
    config_entry = await async_init_integration(hass)
    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Reset data to ensure clean state
        coordinator.data[COORD_DATA_PARSE_DURATION] = 0.0
        coordinator.data[COORD_DATA_PROCESSED_FILES] = 0

        # Initial state should be empty/zero
        assert coordinator.data.get(COORD_DATA_PARSE_DURATION) == 0.0
        assert coordinator.data.get(COORD_DATA_PROCESSED_FILES) == 0

        # Simulate a parse result
        timestamp_str = "2023-01-01T12:00:00+00:00"
        mock_result = ParseResult(
            duration=42.5,
            timestamp=timestamp_str,
            processed_files_count=100,
            ignored_files_count=10
        )

        # Call save stats
        await coordinator.async_save_stats(mock_result)

        # VERIFY: In-memory data should be updated IMMEDIATELY
        # This is expected to FAIL before the fix
        assert coordinator.data[COORD_DATA_PARSE_DURATION] == 42.5
        assert coordinator.data[COORD_DATA_PROCESSED_FILES] == 100
        assert coordinator.data[COORD_DATA_IGNORED_FILES] == 10
        
        # Check timestamp conversion
        last_parse = coordinator.data[COORD_DATA_LAST_PARSE]
        assert last_parse is not None
        assert last_parse.isoformat() == timestamp_str
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
