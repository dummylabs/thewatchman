"""Test table reports"""

from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    DOMAIN,
    CONF_IGNORED_FILES,
    CONF_REPORT_PATH,
    CONF_COLUMNS_WIDTH,
)
from .common import assert_files_equal, async_init_integration

TEST_INCLUDED_FOLDERS = ["/workspaces/thewatchman/tests/input"]


async def test_table_default(hass, tmpdir):
    """test table rendering"""
    base_report = "/workspaces/thewatchman/tests/input/test_report1.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report1.txt")

    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: [],
            CONF_IGNORED_FILES: [],
            CONF_REPORT_PATH: test_report,
        },
    )

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "report", {"test_mode": True})
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)


async def test_table_no_missing(hass, tmpdir):
    """test table rendering with no missing elements"""
    base_report = "/workspaces/thewatchman/tests/input/test_report2.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report2.txt")

    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: ["missing"],
            CONF_IGNORED_FILES: [],
            CONF_REPORT_PATH: test_report,
        },
    )

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "report", {"test_mode": True})
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)


async def test_table_all_clear(hass, tmpdir):
    """test table rendering with no entries"""
    base_report = "/workspaces/thewatchman/tests/input/test_report3.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report3.txt")
    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: ["missing", "unknown", "unavailable"],
            CONF_IGNORED_FILES: [],
            CONF_REPORT_PATH: test_report,
        },
    )

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "report", {"test_mode": True})
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)


async def test_column_resize(hass, tmpdir):
    """test table rendering with narrow columns"""
    base_report = "/workspaces/thewatchman/tests/input/test_report4.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report4.txt")

    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: [],
            CONF_IGNORED_FILES: [],
            CONF_REPORT_PATH: test_report,
            CONF_COLUMNS_WIDTH: [7, 7, 7],
        },
    )
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "report", {"test_mode": True})
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)
