"""Test configuration for parser tests."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from homeassistant.helpers.debounce import Debouncer


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
    """Return the path to the new_tests/data directory."""
    return str(Path(__file__).parent.parent / "data")
