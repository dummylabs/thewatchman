"""Tests for Home Assistant specific domains parsing."""
import asyncio
import os
from pathlib import Path

from custom_components.watchman.utils.parser_core import WatchmanParser
import pytest


@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    return client

def test_ha_domains_parsing(parser_client, new_test_data_dir):
    """Test parsing of Home Assistant specific domains."""
    yaml_file = Path(new_test_data_dir) / "yaml_config" / "ha_domains.yaml"
    yaml_dir = str(yaml_file.parent)

    # Parse the directory
    entities, _, _, _, _, _ = asyncio.run(parser_client.async_parse(yaml_dir, []))

    # List of domains to check
    domains_to_check = [
        "group",
        "input_boolean",
        "input_select",
        "input_text",
        "script",
        "alert",
        "automation",
        "counter",
        "input_datetime",
        "input_number",
        "input_button",
        "person",
        "plant",
        "proximity",
        "sun",
        "timer",
        "zone",
        "schedule",
    ]

    for domain in domains_to_check:
        # We expect to find at least one entity starting with "domain."
        # For 'sun', it is 'sun.sun'
        # For others, like 'input_boolean', it is 'input_boolean.test_bool'

        found = False
        for entity in entities:
            if entity.startswith(f"{domain}."):
                found = True
                break

        assert found, f"Should detect entity for domain '{domain}'"

    # Specific assertions for clarity
    assert "group.living_room_lights" in entities
    assert "input_boolean.test_bool" in entities
    assert "input_select.test_select" in entities
    assert "input_text.test_text" in entities
    assert "script.test_script" in entities
    assert "alert.garage_alert" in entities
    assert "automation.test_automation" in entities
    assert "counter.test_counter" in entities
    assert "input_datetime.test_datetime" in entities
    assert "input_number.test_number" in entities
    assert "input_button.test_button" in entities
    assert "person.test_person" in entities
    assert "plant.test_plant" in entities
    assert "proximity.test_prox" in entities
    assert "sun.sun" in entities
    assert "timer.test_timer" in entities
    assert "zone.test_zone" in entities
    assert "schedule.test_schedule" in entities
