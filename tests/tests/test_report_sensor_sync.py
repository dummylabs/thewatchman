"""Test Watchman Report and Sensor synchronization."""
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed
from custom_components.watchman.const import DOMAIN, CONF_INCLUDED_FOLDERS, COORD_DATA_MISSING_ENTITIES
from custom_components.watchman.coordinator import WatchmanCoordinator
from tests import async_init_integration

@pytest.mark.asyncio
async def test_report_service_forces_full_rescan(hass, tmp_path):
    """Test that watchman.report service forces a full rescan of sensors."""
    # 1. Setup: Config with 1 missing entity
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test.yaml").write_text("sensor:\n  - platform: template\n    sensors:\n      test:\n        value_template: '{{ states.sensor.sync_test }}'", encoding="utf-8")

    await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: str(config_dir)})
    await hass.async_block_till_done()

    config_entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Verify initial state: 1 missing entity
    assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 1
    
    # 2. Action: Set flag to False to simulate cached state
    coordinator._force_full_rescan = False
    coordinator._dirty_entities.clear()
    
    # Change state of the entity in HA but avoid triggering the coordinator's listener 
    # (or just assume we want to prove Branch A is taken regardless of dirty set)
    hass.states.async_set("sensor.sync_test", "on")
    # Coordinator would usually be notified and set dirty, but we want to test the report service override.
    # To be absolutely sure we test the override, we clear dirty entities again.
    coordinator._dirty_entities.clear()
    
    # At this point:
    # _force_full_rescan = False
    # _dirty_entities = empty
    # If we call refresh now, it would return 1 (cached).
    
    # 3. Call watchman.report service
    import custom_components.watchman.coordinator as coord_module
    original_renew = coord_module.renew_missing_items_list
    
    with patch("custom_components.watchman.coordinator.renew_missing_items_list", wraps=None) as mock_renew:
        # We need the real function to execute so sensors update
        mock_renew.side_effect = original_renew
        
        await hass.services.async_call(DOMAIN, "report", {"create_file": False}, blocking=True)
        
        # Service call schedules refresh. Trigger debounce.
        async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=10))
        await hass.async_block_till_done()
        
        # Verify Branch A (Full Rescan) was taken
        assert mock_renew.called, "Full rescan SHOULD be forced by report service"
        
    # 4. Assert Final State: Sensors should be 0
    assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 0
