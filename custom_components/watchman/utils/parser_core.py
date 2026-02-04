import asyncio
from collections.abc import Awaitable, Callable
import contextlib
import datetime
import fnmatch
import logging
import os
import re
import sqlite3
import time
from typing import Any, Generator, TypedDict

from homeassistant.core import HomeAssistant

import anyio
import yaml

from ..const import DB_TIMEOUT
from .logger import _LOGGER
from .parser_const import (
    BUNDLED_IGNORED_ITEMS,
    ESPHOME_ALLOWED_KEYS,
    ESPHOME_PATH_SEGMENT,
    HA_DOMAINS,
    IGNORED_DIRS,
    IGNORED_KEYS,
    JSON_FILE_EXTS,
    MAX_FILE_SIZE,
    PLATFORMS,
    STORAGE_WHITELIST,
    YAML_FILE_EXTS,
)
from .yaml_loader import LineLoader


class FoundItem(TypedDict):
    """Structure of an item found by the parser."""

    line: int
    entity_id: str
    item_type: str
    is_key: bool
    key_name: str | None
    is_automation_context: bool
    parent_type: str | None
    parent_id: str | None
    parent_alias: str | None

def get_domains(hass: HomeAssistant | None = None) -> list[str]:
    """Return a list of valid domains."""
    platforms = PLATFORMS
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

    return sorted(list(set(platforms + HA_DOMAINS + extra_domains)))

_ALL_DOMAINS = get_domains()

# Regex patterns to identify entitites definitions
_ENTITY_PATTERN = re.compile(
    r"(?:^|[^a-zA-Z0-9_./\\])(?:states\.)?((" + "|".join(_ALL_DOMAINS) + r")\.[a-z0-9_]+)",
    re.IGNORECASE
)

# Regex patterns to identify actions (services) definitions
_SERVICE_PATTERN = re.compile(
    r"(?:service|action):\s*([a-z_0-9]+\.[a-z0-9_]+)",
    re.IGNORECASE
)

DEFAULT_CONTEXT = {
    "is_automation_context": False,
    "parent_type": None,
    "parent_id": None,
    "parent_alias": None
}

# Core Logic Functions

def _detect_file_type(filepath: str) -> str:
    filename = os.path.basename(filepath)
    if filename in STORAGE_WHITELIST:
        return 'json'

    # Check for ESPHome path segment
    norm_path = os.path.normpath(filepath)
    path_parts = norm_path.split(os.sep)
    if ESPHOME_PATH_SEGMENT in path_parts:
         # Still check extension to ensure it is yaml
         ext = os.path.splitext(filepath)[1].lower()
         if ext in YAML_FILE_EXTS:
             return 'esphome_yaml'

    ext = os.path.splitext(filepath)[1].lower()

    if ext in YAML_FILE_EXTS:
        return 'yaml'

    if ext in JSON_FILE_EXTS:
        return 'json'

    return 'unknown'

def _is_automation(node: dict) -> bool:
    """Check if a node looks like an automation definition."""
    has_trigger = "trigger" in node or "triggers" in node
    has_action = "action" in node or "actions" in node

    if has_trigger and has_action:
        # Avoid false positives for Template configuration files (trigger-based templates)
        # These files have trigger/action but also other keys like binary_sensor, sensor, etc.
        # An automation dict should mostly contain automation keys.
        # Heuristic: If it has keys typical for integrations, it's not an automation.
        forbidden_keys = {'sensor', 'binary_sensor', 'image', 'number', 'select', 'weather', 'button', 'template', 'homeassistant', 'script', 'scene'}
        if any(k in node for k in forbidden_keys):
             return False
        return True
    return False

def _is_script(node: dict) -> bool:
    """Check if a node looks like a script definition."""
    return "sequence" in node

