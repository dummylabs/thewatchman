"""Constants for the parser."""

# file extensions supported by parser
# .json is not parsed as they typically contains unrelevant false positive entries
YAML_FILE_EXTS = {'.yaml', '.yml'}
JSON_FILE_EXTS = {'.config_entries'}

# For MVP, .storage is ignored completely if in _IGNORED_DIRS
STORAGE_WHITELIST = {'lovelace', 'lovelace_dashboards', 'lovelace_resources', 'core.config_entries'}
MAX_FILE_SIZE = 500 * 1024  # 500 KB

PLATFORMS = [
    "ai_task", "air_quality", "alarm_control_panel", "assist_satellite", "binary_sensor", "button",
    "calendar", "camera", "climate", "conversation", "cover", "date", "datetime", "device_tracker",
    "event", "fan", "geo_location", "humidifier", "image", "image_processing", "lawn_mower",
    "light", "lock", "media_player", "notify", "number", "remote", "scene", "select", "sensor",
    "siren", "stt", "switch", "text", "time", "todo", "tts", "update", "vacuum", "valve",
    "wake_word", "water_heater", "weather",
]

HA_DOMAINS = [
    "automation", "script", "group", "zone", "person", "sun", "input_boolean", "input_button",
    "input_datetime", "input_number", "input_select", "input_text", "timer", "counter",
    "shell_command", "persistent_notification", "homeassistant", "system_log", "logger",
    "recorder", "history", "logbook", "map", "mobile_app", "tag", "webhook", "websocket_api",
    "ble_monitor", "hassio", "mqtt", "python_script", "speedtestdotnet", "telegram_bot",
    "xiaomi_miio", "yeelight", "alert", "plant", "proximity", "schedule"
]

# following patterns are ignored by watchman as they are neither entities, nor actions
BUNDLED_IGNORED_ITEMS = [
    "timer.cancelled", "timer.finished", "timer.started", "timer.restarted",
    "timer.paused", "event.*", "date.*", "time.*", "map.*", "homeassistant.*"
]


# Path which includes this string is considered as ESPHome folder
ESPHOME_PATH_SEGMENT = "esphome"
# Allowed keys for ESPHome files to be considered as HA entities/services
ESPHOME_ALLOWED_KEYS = {'service', 'action', 'entity_id'}

# YAML keys which values should be ignored
IGNORED_KEYS = {'url', 'example', 'description'}

# Domains to parse in core.config_entries
CONFIG_ENTRY_DOMAINS = {'group', 'template'}

# Directories to skip during recursive scan
IGNORED_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'deps', 'backups', 'custom_components', '.cache', '.esphome', '.storage', 'tmp', 'blueprints', 'media', 'share', 'www', 'trash'}
