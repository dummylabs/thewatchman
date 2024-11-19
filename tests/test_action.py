"""Test regexp rules"""

import homeassistant.components.persistent_notification as pn

from custom_components.watchman.const import (
    CONF_HEADER,
    CONF_SECTION_APPEARANCE_LOCATION,
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
    HASS_DATA_MISSING_ENTITIES,
)

from . import async_init_integration

TEST_INCLUDED_FOLDERS = "/workspaces/thewatchman/tests/input_regex"


async def test_notification_action(hass):
    """Test calling notification action from within watchman.report"""
    notifications = pn._async_get_or_create_notifications(hass)
    assert len(notifications) == 0

    await async_init_integration(
        hass,
        add_params={
            CONF_SECTION_APPEARANCE_LOCATION: {CONF_HEADER: "report_header"},
        },
    )
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN,
        "report",
        {
            "service": "persistent_notification.create",
            "send_notification": True,
            "create_file": False,
        },
    )
    await hass.async_block_till_done()
    assert len(notifications) == 1
    notification = notifications[list(notifications)[0]]
    assert "report_header" in notification["message"]
    ## todo: test for calling parse config from watchman.report service


async def test_notification_action_ambiguous_params(hass):
    """Test calling notification action from within watchman.report"""
    notifications = pn._async_get_or_create_notifications(hass)
    assert len(notifications) == 0

    await async_init_integration(hass)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN,
        "report",
        {
            "service": "persistent_notification.create",
            "send_notification": False,
            "create_file": False,
        },
    )
    await hass.async_block_till_done()
    assert len(notifications) == 1
    notification = notifications[list(notifications)[0]]
    assert "send_notification" in notification["message"]


async def test_notification_action_wrong_action(hass):
    """Test calling notification action from within watchman.report"""
    notifications = pn._async_get_or_create_notifications(hass)
    assert len(notifications) == 0

    await async_init_integration(hass)
    await hass.async_block_till_done()
    await hass.services.async_call(
        DOMAIN,
        "report",
        {
            "service": "wrong_service",
            "send_notification": True,
            "create_file": False,
        },
    )
    await hass.async_block_till_done()
    assert len(notifications) == 1
    notification = notifications[list(notifications)[0]]
    assert "wrong_service" in notification["message"]
