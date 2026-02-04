"""Test report service response."""
import os
from unittest.mock import MagicMock

from custom_components.watchman.const import (
    CONF_INCLUDED_FOLDERS,
    CONF_REPORT_PATH,
    CONF_SECTION_APPEARANCE_LOCATION,
    DOMAIN,
)
import pytest
from tests import async_init_integration


@pytest.mark.asyncio
async def test_report_service_response(hass, new_test_data_dir, tmp_path):
    """Test that the report service returns parsing statistics."""
    # Define source config directory (can be minimal)
    config_dir = os.path.join(new_test_data_dir, "reports", "test_report_generation")

    # Mock hass.config.config_dir
    hass.config.config_dir = config_dir

    # Mock hass.config.path to redirect .storage/watchman.db to tmp_path
    def mock_path_side_effect(*args):
        return str(tmp_path / os.path.join(*args))

    hass.config.path = MagicMock(side_effect=mock_path_side_effect)

    report_file = tmp_path / "watchman_report.txt"

    # Initialize integration
    await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: config_dir,
            CONF_SECTION_APPEARANCE_LOCATION: {
                CONF_REPORT_PATH: str(report_file),
            },
        },
    )

    # Call the service and capture the response
    response = await hass.services.async_call(
        DOMAIN,
        "report",
        {"create_file": False}, # Now this should work and return data without side effects
        blocking=True,
        return_response=True
    )

    # Verify the response structure
    assert isinstance(response, dict)
    assert "parse_duration" in response
    assert "last_parse_date" in response
    assert "ignored_files_count" in response
    assert "processed_files_count" in response

    assert "missing_entities" in response
    assert "missing_actions" in response
    assert isinstance(response["missing_entities"], list)
    assert isinstance(response["missing_actions"], list)

    # Check structure of list items if any exist
    if response["missing_entities"]:
        item = response["missing_entities"][0]
        assert "id" in item
        assert "state" in item
        assert "file" in item
        assert "line" in item

    # Verify values are reasonable
    assert isinstance(response["parse_duration"], float)
    assert response["processed_files_count"] >= 0
    assert response["ignored_files_count"] >= 0
    # timestamp might be None if no parse happened or string if it did.
    # Since we just init, it might be None or filled depending on async_init logic.
    # But keys should exist.
