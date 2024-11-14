"""Test setup process."""

from copy import deepcopy
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.watchman import (
    async_setup_entry,
)
from custom_components.watchman.const import (
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
    HASS_DATA_MISSING_ENTITIES,
)
from custom_components.watchman.config_flow import DEFAULT_DATA
from .common import async_init_integration

TEST_INCLUDED_FOLDERS = ["/workspaces/thewatchman/tests/input_regex"]


async def test_regex(hass):
    """test missing entities detection"""
    await async_init_integration(
        hass, add_params={CONF_INCLUDED_FOLDERS: TEST_INCLUDED_FOLDERS}
    )
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 10
