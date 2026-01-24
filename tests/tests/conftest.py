"""Test configuration for parser tests."""
import pytest
import os

# Enable custom component loading
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Automatically enable loading custom integrations in all tests."""
    yield

@pytest.fixture
def new_test_data_dir():
    """Return the path to the new_tests/data directory."""
    return os.path.join(os.path.dirname(__file__), "..", "data")