"""Tests for sensor attribute formatting."""
import pytest
from homeassistant.core import HomeAssistant
from custom_components.watchman.const import DOMAIN, CONF_INCLUDED_FOLDERS
from tests import async_init_integration

@pytest.mark.asyncio
async def test_sensor_attribute_formatting(hass: HomeAssistant, tmp_path):
    """Test that sensor attributes are formatted as strings, not raw data."""
    config_dir = str(tmp_path)
    # Create a dummy config file
    dummy_file = tmp_path / "automations.yaml"
    dummy_file.write_text("light.missing_entity:", encoding="utf-8")

    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: [config_dir],
        },
    )

    try:
        # The integration performs an initial scan on startup
        await hass.async_block_till_done()

        # Manually trigger a report or update if needed, but the coordinator 
        # should have processed the data by now.
        state = hass.states.get("sensor.watchman_missing_entities")
        assert state is not None
        
        # Check the entities attribute
        entities = state.attributes.get("entities", [])
        assert len(entities) > 0
        
        for entity in entities:
            if entity["id"] == "light.missing_entity":
                occurrences = entity.get("occurrences")
                # Assert it is a string and contains the file emoji or path
                assert isinstance(occurrences, str)
                assert "📄" in occurrences
                assert "automations.yaml" in occurrences
                # Ensure it's not a raw string representation of a list of dicts
                assert not occurrences.startswith("[{")
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
