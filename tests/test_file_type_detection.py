from custom_components.watchman.utils.parser_core import _detect_file_type
from custom_components.watchman.utils.parser_const import ESPHOME_PATH_SEGMENT

def test_detect_file_type_yaml():
    assert _detect_file_type("configuration.yaml") == "yaml"
    assert _detect_file_type("automations.yml") == "yaml"
    assert _detect_file_type("/config/lovelace.yaml") == "yaml"

def test_detect_file_type_json():
    assert _detect_file_type("core.config_entries") == "json"
    assert _detect_file_type(".storage/lovelace") == "json"
    assert _detect_file_type(".storage/lovelace_dashboards") == "json"
    assert _detect_file_type("lovelace_dashboard") == "json"

def test_detect_file_type_esphome():
    assert _detect_file_type(f"{ESPHOME_PATH_SEGMENT}/living_room.yaml") == "esphome_yaml"
    assert _detect_file_type(f"/config/{ESPHOME_PATH_SEGMENT}/kitchen.yml") == "esphome_yaml"

def test_detect_file_type_unknown():
    assert _detect_file_type("README.md") == "unknown"
    assert _detect_file_type("script.py") == "unknown"
    assert _detect_file_type("data.json") == "unknown" # .json is ignored unless storage/lovelace
