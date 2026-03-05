"""Test exclusion of items via CONF_IGNORED_ITEMS."""
import pytest
from custom_components.watchman.const import (
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_REPORT_PATH,
    CONF_HEADER,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry
from tests import async_init_integration
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from unittest.mock import patch


@pytest.mark.asyncio
async def test_ignored_items_exact_match(hass: HomeAssistant):
    """Test ignoring specific entities and services by exact name."""
    # We use basic_config.yaml which has:
    # Entities: sensor.skylight, switch.skylight
    # Services: switch.turn_on, switch.turn_off

    # We ignore one of each
    ignored = ["sensor.skylight", "switch.turn_off"]

    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_ITEMS: ignored,
            CONF_IGNORED_STATES: [],  # Ensure everything is reported as missing
        },
    )

    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Check Entities
        # sensor.skylight should be ignored
        # switch.skylight should be reported

        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]

        assert "sensor.skylight" not in missing_entity_ids, "sensor.skylight should be ignored"
        assert "switch.skylight" in missing_entity_ids, "switch.skylight should be reported"

        # Check Services
        # switch.turn_off should be ignored
        # switch.turn_on should be reported

        service_attrs = coordinator.data.get("service_attrs", [])
        missing_service_ids = [s["id"] for s in service_attrs]

        assert "switch.turn_off" not in missing_service_ids, "switch.turn_off should be ignored"
        assert "switch.turn_on" in missing_service_ids, "switch.turn_on should be reported"
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_ignored_items_glob_match(hass: HomeAssistant):
    """Test ignoring items using glob patterns."""
    # We ignore all switches and all services starting with switch.
    ignored = ["switch.*"]

    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_ITEMS: ignored,
            CONF_IGNORED_STATES: [],
        },
    )

    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Check Entities
        # switch.skylight should be ignored (matches switch.*)
        # sensor.skylight should be reported

        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]

        assert "switch.skylight" not in missing_entity_ids, "switch.skylight should be ignored by glob"
        assert "sensor.skylight" in missing_entity_ids, "sensor.skylight should be reported"

        # Check Services
        # switch.turn_on and switch.turn_off should be ignored (matches switch.*)

        service_attrs = coordinator.data.get("service_attrs", [])
        missing_service_ids = [s["id"] for s in service_attrs]

        assert "switch.turn_on" not in missing_service_ids
        assert "switch.turn_off" not in missing_service_ids
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_options_flow_add_ignored_items(hass: HomeAssistant):
    """Test adding ignored items via the options flow chip selector."""
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_ITEMS: [],
            CONF_IGNORED_STATES: [],
        },
    )

    try:
        # Open options flow
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

        # Submit with new ignored items (chip selector passes a list)
        user_input = {
            CONF_IGNORED_ITEMS: ["sensor.skylight", "switch.*"],
            CONF_STARTUP_DELAY: 0,
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: hass.config.path("watchman_report.txt"),
                CONF_HEADER: "-== Watchman Report ==-",
                CONF_COLUMNS_WIDTH: "30, 8, 60",
            },
        }

        with patch("custom_components.watchman.config_flow.async_is_valid_path", return_value=True):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], user_input=user_input
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY

        # Verify the data was persisted as a list
        assert config_entry.data[CONF_IGNORED_ITEMS] == ["sensor.skylight", "switch.*"]

        # Verify coordinator now excludes sensor.skylight and switch.*
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]

        assert "sensor.skylight" not in missing_entity_ids
        assert "switch.skylight" not in missing_entity_ids

        service_attrs = coordinator.data.get("service_attrs", [])
        missing_service_ids = [s["id"] for s in service_attrs]
        assert "switch.turn_on" not in missing_service_ids
        assert "switch.turn_off" not in missing_service_ids
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_options_flow_clear_ignored_items(hass: HomeAssistant):
    """Test clearing ignored items via the options flow."""
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_ITEMS: ["sensor.skylight"],
            CONF_IGNORED_STATES: [],
        },
    )

    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]

        # Confirm sensor.skylight is absent from the initial report
        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]
        assert "sensor.skylight" not in missing_entity_ids, "sensor.skylight should be initially ignored"

        # Open options flow and clear all ignored items
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        user_input = {
            CONF_IGNORED_ITEMS: [],  # User cleared all chips
            CONF_STARTUP_DELAY: 0,
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: hass.config.path("watchman_report.txt"),
                CONF_HEADER: "-== Watchman Report ==-",
                CONF_COLUMNS_WIDTH: "30, 8, 60",
            },
        }

        with patch("custom_components.watchman.config_flow.async_is_valid_path", return_value=True):
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], user_input=user_input
            )
            await hass.async_block_till_done()

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert config_entry.data[CONF_IGNORED_ITEMS] == []

        # Confirm sensor.skylight is now present in the report
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        entity_attrs = coordinator.data.get("entity_attrs", [])
        missing_entity_ids = [e["id"] for e in entity_attrs]
        assert "sensor.skylight" in missing_entity_ids, "sensor.skylight should appear after clearing ignored items"
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_options_flow_initial_render_preserves_chips(hass: HomeAssistant):
    """Test that the initial options form render does not merge list items into one chip.

    Data already stored as list[str] (minor_version=6) must appear as individual
    chips, not a single merged chip.
    """
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_initial_render_chips",
        version=2,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data={**DEFAULT_OPTIONS, CONF_IGNORED_ITEMS: ["sensor.foo", "timer.*"]},
    )
    config_entry.add_to_hass(hass)

    with patch("custom_components.watchman.DEFAULT_DELAY", 0):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    try:
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        # Extract the suggested value for CONF_IGNORED_ITEMS from the schema.
        # add_suggested_values_to_schema stores it in key.description["suggested_value"].
        data_schema = result["data_schema"]
        ignored_items_suggested = None
        for key in data_schema.schema:
            if hasattr(key, "schema") and key.schema == CONF_IGNORED_ITEMS:
                ignored_items_suggested = (key.description or {}).get("suggested_value")
                break

        assert ignored_items_suggested == ["sensor.foo", "timer.*"], (
            "Initial render must preserve individual chips, not merge them into one string"
        )
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
