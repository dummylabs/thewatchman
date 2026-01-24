"""Tests for automation and script parsing contexts."""
import os
import pytest
from custom_components.watchman.utils.parser_core import WatchmanParser

@pytest.fixture
def parser_client(tmp_path):
    """Create a WatchmanParser instance with a temporary database."""
    db_path = tmp_path / "watchman.db"
    client = WatchmanParser(str(db_path))
    yield client

def test_automations_parsing(parser_client, new_test_data_dir):
    """Test parsing of automation files."""
    # Heuristic 10: Automation Context
    # Heuristic 5: List vs Single
    # Heuristic 3: Service Keys

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "automations.yaml")

    entities, services, _, _, _ = parser_client.parse([yaml_file], [])

    # Check Entities
    assert "binary_sensor.motion_sensor" in entities
    assert "light.living_room" in entities
    assert "light.kitchen" in entities
    assert "alarm_control_panel.home" in entities

    # Check Services
    assert "light.turn_on" in services
    assert "alarm_control_panel.arm_home" in services # New 'action' syntax

    # Verify 'light.living_room' is in automation context
    context = parser_client.get_automation_context('light.living_room')
    assert context is not None
    assert context["is_automation_context"] is True
    assert context["parent_type"] == "automation"
    assert context["parent_alias"] == "Morning Routine"

def test_scripts_parsing(parser_client, new_test_data_dir):
    """Test parsing of script files."""
    # Heuristic 10: Script Context

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "scripts.yaml")

    entities, services, _, _, _ = parser_client.parse([yaml_file], [])

    assert "vacuum.robot_cleaner" in entities
    assert "vacuum.start" in services
    assert "notify.mobile_app_phone" in services
    assert "script.cleanup_routine" in services

    # Verify Context
    context = parser_client.get_automation_context('vacuum.robot_cleaner')
    assert context is not None
    assert context["parent_type"] == "script"
    assert context["parent_alias"] == "Cleanup House"

def test_package_mixed_contexts(parser_client, new_test_data_dir):
    """Test parsing of a package file with mixed domains."""
    # Heuristic 10: Context Switching

    yaml_file = os.path.join(new_test_data_dir, "yaml_config", "package_example.yaml")

    _, _, _, _, _ = parser_client.parse([yaml_file], [])

    # 1. Automation Context
    context1 = parser_client.get_automation_context('input_boolean.package_trigger')
    assert context1 is not None
    assert context1["parent_type"] == "automation"

    # 2. Script Context
    context2 = parser_client.get_automation_context('notify.persistent_notification')
    assert context2 is not None
    assert context2["parent_type"] == "script"

    # 3. No Context (Sensor)
    context3 = parser_client.get_automation_context('sensor.package_source')
    assert context3 is not None
    assert context3["is_automation_context"] is False

    # 4. No Context (Switch - even though it has 'turn_on' actions, it's a switch template, not an automation/script)
    context4 = parser_client.get_automation_context('switch.package_target')
    assert context4 is not None
    # Note: Template switches have actions, but they are technically not "automations" in the HA sense (triggers+actions)
    # or "scripts" (sequences). The parser might see 'turn_on' as a key, but unless it recurses into it properly
    # as a sequence/action block defined in _find_context, it might remain None.
    assert context4["is_automation_context"] is False