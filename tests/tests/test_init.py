"""Tests for watchman integration setup and removal."""
import os
from pathlib import Path

from custom_components.watchman.const import DB_FILENAME
from tests import async_init_integration

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


async def test_integration_removal_cleanup(hass: HomeAssistant):
    """Test that the database, journal, and lock files are removed when the integration is deleted."""
    from custom_components.watchman.const import LOCK_FILENAME

    # 1. Setup integration
    config_entry = await async_init_integration(hass)
    assert config_entry.state == ConfigEntryState.LOADED

    # 2. Verify DB file exists
    db_path = Path(hass.config.path(".storage", DB_FILENAME))
    journal_path = Path(str(db_path) + "-journal")
    lock_path = Path(hass.config.path(".storage", LOCK_FILENAME))

    # Manually create journal and lock files if they don't exist (simulating active usage/crash)
    # The integration creates .db, but journal might be transient in WAL/TRUNCATE unless active
    if not journal_path.exists():
        journal_path.touch()
    if not lock_path.exists():
        lock_path.touch()

    assert db_path.exists()
    assert journal_path.exists()
    assert lock_path.exists()

    # 3. Remove integration
    await hass.config_entries.async_remove(config_entry.entry_id)
    await hass.async_block_till_done()

    # 4. Verify all files are removed
    assert not db_path.exists(), "Database file not removed"
    assert not journal_path.exists(), "Journal file not removed"
    assert not lock_path.exists(), "Lock file not removed"
