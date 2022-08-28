"""Test table reports"""
from copy import deepcopy

from homeassistant.core import callback
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman import async_setup_entry
from custom_components.watchman.config_flow import DEFAULT_DATA
from custom_components.watchman.const import CONF_INCLUDED_FOLDERS, DOMAIN

TEST_INCLUDED_FOLDERS = ["/workspaces/thewatchman/tests/input"]


async def test_add_service(hass):
    """Test adding and removing service events."""

    @callback
    def dummy_service_handler(event):  # pylint: disable=unused-argument
        """Dummy service handler."""

    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    assert len(hass.data[DOMAIN]["services_missing"]) == 3
    hass.services.async_register("fake", "service1", dummy_service_handler)
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN]["services_missing"]) == 2
    hass.services.async_remove("fake", "service1")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN]["services_missing"]) == 3


async def test_change_state(hass):
    """Test change entity state events."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    assert len(hass.data[DOMAIN]["services_missing"]) == 3
    hass.states.async_set("sensor.test1_unknown", "available")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN]["entities_missing"]) == 2


async def test_remove_entity(hass):
    """Test entity removal."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    hass.states.async_remove("sensor.test4_avail")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN]["entities_missing"]) == 4


async def test_add_entity(hass):
    """Test entity addition."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 4
    # missing -> 42
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
