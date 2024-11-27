"""Test proper handling of entity state changes."""

from homeassistant.core import callback
from custom_components.watchman.const import (
    DOMAIN,
    HASS_DATA_MISSING_ENTITIES,
    HASS_DATA_MISSING_SERVICES,
)
from . import async_init_integration


async def test_add_service(hass):
    """Test adding and removing service events."""

    @callback
    def dummy_service_handler(event):  # pylint: disable=unused-argument
        """Test service handler."""

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(hass)
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 3
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 3
    hass.services.async_register("fake", "service1", dummy_service_handler)
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 2
    hass.services.async_remove("fake", "service1")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 3


async def test_change_state(hass):
    """Test change entity state events."""

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(hass)
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 3
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 3
    hass.states.async_set("sensor.test1_unknown", "available")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 2


async def test_remove_entity(hass):
    """Test entity removal."""
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(hass)
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 3
    hass.states.async_remove("sensor.test4_avail")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 4


async def test_add_entity(hass):
    """Test entity addition."""
    await async_init_integration(hass)
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 4
    # missing -> 42
    hass.states.async_set("sensor.test4_avail", "42")
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 3
