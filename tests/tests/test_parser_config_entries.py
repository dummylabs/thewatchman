"""Tests for parsing core.config_entries."""
import asyncio
import json
from pathlib import Path

from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest


@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client


def test_parse_core_config_entries(parser_client, tmp_path):
    """Test specialized parsing for core.config_entries."""
    
    # Setup .storage directory
    storage_dir = tmp_path / ".storage"
    storage_dir.mkdir()
    
    config_entries_file = storage_dir / "core.config_entries"
    
    # Mock content
    content = {
        "data": {
            "entries": [
                {
                    "entry_id": "entry_1",
                    "domain": "group",
                    "title": "Kitchen Group",
                    "data": {
                        "entities": ["light.kitchen_ceiling"]
                    }
                },
                {
                    "entry_id": "entry_2",
                    "domain": "template",
                    "title": "Garage Template",
                    "options": {
                        "template_data": "{{ is_state('binary_sensor.garage_door', 'on') }}"
                    }
                },
                {
                    "entry_id": "entry_3",
                    "domain": "hassio",
                    "title": "Supervisor",
                    "data": {
                        "some_config": "sensor.fake_sensor"
                    }
                },
                 {
                    "entry_id": "entry_4",
                    "domain": "system",
                    "title": "System",
                    "data": {
                        "info": "sensor.another_fake"
                    }
                }
            ]
        }
    }
    
    config_entries_file.write_text(json.dumps(content), encoding="utf-8")
    
    # Run Parser
    # We point to tmp_path. The parser should traverse .storage automatically if logic permits, 
    # OR we might need to point to .storage depending on how _scan_files works.
    # _scan_files_sync checks for .storage/whitelist.
    # We need to ensure core.config_entries is in STORAGE_WHITELIST for it to be picked up by the scanner first.
    # If not, the test will fail finding NOTHING.
    # But the instructions say "Update _parse_content to detect if the filename ends with core.config_entries".
    # This implies we might need to add it to whitelist too if it's not there.
    # Let's check the current whitelist in parser_const.py later. For now, we assume if it's not whitelisted, the test will fail as expected (baseline).
    
    asyncio.run(parser_client.async_parse(str(tmp_path), []))
    items = parser_client.get_found_items(item_type='all')
    parsed_entities = [item[0] for item in items if item[3] == 'entity']
    parsed_services = [item[0] for item in items if item[3] == 'service']
    
    # Assertions
    
    # 1. Should find legit entities
    assert "light.kitchen_ceiling" in parsed_entities, "Should find entity in group entry"
    assert "binary_sensor.garage_door" in parsed_entities, "Should find entity in template entry"
    
    # 2. Should NOT find entities in ignored domains
    # CURRENTLY (Baseline): This assertion is expected to FAIL if the parser treats it as generic JSON/Text 
    # and finds "sensor.fake_sensor". 
    # OR it fails because it doesn't parse the file at all (if not in whitelist).
    
    # We write the assert such that if the code IS working as desired, it passes.
    assert "sensor.fake_sensor" not in parsed_entities, "Should ignore entity in hassio entry"
    assert "sensor.another_fake" not in parsed_entities, "Should ignore entity in system entry"

    # 3. Check Context (Advanced)
    # To check context we need to query the DB directly because async_parse returns just lists.
    # WatchmanParser has get_automation_context(entity_id).
    
    ctx = parser_client.get_automation_context("light.kitchen_ceiling")
    assert ctx, "Context should exist for light.kitchen_ceiling"
    assert ctx["parent_alias"] == "Kitchen Group"
    assert ctx["parent_type"] == "helper_group"
    
    ctx_tmpl = parser_client.get_automation_context("binary_sensor.garage_door")
    assert ctx_tmpl, "Context should exist for binary_sensor.garage_door"
    assert ctx_tmpl["parent_alias"] == "Garage Template"
    assert ctx_tmpl["parent_type"] == "helper_template"
