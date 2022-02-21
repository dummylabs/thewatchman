"""Test table reports"""
import os.path
import asyncio
from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from homeassistant.setup import async_setup_component
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, assert_setup_component
from homeassistant.core import callback
from custom_components.watchman import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.watchman.const import CONF_COLUMNS_WIDTH, CONF_IGNORED_STATES, CONF_REPORT_PATH, DOMAIN, DOMAIN_DATA, CONF_INCLUDED_FOLDERS, CONF_IGNORED_FILES
from custom_components.watchman.config_flow import DEFAULT_DATA

async def test_add_service(hass):
    @callback
    def record_event(event):
        """Add recorded event to set."""
        pass

    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    assert len(hass.data[DOMAIN]["services_missing"]) == 3
    hass.services.async_register('fake', 'service1', record_event)
    while len(hass.data[DOMAIN]["services_missing"]) != 2:
        await asyncio.sleep(0.1)
    hass.services.async_remove("fake", "service1")
    while len(hass.data[DOMAIN]["services_missing"]) != 3:
        await asyncio.sleep(0.1)


async def test_change_state(hass):
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    assert len(hass.data[DOMAIN]["services_missing"]) == 3
    hass.states.async_set("sensor.test1_unknown", "available")
    while len(hass.data[DOMAIN]["entities_missing"]) != 2:
        await asyncio.sleep(0.1)