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

    coordinator = AsyncMock()
    coordinator.async_force_parse = AsyncMock()

    # We need to setup the integration partially or mock the services setup
    # Because we are testing the service call, we need the service registered.
    # The easiest way is to let the component set up, then patch the coordinator.
    from custom_components.watchman.const import (
        COORD_DATA_IGNORED_FILES,
        COORD_DATA_LAST_PARSE,
        COORD_DATA_MISSING_ACTIONS,
        COORD_DATA_MISSING_ENTITIES,
        COORD_DATA_PARSE_DURATION,
        COORD_DATA_PROCESSED_FILES,
        DOC_URL,
    )

    with patch("custom_components.watchman.WatchmanCoordinator") as mock_coord_cls, \
         patch("custom_components.watchman.services.async_report_to_file"), \
         patch("custom_components.watchman.services.async_report_to_notification"), \
         patch("custom_components.watchman.coordinator.WatchmanCoordinator") as mock_coord_cls_coord, \
         patch("custom_components.watchman.utils.report.get_entry", return_value=config_entry), \
         patch("custom_components.watchman.utils.report.parsing_stats", new_callable=AsyncMock) as mock_stats:

        mock_stats.return_value = ("2023-01-01 12:00:00", 1.5, 0.1, 0.1)

        mock_coord_cls.return_value = coordinator
        mock_coord_cls_coord.return_value = coordinator
        coordinator.async_get_detailed_report_data = AsyncMock(return_value={})
        coordinator._build_filter_context = MagicMock()
        coordinator.async_get_last_parse_duration = AsyncMock(return_value=1.5)
        coordinator.last_check_duration = 0.1
        # Prevent auto-mocking of config_entry which causes RuntimeWarnings when accessed as dict
        coordinator.config_entry = config_entry
        # async_set_updated_data is synchronous in DataUpdateCoordinator, but AsyncMock makes it async
        coordinator.async_set_updated_data = MagicMock()
        # async_add_listener is also synchronous
        coordinator.async_add_listener = MagicMock()

        # Mock data dict for stats lookup in report.py
        coordinator.data = {
            COORD_DATA_PROCESSED_FILES: 0,
            COORD_DATA_IGNORED_FILES: 0,
            COORD_DATA_PARSE_DURATION: 0.0,
            COORD_DATA_LAST_PARSE: None,
            COORD_DATA_MISSING_ACTIONS: 0,
            COORD_DATA_MISSING_ENTITIES: 0,
        }
        coordinator.hub.async_get_all_items = AsyncMock(return_value={"entities": {}, "services": {}})

        assert await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    return coordinator

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

        mock_coordinator.async_force_parse.assert_called_once_with(ignore_mtime=True)

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
