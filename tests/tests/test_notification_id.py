"""Test default notification_id for watchman report.

Test for this issue: https://github.com/dummylabs/thewatchman/issues/203
"""
from unittest.mock import MagicMock
import pytest
from custom_components.watchman.const import DOMAIN
from tests import async_init_integration

@pytest.mark.asyncio
async def test_default_notification_id(hass, tmp_path):
    """Test that a default notification_id is used if not provided."""

    # Mock config to avoid file creation errors
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    def mock_path(*args):
        if not args:
            return str(tmp_path)
        return str(tmp_path / args[0])

    hass.config.path = MagicMock(side_effect=mock_path)
    hass.config.config_dir = str(config_dir)

    await async_init_integration(hass, add_params={})

    # Capture calls to persistent_notification.create
    captured_data = []

    async def mock_persistent_notification(call):
        captured_data.append(call.data)

    hass.services.async_register("persistent_notification", "create", mock_persistent_notification)

    # Call watchman.report WITHOUT providing notification_id
    data = {
        "action": "persistent_notification.create",
        "create_file": False,
        "data": {
            "title": "Test Title"
            # No notification_id here
        }
    }

    await hass.services.async_call(
        DOMAIN,
        "report",
        service_data=data,
        blocking=True
    )

    assert len(captured_data) > 0, "persistent_notification.create was not called"

    call_data = captured_data[0]

    # This assertion should FAIL before the fix
    assert call_data.get("notification_id") == "watchman_report", \
        f"Expected default notification_id='watchman_report', got '{call_data.get('notification_id')}'"
