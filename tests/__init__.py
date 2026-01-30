"""Tests for watchman integration."""

from copy import deepcopy
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman.const import (
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
    DEFAULT_OPTIONS,
    CONFIG_ENTRY_MINOR_VERSION,
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
    config[CONF_INCLUDED_FOLDERS] = "/workspaces/thewatchman/tests/data"
    if add_params:
        config = config | add_params

    # Support tests that rely on changing the scan root via included_folders
    if CONF_INCLUDED_FOLDERS in config:
        path = config[CONF_INCLUDED_FOLDERS]
        if isinstance(path, list):
            path = path[0]
        # Only set if it looks like a valid path (not empty)
        if path:
             hass.config.config_dir = str(path)

    if config_entry is None:
        config_entry = MockConfigEntry(
            domain=DOMAIN,
            title="WM",
            unique_id="unique_id",
            version=2,
            minor_version=CONFIG_ENTRY_MINOR_VERSION,
            data=config,
        )
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Wait for initial parse to complete (restore deterministic behavior for tests)
    # The integration now starts in background, but tests expect data to be ready.
    if DOMAIN in hass.data and config_entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][config_entry.entry_id]
        import asyncio
        from custom_components.watchman.const import STATE_IDLE, STATE_SAFE_MODE, STATE_WAITING_HA

        # Wait until we are in a stable state (IDLE or SAFE_MODE)
        # We want to avoid returning while in WAITING_HA or PARSING
        for _ in range(200): # 20 seconds max
            if coordinator.status in [STATE_IDLE, STATE_SAFE_MODE, STATE_WAITING_HA]:
                break
            await asyncio.sleep(0.1)
        else:
            raise TimeoutError(f"Coordinator stuck in {coordinator.status} state during initialization")

        await hass.async_block_till_done()
    return config_entry


def assert_files_equal(test, ref):
    """Compare two files line by line."""
    test_array = open(test, encoding="utf-8").readlines()
    for idx, row in enumerate(open(ref, encoding="utf-8")):
        assert test_array[idx].strip() == row.strip()
