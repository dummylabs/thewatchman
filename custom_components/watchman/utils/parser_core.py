import asyncio
from collections.abc import Awaitable, Callable, Generator
import contextlib
from dataclasses import dataclass
import datetime
import fnmatch
import logging
import os
from pathlib import Path
import re
import sqlite3
import time
from typing import Any, TypedDict

import yaml

from homeassistant.core import HomeAssistant

from ..const import DB_TIMEOUT
from .logger import _LOGGER
from .parser_const import (
    ACTION_KEYS,
    BUNDLED_IGNORED_ITEMS,
    CONFIG_ENTRY_DOMAINS,
    ESPHOME_ALLOWED_KEYS,
    ESPHOME_PATH_SEGMENT,
    HA_DOMAINS,
    IGNORED_BRANCH_KEYS,
    IGNORED_DIRS,
    IGNORED_VALUE_KEYS,
    JSON_FILE_EXTS,
    MAX_FILE_SIZE,
    PLATFORMS,
    REGEX_ENTITY_BOUNDARY,
    REGEX_ENTITY_SUFFIX,
    REGEX_OPTIONAL_STATES,
    REGEX_STRICT_SERVICE,
    STORAGE_WHITELIST_PATTERNS,
    YAML_FILE_EXTS,
)
from .yaml_loader import LineLoader


@dataclass
class ParseResult:
    """Dataclass to hold parse statistics."""

    duration: float
    timestamp: str
    ignored_files_count: int
    processed_files_count: int


@dataclass(frozen=True)
class ParserContext:
    """Immutable context object passed during recursion."""

    is_active: bool = False
    parent_type: str | None = None
    parent_id: str | None = None
    parent_alias: str | None = None


DEFAULT_CONTEXT = ParserContext()


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
        from homeassistant.const import Platform #noqa: PLC0415, I001
        platforms = [platform.value for platform in Platform]
    except ImportError:
        pass

    extra_domains = []
    if hass:
        with contextlib.suppress(Exception):
            extra_domains = list(hass.services.async_services().keys())

    return sorted(set(platforms + HA_DOMAINS + extra_domains))

_ALL_DOMAINS = get_domains()

def _compile_entity_pattern(domains: list[str]) -> re.Pattern:
    """Compile entity regex from a list of domains (factory method)."""
    domain_part = "|".join(domains)
    pattern = (
        f"{REGEX_ENTITY_BOUNDARY}{REGEX_OPTIONAL_STATES}(({domain_part})"
        f"{REGEX_ENTITY_SUFFIX})"
    )
    return re.compile(pattern, re.IGNORECASE)


# Regex patterns to identify entitites definitions
_ENTITY_PATTERN = _compile_entity_pattern(_ALL_DOMAINS)

# Regex patterns to identify actions (services) definitions
_SERVICE_PATTERN = re.compile(
    r"(?:service|action):\s*([a-z_0-9]+\.[a-z0-9_]+)",
    re.IGNORECASE
)


# Core Logic Functions

def _detect_file_type(filepath: str) -> str:
    path = Path(filepath)
    filename = path.name
    ext = path.suffix.lower()

    # 1. Check for ESPHome path segment (Specific YAML)
    if ESPHOME_PATH_SEGMENT in path.parts:
        # Ensure it is actually a yaml file
        if ext in YAML_FILE_EXTS:
            return "esphome_yaml"

    # 2. Standard YAML files (Prioritize over 'lovelace' prefix)
    if ext in YAML_FILE_EXTS:
        return "yaml"

    # 3. Specific JSON storage whitelist
    for pattern in STORAGE_WHITELIST_PATTERNS:
        if fnmatch.fnmatch(filename, pattern):
            return "json"

    # 4. Standard JSON files
    if ext in JSON_FILE_EXTS:
        return "json"

    return "unknown"

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
        return not any(k in node for k in forbidden_keys)
    return False

def _is_script(node: dict) -> bool:
    """Check if a node looks like a script definition."""
    return "sequence" in node


def is_template(value: str) -> bool:
    """Check if the string contains Jinja2 or JS template markers.

    Detects markers anywhere in the string to handle inline templates.
    """
    # Fast string search is more efficient than regex for this
    return (
        "{{" in value
        or "{%" in value
        or "{#" in value
        or "[[[" in value
    )


