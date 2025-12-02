"""Test setup process."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman.const import (
    CONF_CHECK_LOVELACE,
    CONF_CHUNK_SIZE,
    CONF_COLUMNS_WIDTH,
    CONF_FRIENDLY_NAMES,
    CONF_HEADER,
    CONF_IGNORED_FILES,
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_STATES,
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    CONF_SECTION_NOTIFY_ACTION,
    CONF_SERVICE_DATA2,
    CONF_SERVICE_NAME,
    CONF_STARTUP_DELAY,
    DOMAIN,
    SENSOR_MISSING_ACTIONS,
    SENSOR_MISSING_SERVICES,
)

from . import from_list

# configuration for version 1

old_config = {
    CONF_SERVICE_NAME: "notify.dima_telegram",
    CONF_SERVICE_DATA2: '{"aaa":"bbb"}',
    CONF_INCLUDED_FOLDERS: ["/config"],
    CONF_HEADER: "header",
    CONF_REPORT_PATH: "report.txt",
    CONF_IGNORED_STATES: ["missing"],
    CONF_CHUNK_SIZE: 3500,
    CONF_COLUMNS_WIDTH: [33, 7, 66],
    CONF_STARTUP_DELAY: 66,
    CONF_FRIENDLY_NAMES: True,
    CONF_CHECK_LOVELACE: True,
    CONF_IGNORED_ITEMS: ["item1", "item2"],
    CONF_IGNORED_FILES: ["file1", "file2"],
}


async def test_entry_migration_1to2(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
):
    """Test watchman initialization."""
    # await async_init_integration(hass)

    mock_config_entry = MockConfigEntry(
        domain=DOMAIN,
        title="WM",
        unique_id="unique_id",
        entry_id="watchman_entry",
        version=1,
        minor_version=1,
        options=old_config,
    )

    mock_config_entry.add_to_hass(hass)

    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        "watchman_entry_watchman_missing_services",
        suggested_object_id="watchman_missing_services",
        config_entry=mock_config_entry,
    )
    assert entity_registry.async_get(f"sensor.{SENSOR_MISSING_SERVICES}")
    await hass.async_block_till_done(wait_background_tasks=True)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert "watchman_data" in hass.data
    assert hass.services.has_service(DOMAIN, "report")

    assert mock_config_entry.data[CONF_INCLUDED_FOLDERS] == from_list(
        old_config[CONF_INCLUDED_FOLDERS]
    )
    assert mock_config_entry.data[CONF_IGNORED_ITEMS] == from_list(
        old_config[CONF_IGNORED_ITEMS]
    )
    assert mock_config_entry.data[CONF_IGNORED_FILES] == from_list(
        old_config[CONF_IGNORED_FILES]
    )

    assert mock_config_entry.data[CONF_STARTUP_DELAY] == old_config[CONF_STARTUP_DELAY]

    assert (
        mock_config_entry.data[CONF_IGNORED_STATES] == old_config[CONF_IGNORED_STATES]
    )
    assert (
        mock_config_entry.data[CONF_CHECK_LOVELACE] == old_config[CONF_CHECK_LOVELACE]
    )
    # === appearance_and_location section ===
    assert mock_config_entry.data[CONF_SECTION_APPEARANCE_LOCATION][CONF_FRIENDLY_NAMES]
    assert (
        mock_config_entry.data[CONF_SECTION_APPEARANCE_LOCATION][CONF_HEADER]
        == old_config[CONF_HEADER]
    )
    assert (
        mock_config_entry.data[CONF_SECTION_APPEARANCE_LOCATION][CONF_REPORT_PATH]
        == old_config[CONF_REPORT_PATH]
    )

    assert mock_config_entry.data[CONF_SECTION_APPEARANCE_LOCATION][
        CONF_COLUMNS_WIDTH
    ] == from_list(old_config[CONF_COLUMNS_WIDTH])

    # === nofity_action section ===
    assert CONF_SECTION_NOTIFY_ACTION not in mock_config_entry.data
    assert CONF_SERVICE_NAME not in mock_config_entry.data
    assert CONF_SERVICE_DATA2 not in mock_config_entry.data
    assert CONF_CHUNK_SIZE not in mock_config_entry.data
    e = entity_registry.async_get(f"sensor.{SENSOR_MISSING_SERVICES}")
    assert e
    assert not entity_registry.async_get(f"sensor.{SENSOR_MISSING_ACTIONS}")
    # entity_registry.async_remove(e.entity_id)
    # assert not entity_registry.async_get(f"sensor.{SENSOR_MISSING_SERVICES}")
    # await hass.config_entries.async_remove(mock_config_entry.entry_id)
    # await hass.async_block_till_done()
    # print(f"---???---{entity_registry.entities.values()}")
