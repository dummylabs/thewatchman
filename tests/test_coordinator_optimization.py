"""Test Watchman Coordinator Optimization logic (Dirty Set)."""
import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed, MockConfigEntry

from custom_components.watchman.const import DOMAIN, CONF_INCLUDED_FOLDERS, COORD_DATA_MISSING_ENTITIES
from custom_components.watchman.coordinator import WatchmanCoordinator
from tests import async_init_integration

@pytest.mark.asyncio
async def test_incremental_update(hass, tmp_path):
    """Test that state change triggers incremental update (Partial Path)."""
    # 1. Setup: Config with 1 missing entity
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test.yaml").write_text("sensor:\n  - platform: template\n    sensors:\n      test:\n        value_template: '{{ states.sensor.missing_one }}'", encoding="utf-8")

    config_entry = await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: str(config_dir)})
    try:
        await hass.async_block_till_done()

        coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Verify initial state: 1 missing entity
        assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 1
        assert "sensor.missing_one" in coordinator._missing_entities_cache

        # 2. Action: Change state to 'on' (Available)
        # We patch renew_missing_items_list to ensure it is NOT called
        with patch("custom_components.watchman.coordinator.renew_missing_items_list", side_effect=AssertionError("Should not call full scan")) as mock_renew:
            hass.states.async_set("sensor.missing_one", "on")
            
            # Trigger debounce immediately
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
            await hass.async_block_till_done()

            # 3. Assert
            # Count should be 0
            assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 0
            assert "sensor.missing_one" not in coordinator._missing_entities_cache
            # Mock verified call count
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_interleaved_events(hass, tmp_path, caplog):
    """Test race condition: Dirty set followed by Global Context change triggers Full Rescan."""
    import logging
    caplog.set_level(logging.DEBUG, logger="custom_components.watchman")
    # 1. Setup
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test.yaml").write_text("sensor:\n  - platform: template\n    sensors:\n      test:\n        value_template: '{{ states.sensor.test_race }}'", encoding="utf-8")

    config_entry = await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: str(config_dir)})
    try:
        await hass.async_block_till_done()
        
        coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Initial state: missing
        assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 1

        # 2. Action: Trigger State Change (Dirty Set) AND Automation Toggle (Full Rescan)
        # Pause debouncer execution to queue both
        
        # a. Dirty Set event
        hass.states.async_set("sensor.test_race", "on")
        await hass.async_block_till_done()
        
        # b. Automation Toggle event (Global Context)
        # We simulate automation state change
        hass.states.async_set("automation.some_automation", "on")
        
        coordinator.invalidate_filter_context()
        
        # 3. Trigger Refresh
        # We verify that renew_missing_items_list IS called (Full Path)
        
        import custom_components.watchman.coordinator as coord_module
        original_renew = coord_module.renew_missing_items_list
        
        with patch("custom_components.watchman.coordinator.renew_missing_items_list", wraps=None) as mock_renew:
            mock_renew.side_effect = original_renew

            # Simulate the refresh request that usually accompanies context invalidation
            await coordinator.async_request_refresh()
            
            # Ensure debouncer fires if delayed
            async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
            await hass.async_block_till_done()

            # Check result first to confirm update ran
            assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 0, "Entities should be found (0 missing)"
            
            # Check logs for Full Rescan path
            assert "performing FULL status check." in caplog.text
            # Mock verification (optional if logs checked, but good double check)
            assert mock_renew.called, "Full rescan SHOULD happen"
            
        # 4. Assert Final State
            
        # 4. Assert Final State
        # Entity is ON, so it should NOT be missing.
        # Full rescan should detect "on" state.
        assert len(coordinator._dirty_entities) == 0
        assert coordinator._force_full_rescan is False
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

@pytest.mark.asyncio
async def test_debounce_flip_flop(hass, tmp_path):
    """Test entity flipping state within debounce window."""
    # 1. Setup
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test.yaml").write_text("sensor:\n  - platform: template\n    sensors:\n      test:\n        value_template: '{{ states.sensor.flip_flop }}'", encoding="utf-8")

    config_entry = await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: str(config_dir)})
    try:
        await hass.async_block_till_done()
        
        coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        # Initial: Missing
        assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 1
        
        # 2. Flip Flop sequence
        # Missing -> On -> Missing
        
        # a. On
        hass.states.async_set("sensor.flip_flop", "on")
        # b. Missing (Unavailable)
        hass.states.async_set("sensor.flip_flop", "unavailable")
        
        # 3. Fire Debounce
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
        await hass.async_block_till_done()
        
        # 4. Assert
        # It should be missing
        assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 1
        # Verify we processed the dirty entity
        assert "sensor.flip_flop" in coordinator._missing_entities_cache
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_unknown_entity(hass, tmp_path):
    """Test state change for unknown entity does not crash or affect counters."""
    # 1. Setup
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test.yaml").write_text("sensor:\n  - platform: template\n    sensors:\n      test:\n        value_template: '{{ states.sensor.known }}'", encoding="utf-8")

    config_entry = await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: str(config_dir)})
    try:
        await hass.async_block_till_done()
        
        coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        initial_missing = coordinator.data[COORD_DATA_MISSING_ENTITIES]
        
        # 2. Action: Fire event for unknown entity
        # This adds it to _dirty_entities
        hass.states.async_set("sensor.random_garbage", "on")
        
        # 3. Fire Debounce
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
        await hass.async_block_till_done()
        
        # 4. Assert
        assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == initial_missing
        # Should not be in missing cache
        assert "sensor.random_garbage" not in coordinator._missing_entities_cache
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
