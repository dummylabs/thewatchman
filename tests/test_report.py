"""Test table reports"""
import os.path
import asyncio
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.watchman import (
    async_setup_entry,
)
from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
    CONF_IGNORED_FILES,
    CONF_REPORT_PATH,
    CONF_COLUMNS_WIDTH
)
from custom_components.watchman.config_flow import DEFAULT_DATA

async def test_table_default(hass, tmpdir):
    """test table rendering"""
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = []
    options[CONF_IGNORED_FILES] = []
    base_report = "/workspaces/thewatchman/tests/input/test_report1.txt"
    #reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report1.txt")
    options[CONF_REPORT_PATH] = test_report
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)

    await hass.services.async_call(DOMAIN, "report", {"test_mode":True})
    while not os.path.exists(test_report):
        await asyncio.sleep(0.1)
    assert [row for row in open(test_report, encoding="utf-8")] ==\
        [row for row in open(base_report, encoding="utf-8")]

async def test_table_no_missing(hass, tmpdir):
    """test table rendering with no missing elements"""
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = ["missing"]
    options[CONF_IGNORED_FILES] = []
    base_report = "/workspaces/thewatchman/tests/input/test_report2.txt"
    #reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report2.txt")
    options[CONF_REPORT_PATH] = test_report
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)

    await hass.services.async_call(DOMAIN, "report", {"test_mode":True})
    while not os.path.exists(test_report):
        await asyncio.sleep(0.1)
    assert [row for row in open(test_report, encoding="utf-8")] ==\
        [row for row in open(base_report, encoding="utf-8")]

async def test_table_all_clear(hass, tmpdir):
    """test table rendering with no entries"""
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = ["missing","unknown","unavailable"]
    options[CONF_IGNORED_FILES] = []
    base_report = "/workspaces/thewatchman/tests/input/test_report3.txt"
    #reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report3.txt")
    options[CONF_REPORT_PATH] = test_report
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)

    await hass.services.async_call(DOMAIN, "report", {"test_mode":True})
    while not os.path.exists(test_report):
        await asyncio.sleep(0.1)
    assert [row for row in open(test_report, encoding="utf-8")] ==\
        [row for row in open(base_report, encoding="utf-8")]

async def test_column_resize(hass, tmpdir):
    """test table rendering with narrow columns"""
    options = DEFAULT_DATA
    options[CONF_INCLUDED_FOLDERS] = ["/workspaces/thewatchman/tests/*"]
    options[CONF_IGNORED_STATES] = []
    options[CONF_IGNORED_FILES] = []
    options[CONF_COLUMNS_WIDTH] = [7,7,7]
    base_report = "/workspaces/thewatchman/tests/input/test_report4.txt"
    #reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report4.txt")
    options[CONF_REPORT_PATH] = test_report
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    config_entry = MockConfigEntry(domain='watchman', data={}, options=options, entry_id="test")
    assert await async_setup_entry(hass, config_entry)

    await hass.services.async_call(DOMAIN, "report", {"test_mode":True})
    while not os.path.exists(test_report):
        await asyncio.sleep(0.1)
    assert [row for row in open(test_report, encoding="utf-8")] ==\
        [row for row in open(base_report, encoding="utf-8")]
