"""Test table reports."""

import os
from unittest.mock import patch

from custom_components.watchman.const import (
    CONF_IGNORED_STATES,
    DOMAIN,
    CONF_IGNORED_FILES,
    CONF_REPORT_PATH,
    CONF_COLUMNS_WIDTH,
    CONF_SECTION_APPEARANCE_LOCATION,
)
from . import async_init_integration, assert_files_equal

TEST_INCLUDED_FOLDERS = ["/workspaces/thewatchman/tests/input"]


async def mock_path(yaml_file, root):
    """Mock function for get_report path."""
    return os.path.sep.join(yaml_file.split(os.path.sep)[-2:])


async def mock_stats(hass, start_time):
    """Mock function for report stats."""
    return ("01 Jan 1970 00:00:00", 0.01, 0.105, 0.0003)


@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
@patch("custom_components.watchman.utils.parser.async_get_short_path", new=mock_path)
async def test_table_default(hass, tmpdir):
    """Test table rendering."""
    base_report = "/workspaces/thewatchman/tests/input/test_report1.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report1.txt")

    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: "",
            CONF_IGNORED_FILES: "",
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: test_report,
            },
        },
    )

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "report")
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)


@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
@patch("custom_components.watchman.utils.parser.async_get_short_path", new=mock_path)
async def test_table_no_missing(hass, tmpdir):
    """Test table rendering with no missing elements."""
    base_report = "/workspaces/thewatchman/tests/input/test_report2.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report2.txt")
    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: ["missing"],
            CONF_IGNORED_FILES: "",
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: test_report,
            },
        },
    )

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "report")
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)


@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
async def test_table_all_clear(hass, tmpdir):
    """Test table rendering with no entries."""
    base_report = "/workspaces/thewatchman/tests/input/test_report3.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report3.txt")
    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: ["missing", "unknown", "unavailable"],
            CONF_IGNORED_FILES: "",
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: test_report,
            },
        },
    )

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()

    await hass.services.async_call(DOMAIN, "report")
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)


@patch("custom_components.watchman.utils.report.parsing_stats", new=mock_stats)
@patch("custom_components.watchman.utils.parser.async_get_short_path", new=mock_path)
async def test_column_resize(hass, tmpdir):
    """Test table rendering with narrow columns."""
    base_report = "/workspaces/thewatchman/tests/input/test_report4.txt"
    # reports stored here: /tmp/pytest-of-root/pytest-current/<test_name>_pyloop_current
    test_report = tmpdir.join("test_report4.txt")
    await async_init_integration(
        hass,
        add_params={
            CONF_IGNORED_STATES: [],
            CONF_IGNORED_FILES: "",
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: test_report,
                CONF_COLUMNS_WIDTH: "7, 7, 7",
            },
        },
    )
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, "report")
    await hass.async_block_till_done()
    assert_files_equal(base_report, test_report)
