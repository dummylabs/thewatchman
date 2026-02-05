"""Test race condition: Zombie Listener Resurrects Database after Unload."""
import os
from pathlib import Path
from custom_components.watchman.const import DB_FILENAME, DOMAIN
from tests import async_init_integration
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
import pytest

@pytest.mark.asyncio
async def test_zombie_listener_resurrection(hass: HomeAssistant):
    """
    Test that the database file reappears after unload if the start event fires.
    This simulates a race condition where the integration is unloaded *before* HA finishes starting.
    """
    # 1. Setup the integration entry (mock config)
    # This will initialize the DB
    entry = await async_init_integration(hass)
    
    # 2. Assert watchman_v2.db exists in the storage directory
    db_path = Path(hass.config.path(".storage", DB_FILENAME))
    assert db_path.exists(), "DB file should exist after setup"

    # 3. Call await hass.config_entries.async_unload(entry.entry_id)
    unload_result = await hass.config_entries.async_unload(entry.entry_id)
    assert unload_result is True, "Unload should succeed"
    await hass.async_block_till_done()

    # 4. Assert watchman_v2.db does NOT exist (cleanup successful)
    # The existing async_remove_entry logic handles this cleanup
    # We trigger removal manually or via config flow, but here async_unload just stops the integration.
    # However, if the user *removes* the entry, it deletes the file.
    # But wait, the issue description says "cleanup successful" after unload.
    # Standard Home Assistant unload does NOT delete data files. Only removing the entry does.
    # Let's re-read the context: "the integration is initialized and immediately unloaded... recreating the deleted database".
    # This implies the user might have removed it, or the test setup assumes cleanup.
    # Let's verify if `async_unload_entry` deletes the DB. 
    # Checking `__init__.py`: `async_unload_entry` does NOT delete the file. `async_remove_entry` does.
    
    # To faithfully reproduce the "Zombie Listener Resurrects Database after Unload" described:
    # If the user *removes* the integration, `async_unload` is called first, then `async_remove`.
    # `async_remove` deletes the file.
    # BUT, the `EVENT_HOMEASSISTANT_STARTED` listener was registered in `setup`.
    # If that listener fires AFTER removal, it calls `coordinator.request_parser_rescan` -> `_execute_parse` -> `_init_db` -> creates file.
    
    # So we must simulate REMOVAL.
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    
    assert not db_path.exists(), "DB file should be deleted after removal"

    # 5. Trigger the start event: hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    # This is the leaked listener firing late
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    
    # 6. Wait for background tasks
    await hass.async_block_till_done()
    
    # The listener schedules a parse with a delay (default 30s).
    # We must advance time to trigger it.
    from pytest_homeassistant_custom_component.common import async_fire_time_changed
    from homeassistant.util import dt as dt_util
    from datetime import timedelta
    
    # Fast forward time past the default startup delay
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=60))
    await hass.async_block_till_done()

    # 7. Assertion (Failure Condition): Check if watchman_v2.db exists again.
    # If it exists, the zombie listener ran `async_on_home_assistant_started` which triggered DB creation.
    assert not db_path.exists(), "Zombie listener resurrected the database file!"
