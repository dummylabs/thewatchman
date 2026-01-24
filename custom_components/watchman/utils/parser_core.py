import os
import sys
import glob
import json
import sqlite3
import datetime
import time
import fnmatch
import logging
import re
import yaml
import contextlib
from typing import List, Tuple, Dict, Any

# file extensions supported by parser
# .json is not parsed as they typically contains unrelevant false positive entries
_YAML_FILE_EXTS = ['.yaml', '.yml']
_JSON_FILE_EXTS = ['', '.config_entries']

_PLATFORMS = [
    "ai_task", "air_quality", "alarm_control_panel", "assist_satellite", "binary_sensor", "button",
    "calendar", "camera", "climate", "conversation", "cover", "date", "datetime", "device_tracker",
    "event", "fan", "geo_location", "humidifier", "image", "image_processing", "lawn_mower",
    "light", "lock", "media_player", "notify", "number", "remote", "scene", "select", "sensor",
    "siren", "stt", "switch", "text", "time", "todo", "tts", "update", "vacuum", "valve",
    "wake_word", "water_heater", "weather",
]

_HA_DOMAINS = [
    "automation", "script", "group", "zone", "person", "sun", "input_boolean", "input_button",
    "input_datetime", "input_number", "input_select", "input_text", "timer", "counter",
    "shell_command", "persistent_notification", "homeassistant", "system_log", "logger",
    "recorder", "history", "logbook", "map", "mobile_app", "tag", "webhook", "websocket_api",
    "ble_monitor", "hassio", "mqtt", "python_script", "speedtestdotnet", "telegram_bot",
    "xiaomi_miio", "yeelight", "alert", "plant", "proximity", "schedule"
]

def get_domains(hass=None) -> List[str]:
    """Return a list of valid domains."""
    platforms = _PLATFORMS
    try:
        from homeassistant.const import Platform
        platforms = [platform.value for platform in Platform]
    except ImportError:
        pass

    extra_domains = []
    if hass:
        try:
            extra_domains = list(hass.services.async_services().keys())
        except Exception:
            pass

    return sorted(list(set(platforms + _HA_DOMAINS + extra_domains)))

_ALL_DOMAINS = get_domains()

# following patterns are ignored by watchman as they are neither entities, nor actions
_BUNDLED_IGNORED_ITEMS = [
    "timer.cancelled", "timer.finished", "timer.started", "timer.restarted",
    "timer.paused", "event.*", "date.*", "Date.*", "time.*", "map.*", "homeassistant.*"
]


# Path which includes this string is considered as ESPHome folder
_ESPHOME_PATH_SEGMENT = "esphome"
# Allowed keys for ESPHome files to be considered as HA entities/services
_ESPHOME_ALLOWED_KEYS = {'service', 'action', 'entity_id'}


# Regex patterns to identify entitites definitions
_ENTITY_PATTERN = re.compile(
    r"(?:^|[^a-zA-Z0-9_.])(?:states\.)?((" + "|".join(_ALL_DOMAINS) + r")\.[a-z0-9_]+)",
    re.IGNORECASE
)

# YAML keys which values should be ignored
_IGNORED_KEYS = {'url', 'example', 'description'}

# Regex patterns to identify actions (services) definitions
_SERVICE_PATTERN = re.compile(
    r"(?:service|action):\s*([a-z_0-9]+\.[a-z0-9_]+)",
    re.IGNORECASE
)



# Custom YAML Loader with Line Numbers

class _StringWithLine(str):
    """String subclass that holds the line number and tag info."""
    def __new__(cls, value, line, is_tag=False):
        obj = str.__new__(cls, value)
        obj.line = line
        obj.is_tag = is_tag
        return obj

class _LineLoader(yaml.SafeLoader):
    """Custom YAML loader that attaches line numbers to scalars."""
    def construct_scalar(self, node):
        value = super().construct_scalar(node)
        if isinstance(value, str):
            return _StringWithLine(value, node.start_mark.line + 1)
        return value

    def flatten_mapping(self, node):
        """
        Override flatten_mapping to handle merge keys ('<<') safely.
        """
        merge = []
        index = 0
        while index < len(node.value):
            key_node, value_node = node.value[index]
            if key_node.tag == 'tag:yaml.org,2002:merge':
                del node.value[index]
                if isinstance(value_node, yaml.MappingNode):
                    self.flatten_mapping(value_node)
                    merge.extend(value_node.value)
                elif isinstance(value_node, yaml.SequenceNode):
                    submerge = []
                    for subnode in value_node.value:
                        if isinstance(subnode, yaml.MappingNode):
                            self.flatten_mapping(subnode)
                            submerge.append(subnode)
                        elif isinstance(subnode, yaml.ScalarNode):
                            continue
                    for subnode in reversed(submerge):
                        merge.extend(subnode.value)
                elif isinstance(value_node, yaml.ScalarNode):
                    continue
            elif key_node.tag == 'tag:yaml.org,2002:value':
                key_node.tag = 'tag:yaml.org,2002:str'
                index += 1
            else:
                index += 1
        if merge:
            node.value = merge + node.value

_LineLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_SCALAR_TAG, _LineLoader.construct_scalar)

# Handle custom HA tags by ignoring them or treating as string
def _default_ctor(loader, tag_suffix, node):
    value = loader.construct_scalar(node)
    if isinstance(value, str):
        return _StringWithLine(value, node.start_mark.line + 1, is_tag=True)
    return value

yaml.add_multi_constructor('!', _default_ctor, Loader=_LineLoader)


# Core Logic Functions

def _detect_file_type(filepath: str) -> str:
    # Check for ESPHome path segment
    norm_path = os.path.normpath(filepath)
    path_parts = norm_path.split(os.sep)
    if _ESPHOME_PATH_SEGMENT in path_parts:
         # Still check extension to ensure it is yaml
         ext = os.path.splitext(filepath)[1].lower()
         if ext in _YAML_FILE_EXTS:
             return 'esphome_yaml'

    ext = os.path.splitext(filepath)[1].lower()

    if ext in _YAML_FILE_EXTS:
        return 'yaml'

    # Check content for JSON signature if extension is missing or not standard
    if ext in _JSON_FILE_EXTS:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                # Read first non-whitespace character
                content = f.read(1024)
                stripped = content.strip()
                if stripped.startswith('{') or stripped.startswith('['):
                    return 'json'
        except Exception:
            pass

    return 'unknown'

def _find_context(breadcrumbs: List[Any]) -> Dict[str, Any]:
    """
    Analyzes breadcrumbs (chain of parent objects) to determine if we are in an automation or script.
    """
    context = {
        "is_automation_context": False,
        "parent_type": None,
        "parent_id": None,
        "parent_alias": None
    }

    for i in range(len(breadcrumbs) - 1, -1, -1):
        node = breadcrumbs[i]

        if isinstance(node, dict):
            c_id = node.get("id")
            c_alias = node.get("alias")

            # Attempt to find ID from parent key if current node is a value in a parent dict
            if not c_id and i > 0:
                parent = breadcrumbs[i-1]
                if isinstance(parent, dict):
                    for k, v in parent.items():
                        if v is node:
                            c_id = k
                            break

            has_trigger = "trigger" in node or "triggers" in node
            has_action = "action" in node or "actions" in node

            if (has_trigger and has_action):
                context["is_automation_context"] = True
                context["parent_type"] = "automation"
                context["parent_id"] = str(c_id) if c_id else None
                context["parent_alias"] = str(c_alias) if c_alias else None
                return context

            if "sequence" in node:
                context["is_automation_context"] = True
                context["parent_type"] = "script"
                context["parent_id"] = str(c_id) if c_id else None
                context["parent_alias"] = str(c_alias) if c_alias else None
                return context

    return context

def _is_part_of_concatenation(text: str, match: re.Match) -> bool:
    start, end = match.span(1)

    pre_quote = None
    pre_quote_idx = -1
    for i in range(start - 1, -1, -1):
        char = text[i]
        if char.isspace():
            continue
        if char in ["'", '"']:
            pre_quote = char
            pre_quote_idx = i
            break
        else:
            break

    if not pre_quote:
        return False

    post_quote = None
    post_quote_idx = -1
    for i in range(end, len(text)):
        char = text[i]
        if char.isspace():
            continue
        if char == pre_quote:
            post_quote = char
            post_quote_idx = i
            break
        else:
            break

    if not post_quote:
        return False

    # Check left of pre_quote
    for i in range(pre_quote_idx - 1, -1, -1):
        char = text[i]
        if char.isspace():
            continue
        if char in ['+', '~', '%']:
            return True
        break

    # Check right of post_quote
    for i in range(post_quote_idx + 1, len(text)):
        char = text[i]
        if char.isspace():
            continue
        if char in ['+', '~', '%']:
            return True
        if char == '.' and text[i:].startswith(".format"):
             return True
        break

    return False

