"""Test Watchman button entity migration."""
from copy import deepcopy
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.watchman.const import (
    CONFIG_ENTRY_MINOR_VERSION,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from tests import async_init_integration


async def test_button_legacy_uid_migration(hass: HomeAssistant):
    """Scenario A: Legacy uid migration ({entry_id}_watchman_report_button)."""
    entity_registry = er.async_get(hass)
    entry_id = "test_entry_id_123"
    button_key = "report_button"
    old_uid = f"{entry_id}_{DOMAIN}_{button_key}"
    new_uid = f"{DOMAIN}_{button_key}"

    # Pre-populate registry with old UID
    entity_registry.async_get_or_create(
        "button", DOMAIN, old_uid, suggested_object_id="watchman_create_report_file"
    )

    config_entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title="Watchman",
        unique_id="watchman_unique_id",
        version=2,
        minor_version=CONFIG_ENTRY_MINOR_VERSION,
        data=deepcopy(DEFAULT_OPTIONS),
    )

    await async_init_integration(hass, config_entry=config_entry)

    try:
        # 1. Verify new UID exists
        entry = entity_registry.async_get("button.watchman_create_report_file")
        assert entry
        assert entry.unique_id == new_uid

        # 2. Verify old UID is GONE
        assert entity_registry.async_get_entity_id("button", DOMAIN, old_uid) is None

        # 3. Verify only one button exists for this platform
        all_watchman_buttons = [
            e
            for e in entity_registry.entities.values()
            if e.domain == "button" and e.platform == DOMAIN
        ]
        assert len(all_watchman_buttons) == 1
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_button_duplicate_domain_uid_migration(hass: HomeAssistant):
    """Scenario B: Duplicate-domain uid migration (watchman_watchman_report_button)."""
    entity_registry = er.async_get(hass)
    button_key = "report_button"
    old_uid = f"{DOMAIN}_{DOMAIN}_{button_key}"
    new_uid = f"{DOMAIN}_{button_key}"

    # Pre-populate registry with duplicate-domain UID
    entity_registry.async_get_or_create(
        "button", DOMAIN, old_uid, suggested_object_id="watchman_create_report_file"
    )

    config_entry = await async_init_integration(hass)

    try:
        # 1. Verify new UID exists
        entry = entity_registry.async_get("button.watchman_create_report_file")
        assert entry
        assert entry.unique_id == new_uid

        # 2. Verify old UID is GONE
        assert entity_registry.async_get_entity_id("button", DOMAIN, old_uid) is None

        # 3. Verify only one button exists
        all_watchman_buttons = [
            e
            for e in entity_registry.entities.values()
            if e.domain == "button" and e.platform == DOMAIN
        ]
        assert len(all_watchman_buttons) == 1
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()


async def test_button_clean_install(hass: HomeAssistant):
    """Scenario C: Clean install (no migration needed)."""
    config_entry = await async_init_integration(hass)

    try:
        entity_registry = er.async_get(hass)
        entry = entity_registry.async_get("button.watchman_create_report_file")
        assert entry
        assert entry.unique_id == "watchman_report_button"
        assert entry.entity_id == "button.watchman_create_report_file"

        all_watchman_buttons = [
            e
            for e in entity_registry.entities.values()
            if e.domain == "button" and e.platform == DOMAIN
        ]
        assert len(all_watchman_buttons) == 1
    finally:
        await hass.config_entries.async_unload(config_entry.entry_id)
        await hass.async_block_till_done()