def _scan_string_for_entities(
    content: str,
    results: list[FoundItem],
    line_no: int,
    key_name: str | None,
    context: ParserContext,
    entity_pattern: re.Pattern,
    expected_item_type: str = "entity",
) -> None:
    """Scan a string for entities using various heuristics."""
    matches = list(entity_pattern.finditer(content))
    for match in matches:
        entity_id = match.group(1)

        if _is_part_of_concatenation(content, match):
            continue

        if match.end(1) < len(content) and content[match.end(1)] == "*":
            continue

        if entity_id.endswith("_"):
            continue

        # Word Boundary Check (Heuristic 18)
        end_idx = match.end(1)
        if end_idx < len(content):
            next_char = content[end_idx]
            if next_char in ("-", "{", "["):
                continue
            if next_char == ".":
                if "states." not in match.group(0).lower():
                    continue

        remaining_text = content[match.end(1) :].lstrip()
        if remaining_text.startswith("("):
            continue

        results.append(
            {
                "line": line_no or 0,
                "entity_id": entity_id,
                "item_type": expected_item_type,
                "is_key": False,
                "key_name": key_name,
                "is_automation_context": context.is_active,
                "parent_type": context.parent_type,
                "parent_id": context.parent_id,
                "parent_alias": context.parent_alias,
            }
        )


def _yield_template_lines(content: str) -> Generator[tuple[str, str, int], None, None]:
    """Yields lines from a template with their heuristic type and line offset.

    Yields:
        (line_content, item_type, line_offset_index)
    """
    for i, line in enumerate(content.splitlines()):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Reuse is_template to avoid DRY violation
        if is_template(line_stripped):
            yield line_stripped, "entity", i
        elif REGEX_STRICT_SERVICE.match(line_stripped):
            yield line_stripped, "service", i
        else:
            yield line_stripped, "entity", i


