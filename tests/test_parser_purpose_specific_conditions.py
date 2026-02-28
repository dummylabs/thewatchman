"""Regression tests for HA 2025.12+ Purpose-Specific Condition Intents (#306).

String values directly under a `condition:` key that look like entity IDs
(e.g. `condition: person.is_not_home`) are Purpose-specific condition intents,
NOT entity references, and must not be reported as false positives.
"""
import asyncio
from pathlib import Path

import pytest

from custom_components.watchman.utils.parser_core import WatchmanParser


@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    return WatchmanParser(str(db_path))


def _parse_and_get_entities(parser_client, yaml_dir):
    """Helper: parse a directory and return list of extracted entity IDs."""
    asyncio.run(parser_client.async_parse(yaml_dir, []))
    items = parser_client.get_found_items(item_type="all")
    return [item[0] for item in items if item[3] == "entity"]


def test_purpose_specific_condition_not_extracted(parser_client, new_test_data_dir):
    """Test 1: condition: person.is_not_home must NOT appear in extracted entities.

    'person.is_not_home' is a Purpose-specific condition intent (HA 2025.12+),
    not an entity reference.  IGNORED_VALUE_KEYS must suppress it.
    """
    yaml_dir = str(Path(new_test_data_dir) / "yaml_config")
    entities = _parse_and_get_entities(parser_client, yaml_dir)
    assert "person.is_not_home" not in entities, (
        "person.is_not_home is a condition intent and must not be reported as an entity"
    )


def test_nested_entity_id_still_extracted(parser_client, new_test_data_dir):
    """Test 2: entity_id nested inside a condition block must still be extracted.

    IGNORED_VALUE_KEYS suppresses only the immediate string value of 'condition:'.
    Recursion into child structures must continue so that
    target.entity_id: person.xxxxxxxxxx is still found.
    """
    yaml_dir = str(Path(new_test_data_dir) / "yaml_config")
    entities = _parse_and_get_entities(parser_client, yaml_dir)
    assert "person.xxxxxxxxxx" in entities, (
        "person.xxxxxxxxxx is a real entity under target.entity_id and must be extracted"
    )


def test_jinja2_template_in_condition_extracted(parser_client, new_test_data_dir):
    """Test 3: Jinja2 template under condition: must still yield entities (Heuristic 21).

    condition: "{{ is_state('light.kitchen', 'on') }}"
    light.kitchen must be extracted — is_template() guard must bypass suppression.
    """
    yaml_dir = str(Path(new_test_data_dir) / "yaml_config")
    entities = _parse_and_get_entities(parser_client, yaml_dir)
    assert "light.kitchen" in entities, (
        "light.kitchen inside a Jinja2 template under condition: must be extracted"
    )


def test_jinja2_template_in_trigger_extracted(parser_client, new_test_data_dir):
    """Test 4: Jinja2 template under trigger: must still yield entities.

    trigger: "{{ states('sensor.outdoor_temp') | float > 30 }}"
    sensor.outdoor_temp must be extracted — verifies that the is_template()
    exception that fixes condition: also works correctly for trigger:.
    """
    yaml_dir = str(Path(new_test_data_dir) / "yaml_config")
    entities = _parse_and_get_entities(parser_client, yaml_dir)
    assert "sensor.outdoor_temp" in entities, (
        "sensor.outdoor_temp inside a Jinja2 template under trigger: must be extracted"
    )
