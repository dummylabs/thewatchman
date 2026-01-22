"""Test setup process."""

from homeassistant.setup import async_setup_component
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from . import async_init_integration

from custom_components.watchman.const import (
    CONF_IGNORED_ITEMS,
    CONF_IGNORED_LABELS,
    CONF_IGNORED_STATES,
    DOMAIN,
    CONF_IGNORED_FILES,
    HASS_DATA_MISSING_ENTITIES,
    HASS_DATA_MISSING_SERVICES,
    HASS_DATA_PARSED_ENTITY_LIST,
    HASS_DATA_PARSED_SERVICE_LIST,
    SENSOR_LAST_UPDATE,
    SENSOR_MISSING_ACTIONS,
    SENSOR_MISSING_ENTITIES,
)


async def test_async_setup(hass: HomeAssistant):
    """Test a successful setup component."""
    await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


async def test_init(hass: HomeAssistant, entity_registry: er.EntityRegistry):
    """Test watchman initialization."""
    await async_init_integration(hass)
    assert "watchman_data" in hass.data
    assert hass.services.has_service(DOMAIN, "report")
    assert entity_registry.async_get(f"sensor.{SENSOR_MISSING_ACTIONS}")
    assert entity_registry.async_get(f"sensor.{SENSOR_MISSING_ENTITIES}")
    assert entity_registry.async_get(f"sensor.{SENSOR_LAST_UPDATE}")


async def test_missing(hass):
    """Test missing entities detection."""
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(hass)
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 3
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 3


async def test_ignored_state(hass):
    """Test single ingnored state processing."""
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(hass, add_params={CONF_IGNORED_STATES: ["unknown"]})
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 2
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 3


async def test_multiple_ignored_states(hass):
    """Test multiple ingnored states processing."""
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(
        hass, add_params={CONF_IGNORED_STATES: ["unknown", "missing", "unavailable"]}
    )
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 0
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 0


async def test_ignored_files(hass):
    """Test ignored files processing."""
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(
        hass, add_params={CONF_IGNORED_FILES: "*/test_services.yaml"}
    )
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 3
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 0


async def test_ignored_items(hass):
    """Test ignored items processing."""
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")
    await async_init_integration(
        hass, add_params={CONF_IGNORED_ITEMS: "sensor.test1_*, timer_.*"}
    )
    assert len(hass.data[DOMAIN][HASS_DATA_PARSED_ENTITY_LIST]) == 3
    assert len(hass.data[DOMAIN][HASS_DATA_PARSED_SERVICE_LIST]) == 2
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 2
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 2


async def test_ignored_labels(hass):
    """Test ignored labels processing."""
    label_registry = lr.async_get(hass)
    ignored_label = label_registry.async_create("ignore_watchman")
    ignored_label_id = getattr(ignored_label, "label_id", None) or getattr(
        ignored_label, "id", None
    )
    assert ignored_label_id

    entity_registry = er.async_get(hass)
    reg_entry = entity_registry.async_get_or_create(
        "sensor",
        "watchman",
        "test1_unknown",
        suggested_object_id="test1_unknown",
    )
    entity_registry.async_update_entity(reg_entry.entity_id, labels={ignored_label_id})

    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")

    await async_init_integration(
        hass, add_params={CONF_IGNORED_LABELS: "ignore_watchman"}
    )

    # entity with ignored label is excluded from missing entities report
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]) == 2
    assert len(hass.data[DOMAIN][HASS_DATA_MISSING_SERVICES]) == 3
