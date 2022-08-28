"""Test setup process."""
from copy import deepcopy

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman import async_setup_entry
from custom_components.watchman.config_flow import DEFAULT_DATA
from custom_components.watchman.const import (
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    DOMAIN,
)

TEST_INCLUDED_FOLDERS = ["/workspaces/thewatchman/tests/input"]


async def test_init(hass):
    """Test watchman initialization."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert "watchman_data" in hass.data
    assert hass.services.has_service(DOMAIN, "report")


async def test_missing(hass):
    """Test missing entities detection."""
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


async def test_ignored_state(hass):
    """Test single ignored state processing."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    options[CONF_IGNORED_STATES] = ["unknown"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 2
    assert len(hass.data[DOMAIN]["services_missing"]) == 3


async def test_multiple_ignored_states(hass):
    """Test multiple ignored states processing."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    options[CONF_IGNORED_STATES] = ["unknown", "missing", "unavailable"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 0
    assert len(hass.data[DOMAIN]["services_missing"]) == 0


async def test_ignored_files(hass):
    """Test ignored files processing."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    options[CONF_IGNORED_STATES] = []
    options[CONF_IGNORED_FILES] = ["*/test_services.yaml"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entities_missing"]) == 3
    assert len(hass.data[DOMAIN]["services_missing"]) == 0


async def test_ignored_items(hass):
    """Test ignored files processing."""
    options = deepcopy(DEFAULT_DATA)
    options[CONF_INCLUDED_FOLDERS] = TEST_INCLUDED_FOLDERS
    options[CONF_IGNORED_STATES] = []
    options[CONF_IGNORED_ITEMS] = ["sensor.test1_*", "timer.*"]
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(
        domain="watchman", data={}, options=options, entry_id="test"
    )
    assert await async_setup_entry(hass, config_entry)
    assert len(hass.data[DOMAIN]["entity_list"]) == 3
    assert len(hass.data[DOMAIN]["service_list"]) == 2
    assert len(hass.data[DOMAIN]["entities_missing"]) == 2
    assert len(hass.data[DOMAIN]["services_missing"]) == 2
