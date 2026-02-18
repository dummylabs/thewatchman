"""Test enforce_file_size option and parser behavior."""
import asyncio
import os
import sqlite3
import pytest
from unittest.mock import patch, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant import data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman.const import (
    DOMAIN,
    CONF_ENFORCE_FILE_SIZE,
    CONF_STARTUP_DELAY,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_REPORT_PATH,
    CONF_HEADER,
    CONF_COLUMNS_WIDTH,
    DB_FILENAME,
)
from custom_components.watchman.utils.parser_const import MAX_FILE_SIZE

# Create a file slightly larger than MAX_FILE_SIZE
LARGE_FILE_SIZE = MAX_FILE_SIZE + 1024

@pytest.fixture
def large_file(hass):
    """Create a large dummy configuration file."""
    config_dir = hass.config.config_dir
    file_path = os.path.join(config_dir, "large_config.yaml")
    
    # Content that is valid YAML but large
    # We include a reference to an entity that watchman should find
    content = """
test_reference:
  - service: light.turn_on
    entity_id: light.large_file_test_light
"""
    padding = "# " + ("x" * 100) + "\n"
    
    # Calculate how many lines we need to exceed MAX_FILE_SIZE
    # 3 lines of content (~60 bytes) + padding lines (~103 bytes each)
    target_size = LARGE_FILE_SIZE
    current_size = len(content.encode('utf-8'))
    
    while current_size < target_size:
        content += padding
        current_size += len(padding.encode('utf-8'))
        
    with open(file_path, "w") as f:
        f.write(content)
        
    yield file_path
    
    # Cleanup
    if os.path.exists(file_path):
        os.remove(file_path)

async def _get_processed_files(hass):
    """Helper to query processed_files table."""
    db_path = hass.config.path(".storage", DB_FILENAME)
    if not os.path.exists(db_path):
        return []
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT path FROM processed_files")
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

async def _get_found_items(hass, entity_id):
    """Helper to query found_items table."""
    db_path = hass.config.path(".storage", DB_FILENAME)
    if not os.path.exists(db_path):
        return []
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT entity_id FROM found_items WHERE entity_id = ?", (entity_id,))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

@pytest.mark.asyncio
async def test_options_flow_enforce_file_size(hass: HomeAssistant):
    """Test that enforce_file_size can be toggled via OptionsFlow."""
    
    # Initialize Config Entry with default (True)
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry_options",
        version=2,
        minor_version=5,
        data={
            CONF_ENFORCE_FILE_SIZE: True,
            CONF_STARTUP_DELAY: 0
        }
    )
    config_entry.add_to_hass(hass)
    
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    
    with patch("custom_components.watchman.config_flow.async_is_valid_path", return_value=True):
        try:
            # Start Options Flow
            result = await hass.config_entries.options.async_init(config_entry.entry_id)
            assert result["type"] == data_entry_flow.FlowResultType.FORM
            assert result["step_id"] == "init"
            
            # Check if option is present in schema
            schema = result["data_schema"]
            assert CONF_ENFORCE_FILE_SIZE in schema.schema
            
            # Change option to False
            user_input = {
                CONF_ENFORCE_FILE_SIZE: False,
                CONF_STARTUP_DELAY: 30,
                CONF_SECTION_APPEARANCE_LOCATION: {
                    CONF_REPORT_PATH: "/config/report.txt",
                    CONF_HEADER: "-== Watchman Report ==-",
                    CONF_COLUMNS_WIDTH: "30, 8, 60"
                }
            }
            
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], user_input=user_input
            )
            await hass.async_block_till_done()
            
            assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
            
            # Verify persistence
            assert config_entry.data[CONF_ENFORCE_FILE_SIZE] is False
            
        finally:
            await hass.config_entries.async_unload(config_entry.entry_id)
            await hass.async_block_till_done()

@pytest.mark.asyncio
async def test_parser_file_size_limit_end_to_end(hass: HomeAssistant, large_file):
    """Test end-to-end parser behavior with enforce_file_size toggle."""
    
    with patch("custom_components.watchman.DEFAULT_DELAY", 0), \
         patch("custom_components.watchman.coordinator.PARSE_COOLDOWN", 0):
        # Phase 1: Default Behavior (enforce_file_size = True)
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            unique_id="test_entry_e2e",
            version=2,
            minor_version=5,
            data={
                CONF_ENFORCE_FILE_SIZE: True,
                CONF_STARTUP_DELAY: 0,
                # We need to specify ignored_files to match default behavior or it might be missing
                "ignored_files": "" 
            }
        )
        config_entry.add_to_hass(hass)
        
        # Start integration
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
        
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        
        # Force initial parse (simulating startup scan)
        await coordinator.async_force_parse()
        await hass.async_block_till_done()
        
        # Verify file is ignored (NOT in processed_files)
        processed_files = await _get_processed_files(hass)
        # The path stored in DB is relative to config dir
        large_file_rel = os.path.basename(large_file)
        assert large_file_rel not in processed_files, "Large file should be ignored when enforce_file_size is True"
        
        # Phase 2: Toggle OFF (enforce_file_size = False)
        # Update options via ConfigEntry update (simulating OptionsFlow result)
        hass.config_entries.async_update_entry(
            config_entry, 
            data={**config_entry.data, CONF_ENFORCE_FILE_SIZE: False}
        )
        await hass.async_block_till_done()
        
        # Wait for background parser task triggered by reload
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        if coordinator._parse_task:
            await coordinator._parse_task
        await hass.async_block_till_done()
        
        # Verify file is processed (IS in processed_files)
        processed_files = await _get_processed_files(hass)
        assert large_file_rel in processed_files, "Large file should be processed when enforce_file_size is False"
        
        # Verify entities found
        found_items = await _get_found_items(hass, "light.large_file_test_light")
        assert "light.large_file_test_light" in found_items, "Entity in large file should be found"
        
        # Phase 3: Toggle ON (enforce_file_size = True)
        hass.config_entries.async_update_entry(
            config_entry, 
            data={**config_entry.data, CONF_ENFORCE_FILE_SIZE: True}
        )
        await hass.async_block_till_done()
        
        # Wait for background parser task triggered by reload
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        if coordinator._parse_task:
            await coordinator._parse_task
        await hass.async_block_till_done()
        
        # Verify file is evicted (NOT in processed_files)
        processed_files = await _get_processed_files(hass)
        assert large_file_rel not in processed_files, "Large file should be evicted when enforce_file_size is True"
        
        # Verify entities removed
        found_items = await _get_found_items(hass, "light.large_file_test_light")
        assert "light.large_file_test_light" not in found_items, "Entity from large file should be removed"
        
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
