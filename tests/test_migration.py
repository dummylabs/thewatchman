"""Tests for Watchman configuration migration."""
from unittest.mock import MagicMock, patch, AsyncMock

from custom_components.watchman import async_migrate_entry, async_setup_entry
from custom_components.watchman.const import (
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_MAX_FILE_SIZE,
    CONF_STARTUP_DELAY,
    CONFIG_ENTRY_MINOR_VERSION,
    CONFIG_ENTRY_VERSION,
    DEFAULT_OPTIONS,
    DOMAIN,
    CONF_LOG_OBFUSCATE,
    CONF_ENFORCE_FILE_SIZE,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


@pytest.mark.asyncio
async def test_migrate_v1_to_v2(hass: HomeAssistant):
    """Test migration from version 1 (options) to version 2 (data)."""
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 1
    mock_entry.minor_version = 1
    mock_entry.data = {}
    mock_entry.options = {
        CONF_STARTUP_DELAY: 15  # Custom value from v1
    }
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    # Mock async_update_entry to capture the result
    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check that update was called with migrated data
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_entry = args[0]
    updated_data = kwargs["data"]

    assert updated_data[CONF_STARTUP_DELAY] == 15
    assert kwargs["version"] == CONFIG_ENTRY_VERSION
    assert kwargs["minor_version"] == CONFIG_ENTRY_MINOR_VERSION

@pytest.mark.asyncio
async def test_migrate_v2_minor_upgrade_forces_delay(hass: HomeAssistant):
    """Test minor version upgrade enforces minimum startup delay."""
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 1 # Previous minor version
    mock_entry.data = {
        CONF_STARTUP_DELAY: 5  # Too small, should be bumped
    }
    mock_entry.options = {}
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check update call
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_data = kwargs["data"]

    # Should be updated to default (30)
    assert updated_data[CONF_STARTUP_DELAY] == DEFAULT_OPTIONS[CONF_STARTUP_DELAY]

    # It continues to migrate to v7
    assert kwargs["minor_version"] == 7
    assert updated_data[CONF_ENFORCE_FILE_SIZE] is True

@pytest.mark.asyncio
async def test_migrate_v2_minor_upgrade_preserves_valid_delay(hass: HomeAssistant):
    """Test minor version upgrade preserves valid startup delay."""
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 1
    mock_entry.data = {
        CONF_STARTUP_DELAY: 60  # Valid custom value
    }
    mock_entry.options = {}
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check update call
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_data = kwargs["data"]

    assert updated_data[CONF_STARTUP_DELAY] == 60
    # It continues to migrate to v7
    assert kwargs["minor_version"] == 7
    assert updated_data[CONF_ENFORCE_FILE_SIZE] is True

@pytest.mark.asyncio
async def test_migrate_v2_current_version_no_op(hass: HomeAssistant):
    """Test no migration needed if version is current."""
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    # Set to current minor version (7)
    mock_entry.minor_version = 7
    mock_entry.data = {
        CONF_STARTUP_DELAY: 5 # Should remain 5 as migration logic won't run
    }
    mock_entry.options = {}

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True
    # Should not be called
    hass.config_entries.async_update_entry.assert_not_called()

@pytest.mark.asyncio
async def test_migrate_v2_minor_upgrade_adds_obfuscation(hass: HomeAssistant):
    """Test minor version upgrade to 3 adds log_obfuscate."""
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 2
    mock_entry.data = {
        CONF_STARTUP_DELAY: 30
    }
    mock_entry.options = {}
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check update call
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_data = kwargs["data"]

    assert CONF_LOG_OBFUSCATE in updated_data
    assert updated_data[CONF_LOG_OBFUSCATE] is True
    # It upgrades to 7 eventually
    assert kwargs["minor_version"] == 7
    assert updated_data[CONF_ENFORCE_FILE_SIZE] is True

@pytest.mark.asyncio
async def test_migrate_v2_minor_upgrade_adds_enforce_file_size(hass: HomeAssistant):
    """Test minor version upgrade to 5 adds enforce_file_size."""
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.version = 2
    mock_entry.minor_version = 4
    mock_entry.data = {
        CONF_STARTUP_DELAY: 30,
        CONF_LOG_OBFUSCATE: True
    }
    mock_entry.options = {}
    mock_entry.entry_id = "test_entry"
    mock_entry.domain = DOMAIN

    hass.config_entries.async_update_entry = MagicMock()

    result = await async_migrate_entry(hass, mock_entry)

    assert result is True

    # Check update call
    args, kwargs = hass.config_entries.async_update_entry.call_args
    updated_data = kwargs["data"]

    assert CONF_ENFORCE_FILE_SIZE in updated_data
    assert updated_data[CONF_ENFORCE_FILE_SIZE] is True
    assert kwargs["minor_version"] == 7

@pytest.mark.asyncio
async def test_migrate_v2_downgrade_compatibility(hass: HomeAssistant):
    """Test compatibility with future minor version (downgrade scenario)."""
    # Create entry with v2.3 data (or even future v2.4 data)
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_downgrade",
        version=2,
        # Simulate a version 3 config loaded by this integration (which handles v3)
        # But specifically checking if extra keys cause crash
        minor_version=3,
        data={
            CONF_STARTUP_DELAY: 30,
            CONF_LOG_OBFUSCATE: True,
            "future_key": "future_value" # Unknown key
        }
    )
    mock_entry.add_to_hass(hass)

    # We need to mock dependencies for async_setup_entry to run far enough
    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanHub"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coordinator_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch.object(hass.config_entries, "async_forward_entry_setups") as mock_forward:

        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load_stats = AsyncMock()
        mock_coordinator.safe_mode = False

        # Run setup
        try:
            result = await async_setup_entry(hass, mock_entry)
            assert result is True
            mock_forward.assert_called_once()
            # Verify no crash
        finally:
            await hass.config_entries.async_unload(mock_entry.entry_id)
            await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_migrate_minor_v5_to_v6_preserves_ignored_items(hass: HomeAssistant):
    """Test migration from minor v5 to v6 converts ignored_items and ignored_files from str to list."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_v5_to_v6_items",
        version=2,
        minor_version=5,
        data={
            **DEFAULT_OPTIONS,
            CONF_IGNORED_ITEMS: "sensor.foo, timer.*, switch.bar",
            CONF_IGNORED_FILES: "/config/esphome/*, */blueprints/*",
        },
    )
    mock_entry.add_to_hass(hass)

    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanHub"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coordinator_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch.object(hass.config_entries, "async_forward_entry_setups"):

        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load_stats = AsyncMock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_coordinator.safe_mode = False

        try:
            result = await hass.config_entries.async_setup(mock_entry.entry_id)
            await hass.async_block_till_done()
            assert result is True
            assert mock_entry.minor_version == 7
            assert mock_entry.data[CONF_IGNORED_ITEMS] == ["sensor.foo", "timer.*", "switch.bar"]
            assert mock_entry.data[CONF_IGNORED_FILES] == ["/config/esphome/*", "*/blueprints/*"]
        finally:
            await hass.config_entries.async_unload(mock_entry.entry_id)
            await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_migrate_minor_v5_to_v6_empty_strings(hass: HomeAssistant):
    """Test migration from minor v5 to v6 converts empty strings to empty lists."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_v5_to_v6_empty",
        version=2,
        minor_version=5,
        data={
            **DEFAULT_OPTIONS,
            CONF_IGNORED_ITEMS: "",
            CONF_IGNORED_FILES: "",
        },
    )
    mock_entry.add_to_hass(hass)

    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanHub"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coordinator_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch.object(hass.config_entries, "async_forward_entry_setups"):

        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load_stats = AsyncMock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_coordinator.safe_mode = False

        try:
            result = await hass.config_entries.async_setup(mock_entry.entry_id)
            await hass.async_block_till_done()
            assert result is True
            assert mock_entry.minor_version == 7
            assert mock_entry.data[CONF_IGNORED_ITEMS] == []
            assert mock_entry.data[CONF_IGNORED_FILES] == []
        finally:
            await hass.config_entries.async_unload(mock_entry.entry_id)
            await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_migrate_minor_v5_to_v6_already_list(hass: HomeAssistant):
    """Test migration from minor v5 to v6 does not crash when values are already lists."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_v5_to_v6_already_list",
        version=2,
        minor_version=5,
        data={
            **DEFAULT_OPTIONS,
            CONF_IGNORED_ITEMS: ["sensor.foo"],
            CONF_IGNORED_FILES: [],
        },
    )
    mock_entry.add_to_hass(hass)

    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanHub"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coordinator_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch.object(hass.config_entries, "async_forward_entry_setups"):

        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load_stats = AsyncMock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_coordinator.safe_mode = False

        try:
            result = await hass.config_entries.async_setup(mock_entry.entry_id)
            await hass.async_block_till_done()
            assert result is True
            assert mock_entry.minor_version == 7
            assert mock_entry.data[CONF_IGNORED_ITEMS] == ["sensor.foo"]
            assert mock_entry.data[CONF_IGNORED_FILES] == []
        finally:
            await hass.config_entries.async_unload(mock_entry.entry_id)
            await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_migrate_v1_to_v2_ignored_fields_are_list(hass: HomeAssistant):
    """Test that v1-to-v2 migration stores ignored_items and ignored_files as lists."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_v1_to_v2_list",
        version=1,
        minor_version=1,
        options={
            CONF_STARTUP_DELAY: 30,
            CONF_IGNORED_ITEMS: ["sensor.foo", "timer.*"],
            CONF_IGNORED_FILES: ["/config/esphome/*"],
        },
        data={},
    )
    mock_entry.add_to_hass(hass)

    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanHub"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coordinator_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch.object(hass.config_entries, "async_forward_entry_setups"):

        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load_stats = AsyncMock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_coordinator.safe_mode = False

        try:
            result = await hass.config_entries.async_setup(mock_entry.entry_id)
            await hass.async_block_till_done()
            assert result is True
            assert mock_entry.version == 2
            assert mock_entry.minor_version == 7
            assert mock_entry.data[CONF_IGNORED_ITEMS] == ["sensor.foo", "timer.*"]
            assert mock_entry.data[CONF_IGNORED_FILES] == ["/config/esphome/*"]
        finally:
            await hass.config_entries.async_unload(mock_entry.entry_id)
            await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_migrate_minor_v6_to_v7_adds_max_file_size(hass: HomeAssistant):
    """Test migration from minor v6 to v7 adds max_file_size with default value."""
    mock_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_v6_to_v7_max_file_size",
        version=2,
        minor_version=6,
        data={
            **DEFAULT_OPTIONS,
        },
    )
    mock_entry.add_to_hass(hass)

    with patch("custom_components.watchman.async_get_integration"), \
         patch("custom_components.watchman.WatchmanHub"), \
         patch("custom_components.watchman.WatchmanCoordinator") as mock_coordinator_cls, \
         patch("custom_components.watchman.WatchmanServicesSetup"), \
         patch.object(hass.config_entries, "async_forward_entry_setups"):

        mock_coordinator = mock_coordinator_cls.return_value
        mock_coordinator.async_load_stats = AsyncMock()
        mock_coordinator.async_shutdown = AsyncMock()
        mock_coordinator.safe_mode = False

        try:
            result = await hass.config_entries.async_setup(mock_entry.entry_id)
            await hass.async_block_till_done()
            assert result is True
            assert mock_entry.minor_version == 7
            assert mock_entry.data[CONF_MAX_FILE_SIZE] == DEFAULT_OPTIONS[CONF_MAX_FILE_SIZE]
        finally:
            await hass.config_entries.async_unload(mock_entry.entry_id)
            await hass.async_block_till_done()
