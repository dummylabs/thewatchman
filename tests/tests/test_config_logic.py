"""Unit tests for configuration logic helper functions."""
from unittest.mock import patch
from custom_components.watchman.utils.utils import get_included_folders
from custom_components.watchman.const import CONF_INCLUDED_FOLDERS

def test_get_included_folders_default(hass):
    """Test fallback to config dir when no folders specified."""
    # Mock get_config to return empty list (default behavior if not set or empty)
    with patch("custom_components.watchman.utils.utils.get_config", return_value=[]):
        folders = get_included_folders(hass)
        assert len(folders) == 1
        assert folders[0] == (hass.config.config_dir, "**")

def test_get_included_folders_empty_string(hass):
    """Test fallback to config dir when user explicitly sets empty string."""
    # This simulates the case where to_lists returns [] because the input was ""
    with patch("custom_components.watchman.utils.utils.get_config", return_value=[]):
        folders = get_included_folders(hass)
        assert len(folders) == 1
        assert folders[0] == (hass.config.config_dir, "**")

def test_get_included_folders_single_custom(hass):
    """Test single custom folder."""
    custom_path = "/custom/path"
    with patch("custom_components.watchman.utils.utils.get_config", return_value=[custom_path]):
        folders = get_included_folders(hass)
        assert len(folders) == 1
        assert folders[0] == (custom_path, "**")

def test_get_included_folders_multiple_custom(hass):
    """Test multiple custom folders."""
    paths = ["/path/one", "/path/two"]
    with patch("custom_components.watchman.utils.utils.get_config", return_value=paths):
        folders = get_included_folders(hass)
        assert len(folders) == 2
        assert (paths[0], "**") in folders
        assert (paths[1], "**") in folders