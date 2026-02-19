"""Test configuration for parser tests."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from homeassistant.helpers.debounce import Debouncer

from syrupy import SnapshotAssertion
from syrupy.extensions.amber import AmberSnapshotExtension

@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Override snapshot to always use standard Amber extension with __snapshots__ dir."""
    return snapshot.use_extension(AmberSnapshotExtension)

# Enable custom component loading
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable loading custom integrations in all tests."""
    return

@pytest.fixture(autouse=True)
def patch_debouncer():
    """Patch Debouncer to be immediate in tests."""
    def immediate_debouncer(hass, logger, cooldown, immediate):
        return Debouncer(hass, logger, cooldown=0.0, immediate=True)

    with patch("custom_components.watchman.coordinator.Debouncer", side_effect=immediate_debouncer):
        yield

@pytest.fixture
def new_test_data_dir():
    """Return the path to the tests/data directory."""
    return str(Path(__file__).parent / "data")

@pytest.fixture(autouse=True)
def cleanup_watchman_files(new_test_data_dir):
    """Cleanup watchman database files after tests."""
    yield
    storage_dir = Path(new_test_data_dir) / ".storage"
    if not storage_dir.exists():
        return

    for filename in ["watchman.db", "watchman_v2.db", "watchman.lock"]:
        file_path = storage_dir / filename
        if file_path.exists():
            file_path.unlink()

    # Also clean journal/wal/shm files
    for path in storage_dir.glob("watchman*.db-*"):
        path.unlink(missing_ok=True)
