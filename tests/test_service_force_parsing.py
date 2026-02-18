"""Test Watchman services logic."""
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from homeassistant.core import HomeAssistant
from custom_components.watchman.const import (
    CONF_FORCE_PARSING,
    CONF_PARSE_CONFIG,
    DOMAIN,
    REPORT_SERVICE_NAME,
    DOC_URL,
)

@pytest.fixture
async def mock_coordinator(hass):
    """Mock the coordinator."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    config_entry = MockConfigEntry(domain=DOMAIN, data={}, entry_id="test_entry")
    config_entry.add_to_hass(hass)

    # Let the real component setup, but mock side-effects
    with patch("custom_components.watchman.services.async_report_to_file"), \
         patch("custom_components.watchman.services.async_report_to_notification"):

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    # Retrieve the REAL coordinator created by the integration setup
    coordinator = config_entry.runtime_data.coordinator

    # Patch ONLY the async_force_parse method
    with patch.object(coordinator, "async_force_parse", new_callable=AsyncMock):
        yield coordinator

async def test_report_service_force_parsing(hass: HomeAssistant, mock_coordinator):
    """Test calling report service with force_parsing=True."""
    with patch("custom_components.watchman.services.ir.async_create_issue") as mock_create_issue:
        await hass.services.async_call(
            DOMAIN,
            REPORT_SERVICE_NAME,
            {CONF_FORCE_PARSING: True},
            blocking=True,
        )

        mock_coordinator.async_force_parse.assert_called_once_with(ignore_mtime=True)
        # Verify no issue created
        mock_create_issue.assert_not_called()

async def test_report_service_legacy_parse_config(hass: HomeAssistant, mock_coordinator):
    """Test calling report service with legacy parse_config=True."""
    with patch("custom_components.watchman.services.ir.async_create_issue") as mock_create_issue:
        await hass.services.async_call(
            DOMAIN,
            REPORT_SERVICE_NAME,
            {CONF_PARSE_CONFIG: True},
            blocking=True,
        )

        mock_coordinator.async_force_parse.assert_called_once_with(ignore_mtime=False)

        # Verify issue created
        mock_create_issue.assert_called_once()
        args, kwargs = mock_create_issue.call_args
        assert args[1] == DOMAIN
        assert args[2] == "deprecated_parse_config_parameter"
        assert kwargs["translation_key"] == "deprecated_service_param"
        assert kwargs["translation_placeholders"]["deprecated_param"] == CONF_PARSE_CONFIG
        assert kwargs["translation_placeholders"]["url"] == DOC_URL

async def test_report_service_default(hass: HomeAssistant, mock_coordinator):
    """Test calling report service with default parameters (False)."""
    await hass.services.async_call(
        DOMAIN,
        REPORT_SERVICE_NAME,
        {},
        blocking=True,
    )

    mock_coordinator.async_force_parse.assert_called_once_with(ignore_mtime=False)
