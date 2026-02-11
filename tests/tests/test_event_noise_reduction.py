"""Test Watchman Event Noise Reduction logic."""
import pytest
from unittest.mock import patch, MagicMock
from homeassistant.const import EVENT_STATE_CHANGED
from custom_components.watchman.const import DOMAIN, CONF_INCLUDED_FOLDERS
from custom_components.watchman.coordinator import WatchmanCoordinator
from tests import async_init_integration

@pytest.mark.asyncio
async def test_event_noise_reduction(hass, tmp_path):
    """Test that irrelevant state changes are filtered out."""
    # 1. Setup
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test.yaml").write_text("sensor:\n  - platform: template\n    sensors:\n      test:\n        value_template: '{{ states.sensor.noise_test }}'", encoding="utf-8")

    await async_init_integration(hass, add_params={CONF_INCLUDED_FOLDERS: str(config_dir)})
    await hass.async_block_till_done()

    config_entry = hass.config_entries.async_entries(DOMAIN)[0]
    coordinator: WatchmanCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Helper to simulate state change and check if refresh called
    async def verify_event(old_state_val, new_state_val, should_trigger):
        with patch.object(coordinator, "async_request_refresh") as mock_refresh:
            old = MagicMock(state=old_state_val) if old_state_val is not None else None
            new = MagicMock(state=new_state_val) if new_state_val is not None else None
            
            hass.bus.async_fire(EVENT_STATE_CHANGED, {
                "entity_id": "sensor.noise_test",
                "old_state": old,
                "new_state": new
            })
            await hass.async_block_till_done()
            
            if should_trigger:
                assert mock_refresh.called, f"Should trigger for {old_state_val} -> {new_state_val}"
                assert "sensor.noise_test" in coordinator._dirty_entities
            else:
                assert not mock_refresh.called, f"Should NOT trigger for {old_state_val} -> {new_state_val}"

    # 1. Active -> Active (1 -> 2)
    # Should IGNORE
    await verify_event("1", "2", False)

    # 2. Attribute Change (1 -> 1)
    # Should IGNORE
    await verify_event("1", "1", False)

    # 3. Missing -> Active (unavailable -> on)
    # Should CAPTURE
    await verify_event("unavailable", "on", True)
    coordinator._dirty_entities.clear() # Reset

    # 4. Active -> Missing (on -> unavailable)
    # Should CAPTURE
    await verify_event("on", "unavailable", True)
    coordinator._dirty_entities.clear()

    # 5. Entity Creation (None -> on)
    # Should CAPTURE
    await verify_event(None, "on", True)
    coordinator._dirty_entities.clear()

    # 6. Missing -> Missing (unknown -> unavailable)
    # Should IGNORE
    await verify_event("unknown", "unavailable", False)

    # 7. Entity Removal (on -> None)
    # Should CAPTURE
    await verify_event("on", None, True)
    coordinator._dirty_entities.clear()
