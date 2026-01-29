"""Test for custom domain injection via hass services."""
import pytest
import os
import asyncio
from unittest.mock import MagicMock
from custom_components.watchman.hub import WatchmanHub
from custom_components.watchman.const import DOMAIN_DATA

@pytest.mark.asyncio
async def test_custom_domain_injection(new_test_data_dir, tmp_path):
    """Test that custom domains from hass.services are recognized."""
    
    # 1. Setup Mock Hass
    hass = MagicMock()
    
    # Mock services.async_services() to return a dict with our fake domain
    hass.services.async_services.return_value = {
        "fake_custom_domain": {"my_service": "description"}
    }
    
    # Mock hass.config properties for DB path and relative path calculations
    hass.config.config_dir = new_test_data_dir
    
    def mock_path(*args):
        # redirect .storage/watchman.db to tmp_path
        return str(tmp_path / os.path.join(*args))
    
    hass.config.path = MagicMock(side_effect=mock_path)
    
    # Mock async_add_executor_job to run synchronously for the test
    # We return a Future so it can be awaited (by parser methods) OR ignored (by __init__)
    def run_sync(target, *args):
        res = target(*args)
        f = asyncio.Future()
        f.set_result(res)
        return f
        
    hass.async_add_executor_job = MagicMock(side_effect=run_sync)

    # Mock hass.data and config_entries for get_entry(hass)
    hass.data = {DOMAIN_DATA: {"config_entry_id": "test_entry_id"}}
    
    from homeassistant.config_entries import ConfigEntry
    mock_entry = MagicMock(spec=ConfigEntry)
    mock_entry.entry_id = "test_entry_id"
    mock_entry.data = {
        "ignored_items": "",
    }
    
    # Setup WatchmanHub with a temp DB path
    db_path = str(tmp_path / "watchman.db")
    hub = WatchmanHub(hass, db_path)
    
    # Mock runtime_data structure
    mock_runtime_data = MagicMock()
    mock_runtime_data.hub = hub
    mock_entry.runtime_data = mock_runtime_data
    
    hass.config_entries.async_get_entry.return_value = mock_entry

    # 2. Setup Config File Input
    # We only scan the specific file
    yaml_dir = os.path.join(new_test_data_dir, "yaml_config")
    ignored_files = []

    # 3. Execute
    # Run parsing
    await hub.async_parse(
        ignored_files
    )
    
    # We need to get parsed items from the hub to check services
    parsed_services = await hub.async_get_parsed_services()
    parsed_service_list = list(parsed_services.keys())
    # 'fake_custom_domain.my_service' should be found because 'fake_custom_domain' 
    # was provided in hass.services
    assert "fake_custom_domain.my_service" in parsed_service_list, \
        "Custom domain service should be detected when injected via hass"