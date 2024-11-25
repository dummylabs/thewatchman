"definition of constants"

from homeassistant.const import Platform

DOMAIN = "watchman"
DOMAIN_DATA = "watchman_data"
VERSION = "0.6.5"

CONFIG_ENTRY_VERSION = 2
CONFIG_ENTRY_MINOR_VERSION = 1

DEFAULT_REPORT_FILENAME = "watchman_report.txt"
DEFAULT_HEADER = "-== WATCHMAN REPORT ==- "
DEFAULT_CHUNK_SIZE = 3500

PACKAGE_NAME = "custom_components.watchman"

HASS_DATA_PARSED_ENTITY_LIST = "entity_list"
HASS_DATA_PARSED_SERVICE_LIST = "service_list"
HASS_DATA_FILES_PARSED = "files_parsed"
HASS_DATA_FILES_IGNORED = "files_ignored"
HASS_DATA_PARSE_DURATION = "parse_duration"
HASS_DATA_CANCEL_HANDLERS = "cancel_handlers"
HASS_DATA_COORDINATOR = "coordinator"
HASS_DATA_MISSING_ENTITIES = "entities_missing"
HASS_DATA_MISSING_SERVICES = "services_missing"
HASS_DATA_CHECK_DURATION = "check_duration"

COORD_DATA_MISSING_ENTITIES = "entities_missing"
COORD_DATA_MISSING_SERVICES = "services_missing"
COORD_DATA_LAST_UPDATE = "last_update"
COORD_DATA_SERVICE_ATTRS = "service_attrs"
COORD_DATA_ENTITY_ATTRS = "entity_attrs"

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
CONF_CHECK_LOVELACE = "check_lovelace"
CONF_IGNORED_STATES = "ignored_states"
CONF_CHUNK_SIZE = "chunk_size"
CONF_CREATE_FILE = "create_file"
CONF_SEND_NOTIFICATION = "send_notification"
CONF_PARSE_CONFIG = "parse_config"
CONF_COLUMNS_WIDTH = "columns_width"
CONF_STARTUP_DELAY = "startup_delay"
CONF_FRIENDLY_NAMES = "friendly_names"
CONF_TEST_MODE = "test_mode"
# configuration parameters allowed in watchman.report service data
CONF_ALLOWED_SERVICE_PARAMS = [
    CONF_SERVICE_NAME,
    CONF_ACTION_NAME,
    CONF_CHUNK_SIZE,
    CONF_CREATE_FILE,
    CONF_SEND_NOTIFICATION,
    CONF_PARSE_CONFIG,
    CONF_SERVICE_DATA,
    CONF_TEST_MODE,
]

CONF_SECTION_APPEARANCE_LOCATION = "appearance_location_options"
CONF_SECTION_NOTIFY_ACTION = "notify_action_options"

EVENT_AUTOMATION_RELOADED = "automation_reloaded"
EVENT_SCENE_RELOADED = "scene_reloaded"

SENSOR_LAST_UPDATE = "watchman_last_updated"
SENSOR_MISSING_ENTITIES = "watchman_missing_entities"
SENSOR_MISSING_SERVICES = "watchman_missing_services"
SENSOR_MISSING_ACTIONS = "watchman_missing_actions"
MONITORED_STATES = ["unavailable", "unknown", "missing"]

TRACKED_EVENT_DOMAINS = [
    "homeassistant",
    "input_boolean",
    "input_button",
    "input_select",
    "input_number",
    "input_datetime",
    "person",
    "input_text",
    "script",
    "timer",
    "zone",
]

BUNDLED_IGNORED_ITEMS = [
    "timer.cancelled",
    "timer.finished",
    "timer.started",
    "timer.restarted",
    "timer.paused",
]

# Platforms
PLATFORMS = [Platform.SENSOR]

DEFAULT_OPTIONS = {
    CONF_INCLUDED_FOLDERS: "/config",
    CONF_IGNORED_ITEMS: "",
    CONF_IGNORED_STATES: [],
    CONF_IGNORED_FILES: "*/blueprints/*, */custom_components/*, */esphome/*",
    CONF_CHECK_LOVELACE: False,
    CONF_STARTUP_DELAY: 0,
    CONF_SECTION_APPEARANCE_LOCATION: {
        CONF_HEADER: "-== Watchman Report ==-",
        CONF_REPORT_PATH: "",
        CONF_COLUMNS_WIDTH: "30, 7, 60",
        CONF_FRIENDLY_NAMES: False,
    },
}

# additional domains to detect entities which are not included into
# homeassistant.const.Platform enum
DEFAULT_HA_DOMAINS = [
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