def _recursive_search(data: Any, breadcrumbs: List[Any], results: List[Dict], file_type: str = 'yaml', entity_pattern: re.Pattern = _ENTITY_PATTERN):
    """
    Recursively searches for entities and services.
    """
    is_esphome = (file_type == 'esphome_yaml')

    if isinstance(data, dict):
        for key, value in data.items():
            line_no = getattr(key, 'line', None)

            # Check for Ignored Keys
            if isinstance(key, str) and key.lower() in _IGNORED_KEYS:
                continue

            # 1. Check Key (Skip if ESPHome mode)
            if isinstance(key, str) and not is_esphome:
                matches = list(entity_pattern.finditer(key))
                for match in matches:
                    entity_id = match.group(1)

                    if _is_part_of_concatenation(key, match):
                        continue

                    if match.end(1) < len(key) and key[match.end(1)] == '*':
                        continue

                    if entity_id.endswith('_'):
                        continue

                    remaining_text = key[match.end(1):].lstrip()
                    if remaining_text.startswith('('):
                        continue

                    ctx = _find_context(breadcrumbs + [data])
                    results.append({
                        "line": line_no or 0,
                        "entity_id": entity_id,
                        "item_type": 'entity',
                        "is_key": True,
                        "key_name": key,
                        **ctx
                    })

            # 2. Special Check for Service/Action Keys
            is_action_key = isinstance(key, str) and key.lower() in ["service", "action"]

            # Recurse
            _recursive_search(value, breadcrumbs + [data], results, file_type, entity_pattern)

    elif isinstance(data, list):
        for item in data:
            _recursive_search(item, breadcrumbs + [data], results, file_type, entity_pattern)

    elif isinstance(data, str):
        # Check Value
        if getattr(data, 'is_tag', False):
            return

        line_no = getattr(data, 'line', None)

        # Try to find key name from parent if parent is dict
        key_name = None
        if breadcrumbs and isinstance(breadcrumbs[-1], dict):
            for k, v in breadcrumbs[-1].items():
                if v is data:
                    key_name = k
                    break

        # ESPHome Mode: Only process value if key_name is allowed
        if is_esphome:
             if not key_name or str(key_name).lower() not in _ESPHOME_ALLOWED_KEYS:
                 return

        # Check for Entities
        matches = list(entity_pattern.finditer(data))
        for match in matches:
            entity_id = match.group(1)

            if _is_part_of_concatenation(data, match):
                continue

            if match.end(1) < len(data) and data[match.end(1)] == '*':
                continue

            if entity_id.endswith('_'):
                continue

            remaining_text = data[match.end(1):].lstrip()
            if remaining_text.startswith('('):
                continue

            ctx = _find_context(breadcrumbs)

            # Determine item_type
            item_type = 'entity'
            if key_name and key_name.lower() in ['service', 'action']:
                item_type = 'service'

            results.append({
                "line": line_no or 0,
                "entity_id": entity_id,
                "item_type": item_type,
                "is_key": False,
                "key_name": key_name,
                **ctx
            })

        # Check for Services (e.g. "service: light.turn_on" inside a string template)
        matches_svc = list(_SERVICE_PATTERN.finditer(data))
        for match in matches_svc:
            service_id = match.group(1)
            ctx = _find_context(breadcrumbs)

            key_name = None
            if breadcrumbs and isinstance(breadcrumbs[-1], dict):
                for k, v in breadcrumbs[-1].items():
                    if v is data:
                        key_name = k
                        break

            results.append({
                "line": line_no or 0,
                "entity_id": service_id,
                "item_type": 'service',
                "is_key": False,
                "key_name": key_name,
                **ctx
            })


def _parse_content(content: str, file_type: str, logger: logging.Logger = None, entity_pattern: re.Pattern = _ENTITY_PATTERN) -> List[Dict]:
    """
    Parses YAML/JSON content and extracts entities.
    """
    if file_type == 'unknown':
        return []

    try:
        # JSON is valid YAML 1.2
        data = yaml.load(content, Loader=_LineLoader)
    except yaml.YAMLError as e:
        if logger:
            logger.error(f"Error parsing content: {e}")
        return []
    except Exception as e:
        if logger:
             logger.error(f"Critical error parsing content: {e}")
        return []

    results = []
    if data:
        _recursive_search(data, [], results, file_type, entity_pattern)

    return results


