"""Definition of constants."""

from homeassistant.components.automation import EVENT_AUTOMATION_RELOADED
from homeassistant.components.homeassistant import (
    SERVICE_RELOAD_ALL,
    SERVICE_RELOAD_CORE_CONFIG,
    SERVICE_RELOAD_CUSTOM_TEMPLATES,
)
from homeassistant.components.homeassistant.scene import EVENT_SCENE_RELOADED
from homeassistant.const import SERVICE_RELOAD, Platform

DOMAIN = "watchman"
DOMAIN_DATA = f"{DOMAIN}_data"


CONFIG_ENTRY_VERSION = 2
CONFIG_ENTRY_MINOR_VERSION = 4

DEFAULT_REPORT_FILENAME = f"{DOMAIN}_report.txt"
DB_FILENAME = f"{DOMAIN}_v2.db"
LEGACY_DB_FILENAME = f"{DOMAIN}.db"
CURRENT_DB_SCHEMA_VERSION = 7
STORAGE_KEY = f"{DOMAIN}.stats"
STORAGE_VERSION = 1
LOCK_FILENAME = f"{DOMAIN}.lock"
DEFAULT_HEADER = "-== WATCHMAN REPORT ==- "
DEFAULT_CHUNK_SIZE = 3500
DB_TIMEOUT = 5
# parsing runs at most once per interval.
PARSE_COOLDOWN = 60
# delay before start parsing
DEFAULT_DELAY = 10

PACKAGE_NAME = f"custom_components.{DOMAIN}"
REPORT_SERVICE_NAME = "report"
LABELS_SERVICE_NAME = "set_ignored_labels"

HASS_DATA_CANCEL_HANDLERS = "cancel_handlers"

COORD_DATA_MISSING_ENTITIES = "entities_missing"
COORD_DATA_MISSING_ACTIONS = "services_missing"
COORD_DATA_LAST_UPDATE = "last_update"
COORD_DATA_SERVICE_ATTRS = "service_attrs"
COORD_DATA_ENTITY_ATTRS = "entity_attrs"
COORD_DATA_PARSE_DURATION = "parse_duration"
COORD_DATA_LAST_PARSE = "last_parse"
COORD_DATA_PROCESSED_FILES = "processed_files"
COORD_DATA_IGNORED_FILES = "ignored_files"

REPORT_ENTRY_TYPE_SERVICE = "service_list"
REPORT_ENTRY_TYPE_ENTITY = "entity_list"

CONF_IGNORED_FILES = "ignored_files"
CONF_HEADER = "report_header"
CONF_REPORT_PATH = "report_path"
CONF_IGNORED_ITEMS = "ignored_items"
CONF_SERVICE_NAME = "service"
CONF_ACTION_NAME = "action"
CONF_SERVICE_DATA = "data"
CONF_SERVICE_DATA2 = "service_data"
CONF_INCLUDED_FOLDERS = "included_folders"
CONF_EXCLUDE_DISABLED_AUTOMATION = "exclude_disabled_automation"
CONF_IGNORED_STATES = "ignored_states"
CONF_CHUNK_SIZE = "chunk_size"
CONF_CREATE_FILE = "create_file"
CONF_SEND_NOTIFICATION = "send_notification"
CONF_PARSE_CONFIG = "parse_config"
CONF_COLUMNS_WIDTH = "columns_width"
CONF_STARTUP_DELAY = "startup_delay"
CONF_FRIENDLY_NAMES = "friendly_names"
CONF_LOG_OBFUSCATE = "log_obfuscate"
CONF_IGNORED_LABELS = "ignored_labels"
# configuration parameters allowed in watchman.report service data
CONF_ALLOWED_SERVICE_PARAMS = [
    CONF_SERVICE_NAME,
    CONF_ACTION_NAME,
    CONF_CHUNK_SIZE,
    CONF_CREATE_FILE,
    CONF_SEND_NOTIFICATION,
    CONF_PARSE_CONFIG,
    CONF_SERVICE_DATA,
]



CONF_SECTION_APPEARANCE_LOCATION = "appearance_location_options"
CONF_SECTION_NOTIFY_ACTION = "notify_action_options"


# events and service calls monitored by Watchman
# these events indicate that configuration files
# changed on disk that requires re-parsing
WATCHED_EVENTS =[
    EVENT_AUTOMATION_RELOADED,
    EVENT_SCENE_RELOADED
]

WATCHED_SERVICES = [
    SERVICE_RELOAD_CORE_CONFIG,
    SERVICE_RELOAD,
    SERVICE_RELOAD_ALL,
    SERVICE_RELOAD_CUSTOM_TEMPLATES
]

SENSOR_LAST_UPDATE = "last_updated"
SENSOR_MISSING_ENTITIES = "missing_entities"
SENSOR_MISSING_ACTIONS = "missing_actions"
SENSOR_STATUS = "status"
SENSOR_PARSE_DURATION = "parse_duration"
SENSOR_LAST_PARSE = "last_parse"
SENSOR_PROCESSED_FILES = "processed_files"
SENSOR_IGNORED_FILES = "ignored_files"
MONITORED_STATES = ["unavailable", "unknown", "missing", "disabled"]

STATE_WAITING_HA = "waiting_for_ha"
STATE_PARSING = "parsing"
STATE_PENDING = "pending"
STATE_IDLE = "idle"
STATE_SAFE_MODE = "safe_mode"

BUNDLED_IGNORED_ITEMS = [
    "timer.cancelled",
    "timer.finished",
    "timer.started",
    "timer.restarted",
    "timer.paused",
    "event.*",
    "date.*",
]

# Platforms
PLATFORMS = [Platform.SENSOR, Platform.TEXT, Platform.BUTTON]

DEFAULT_OPTIONS = {
    CONF_IGNORED_ITEMS: "",
    CONF_IGNORED_STATES: [],
    CONF_EXCLUDE_DISABLED_AUTOMATION: True,
    CONF_IGNORED_FILES: "",
    CONF_STARTUP_DELAY: 30,
    CONF_LOG_OBFUSCATE: True,
    CONF_SECTION_APPEARANCE_LOCATION: {
        CONF_HEADER: "-== Watchman Report ==-",
        CONF_REPORT_PATH: "",
        CONF_COLUMNS_WIDTH: "30, 8, 60",
        CONF_FRIENDLY_NAMES: False,
    },
}
