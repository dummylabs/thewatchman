"""Test Watchman Options Flow."""
from unittest.mock import patch, MagicMock
import pytest

from custom_components.watchman.const import (
    DOMAIN,
    CONF_IGNORED_LABELS,
    CONF_STARTUP_DELAY,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_REPORT_PATH,
    CONF_HEADER,
    CONF_COLUMNS_WIDTH,
)
from custom_components.watchman.utils.parser_const import MAX_FILE_SIZE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

@pytest.mark.asyncio
async def test_options_flow_labels(hass: HomeAssistant):
    """Test options flow label selection."""

    # 1. Setup Label Registry
    mock_registry = MagicMock()
    # Mock list of labels
    label1 = MagicMock()
    label1.label_id = "test"
    label1.name = "Test Label"

    label2 = MagicMock()
    label2.label_id = "private"
    label2.name = "Private Label"

    mock_registry.async_list_labels.return_value = [label1, label2]

    with patch("homeassistant.helpers.label_registry.async_get", return_value=mock_registry), \
         patch("custom_components.watchman.config_flow.async_is_valid_path", return_value=True), \
         patch("custom_components.watchman.DEFAULT_DELAY", 0):

        # Initialize Config Entry
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="test_entry",
            version=2,
            minor_version=4, # Current version
            data={
                CONF_IGNORED_LABELS: [],
                CONF_STARTUP_DELAY: 0
            }
        )
        config_entry.add_to_hass(hass)

        # Setup integration
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

        try:
            # 2. Interaction
            result = await hass.config_entries.options.async_init(config_entry.entry_id)

            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "init"

            # Check schema has the key
            schema = result["data_schema"]
            assert CONF_IGNORED_LABELS in schema.schema

            # Check description placeholders
            assert "max_size_kb" in result["description_placeholders"]
            assert result["description_placeholders"]["max_size_kb"] == str(MAX_FILE_SIZE//1024)

            # Simulate user selecting "test" and "private"
            # We must provide all required fields as per schema

            user_input = {
                CONF_IGNORED_LABELS: ["test", "private"],
                CONF_STARTUP_DELAY: 30,
                CONF_SECTION_APPEARANCE_LOCATION: {
                    CONF_REPORT_PATH: "/config/report.txt",
                    CONF_HEADER: "-== Watchman Report ==-",
                    CONF_COLUMNS_WIDTH: "30, 8, 60"
                }
            }

            # 3. Assertion
            # We need to mock async_update_entry on hass.config_entries because the real one updates the entry object
            # but we want to verify the call or just check the entry object afterwards.
            # The real async_update_entry updates the entry in memory.

            result = await hass.config_entries.options.async_configure(
                result["flow_id"], user_input=user_input
            )
            await hass.async_block_till_done() # Wait for possible reload

            assert result["type"] == FlowResultType.CREATE_ENTRY

            # Verify persistence
            assert config_entry.data[CONF_IGNORED_LABELS] == ["test", "private"]
        finally:
            await hass.config_entries.async_unload(config_entry.entry_id)
            await hass.async_block_till_done()