def _derive_context(node: dict, parent_context: dict[str, Any], parent_key: str = None) -> dict[str, Any]:
    """Derive the context for a node based on its content and parent key.

    If the node defines an automation or script, return a new context.
    Otherwise, return the parent context.
    """
    if not isinstance(node, dict):
        return parent_context

    c_id = node.get("id")
    c_alias = node.get("alias")

    # Heuristic: use parent key as ID if no explicit ID is present
    # This is common in named scripts: `script_name: { sequence: ... }`
    if not c_id and parent_key:
        c_id = parent_key

    if _is_automation(node):
        return {
            "is_automation_context": True,
            "parent_type": "automation",
            "parent_id": str(c_id) if c_id else None,
            "parent_alias": str(c_alias) if c_alias else None
        }

    if _is_script(node):
        return {
            "is_automation_context": True,
            "parent_type": "script",
            "parent_id": str(c_id) if c_id else None,
            "parent_alias": str(c_alias) if c_alias else None
        }

    return parent_context

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

def _recursive_search(
    data: Any,
    breadcrumbs: list[Any],
    results: list[FoundItem],
    file_type: str = "yaml",
    entity_pattern: re.Pattern = _ENTITY_PATTERN,
    current_context: dict[str, Any] | None = None,
    expected_item_type: str = "entity",
    parent_key: str | None = None,
) -> None:
    """Recursively searches for entities and services.
    """
    if current_context is None:
        current_context = DEFAULT_CONTEXT
        # Check if the ROOT node itself establishes a context (e.g., Root Automation)
        if not breadcrumbs and isinstance(data, dict):
             current_context = _derive_context(data, current_context)

    is_esphome = (file_type == 'esphome_yaml')

    if isinstance(data, dict):
        for key, value in data.items():
            line_no = getattr(key, 'line', None)

            # Check for Ignored Keys
            if isinstance(key, str) and key.lower() in IGNORED_KEYS:
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

                    # Word Boundary Check (Heuristic 18)
                    end_idx = match.end(1)
                    if end_idx < len(key):
                        next_char = key[end_idx]
                        if next_char == '-':
                            continue
                        if next_char == '.':
                            if "states." not in match.group(0).lower():
                                continue

                    remaining_text = key[match.end(1):].lstrip()
                    if remaining_text.startswith('('):
                        continue

                    results.append({
                        "line": line_no or 0,
                        "entity_id": entity_id,
                        "item_type": 'entity', # Keys are usually entities
                        "is_key": True,
                        "key_name": key,
                        **current_context
                    })

            # Determine expected type for value
            is_action_key = isinstance(key, str) and key.lower() in ["service", "action", "service_template"]
            next_type = 'service' if is_action_key else 'entity'

            # Recurse
            # Calculate context for the child node
            child_ctx = current_context
            if isinstance(value, dict):
                child_ctx = _derive_context(value, current_context, parent_key=key)

            _recursive_search(value, breadcrumbs + [data], results, file_type, entity_pattern, child_ctx, next_type, parent_key=key)

    elif isinstance(data, list):
        for item in data:
            child_ctx = current_context
            if isinstance(item, dict):
                child_ctx = _derive_context(item, current_context)
            # List items inherit expected_item_type from parent
            # List items inherit parent_key from parent (e.g. entity_id: [item1, item2])
            _recursive_search(item, breadcrumbs + [data], results, file_type, entity_pattern, child_ctx, expected_item_type, parent_key=parent_key)

    elif isinstance(data, str):
        # Check Value
        if getattr(data, 'is_tag', False):
            return

        line_no = getattr(data, 'line', None)
        key_name = parent_key

        # ESPHome Mode: Only process value if key_name is allowed
        if is_esphome:
             if not key_name or str(key_name).lower() not in ESPHOME_ALLOWED_KEYS:
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

            # Word Boundary Check (Heuristic 18)
            end_idx = match.end(1)
            if end_idx < len(data):
                next_char = data[end_idx]
                if next_char == '-':
                    continue
                if next_char == '.':
                    if "states." not in match.group(0).lower():
                        continue

            remaining_text = data[match.end(1):].lstrip()
            if remaining_text.startswith('('):
                continue

            results.append({
                "line": line_no or 0,
                "entity_id": entity_id,
                "item_type": expected_item_type,
                "is_key": False,
                "key_name": key_name,
                **current_context
            })

        # Check for Services (e.g. "service: light.turn_on" inside a string template)
        matches_svc = list(_SERVICE_PATTERN.finditer(data))
        for match in matches_svc:
            service_id = match.group(1)

            results.append({
                "line": line_no or 0,
                "entity_id": service_id,
                "item_type": 'service',
                "is_key": False,
                "key_name": key_name,
                **current_context
            })


