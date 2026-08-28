"""Test that ignored states are honoured when an entity changes monitored state.

Regression tests for the case when a reported entity switches from one monitored
state to another (e.g. `missing` -> `unavailable`). Such transitions used to be
dropped by the state change listener, so the cached verdict for the entity was
never revisited and the entity kept showing up in the report/sensor even though
its new state was excluded by the user.
"""

from pathlib import Path
from unittest.mock import MagicMock

from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    TRACKED_STATE_UNAVAILABLE,
)
import pytest
from tests import async_init_integration


async def _setup(hass, new_test_data_dir, tmp_path, ignored_states):
    """Set up watchman on the report test data folder."""
    config_dir = str(Path(new_test_data_dir) / "reports" / "test_report_generation")
    hass.config.config_dir = config_dir
    hass.config.path = MagicMock(side_effect=lambda *args: str(tmp_path.joinpath(*args)))

    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: config_dir,
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: str(tmp_path / "watchman_report.txt"),
            },
            CONF_IGNORED_STATES: ignored_states,
        },
    )
    # entities which should never show up in the report
    hass.states.async_set("sensor.outside_temp", "25.0")
    hass.states.async_set("light.living_room", "on")
    await hass.async_block_till_done()
    return config_entry


@pytest.mark.asyncio
async def test_missing_entity_becomes_unavailable_is_dropped(
    hass, new_test_data_dir, tmp_path
):
    """Entity turning from `missing` to an ignored `unavailable` leaves the report."""
    config_entry = await _setup(
        hass, new_test_data_dir, tmp_path, [TRACKED_STATE_UNAVAILABLE]
    )
    try:
        coordinator = config_entry.runtime_data.coordinator
        await coordinator.async_refresh()
        assert "switch.missing_switch" in coordinator._missing_entities_cache

        # the entity finally appears in the state machine, but as `unavailable`
        # (a common scenario shortly after a Home Assistant restart)
        hass.states.async_set("switch.missing_switch", TRACKED_STATE_UNAVAILABLE)
        await hass.async_block_till_done()

        assert "switch.missing_switch" not in coordinator._missing_entities_cache
        attrs = {item["id"]: item["state"] for item in coordinator.data["entity_attrs"]}
        assert "switch.missing_switch" not in attrs
        assert "unavail" not in attrs.values()
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_ignored_unavailable_entity_becomes_missing_is_reported(
    hass, new_test_data_dir, tmp_path
):
    """Entity leaving the ignored `unavailable` state is added back to the report."""
    config_entry = await _setup(
        hass, new_test_data_dir, tmp_path, [TRACKED_STATE_UNAVAILABLE]
    )
    try:
        coordinator = config_entry.runtime_data.coordinator
        hass.states.async_set("binary_sensor.motion_sensor", TRACKED_STATE_UNAVAILABLE)
        await coordinator.async_refresh()
        assert "binary_sensor.motion_sensor" not in coordinator._missing_entities_cache

        # entity disappears from the state machine -> `missing`, which is reported
        hass.states.async_remove("binary_sensor.motion_sensor")
        await hass.async_block_till_done()

        assert "binary_sensor.motion_sensor" in coordinator._missing_entities_cache
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_transition_between_monitored_states_without_ignored_states(
    hass, new_test_data_dir, tmp_path
):
    """Without ignored states a monitored -> monitored change keeps the entity."""
    config_entry = await _setup(hass, new_test_data_dir, tmp_path, [])
    try:
        coordinator = config_entry.runtime_data.coordinator
        await coordinator.async_refresh()
        assert "switch.missing_switch" in coordinator._missing_entities_cache

        hass.states.async_set("switch.missing_switch", TRACKED_STATE_UNAVAILABLE)
        await hass.async_block_till_done()

        assert "switch.missing_switch" in coordinator._missing_entities_cache
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