def _derive_context(
    node: dict, parent_context: ParserContext, parent_key: str | None = None
) -> ParserContext:
    """Derive the context for a node based on its content and parent key.

    If the node defines an automation or script, return a new context.
    Otherwise, return the parent context.
    """
    if not isinstance(node, dict):
        return parent_context

    # guard: if we are already inside a defined context (Automation or Script),
    # do not allow nested structures (like repeat, choose) to redefine it.
    if parent_context.is_active:
        return parent_context

    c_id = node.get("id")
    c_alias = node.get("alias")

    # Heuristic: use parent key as ID if no explicit ID is present
    # This is common in named scripts: `script_name: { sequence: ... }`
    if not c_id and parent_key:
        c_id = parent_key

    if _is_automation(node):
        return ParserContext(
            is_active=True,
            parent_type="automation",
            parent_id=str(c_id) if c_id else None,
            parent_alias=str(c_alias) if c_alias else None,
        )

    if _is_script(node):
        return ParserContext(
            is_active=True,
            parent_type="script",
            parent_id=str(c_id) if c_id else None,
            parent_alias=str(c_alias) if c_alias else None,
        )

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
    current_context: ParserContext | None = None,
    expected_item_type: str = "entity",
    parent_key: str | None = None,
) -> None:
    """Recursively searches for entities and services."""
    if current_context is None:
        current_context = DEFAULT_CONTEXT
        # Check if the ROOT node itself establishes a context (e.g., Root Automation)
        if not breadcrumbs and isinstance(data, dict):
            current_context = _derive_context(data, current_context)

    is_esphome = file_type == "esphome_yaml"

    if isinstance(data, dict):
        for key, value in data.items():
            line_no = getattr(key, "line", None)

            # exclude whole branch with key name from IGNORED_BRANCH_KEYS
            if isinstance(key, str) and key.lower() in IGNORED_BRANCH_KEYS:
                continue

            # 1. Check Key (Skip if ESPHome mode)
            if isinstance(key, str) and not is_esphome:
                matches = list(entity_pattern.finditer(key))
                for match in matches:
                    entity_id = match.group(1)

                    if _is_part_of_concatenation(key, match):
                        continue

                    if match.end(1) < len(key) and key[match.end(1)] == "*":
                        continue

                    if entity_id.endswith("_"):
                        continue

                    # Word Boundary Check (Heuristic 18)
                    end_idx = match.end(1)
                    if end_idx < len(key):
                        next_char = key[end_idx]
                        if next_char == "-":
                            continue
                        if next_char == ".":
                            if "states." not in match.group(0).lower():
                                continue

                    remaining_text = key[match.end(1) :].lstrip()
                    if remaining_text.startswith("("):
                        continue

                    results.append(
                        {
                            "line": line_no or 0,
                            "entity_id": entity_id,
                            "item_type": "entity",  # Keys are usually entities
                            "is_key": True,
                            "key_name": key,
                            "is_automation_context": current_context.is_active,
                            "parent_type": current_context.parent_type,
                            "parent_id": current_context.parent_id,
                            "parent_alias": current_context.parent_alias,
                        }
                    )

            # Determine expected type for value
            is_action_key = (
                isinstance(key, str)
                and key.lower() in ACTION_KEYS
            )
            next_type = "service" if is_action_key else "entity"

            # Recurse
            # Calculate context for the child node
            child_ctx = current_context
            if isinstance(value, dict):
                child_ctx = _derive_context(value, current_context, parent_key=key)

            _recursive_search(
                value,
                [*breadcrumbs, data],
                results,
                file_type,
                entity_pattern,
                child_ctx,
                next_type,
                parent_key=key,
            )

    elif isinstance(data, list):
        for item in data:
            child_ctx = current_context
            if isinstance(item, dict):
                child_ctx = _derive_context(item, current_context)
            # List items inherit expected_item_type from parent
            # List items inherit parent_key from parent (e.g. entity_id: [item1, item2])
            _recursive_search(
                item,
                [*breadcrumbs, data],
                results,
                file_type,
                entity_pattern,
                child_ctx,
                expected_item_type,
                parent_key=parent_key,
            )

    elif isinstance(data, str):
        # Check Value
        if getattr(data, "is_tag", False):
            return

        line_no = getattr(data, "line", None)
        key_name = parent_key

        # ignore _values_ of the key from IGNORED_VALUE_KEYS
        # this does not prevent parser to traverse in if there are nested keys
        if key_name and str(key_name).lower() in IGNORED_VALUE_KEYS:
            return

        # ESPHome Mode: Only process value if key_name is allowed
        if is_esphome:
            if not key_name or str(key_name).lower() not in ESPHOME_ALLOWED_KEYS:
                return

        # Handle Action Templates
        if expected_item_type == "service" and is_template(data):
            # Check if this is a block scalar (starts with > or |)
            # If so, the content physically starts on the next line relative to line_no
            is_block_scalar = getattr(data, "style", None) in (">", "|")
            base_offset = 1 if is_block_scalar else 0

            for line, line_type, offset in _yield_template_lines(data):
                # Calculate precise line number
                current_line = (line_no or 0) + offset + base_offset

                if line_type == "service":
                    # Add directly as service
                    results.append(
                        {
                            "line": current_line,
                            "entity_id": line,
                            "item_type": "service",
                            "is_key": False,
                            "key_name": key_name,
                            "is_automation_context": current_context.is_active,
                            "parent_type": current_context.parent_type,
                            "parent_id": current_context.parent_id,
                            "parent_alias": current_context.parent_alias,
                        }
                    )
                else:
                    # Scan for entities within this line
                    _scan_string_for_entities(
                        line,
                        results,
                        current_line,
                        key_name,
                        current_context,
                        entity_pattern,
                    )
            return  # Done processing this string

        # Standard Processing
        # Check for Entities
        _scan_string_for_entities(
            data,
            results,
            line_no or 0,
            key_name,
            current_context,
            entity_pattern,
            expected_item_type,
        )

        # Check for Services (e.g. "service: light.turn_on" inside a string template)
        matches_svc = list(_SERVICE_PATTERN.finditer(data))
        for match in matches_svc:
            service_id = match.group(1)

            results.append(
                {
                    "line": line_no or 0,
                    "entity_id": service_id,
                    "item_type": "service",
                    "is_key": False,
                    "key_name": key_name,
                    "is_automation_context": current_context.is_active,
                    "parent_type": current_context.parent_type,
                    "parent_id": current_context.parent_id,
                    "parent_alias": current_context.parent_alias,
                }
            )


