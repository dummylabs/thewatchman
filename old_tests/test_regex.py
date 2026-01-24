"""Test regexp rules."""

from custom_components.watchman.const import (
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
    HASS_DATA_MISSING_ENTITIES,
)

from . import async_init_integration

TEST_INCLUDED_FOLDERS = "/workspaces/thewatchman/tests/input_regex"


async def test_regex(hass):
    """Test missing entities detection."""
    await async_init_integration(
        hass, add_params={CONF_INCLUDED_FOLDERS: TEST_INCLUDED_FOLDERS}
    )
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 50
