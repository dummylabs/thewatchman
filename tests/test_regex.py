"""Test setup process."""
from copy import deepcopy

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman import async_setup_entry
from custom_components.watchman.config_flow import DEFAULT_DATA
from custom_components.watchman.const import CONF_INCLUDED_FOLDERS, DOMAIN

TEST_INCLUDED_FOLDERS = ["/workspaces/thewatchman/tests/input_regex"]


async def test_regex(hass):
    """Test missing entities detection."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 9