def _parse_config_entries_file(
    data: dict,
    results: list[FoundItem],
    file_type: str,
    entity_pattern: re.Pattern,
) -> None:
    """Parse core.config_entries to extract only relevant domains."""
    if not isinstance(data, dict):
        return

    entries = data.get("data", {}).get("entries", [])
    if not isinstance(entries, list):
        return

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        domain = entry.get("domain")
        if domain not in CONFIG_ENTRY_DOMAINS:
            continue

        # Create Context
        context = ParserContext(
            is_active=True,
            parent_type=f"helper_{domain}",
            parent_alias=entry.get("title") or entry.get("options", {}).get("name"),
            parent_id=entry.get("entry_id"),
        )

        # Recursive Search on this entry only
        _recursive_search(
            entry,
            [],
            results,
            file_type,
            entity_pattern,
            current_context=context,
        )


def _parse_content(content: str, file_type: str, filepath: str | None = None, logger: logging.Logger | None = None, entity_pattern: re.Pattern = _ENTITY_PATTERN) -> list[FoundItem]:
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
        # Check for core.config_entries
        if filepath and filepath.endswith("core.config_entries"):
            _parse_config_entries_file(data, results, file_type, entity_pattern)
        else:
            # Pass DEFAULT_CONTEXT explicitly if needed, or let it default to None -> DEFAULT_CONTEXT inside
            _recursive_search(data, [], results, file_type, entity_pattern)

    # Deduplication
    unique_results: list[FoundItem] = []
    seen = set()
    for item in results:
        signature = (
            item["entity_id"],
            item["line"],
            item["item_type"],
            item["parent_id"],
            item["parent_type"],
        )

        if signature in seen:
            continue

        seen.add(signature)
        unique_results.append(item)

    return unique_results

def process_file_sync(filepath: str, entity_pattern: re.Pattern = _ENTITY_PATTERN) -> tuple[int, list[FoundItem], str]:
    """Process a single file synchronously.

    This function is intended to be run in an executor.
    Returns a tuple of (count, items, detected_file_type).
    """
    file_type = _detect_file_type(filepath)

    if file_type == 'unknown':
        return 0, [], 'unknown'

    try:
        path = Path(filepath)
        file_size = path.stat().st_size
        if file_size > MAX_FILE_SIZE:
            _LOGGER.error(
                f"File {filepath} is too large ({file_size} bytes), skipping. Max size: {MAX_FILE_SIZE} bytes."
            )
            return 0, [], file_type

        content = path.read_text(encoding="utf-8")

        # Call the engine
        items = _parse_content(content, file_type, filepath, _LOGGER, entity_pattern)

        return len(items), items, file_type

    except Exception as e:
        _LOGGER.error(f"Critical error processing {filepath}: {e}")
        return 0, [], file_type


async def default_async_executor(func: Callable, *args: Any) -> Any:
    """Default executor that runs the synchronous function in a thread."""
    return await asyncio.to_thread(func, *args)


def _is_file_ignored(path_obj: Path, cwd: Path, ignored_patterns: list[str]) -> bool:
    """Check if file path matches any ignored pattern."""
    abs_path_str = str(path_obj)
    try:
        rel_path_cwd = str(path_obj.relative_to(cwd))
    except ValueError:
        rel_path_cwd = abs_path_str

    for pattern in ignored_patterns:
        if fnmatch.fnmatch(abs_path_str, pattern) or fnmatch.fnmatch(
            rel_path_cwd, pattern
        ):
            _LOGGER.debug(f"Parser: file {abs_path_str} skipped due to ignored pattern")
            return True
    return False