def _parse_content(content: str, file_type: str, filepath: str = None, logger: logging.Logger = None, entity_pattern: re.Pattern = _ENTITY_PATTERN) -> list[FoundItem]:
    """Parses YAML/JSON content and extracts entities.

    Returns a list of FoundItem dictionaries.
    """
    if file_type == 'unknown':
        return []

    try:
        # JSON is valid YAML 1.2
        data = yaml.load(content, Loader=LineLoader)
    except yaml.YAMLError as e:
        if logger:
            logger.error(f"Error parsing content in {filepath or 'unknown'}: {e}")
        return []
    except Exception as e:
        if logger:
             logger.error(f"Critical error parsing content in {filepath or 'unknown'}: {e}")
        return []

    results: list[FoundItem] = []
    if data:
        # Pass DEFAULT_CONTEXT explicitly if needed, or let it default to None -> DEFAULT_CONTEXT inside
        _recursive_search(data, [], results, file_type, entity_pattern)

    return results

def process_file_sync(filepath: str, entity_pattern: re.Pattern = _ENTITY_PATTERN) -> tuple[int, list[FoundItem], str]:
    """Process a single file synchronously.

    This function is intended to be run in an executor.
    Returns a tuple of (count, items, detected_file_type).
    """
    file_type = _detect_file_type(filepath)

    if file_type == 'unknown':
        return 0, [], 'unknown'

    try:
        file_size = os.path.getsize(filepath)
        if file_size > MAX_FILE_SIZE:
            _LOGGER.error(f"File {filepath} is too large ({file_size} bytes), skipping. Max size: {MAX_FILE_SIZE} bytes.")
            return 0, [], file_type

        with open(filepath, encoding='utf-8') as f:
            content = f.read()

        # Call the engine
        items = _parse_content(content, file_type, filepath, _LOGGER, entity_pattern)

        return len(items), items, file_type

    except Exception as e:
        _LOGGER.error(f"Critical error processing {filepath}: {e}")
        return 0, [], file_type


async def default_async_executor(func: Callable, *args: Any) -> Any:
    """Default executor that runs the synchronous function in a thread."""
    return await asyncio.to_thread(func, *args)

