"""Tests for sensor attribute formatting."""
import pytest
from homeassistant.core import HomeAssistant
from custom_components.watchman.const import DOMAIN, CONF_INCLUDED_FOLDERS
from custom_components.watchman.coordinator import _build_references
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


def test_build_references_flattens_context():
    """_build_references must flatten parser context and default missing fields to None."""
    result = _build_references([
        {"path": "a.yaml", "line": 1, "context": None},
        {
            "path": "b.yaml",
            "line": 2,
            "context": {
                "parent_type": "automation",
                "parent_id": "auto_1",
                "parent_alias": "Test",
            },
        },
    ])
    assert result == [
        {
            "path": "a.yaml",
            "line": 1,
            "parent_type": None,
            "parent_id": None,
            "parent_alias": None,
        },
        {
            "path": "b.yaml",
            "line": 2,
            "parent_type": "automation",
            "parent_id": "auto_1",
            "parent_alias": "Test",
        },
    ]


@pytest.mark.asyncio
async def test_sensor_attribute_references(hass: HomeAssistant, tmp_path):
    """Structured `references` attribute carries per-occurrence parent context."""
    config_dir = str(tmp_path)
    automations = tmp_path / "automations.yaml"
    automations.write_text(
        "- id: test_auto_123\n"
        "  alias: Test Automation\n"
        "  trigger:\n"
        "    - platform: state\n"
        "      entity_id: light.missing_from_auto\n"
        "  action:\n"
        "    - service: light.turn_on\n"
        "      target:\n"
        "        entity_id: light.missing_from_auto\n",
        encoding="utf-8",
    )

    config_entry = await async_init_integration(
        hass,
        add_params={CONF_INCLUDED_FOLDERS: [config_dir]},
    )

    try:
        await hass.async_block_till_done()
        state = hass.states.get("sensor.watchman_missing_entities")
        assert state is not None

        entities = state.attributes.get("entities", [])
        missing = next(
            (e for e in entities if e["id"] == "light.missing_from_auto"), None
        )
        assert missing is not None, (
            f"expected light.missing_from_auto in {[e['id'] for e in entities]}"
        )

        # Back-compat: `occurrences` remains a string
        assert isinstance(missing["occurrences"], str)

        # New structured sibling attribute
        refs = missing.get("references")
        assert isinstance(refs, list) and refs

        expected_keys = {"path", "line", "parent_type", "parent_id", "parent_alias"}
        for r in refs:
            assert set(r.keys()) == expected_keys

        auto_refs = [r for r in refs if r["parent_type"] == "automation"]
        assert auto_refs, f"no automation-sourced references in {refs}"
        first = auto_refs[0]
        assert first["parent_id"] == "test_auto_123"
        assert first["parent_alias"] == "Test Automation"
        assert first["path"].endswith("automations.yaml")
        assert isinstance(first["line"], int)
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