def _scan_files_sync(root_path: str, ignored_patterns: list[str]) -> tuple[list[dict[str, Any]], int]:
    """Scan files syncronously using os.walk (blocking).

    Executed as a single job in the executor.
    """
    scanned_files = []
    ignored_count = 0
    cwd = Path.cwd()

    # 1. Main recursive scan (os.walk)
    for root, dirs, files in os.walk(root_path, topdown=True):
        # Prune ignored directories
        # Remove ignored dirs and hidden dirs from traversal
        dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

        root_path_obj = Path(root)
        for file in files:
            abs_path_obj = root_path_obj / file
            # Extension check
            if abs_path_obj.suffix.lower() not in YAML_FILE_EXTS:
                continue

            if _is_file_ignored(abs_path_obj, cwd, ignored_patterns):
                ignored_count += 1
                continue

            # Stat
            try:
                stat_res = abs_path_obj.stat()
                scanned_files.append(
                    {
                        "path": str(abs_path_obj),
                        "mtime": stat_res.st_mtime,
                        "size": stat_res.st_size,
                    }
                )
            except OSError as e:
                if abs_path_obj.is_symlink():
                    _LOGGER.warning(f"Skipping broken symlink: {abs_path_obj}")
                else:
                    _LOGGER.error(f"Error accessing file {abs_path_obj}: {e}")

    # 2. Targeted scan of .storage
    storage_path_obj = Path(root_path) / ".storage"
    if storage_path_obj.is_dir():
        for file_path_obj in storage_path_obj.iterdir():
            if not file_path_obj.is_file():
                continue

            filename = file_path_obj.name

            is_whitelisted = False
            for pattern in STORAGE_WHITELIST_PATTERNS:
                if fnmatch.fnmatch(filename, pattern):
                    is_whitelisted = True
                    break

            if is_whitelisted:
                if _is_file_ignored(file_path_obj, cwd, ignored_patterns):
                    ignored_count += 1
                    continue

                try:
                    stat_res = file_path_obj.stat()
                    scanned_files.append(
                        {
                            "path": str(file_path_obj),
                            "mtime": stat_res.st_mtime,
                            "size": stat_res.st_size,
                        }
                    )
                except OSError as e:
                    _LOGGER.error(f"Error accessing file {file_path_obj}: {e}")

    return scanned_files, ignored_count


# --- WatchmanParser ---

