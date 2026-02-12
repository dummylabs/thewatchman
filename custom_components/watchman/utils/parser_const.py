import re

"""Constants for the parser."""

# file extensions supported by parser
# .json is not parsed as they typically contains unrelevant false positive entries
YAML_FILE_EXTS = {'.yaml', '.yml'}
JSON_FILE_EXTS = {'.config_entries'}

# .storage folder is ignored completely if in _IGNORED_DIRS
# but whitelisted files in .storage are detected dynamically by the parser
STORAGE_WHITELIST_PATTERNS = {'core.config_entries', 'lovelace*'}
MAX_FILE_SIZE = 500 * 1024  # 500 KB

# A fallback list of Home Assistant entity platforms for the CLI parser.
# This list is used ONLY when the 'homeassistant' library is not importable.
# If the library is present, this list is overwritten by the official constants.
# DO NOT EXTEND this list for missing integration domains; use HA_DOMAINS instead.
PLATFORMS = [
    "ai_task", "air_quality", "alarm_control_panel", "assist_satellite", "binary_sensor", "button",
    "calendar", "camera", "climate", "conversation", "cover", "date", "datetime", "device_tracker",
    "event", "fan", "geo_location", "humidifier", "image", "image_processing", "lawn_mower",
    "light", "lock", "media_player", "notify", "number", "remote", "scene", "select", "sensor",
    "siren", "stt", "switch", "text", "time", "todo", "tts", "update", "vacuum", "valve",
    "wake_word", "water_heater", "weather"
]


# Integration domains used as a fallback for the standalone CLI parser.
# In runtime, this list is merged with `hass.config.components`.
# It includes standard domains (e.g., 'automation') and common integrations for testing.
HA_DOMAINS = [
    "automation", "script", "group", "zone", "person", "sun", "input_boolean", "input_button",
    "input_datetime", "input_number", "input_select", "input_text", "timer", "counter",
    "shell_command", "persistent_notification", "homeassistant", "system_log", "logger",
    "recorder", "history", "logbook", "map", "mobile_app", "tag", "webhook", "websocket_api",
    "ble_monitor", "hassio", "mqtt", "python_script", "speedtestdotnet", "telegram_bot",
    "xiaomi_miio", "yeelight", "alert", "plant", "proximity", "schedule", "template"
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

# Keys which values (whole hierarchy) should be ignored
IGNORED_BRANCH_KEYS = {'url', 'example', 'description', 'event_type', 'logger'}

# Keys identifying an action/service call
ACTION_KEYS = {'service', 'action', 'service_template', 'perform_action'}

# Keys where the parser ignores the immediate string value (to avoid false positives)
# but continues recursion if the value is a complex structure
IGNORED_VALUE_KEYS = {'trigger', 'triggers'}

# Domains to parse in core.config_entries
CONFIG_ENTRY_DOMAINS = {'group', 'template'}

# Directories to skip during recursive scan
IGNORED_DIRS = {'.git', '__pycache__', '.venv', 'venv', 'deps', 'backups', 'custom_components', '.cache', '.esphome', '.storage', 'tmp', 'blueprints', 'media', 'share', 'www', 'trash'}

# Regex building blocks for entity detection

# Forbidden prefixes: letters, numbers, _, ., /, \, @, $, %, &, |, -

REGEX_ENTITY_BOUNDARY = r"(?:^|[^a-zA-Z0-9_./\\@$%&|-])"

REGEX_OPTIONAL_STATES = r"(?:states\.)?"

REGEX_ENTITY_SUFFIX = r"\.[a-z0-9_]+"



REGEX_STRICT_SERVICE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$", re.IGNORECASE)