def _scan_files_sync(root_path: str, ignored_patterns: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Synchronous, blocking file scanner using os.walk.

    Executed as a single job in the executor.
    """
    scanned_files = []
    ignored_count = 0
    cwd = os.getcwd()

    # 1. Main recursive scan (os.walk)
    for root, dirs, files in os.walk(root_path, topdown=True):
        # Prune ignored directories
        # Remove ignored dirs and hidden dirs from traversal
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith('.')]

        for file in files:
            abs_path = os.path.join(root, file)
            # Extension check
            _, ext = os.path.splitext(file)
            if ext.lower() not in YAML_FILE_EXTS:
                continue

            # User ignore patterns
            rel_path_cwd = os.path.relpath(abs_path, cwd)
            is_ignored = False
            for pattern in ignored_patterns:
                if fnmatch.fnmatch(abs_path, pattern) or fnmatch.fnmatch(rel_path_cwd, pattern):
                    is_ignored = True
                    break

            if is_ignored:
                ignored_count += 1
                continue

            # Stat
            try:
                stat_res = os.stat(abs_path)
                scanned_files.append({
                    'path': abs_path,
                    'mtime': stat_res.st_mtime,
                    'size': stat_res.st_size
                })
            except OSError as e:
                if os.path.islink(abs_path):
                    _LOGGER.warning(f"Skipping broken symlink: {abs_path}")
                else:
                    _LOGGER.error(f"Error accessing file {abs_path}: {e}")

    # 2. Targeted scan of .storage
    storage_path = os.path.join(root_path, '.storage')
    if os.path.isdir(storage_path):
        for filename in STORAGE_WHITELIST:
            file_path = os.path.join(storage_path, filename)
            if os.path.isfile(file_path):
                try:
                    stat_res = os.stat(file_path)
                    scanned_files.append({
                        'path': file_path,
                        'mtime': stat_res.st_mtime,
                        'size': stat_res.st_size
                    })
                except OSError as e:
                    _LOGGER.error(f"Error accessing whitelist file {file_path}: {e}")

    return scanned_files, ignored_count


# --- WatchmanParser ---

class WatchmanParser:
    def __init__(self, db_path: str, executor: Callable[[Callable, Any], Awaitable[Any]] = None):
        self.db_path = db_path
        # default_async_executor is used by parser CLI
        self.executor = executor or default_async_executor

    @contextlib.contextmanager
    def _db_session(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        try:
            conn = self._init_db(self.db_path)
            try:
                yield conn
            finally:
                conn.close()
        except sqlite3.DatabaseError as e:
            _LOGGER.error(f"Database error in {self.db_path}: {e}")
            raise

    def check_and_fix_db(self) -> None:
        """Check if database is valid, delete and recreate if corrupted."""
        try:
            with self._db_session() as conn:
                conn.execute("SELECT 1")
        except sqlite3.DatabaseError as e:
            msg = str(e).lower()
            if "locked" in msg or "busy" in msg:
                _LOGGER.warning(f"Database locked during check, skipping repair: {e}")
                return

            _LOGGER.error(f"Database corrupted ({e}), deleting {self.db_path}")
            if os.path.exists(self.db_path):
                try:
                    os.remove(self.db_path)
                except OSError as remove_err:
                    _LOGGER.error(f"Failed to remove corrupted DB: {remove_err}")

            # Re-init (will create new file)
            try:
                self._init_db(self.db_path).close()
            except Exception as init_err:
                _LOGGER.error(f"Failed to recreate DB: {init_err}")

    def _init_db(self, db_path: str) -> sqlite3.Connection:
        # Ensure directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
        try:
            c = conn.cursor()

            c.execute("PRAGMA foreign_keys = ON;")
            c.execute("PRAGMA journal_mode = WAL;")
            c.execute("PRAGMA synchronous = OFF;")

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

            c.execute("CREATE INDEX IF NOT EXISTS idx_found_items_file_id ON found_items(file_id);")
            c.execute("CREATE INDEX IF NOT EXISTS idx_found_items_item_type ON found_items(item_type);")

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

            c.execute("INSERT OR IGNORE INTO scan_config (id) VALUES (1)")

            conn.commit()
            return conn
        except Exception:
            conn.close()
            raise

    async def _async_scan_files_legacy(self, root_path: str, ignored_patterns: list[str]) -> tuple[list[dict[str, Any]], int]:
        """Phase 1: Asynchronous file scanning using anyio.

        Returns a list of file metadata and a count of ignored files.
        """
        scanned_files = []
        ignored_count = 0
        cwd = os.getcwd()
        root = anyio.Path(root_path)



        # rglob("**/*.yaml") iterates recursively
        # also need to filter against _IGNORED_DIRS and ignored_patterns
        try:
            # 1. Glob all YAML files
            async for path in root.glob("**/*.yaml"):
                # Check _IGNORED_DIRS
                # We must check relative path to avoid matching parents of root (like /tmp in tests)
                try:
                    rel_path = path.relative_to(root)
                except ValueError:
                    # Should not happen with glob from root, but safe fallback
                    continue

                # If any parent directory in the relative path is ignored, skip
                # we exclude the last part (filename) to allow files named like ignored dirs (unlikely but safe)
                if any(part in IGNORED_DIRS for part in rel_path.parts[:-1]):
                    continue

                abs_path = str(path)

                # Check ignored_patterns (user config)
                is_ignored_user = False
                rel_path_cwd = os.path.relpath(abs_path, cwd)

                for pattern in ignored_patterns:
                    if fnmatch.fnmatch(abs_path, pattern) or fnmatch.fnmatch(rel_path_cwd, pattern):
                        is_ignored_user = True
                        break

                if is_ignored_user:
                    ignored_count += 1
                    continue

                # Stat the file to get mtime
                try:
                    stat_result = await path.stat()
                    mtime = stat_result.st_mtime
                    scanned_files.append({'path': abs_path, 'mtime': mtime, 'size': stat_result.st_size})
                except OSError as e:
                    if os.path.islink(abs_path):
                         _LOGGER.warning(f"Skipping broken symlink: {abs_path}")
                    else:
                         _LOGGER.error(f"Error accessing file {abs_path}: {e}")
                    continue

            # 2. Targeted scan of .storage (whitelist)
            # This handles extensionless JSON files like 'lovelace_dashboards'
            storage_path = root / ".storage"
            if await storage_path.exists() and await storage_path.is_dir():
                for whitelist_name in STORAGE_WHITELIST:
                    file_path = storage_path / whitelist_name
                    if await file_path.exists() and await file_path.is_file():
                         try:
                            abs_path = str(file_path)
                            stat_result = await file_path.stat()
                            scanned_files.append({'path': abs_path, 'mtime': stat_result.st_mtime, 'size': stat_result.st_size})
                         except OSError as e:
                            _LOGGER.error(f"Error accessing whitelist file {abs_path}: {e}")

        except OSError as e:
            _LOGGER.error(f"Error during file scan: {e}")

        return scanned_files, ignored_count

    async def _async_scan_files(self, root_path: str, ignored_patterns: list[str]) -> tuple[list[dict[str, Any]], int]:
        """Phase 1: Synchronous file scanning (offloaded to thread).

        Calls _scan_files_sync in executor.
        """
        return await self.executor(_scan_files_sync, root_path, ignored_patterns)

    async def async_scan(
        self,
        root_path: str,
        ignored_files: list[str],
        *,
        force: bool = False,
        custom_domains: list[str] | None = None,
        base_path: str | None = None,
    ) -> None:
        """Orchestrates the scanning process.

        If force = True, unmodified files will be scanned again
        """
        start_time = time.monotonic()
        try:
            # --- Phase 0: Setup ---
            # Build Entity Pattern
            entity_pattern = _ENTITY_PATTERN
            if custom_domains:
                entity_pattern = re.compile(
                    r"(?:^|[^a-zA-Z0-9_.])(?:states\.)?((" + "|".join(custom_domains) + r")\.[a-z0-9_]+)",
                    re.IGNORECASE
                )

            # --- Phase 1: Async File Scanning ---
            _LOGGER.debug(f"Phase 1 (Scan): Starting scan of {root_path} with patterns {ignored_files}")
            scan_time = time.monotonic()
            files_scanned, ignored_count = await self._async_scan_files(root_path, ignored_files)
            _LOGGER.debug(f"Phase 1 (Scan): Found {len(files_scanned)} files in {(time.monotonic() - scan_time):.3f} sec")

            # --- Phase 2: Reconciliation (DB Check) ---
            reconcile_time = time.monotonic()

            # Fetch all previously processed files metadata into memory cache
            processed_cache = {}
            with self._db_session() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT path, scan_date, file_id FROM processed_files")
                processed_cache = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

            files_to_parse = []
            actual_file_ids = []
            skipped_count = 0
            total_size_to_parse = 0

            for file_data in files_scanned:
                filepath = file_data['path']
                mtime = file_data['mtime']
                size = file_data.get('size', 0)

                # Determine path to store in DB
                path_for_db = filepath
                if base_path:
                    try:
                        path_for_db = os.path.relpath(filepath, base_path)
                    except ValueError:
                        pass # Keep absolute if relpath fails

                scan_date = datetime.datetime.now().isoformat()
                file_id = None
                row = processed_cache.get(path_for_db)
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
                else:
                    should_scan = True

                if should_scan:
                    files_to_parse.append({
                        "path": filepath,
                        "path_for_db": path_for_db,
                        "scan_date": scan_date,
                        "file_id": file_id
                    })
                    total_size_to_parse += size
                else:
                    skipped_count += 1
                    actual_file_ids.append(file_id)

            _LOGGER.debug(f"Phase 2 (Reconciliation): Identified {len(files_to_parse)} files to parse ({total_size_to_parse} bytes). Skipped {skipped_count}. Took {(time.monotonic() - reconcile_time):.3f} sec")

            # --- Phase 3: Sequential Parsing & Persistence ---
            parse_time = time.monotonic()

            # Open a single DB session for the batch
            with self._db_session() as conn:
                cursor = conn.cursor()

                for i, file_info in enumerate(files_to_parse):
                    filepath = file_info["path"]
                    path_for_db = file_info["path_for_db"]
                    scan_date = file_info["scan_date"]
                    file_id = file_info["file_id"]

                    # Execute parsing in executor (CPU-bound)
                    # We do this sequentially to avoid CPU bursts
                    count, items, detected_ftype = await self.executor(process_file_sync, filepath, entity_pattern)

                    # Update DB immediately (transaction is still open until we exit context manager)
                    if file_id:
                        cursor.execute("UPDATE processed_files SET scan_date=?, entity_count=?, file_type=? WHERE file_id=?",
                                    (scan_date, count, detected_ftype, file_id))
                        cursor.execute("DELETE FROM found_items WHERE file_id=?", (file_id,))
                    else:
                        cursor.execute("INSERT INTO processed_files (scan_date, path, entity_count, file_type) VALUES (?, ?, ?, ?)",
                                    (scan_date, path_for_db, count, detected_ftype))
                        file_id = cursor.lastrowid

                    if file_id not in actual_file_ids:
                        actual_file_ids.append(file_id)

                    # Bulk insert items for this file
                    for item in items:
                        # Filter out bundled ignored items
                        is_ignored = False
                        for pattern in BUNDLED_IGNORED_ITEMS:
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

                # --- Cleanup stale files ---
                if actual_file_ids:
                    placeholders = ','.join('?' * len(actual_file_ids))
                    cursor.execute(f"DELETE FROM processed_files WHERE file_id NOT IN ({placeholders})", actual_file_ids)
                else:
                    cursor.execute("DELETE FROM processed_files")

                # Update last parse stats
                duration = time.monotonic() - start_time
                _LOGGER.debug(f"Phase 3 (Parse): finished in {(time.monotonic() - parse_time):.3f} sec")
                _LOGGER.debug(f"Total Scan finished in {duration:.3f} sec")

                current_timestamp = datetime.datetime.now().isoformat()
                cursor.execute("UPDATE scan_config SET last_parse_duration = ?, last_parse_timestamp = ?, ignored_files_count = ? WHERE id = 1",
                            (duration, current_timestamp, ignored_count))

                # Commit transaction
                conn.commit()

        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                _LOGGER.error(f"Database locked, aborting scan: {e}")
                return
            raise

    def get_last_parse_info(self) -> dict[str, Any]:
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

    def get_processed_files(self) -> list[tuple]:
        """Fetch all processed files from the database."""
        with self._db_session() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT file_id, path, file_type, entity_count, scan_date
                FROM processed_files
                ORDER BY path
            """,)
            return cursor.fetchall()

    def get_found_items(self, item_type: str = None) -> list[tuple]:
        """Fetch found items from the database.

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

    def get_automation_context(self, entity_id: str) -> dict[str, Any]:
        """Get automation/script context for a specific entity or service.

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

    async def async_parse(
        self,
        root_path: str,
        ignored_files: list[str],
        *,
        force: bool = False,
        custom_domains: list[str] | None = None,
        base_path: str | None = None,
    ) -> tuple[list[str], list[str], int, int, dict]:
        """main parse function

        Params:
            root_path: where to scan
            ignored_files: file paths which should be ignored during scan
            force (bool): if false, files witch unchanged modification time will be not be parsed
            custom_domains: additional domains provided by customer integrations which should not be ignored by WM, e.g. xiaomi_miio.*
            base_path: root path to make file paths relative in the database

        Returns:
            parsed_entity_list (list): Unique entity_ids (item_type='entity').
            parsed_service_list (list): Unique services (item_type='service').
            parsed_files_count (int): Number of entries in processed_files.
            ignored_files_count (int): Always 0 (stub).
            entity_to_automations (dict): Empty dictionary (stub).

        """
        await self.async_scan(
            root_path,
            ignored_files,
            force=force,
            custom_domains=custom_domains,
            base_path=base_path,
        )

        try:
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

            entity_to_automations = {}

            return (
                parsed_entity_list,
                parsed_service_list,
                parsed_files_count,
                ignored_files_count,
                entity_to_automations
            )
        except sqlite3.OperationalError:
            _LOGGER.error("Database locked during result fetching in parse(), returning empty results.")
            return ([], [], 0, 0, {})
