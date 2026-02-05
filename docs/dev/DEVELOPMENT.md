
## Dev Entironment Setup

Please make sure to install the git pre-push hook before pushing any commits to the remote. You can do this by running:

```bash
uv run pre-commit install    # run linters before commit (TODO, not yet implemented)
uv run pre-commit install --hook-type pre-push  # run tests before push
```

## Data Persistence & Migrations

Watchman uses a hybrid storage approach to balance performance and reliability. Data is segregated into three categories based on its lifecycle and access patterns.

### 1. Data Storage Model

|**Data Type**|**Storage Mechanism**|**Location**|**Description**|
|---|---|---|---|
|**User Configuration**|HA Config Entries|`.storage/core.config_entries`|Persistent settings (ignore lists, report paths). Managed by HA.|
|**Parsing Index**|SQLite|`.storage/watchman_v2.db`|"Cold" cache. Relational data (files, entities, line numbers). Optimized for read performance.|
|**Operational Stats**|JSON Store|`.storage/watchman.stats`|"Hot" data. Volatile statistics (last scan time, duration, counters). Loaded into memory on startup.|

### 2. Configuration Migration (`ConfigEntry`)

Standard Home Assistant migration logic is used for user settings.

- **Implementation:** `async_migrate_entry` in `__init__.py`.
- **Versioning:** Controlled by `CONFIG_ENTRY_VERSION` and `CONFIG_ENTRY_MINOR_VERSION` in `const.py`.
- **Strategy:**
    - **Minor bumps:** For backward-compatible additions (e.g., adding a new option with a default value).
    - **Major bumps:** For breaking changes requiring structure transformation.
        

### 3. Database Migration (SQLite)

The SQLite database stores the parsing cache. Since this data is reproducible (by rescanning), the migration strategy prioritizes stability over data preservation during downgrades.

- **Implementation:** `WatchmanParser._init_db` in `parser_core.py`.
- **Versioning:** Uses SQLite `PRAGMA user_version`. Controlled by `CURRENT_DB_SCHEMA_VERSION`.
- **Strategy:**
    - **Upgrade (vCurrent < vTarget):** Apply sequential SQL migrations (ALTER TABLE) inside `_migrate_db`.
    - **Downgrade (vCurrent > vTarget):** **Hard Reset.** The system detects a newer schema version than supported, deletes the `.db` file, and rebuilds it from scratch. We do not implement downgrade logic for the cache.
        
- **Legacy Note:** Version 0.8.3-rc2 introduced a hard break by renaming the file from `watchman.db` to `watchman_v2.db`to isolate the new schema from legacy versions.

### 4. Statistics Migration (JSON Store)

Statistics are stored using `homeassistant.helpers.storage.Store`.

- **Implementation:** `WatchmanCoordinator` in `coordinator.py`.
- **Versioning:** Controlled by `STORAGE_VERSION`.
- **Strategy:**
    - **Soft Upgrades:** We rely on Python's dictionary `.get(key, default)` method.
    - **Reset:** If `STORAGE_VERSION` is incremented, HA treats the old file as invalid and starts with fresh stats (effective reset).
        

### 5. Versioning Guidelines

- **When to bump versions:**
    - **SQLite:** **Mandatory** if you modify `CREATE TABLE` statements or add columns.
    - **Stats:** **Avoid** bumping `STORAGE_VERSION` for simple field additions. Only bump if the root structure changes (e.g., dict to list) or if key types change incompatibly.
    - **ConfigEntry:** Bump **Minor** version when adding new configuration options to `const.py` defaults.
- **Adding fields to Stats:**
    Do not create a migration. Simply add the field to the `ParseResult` dataclass and use `stats.get("new_field", default_value)` in `coordinator.py`. Old files will simply yield the default value until the next save.
    

### 6. Schema Integrity Testing

We use snapshot testing to prevent accidental schema changes.

- **Tests:** `tests/test_integrity.py`.
- **Mechanism:** The tests dump the in-memory SQLite schema and `ParseResult` fields, comparing them against stored snapshots in `tests/snapshots/`.
- **Workflow:**
    1. If you modify the SQL schema or Stats structure, `pytest` will fail.
    2. Verify the change is intentional.
    3. Bump `CURRENT_DB_SCHEMA_VERSION` in `const.py`.
    4. Run `pytest --snapshot-update` to update the golden files.
    5. If modification of `Stats` structure simply adds a field (no breaking change), do not increment `STORAGE_VERSION`, just update test snapshot
