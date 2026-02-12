"""Test Watchman Diagnostic Sensors."""
from unittest.mock import patch

from custom_components.watchman.const import (
    DOMAIN,
    SENSOR_IGNORED_FILES,
    SENSOR_LAST_PARSE,
    SENSOR_PARSE_DURATION,
    SENSOR_PROCESSED_FILES,
)
from tests import async_init_integration

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


async def test_diagnostic_sensors(hass: HomeAssistant):
    """Test the new diagnostic sensors."""
    config_entry = await async_init_integration(hass)

    try:
        ent_reg = er.async_get(hass)
        entity_registry = list(ent_reg.entities.values())

        # Helper to find entity_id by suffix
        def get_entity_id(suffix):
            return next(e.entity_id for e in entity_registry if e.unique_id.endswith(suffix))

        # 1. Verify Sensors Exist and have correct Category
        sensors = [
            SENSOR_PARSE_DURATION,
            SENSOR_LAST_PARSE,
            SENSOR_PROCESSED_FILES,
            SENSOR_IGNORED_FILES
        ]

        for sensor_suffix in sensors:
            entity_id = get_entity_id(sensor_suffix)
            entry = ent_reg.async_get(entity_id)
            assert entry is not None
            assert entry.entity_category == EntityCategory.DIAGNOSTIC, f"{sensor_suffix} should be DIAGNOSTIC"

        # 2. Trigger a scan and verify values update
        coordinator = hass.data[DOMAIN][config_entry.entry_id]

        from custom_components.watchman.utils.parser_core import ParseResult

        # Simulate parse results
        mock_result = ParseResult(
            duration=12.5,
            timestamp="2023-01-01T12:00:00+00:00",
            processed_files_count=42,
            ignored_files_count=5
        )

        await coordinator.async_save_stats(mock_result)
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        # Verify Values
        processed_id = get_entity_id(SENSOR_PROCESSED_FILES)
        assert hass.states.get(processed_id).state == "42"

        ignored_id = get_entity_id(SENSOR_IGNORED_FILES)
        assert hass.states.get(ignored_id).state == "5"

        duration_id = get_entity_id(SENSOR_PARSE_DURATION)
        assert hass.states.get(duration_id).state == "12.5"

        last_parse_id = get_entity_id(SENSOR_LAST_PARSE)
        # HA handles timestamp formatting, but it should be present
        assert hass.states.get(last_parse_id).state == "2023-01-01T12:00:00+00:00"
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
