"""Test setup process."""
import os.path
import asyncio
from homeassistant.exceptions import ConfigEntryNotReady
import pytest
from homeassistant.setup import async_setup_component
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, assert_setup_component
from custom_components.watchman import (
    async_setup_entry,
    async_unload_entry,
)
from custom_components.watchman.const import CONF_IGNORED_STATES, CONF_REPORT_PATH, DOMAIN, DOMAIN_DATA, CONF_INCLUDED_FOLDERS, CONF_IGNORED_FILES
from custom_components.watchman.config_flow import DEFAULT_DATA

async def test_init(hass):
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    assert "watchman_data" in hass.data
    assert hass.services.has_service(DOMAIN, 'report')
#    assert len(hass.data[DOMAIN]["entities_missing"]) == 4
#    assert len(hass.data[DOMAIN]["services_missing"]) == 3
    #print(hass.data[DOMAIN])

async def test_missing(hass):
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

async def test_ignored_state(hass):
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = ["unknown"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 2
    assert len(hass.data[DOMAIN]["services_missing"]) == 3

async def test_multiple_ignored_states(hass):
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = ["unknown","missing","unavailable"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 0
    assert len(hass.data[DOMAIN]["services_missing"]) == 0

async def test_ignored_files(hass):
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = []
    options[CONF_IGNORED_FILES] = ["*/test_services.yaml"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    assert len(hass.data[DOMAIN]["services_missing"]) == 0