class WatchmanParser:
    """Parses HA configuration files to extract entities and actions."""

    def __init__(self, db_path: str, executor: Callable[[Callable, Any], Awaitable[Any]] | None = None) -> None:
        self.db_path = db_path
        # default_async_executor is used by parser CLI
        self.executor = executor or default_async_executor

    @contextlib.contextmanager
    def _db_session(self) -> Generator[sqlite3.Connection]:
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

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        """Apply runtime settings to the connection.

        These operations should not trigger extra i/o writes and
        can be applied each time database is opened"""

        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = TRUNCATE;")
        conn.execute("PRAGMA synchronous = OFF;")

    def _create_fresh_db(self, db_path: str) -> sqlite3.Connection:
        """Create a fresh database with the current schema."""
        from ..const import CURRENT_DB_SCHEMA_VERSION

        conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
        try:
            c = conn.cursor()

            # Set pragmas ensuring they are active for creation
            self._configure_connection(conn)

            c.execute(
                """CREATE TABLE IF NOT EXISTS processed_files (
                            file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            scan_date TEXT,
                            path TEXT UNIQUE,
                            entity_count INTEGER,
                            file_type TEXT
                        )"""
            )

            c.execute(
                """CREATE TABLE IF NOT EXISTS found_items (
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
                                        )"""
            )

            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_found_items_file_id ON found_items(file_id);"
            )
            c.execute(
                "CREATE INDEX IF NOT EXISTS idx_found_items_item_type ON found_items(item_type);"
            )

            c.execute(
                """CREATE TABLE IF NOT EXISTS scan_config (
                            id INTEGER PRIMARY KEY DEFAULT 1 CHECK(id=1), -- Ensure only one row
                            included_folders TEXT,
                            ignored_files TEXT
                        )"""
            )

            c.execute("INSERT OR IGNORE INTO scan_config (id) VALUES (1)")

            # Set version
            c.execute(f"PRAGMA user_version = {CURRENT_DB_SCHEMA_VERSION}")

            conn.commit()
            return conn
        except Exception:
            conn.close()
            raise

    def _init_db(self, db_path: str) -> sqlite3.Connection:
        """Initialize the database connection, handling creation and migrations."""
        # Ensure directory exists
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # 1. File Missing -> Fresh Create
        if not path.exists():
            return self._create_fresh_db(db_path)

        from ..const import CURRENT_DB_SCHEMA_VERSION

        conn = None
        try:
            # 2. File Exists -> Check Version
            conn = sqlite3.connect(db_path, timeout=DB_TIMEOUT)
            cursor = conn.cursor()
            cursor.execute("PRAGMA user_version")
            db_version = cursor.fetchone()[0]

            if db_version != CURRENT_DB_SCHEMA_VERSION:
                _LOGGER.info(
                    "Cache DB version mismatch (found %s, expected %s), recreating cache. First parse may take some time.",
                    db_version,
                    CURRENT_DB_SCHEMA_VERSION,
                )
                conn.close()
                path.unlink(missing_ok=True)
                return self._create_fresh_db(db_path)

            # 3. Version Match -> Setup Runtime Pragmas & Return
            self._configure_connection(conn)
            return conn

        except (sqlite3.DatabaseError, Exception) as e:
            _LOGGER.error(f"Database error during init ({e}), recreating cache.")
            # Ensure connection is closed if it was opened
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

            path.unlink(missing_ok=True)
            return self._create_fresh_db(db_path)

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
    ) -> ParseResult | None:
        """Orchestrates the scanning process.

        If force = True, unmodified files will be scanned again
        """
        start_time = time.monotonic()
        try:
            # --- Phase 0: Setup ---
            # Build Entity Pattern
            entity_pattern = (
                _compile_entity_pattern(custom_domains)
                if custom_domains
                else _ENTITY_PATTERN
            )

            # --- Phase 1: Async File Scanning ---
            _LOGGER.debug(
                f"Parser (Scan): Starting scan of {root_path} with ignore patterns: {ignored_files}"
            )
            scan_time = time.monotonic()
            files_scanned, ignored_count = await self._async_scan_files(
                root_path, ignored_files
            )
            _LOGGER.debug(
                f"Parser (Scan): Found {len(files_scanned)} files in {(time.monotonic() - scan_time):.3f} sec"
            )

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
                filepath = file_data["path"]
                mtime = file_data["mtime"]
                size = file_data.get("size", 0)

                # Determine path to store in DB
                path_for_db = filepath
                if base_path:
                    with contextlib.suppress(ValueError):
                        path_for_db = os.path.relpath(filepath, base_path)

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
                    files_to_parse.append(
                        {
                            "path": filepath,
                            "path_for_db": path_for_db,
                            "scan_date": scan_date,
                            "file_id": file_id,
                        }
                    )
                    total_size_to_parse += size
                else:
                    skipped_count += 1
                    actual_file_ids.append(file_id)

            _LOGGER.debug(
                f"Parser (Reconciliation): Identified {len(files_to_parse)} files to parse ({total_size_to_parse} bytes). Skipped {skipped_count}. Took {(time.monotonic() - reconcile_time):.3f} sec"
            )

            # --- Phase 3: Sequential Parsing & Persistence ---
            parse_time = time.monotonic()

            # Open a single DB session for the batch
            with self._db_session() as conn:
                cursor = conn.cursor()

                for _i, file_info in enumerate(files_to_parse):
                    filepath = file_info["path"]
                    path_for_db = file_info["path_for_db"]
                    scan_date = file_info["scan_date"]
                    file_id = file_info["file_id"]

                    # Execute parsing in executor (CPU-bound)
                    # We do this sequentially to avoid CPU bursts
                    count, items, detected_ftype = await self.executor(
                        process_file_sync, filepath, entity_pattern
                    )

                    # Update DB immediately (transaction is still open until we exit context manager)
                    if file_id:
                        cursor.execute(
                            "UPDATE processed_files SET scan_date=?, entity_count=?, file_type=? WHERE file_id=?",
                            (scan_date, count, detected_ftype, file_id),
                        )
                        cursor.execute(
                            "DELETE FROM found_items WHERE file_id=?", (file_id,)
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO processed_files (scan_date, path, entity_count, file_type) VALUES (?, ?, ?, ?)",
                            (scan_date, path_for_db, count, detected_ftype),
                        )
                        file_id = cursor.lastrowid

                    if file_id not in actual_file_ids:
                        actual_file_ids.append(file_id)

                    # Bulk insert items for this file
                    for item in items:
                        # Filter out bundled ignored items
                        is_ignored = False
                        for pattern in BUNDLED_IGNORED_ITEMS:
                            if fnmatch.fnmatch(item["entity_id"], pattern):
                                is_ignored = True
                                break

                        if is_ignored:
                            continue

                        cursor.execute(
                            """INSERT INTO found_items
                                        (file_id, line, entity_id, item_type, is_key, key_name, is_automation_context, parent_type, parent_id, parent_alias)
                                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (
                                file_id,
                                item["line"],
                                item["entity_id"],
                                item["item_type"],
                                item["is_key"],
                                item["key_name"],
                                item["is_automation_context"],
                                item["parent_type"],
                                item["parent_id"],
                                item["parent_alias"],
                            ),
                        )

                # --- Cleanup stale files ---
                if actual_file_ids:
                    placeholders = ",".join("?" * len(actual_file_ids))
                    cursor.execute(
                        f"DELETE FROM processed_files WHERE file_id NOT IN ({placeholders})",
                        actual_file_ids,
                    )
                else:
                    cursor.execute("DELETE FROM processed_files")

                # Commit transaction
                conn.commit()

            # Update last parse stats
            duration = time.monotonic() - start_time
            _LOGGER.debug(
                f"Parser (Parsing): finished in {(time.monotonic() - parse_time):.3f} sec"
            )
            _LOGGER.debug(f"Parser: total scan finished in {duration:.3f} sec, force refresh sensors now.")

            current_timestamp = datetime.datetime.now().isoformat()

            # Return ParseResult instead of writing to DB
            with self._db_session() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM processed_files")
                processed_files_count = cursor.fetchone()[0]

            return ParseResult(
                duration=duration,
                timestamp=current_timestamp,
                ignored_files_count=ignored_count,
                processed_files_count=processed_files_count,
            )

        except sqlite3.OperationalError as e:
            if "locked" in str(e):
                _LOGGER.error(f"Database locked, aborting scan: {e}")
                return None
            raise

    def get_last_parse_info(self) -> dict[str, Any]:
        """Return the duration, timestamp, ignored files count and processed files count of the last successful scan."""
        with self._db_session() as conn:
            cursor = conn.cursor()
            # Note: last_parse_duration and last_parse_timestamp are now dead columns
            # This method should probably be removed in favor of Store, but kept for compatibility
            # if anything still uses it during transition.
            cursor.execute("SELECT id FROM scan_config WHERE id = 1")
            row = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) FROM processed_files")
            processed_files_count = cursor.fetchone()[0]

            if row:
                return {
                    "duration": 0.0,
                    "timestamp": None,
                    "ignored_files_count": 0,
                    "processed_files_count": processed_files_count,
                }
        return {
            "duration": 0.0,
            "timestamp": None,
            "ignored_files_count": 0,
            "processed_files_count": 0,
        }

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

    def get_found_items(self, item_type: str | None = None) -> list[tuple]:
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
    ) -> tuple[list[str], list[str], int, int, dict, ParseResult | None]:
        """Main parse function.

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
            parse_result (ParseResult): Operational statistics.

        """
        parse_result = await self.async_scan(
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
                cursor.execute(
                    "SELECT DISTINCT entity_id FROM found_items WHERE item_type = 'entity'"
                )
                parsed_entity_list = [row[0] for row in cursor.fetchall()]

                # parsed_service_list
                cursor.execute(
                    "SELECT DISTINCT entity_id FROM found_items WHERE item_type = 'service'"
                )
                parsed_service_list = [row[0] for row in cursor.fetchall()]

                # parsed_files_count
                cursor.execute("SELECT COUNT(*) FROM processed_files")
                parsed_files_count = cursor.fetchone()[0]

                # ignored_files_count
                ignored_files_count = (
                    parse_result.ignored_files_count if parse_result else 0
                )

            entity_to_automations = {}

            return (
                parsed_entity_list,
                parsed_service_list,
                parsed_files_count,
                ignored_files_count,
                entity_to_automations,
                parse_result,
            )
        except sqlite3.OperationalError:
            _LOGGER.error(
                "Database locked during result fetching in parse(), returning empty results."
            )
            return ([], [], 0, 0, {}, None)
