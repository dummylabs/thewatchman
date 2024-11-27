"""Test setup process."""

from homeassistant.core import HomeAssistant
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from collections.abc import Generator
from typing import Any
import pytest
from unittest.mock import patch

from . import async_init_integration

from custom_components.watchman.const import DOMAIN


# This fixture bypasses the actual setup of the integration
# since we only want to test the config flow. We test the
# actual functionality of the integration in other test modules.
@pytest.fixture(autouse=True)
def _bypass_setup_fixture(request: pytest.FixtureRequest) -> Generator[Any]:
    """Prevent setup."""
    with patch("custom_components.watchman.async_setup_entry", return_value=True):
        yield


async def test_show_config_form(hass: HomeAssistant) -> None:
    """Test show configuration form."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_options_flow(hass: HomeAssistant) -> None:
    """Test show options form."""
    # update_data = {
    #     CONF_NAME: "test",
    #     CONF_LATITUDE: 12,
    #     CONF_LONGITUDE: 23,
    #     CONF_ELEVATION: 456,
    # }

    entry = await async_init_integration(hass)
    await hass.async_block_till_done()

    # Test show Options form
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
