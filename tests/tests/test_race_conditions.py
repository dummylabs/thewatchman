import asyncio
from datetime import timedelta
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

from custom_components.watchman.const import (
    DOMAIN,
    PARSE_COOLDOWN,
    STATE_IDLE,
)
from custom_components.watchman.coordinator import WatchmanCoordinator
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from tests import async_init_integration

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


@pytest.fixture
def mock_hub_parse():
    with patch("custom_components.watchman.hub.WatchmanHub.async_parse", new_callable=AsyncMock) as mock_parse:
        yield mock_parse

async def test_request_during_scan(hass: HomeAssistant, mock_hub_parse):
    """Test that a request during scan is queued and executed later."""
    # Ensure no leftover lock file from previous failed runs
    lock_path_obj = Path.cwd() / "tests/data/.storage/watchman.lock"
    lock_path_obj.unlink(missing_ok=True)

    config_entry = await async_init_integration(hass)
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    if coordinator.safe_mode:
        coordinator.update_status(STATE_IDLE)

    # 1. Start a scan that takes some time
    finish_first_parse = asyncio.Event()

    from custom_components.watchman.utils.parser_core import ParseResult

    async def slow_parse(*args, **kwargs):
        await finish_first_parse.wait()
        return ParseResult(
            duration=1.0,
            timestamp="2026-01-01T12:00:00",
            processed_files_count=1,
            ignored_files_count=0,
        )

    mock_hub_parse.side_effect = slow_parse
    mock_hub_parse.reset_mock()
    coordinator._last_parse_time = 0

    # Trigger first scan
    coordinator.request_parser_rescan(reason="first", delay=0)

    # Wait for the task to start and reach the mock
    for _ in range(10):
        if coordinator.status == "parsing":
            break
        await asyncio.sleep(0.1)

    # Verify scan is running
    assert coordinator.status == "parsing"

    # 2. Request another rescan while first is running
    coordinator.request_parser_rescan(reason="during_scan", delay=1)

    # Verify no delay timer was created (because scan is in progress)
    assert coordinator._delay_unsub is None
    # Verify flag is set
    assert coordinator._needs_parse is True

    # 3. Finish the first scan
    finish_first_parse.set()

    # Wait for it to finish and trigger the next one (which will be cooldown)
    for _ in range(10):
        if coordinator._cooldown_unsub is not None:
            break
        await asyncio.sleep(0.1)

    # The first parse finished. Because _needs_parse was True, it should have called _schedule_parse.
    # Since it's immediately after parse, it should hit COOLDOWN logic.
    assert coordinator._cooldown_unsub is not None
    assert coordinator.status == "pending"

    # 4. Advance time to pass cooldown
    # Manipulate time to satisfy check
    coordinator._last_parse_time -= (PARSE_COOLDOWN + 5)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=PARSE_COOLDOWN + 5))
    await hass.async_block_till_done()

    # Wait for the second parse to finish (we need to clear the side effect or it will hang again)
    mock_hub_parse.side_effect = None

    # Wait for background task
    for _ in range(10):
        if mock_hub_parse.call_count >= 2:
            break
        await asyncio.sleep(0.1)

    # Should have been called twice (once for first, once for queued)
    assert mock_hub_parse.call_count >= 2
