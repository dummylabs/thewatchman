"""Test ignored files in .storage directory."""
import asyncio
import os
from pathlib import Path
from unittest.mock import patch

from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest
from custom_components.watchman.const import (
    CONF_IGNORED_FILES,
    CONF_IGNORED_STATES,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_REPORT_PATH,
    CONF_HEADER,
    CONF_COLUMNS_WIDTH,
    CONF_STARTUP_DELAY,
    DOMAIN,
    STATE_IDLE,
    STATE_SAFE_MODE,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from tests import async_init_integration

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

def test_storage_ignored_files(parser_client, tmp_path):
    """Test that ignored files in .storage are respected."""
    
    # 1. Setup Mock Directory Structure
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    storage_dir = config_dir / ".storage"
    storage_dir.mkdir()
    
    # Create a standard whitelisted file
    (storage_dir / "core.config_entries").write_text("{}")
    
    # Create a lovelace file that we want to IGNORE
    (storage_dir / "lovelace.dashboard_test").write_text("{}")
    
    # Create a lovelace file that we want to KEEP
    (storage_dir / "lovelace.dashboard_keep").write_text("{}")
    
    # 2. Run Parser with ignored pattern
    ignored_patterns = ["*dashboard_test*"]
    
    # We use async_parse but we are interested in the side effect (DB content)
    asyncio.run(parser_client.async_parse(
        str(config_dir),
        ignored_patterns
    ))
    
    # 3. Verify Results
    processed_files = parser_client.get_processed_files()
    processed_paths = [f[1] for f in processed_files]
    
    # Debug info
    print(f"Processed paths: {processed_paths}")
    
    # Check that core.config_entries is present (baseline)
    # The path in DB is relative to where parser ran or absolute?
    # parser_core.py says:
    # if base_path: path_for_db = relpath
    # In async_parse call above, we didn't provide base_path, so it stores absolute path usually,
    # or whatever _scan_files_sync returns.
    # _scan_files_sync returns absolute paths.
    
    # Let's check for substring presence to be safe
    assert any("core.config_entries" in p for p in processed_paths), "core.config_entries should be scanned"
    assert any("lovelace.dashboard_keep" in p for p in processed_paths), "lovelace.dashboard_keep should be scanned"
    
    # THIS SHOULD FAIL INITIALLY
    assert not any("lovelace.dashboard_test" in p for p in processed_paths), "lovelace.dashboard_test should be IGNORED"


async def _force_parse_and_wait(hass: HomeAssistant, config_entry_id: str) -> None:
    """Force an immediate re-parse on the current coordinator and wait for it to finish.

    After an options-flow reload, the coordinator is in STATE_PENDING waiting on a
    call_later(0) handle that the asyncio test loop does not automatically drain.
    Calling request_parser_rescan(force=True) cancels the pending timer and creates a
    real asyncio Task that async_block_till_done() can observe.
    """
    coordinator = hass.data[DOMAIN][config_entry_id]
    coordinator.request_parser_rescan(force=True)
    await hass.async_block_till_done()
    # Executor jobs (hass.async_add_executor_job) may not all be captured by a single
    # async_block_till_done; use a short polling loop as a safety net.
    for _ in range(50):
        if coordinator.status in [STATE_IDLE, STATE_SAFE_MODE]:
            break
        await asyncio.sleep(0.1)
    else:
        raise TimeoutError(f"Coordinator stuck in '{coordinator.status}' after forced parse")


@pytest.mark.asyncio
async def test_options_flow_add_ignored_files(hass: HomeAssistant):
    """Test that adding an ignored file pattern via options flow hides its entities."""
    # Init with default settings (basic_config.yaml is included, sensor.skylight is reported)
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_FILES: [],
            CONF_IGNORED_STATES: [],
        },
    )

    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        entity_ids_before = [e["id"] for e in coordinator.data.get("entity_attrs", [])]
        assert "sensor.skylight" in entity_ids_before, (
            "sensor.skylight must be present before ignoring basic_config.yaml"
        )

        # Open options flow and ignore basic_config.yaml
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        user_input = {
            CONF_IGNORED_FILES: ["*/basic_config.yaml"],
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
        assert config_entry.data[CONF_IGNORED_FILES] == ["*/basic_config.yaml"]

        # Force an immediate re-parse (which skips basic_config.yaml) and wait
        await _force_parse_and_wait(hass, config_entry.entry_id)

        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        entity_ids_after = [e["id"] for e in coordinator.data.get("entity_attrs", [])]
        assert "sensor.skylight" not in entity_ids_after, (
            "sensor.skylight must be absent after ignoring basic_config.yaml"
        )
        assert "switch.skylight" not in entity_ids_after, (
            "switch.skylight must be absent after ignoring basic_config.yaml"
        )
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_options_flow_clear_ignored_files(hass: HomeAssistant):
    """Test that clearing ignored files via options flow restores their entities."""
    # Init with basic_config.yaml already ignored — sensor.skylight is NOT parsed
    config_entry = await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_FILES: ["*/basic_config.yaml"],
            CONF_IGNORED_STATES: [],
        },
    )

    try:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        entity_ids_before = [e["id"] for e in coordinator.data.get("entity_attrs", [])]
        assert "sensor.skylight" not in entity_ids_before, (
            "sensor.skylight must be absent when basic_config.yaml is ignored"
        )

        # Open options flow and clear ignored files
        result = await hass.config_entries.options.async_init(config_entry.entry_id)
        assert result["type"] == FlowResultType.FORM

        user_input = {
            CONF_IGNORED_FILES: [],
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
        assert config_entry.data[CONF_IGNORED_FILES] == []

        # Force an immediate re-parse (which now includes basic_config.yaml) and wait
        await _force_parse_and_wait(hass, config_entry.entry_id)

        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        entity_ids_after = [e["id"] for e in coordinator.data.get("entity_attrs", [])]
        assert "sensor.skylight" in entity_ids_after, (
            "sensor.skylight must reappear after clearing ignored files"
        )
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