# --- WatchmanParser ---

class WatchmanParser:
    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextlib.contextmanager
    def _db_session(self):
        """Context manager for database connections."""
        conn = self._init_db(self.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self, db_path: str) -> sqlite3.Connection:
        # Ensure directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute("PRAGMA foreign_keys = ON;")
        c.execute("PRAGMA journal_mode = WAL;")
        c.execute("PRAGMA synchronous = NORMAL;")

        c.execute('''CREATE TABLE IF NOT EXISTS processed_files (
                        file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scan_date TEXT,
                        path TEXT UNIQUE,
                        entity_count INTEGER,
                        file_type TEXT
                    )''')

        c.execute('''CREATE TABLE IF NOT EXISTS found_items (
                        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_id INTEGER,
                        line INTEGER,
                        entity_id TEXT,
                        item_type TEXT DEFAULT 'entity',
                        is_key BOOLEAN,
                        key_name TEXT,
                        is_automation_context BOOLEAN,
                        parent_type TEXT,
                        parent_id TEXT,
                        parent_alias TEXT,
                                        FOREIGN KEY(file_id) REFERENCES processed_files(file_id) ON DELETE CASCADE
                                    )''')

        # Schema migration for existing DB
        try:
            c.execute("ALTER TABLE found_items ADD COLUMN item_type TEXT DEFAULT 'entity'")
        except sqlite3.OperationalError:
            pass # Column likely exists

        c.execute('''CREATE TABLE IF NOT EXISTS scan_config (
                        id INTEGER PRIMARY KEY DEFAULT 1 CHECK(id=1), -- Ensure only one row
                        included_folders TEXT,
                        ignored_files TEXT,
                        last_parse_duration REAL,
                        last_parse_timestamp TEXT
                    )''')

        # Schema migration for last_parse_duration
        try:
            c.execute("ALTER TABLE scan_config ADD COLUMN last_parse_duration REAL")
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("ALTER TABLE scan_config ADD COLUMN last_parse_timestamp TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            c.execute("ALTER TABLE scan_config ADD COLUMN ignored_files_count INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        return conn

    def _get_files(self, folders: List[str], ignored_files: List[str]) -> Tuple[List[str], int]:
        """
        Collects files based on whitelist folders and filters by blacklist patterns.
        Returns:
            Tuple[List[str], int]: (list of files to scan, count of ignored files)
        """
        found_files = set()
        cwd = os.getcwd()

        for pattern in folders:
            # Handle relative paths for folders if they are not absolute
            if not os.path.isabs(pattern):
                 pass

            if os.path.isdir(pattern):
                for root, _, files in os.walk(pattern):
                    for file in files:
                        filepath = os.path.join(root, file)
                        if os.path.exists(filepath):
                            abs_path = os.path.abspath(filepath)
                            found_files.add(abs_path)
            else:
                search_pattern = pattern

                for filepath in glob.glob(search_pattern, recursive=True):
                    if os.path.isfile(filepath):
                        abs_path = os.path.abspath(filepath)
                        found_files.add(abs_path)

        final_files = []
        ignored_count = 0
        for filepath in found_files:
            rel_path = os.path.relpath(filepath, cwd)
            is_ignored = False
            for ignore_pat in ignored_files:
                if fnmatch.fnmatch(filepath, ignore_pat) or fnmatch.fnmatch(rel_path, ignore_pat):
                    is_ignored = True
                    break

            if not is_ignored:
                basename = os.path.basename(filepath)
                _, ext = os.path.splitext(basename)
                if ext.lower() in _YAML_FILE_EXTS + _JSON_FILE_EXTS:
                    final_files.append(filepath)
            else:
                ignored_count += 1

        return sorted(final_files), ignored_count

    def _parse_file(self, filepath: str, file_type: str, entity_pattern: re.Pattern = _ENTITY_PATTERN) -> Tuple[int, List[dict]]:
        if file_type == 'unknown':
            return 0, []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            # Setup basic logger
            logger = logging.getLogger("parser_core")
            # We don't add handlers here to avoid interfering with HA logging or CLI logging config

            # Call the engine
            items = _parse_content(content, file_type, logger, entity_pattern)

            return len(items), items

        except Exception as e:
            # We might want to log this properly
            print(f"Critical error processing {filepath}: {e}", file=sys.stderr)
            return 0, []

    def scan(self, included_folders: List[str], ignored_files: List[str], force: bool = False, custom_domains: List[str] = None) -> None:
        """
        Orchestrates the scanning process.
        """
        start_time = time.monotonic()
        with self._db_session() as conn:
            cursor = conn.cursor()

            # Build Entity Pattern
            entity_pattern = _ENTITY_PATTERN
            if custom_domains:
                entity_pattern = re.compile(
                    r"(?:^|[^a-zA-Z0-9_.])(?:states\.)?((" + "|".join(custom_domains) + r")\.[a-z0-9_]+)",
                    re.IGNORECASE
                )

            # --- Configuration Change Detection ---
            cursor.execute("SELECT included_folders, ignored_files FROM scan_config WHERE id = 1")
            stored_config = cursor.fetchone()

            current_included_json = json.dumps(sorted(included_folders))
            current_ignored_json = json.dumps(sorted(ignored_files))

            if stored_config:
                stored_included_json, stored_ignored_json = stored_config
                if current_included_json != stored_included_json or current_ignored_json != stored_ignored_json:
                    force = True
            else:
                force = True # First run, always force

            if stored_config:
                cursor.execute("UPDATE scan_config SET included_folders = ?, ignored_files = ? WHERE id = 1",
                               (current_included_json, current_ignored_json))
            else:
                cursor.execute("INSERT INTO scan_config (id, included_folders, ignored_files) VALUES (1, ?, ?)",
                               (current_included_json, current_ignored_json))
            conn.commit()
            # --- End Configuration Change Detection ---

            files_to_scan, ignored_count = self._get_files(included_folders, ignored_files)

            actual_file_ids = []

            for filepath in files_to_scan:
                mtime = os.path.getmtime(filepath)
                scan_date = datetime.datetime.now().isoformat()

                file_id = None

                cursor.execute("SELECT scan_date, file_id FROM processed_files WHERE path = ?", (filepath,))
                row = cursor.fetchone()

                should_scan = False

                if row:
                    last_scan_str, file_id = row
                    try:
                        last_scan_dt = datetime.datetime.fromisoformat(last_scan_str)
                        file_mtime_dt = datetime.datetime.fromtimestamp(mtime)
                        if force or file_mtime_dt > last_scan_dt:
                            should_scan = True
                    except ValueError:
                        should_scan = True

                    actual_file_ids.append(file_id)
                else:
                    should_scan = True

                if should_scan:
                    ftype = _detect_file_type(filepath)
                    count, items = self._parse_file(filepath, ftype, entity_pattern)

                    if file_id:
                        cursor.execute("UPDATE processed_files SET scan_date=?, entity_count=?, file_type=? WHERE file_id=?",
                                       (scan_date, count, ftype, file_id))
                        cursor.execute("DELETE FROM found_items WHERE file_id=?", (file_id,))
                    else:
                        cursor.execute("INSERT INTO processed_files (scan_date, path, entity_count, file_type) VALUES (?, ?, ?, ?)",
                                       (scan_date, filepath, count, ftype))
                        file_id = cursor.lastrowid

                    if file_id not in actual_file_ids:
                         actual_file_ids.append(file_id)

                    for item in items:
                        # Filter out bundled ignored items
                        is_ignored = False
                        for pattern in _BUNDLED_IGNORED_ITEMS:
                            if fnmatch.fnmatch(item['entity_id'], pattern):
                                is_ignored = True
                                break

                        if is_ignored:
                            continue

                        cursor.execute('''INSERT INTO found_items
                                          (file_id, line, entity_id, item_type, is_key, key_name, is_automation_context, parent_type, parent_id, parent_alias)
                                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                       (file_id, item['line'], item['entity_id'], item['item_type'], item['is_key'], item['key_name'],
                                        item['is_automation_context'], item['parent_type'], item['parent_id'], item['parent_alias']))

                    conn.commit()

            # --- Cleanup stale files ---
            if actual_file_ids:
                placeholders = ','.join('?' * len(actual_file_ids))
                cursor.execute(f"DELETE FROM processed_files WHERE file_id NOT IN ({placeholders})", actual_file_ids)
                conn.commit()
            else:
                cursor.execute("DELETE FROM processed_files")
                conn.commit()

            # Update last parse stats
            duration = time.monotonic() - start_time
            # Use datetime.datetime.now(datetime.timezone.utc) to ensure UTC timestamp if possible or local if required by HA conventions.
            # But previous code used datetime.datetime.now().isoformat()
            current_timestamp = datetime.datetime.now().isoformat()
            cursor.execute("UPDATE scan_config SET last_parse_duration = ?, last_parse_timestamp = ?, ignored_files_count = ? WHERE id = 1",
                           (duration, current_timestamp, ignored_count))
            conn.commit()

    def get_last_parse_info(self) -> Dict[str, Any]:
        """Return the duration, timestamp, ignored files count and processed files count of the last successful scan."""
        with self._db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT last_parse_duration, last_parse_timestamp, ignored_files_count FROM scan_config WHERE id = 1")
            row = cursor.fetchone()
            
            cursor.execute("SELECT COUNT(*) FROM processed_files")
            processed_files_count = cursor.fetchone()[0]
            
            if row:
                return {
                    "duration": row[0],
                    "timestamp": row[1],
                    "ignored_files_count": row[2],
                    "processed_files_count": processed_files_count
                }
        return {"duration": 0.0, "timestamp": None, "ignored_files_count": 0, "processed_files_count": 0}

    def get_processed_files(self) -> List[Tuple]:
        """Fetch all processed files from the database."""
        with self._db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_id, path, file_type, entity_count, scan_date 
                FROM processed_files 
                ORDER BY path
            """)
            return cursor.fetchall()

    def get_found_items(self, item_type: str = None) -> List[Tuple]:
        """
        Fetch found items from the database.
        
        Args:
            item_type: 'entity', 'service', or 'all' (default).
        
        Returns:
            List of tuples: (entity_id, path, line, item_type, parent_type, parent_alias, parent_id)
        """
        query = """
            SELECT fi.entity_id, pf.path, fi.line, fi.item_type, fi.parent_type, fi.parent_alias, fi.parent_id
            FROM found_items fi
            JOIN processed_files pf ON fi.file_id = pf.file_id
        """
        params = ()
        if item_type and item_type != 'all':
            query += " WHERE fi.item_type = ?"
            params = (item_type,)
        
        query += " ORDER BY pf.path, fi.line"

        with self._db_session() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return cursor.fetchall()

    def get_automation_context(self, entity_id: str) -> Dict[str, Any]:
        """
        Get automation/script context for a specific entity or service.
        Returns the first match found.
        """
        with self._db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT is_automation_context, parent_type, parent_alias, parent_id
                FROM found_items
                WHERE entity_id = ?
                LIMIT 1
            """, (entity_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    "is_automation_context": bool(row[0]),
                    "parent_type": row[1],
                    "parent_alias": row[2],
                    "parent_id": row[3]
                }
            return None

    def parse(self, included_folders: List[str], ignored_files: List[str], force: bool = False, custom_domains: List[str] = None) -> Tuple[List[str], List[str], int, int, Dict]:
        """
        Drop-in replacement for the legacy parse function format.

        Returns:
            parsed_entity_list (list): Unique entity_ids (item_type='entity').
            parsed_service_list (list): Unique services (item_type='service').
            parsed_files_count (int): Number of entries in processed_files.
            ignored_files_count (int): Always 0 (stub).
            entity_to_automations (dict): Empty dictionary (stub).
        """
        # Run the scan
        self.scan(included_folders, ignored_files, force, custom_domains)

        with self._db_session() as conn:
            cursor = conn.cursor()
            # parsed_entity_list
            cursor.execute("SELECT DISTINCT entity_id FROM found_items WHERE item_type = 'entity'")
            parsed_entity_list = [row[0] for row in cursor.fetchall()]

            # parsed_service_list
            cursor.execute("SELECT DISTINCT entity_id FROM found_items WHERE item_type = 'service'")
            parsed_service_list = [row[0] for row in cursor.fetchall()]

            # parsed_files_count
            cursor.execute("SELECT COUNT(*) FROM processed_files")
            parsed_files_count = cursor.fetchone()[0]

            # ignored_files_count
            cursor.execute("SELECT ignored_files_count FROM scan_config WHERE id = 1")
            row = cursor.fetchone()
            ignored_files_count = row[0] if row else 0

        # entity_to_automations (stub)
        entity_to_automations = {}

        return (
            parsed_entity_list,
            parsed_service_list,
            parsed_files_count,
            ignored_files_count,
            entity_to_automations
        )
