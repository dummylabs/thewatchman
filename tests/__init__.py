"""Tests for watchman integration."""

from copy import deepcopy
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman.const import (
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
    DEFAULT_OPTIONS,
)


def from_list(list):
    """Support function."""
    return ",".join(str(x) for x in list)


async def async_init_integration(
    hass: HomeAssistant,
    config_entry: ConfigEntry | None = None,
    add_params=None,
) -> MockConfigEntry:
    """Set up integration in Home Assistant."""
    config = deepcopy(DEFAULT_OPTIONS)
    config[CONF_INCLUDED_FOLDERS] = "/workspaces/thewatchman/tests/input"
    if add_params:
        config = config | add_params
    if config_entry is None:
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            title="WM",
            unique_id="unique_id",
            version=2,
            data=config,
        )
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    return config_entry


def assert_files_equal(test, ref):
    """Compare two files line by line."""
    test_array = open(test, encoding="utf-8").readlines()
    for idx, row in enumerate(open(ref, encoding="utf-8")):
        assert test_array[idx].strip() == row.strip()
