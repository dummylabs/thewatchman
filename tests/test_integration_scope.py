"""Integration tests for scope filtering."""
from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    DOMAIN,
)
import pytest
from tests import async_init_integration


@pytest.fixture
def scope_test_data(tmp_path):
    """Create a temporary directory structure for scope testing."""
    # Structure:
    # /root_sensor.yaml  (sensor.root_sensor)
    # /custom/nested_sensor.yaml (sensor.nested_sensor)

    root = tmp_path / "config"
    root.mkdir()

    custom = root / "custom"
    custom.mkdir()

    (root / "root_sensor.yaml").write_text("name: \"{{ states('sensor.root_sensor') }}\"", encoding="utf-8")
    (custom / "nested_sensor.yaml").write_text("name: \"{{ states('sensor.nested_sensor') }}\"", encoding="utf-8")

    return root


async def _get_parsed_entities(hass):
    """Helper to fetch parsed entities from coordinator."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        return {}
    coordinator = entries[0].runtime_data.coordinator
    # Run parsing
    # We don't need to trigger parsing here if it was already triggered by the test
    # But if we want to force parse, we should use coordinator.hub
    
    # Actually, the parsing is async. If we just want to fetch the data:
    return (await coordinator.hub.async_get_all_items())["entities"]
async def test_scope_filtering_custom_folder(hass, scope_test_data, tmp_path):
    """Test that only files in included folders are parsed."""
    from custom_components.watchman.const import DEFAULT_OPTIONS

    report_file = tmp_path / "report.txt"
    custom_folder = str(scope_test_data / "custom")

    # Verify file exists
    assert (scope_test_data / "custom" / "nested_sensor.yaml").exists()

    # Prepare appearance options properly merging with defaults
    appearance = DEFAULT_OPTIONS[CONF_SECTION_APPEARANCE_LOCATION].copy()
    appearance[CONF_REPORT_PATH] = str(report_file)

    # Initialize integration with ONLY the custom folder included
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: custom_folder,
            CONF_SECTION_APPEARANCE_LOCATION: appearance,
            CONF_IGNORED_STATES: [],
        },
    )

    try:
        # Force parse (usually happens on init, but we can call report service to be sure/refresh)
        await hass.services.async_call(DOMAIN, "report")
        await hass.async_block_till_done()

        # Check internal data structures directly to verify what was parsed
        parsed_entities = await _get_parsed_entities(hass)

        # sensor.nested_sensor SHOULD be found (it's in /custom)
        assert "sensor.nested_sensor" in parsed_entities, f"Parsed entities: {parsed_entities.keys()}"

        # sensor.root_sensor SHOULD NOT be found (it's in root, which is excluded)
        assert "sensor.root_sensor" not in parsed_entities
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()

async def test_scope_filtering_default_root(hass, scope_test_data, tmp_path):
    """Test that default behavior includes everything from root."""
    from custom_components.watchman.const import DEFAULT_OPTIONS

    report_file = tmp_path / "report.txt"
    root_folder = str(scope_test_data)

    appearance = DEFAULT_OPTIONS[CONF_SECTION_APPEARANCE_LOCATION].copy()
    appearance[CONF_REPORT_PATH] = str(report_file)

    # Initialize integration with root folder (simulating default or explicit root)
    # Note: We pass the root folder explicitly here to match the test setup,
    # but logically if we passed nothing (and hass.config.config_dir was set correctly), it should also work.

    # We need to ensure hass.config.config_dir points to our temp root for the "default" logic to work
    # if we were testing the fallback. But here we can test explicit root inclusion.

    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: root_folder,
            CONF_SECTION_APPEARANCE_LOCATION: appearance,
        },
    )

    try:
        await hass.services.async_call(DOMAIN, "report")
        await hass.async_block_till_done()

        parsed_entities = await _get_parsed_entities(hass)

        assert "sensor.nested_sensor" in parsed_entities, f"Parsed entities: {parsed_entities.keys()}"
        assert "sensor.root_sensor" in parsed_entities
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
