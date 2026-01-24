"""Test ignored labels functionality."""
import pytest
import os
from unittest.mock import MagicMock
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import label_registry as lr
from custom_components.watchman.const import (
    CONF_IGNORED_LABELS,
    COORD_DATA_MISSING_ENTITIES,
    COORD_DATA_ENTITY_ATTRS,
    DOMAIN,
    CONF_INCLUDED_FOLDERS,
)
from tests import async_init_integration

@pytest.mark.asyncio
async def test_ignored_labels(hass, tmp_path, new_test_data_dir):
    """Test ignored labels processing."""
    
    # Define source config directory
    config_dir = os.path.join(new_test_data_dir, "reports", "test_ignored_labels")
    
    # Mock hass.config.config_dir to the source dir so relative paths are calculated correctly
    hass.config.config_dir = config_dir

    # Mock hass.config.path to redirect .storage/watchman.db to tmp_path
    def mock_path_side_effect(*args):
        return str(tmp_path / os.path.join(*args))
    
    hass.config.path = MagicMock(side_effect=mock_path_side_effect)

    # Setup Label Registry
    label_registry = lr.async_get(hass)
    ignored_label = label_registry.async_create("ignore_watchman")
    ignored_label_id = ignored_label.label_id

    # Setup Entity Registry and Entity
    entity_registry = er.async_get(hass)
    reg_entry = entity_registry.async_get_or_create(
        "sensor",
        "watchman",
        "test1_unknown",
        suggested_object_id="test1_unknown",
    )
    # Assign label to entity
    entity_registry.async_update_entity(reg_entry.entity_id, labels={ignored_label_id})

    # Setup States
    hass.states.async_set("sensor.test1_unknown", "unknown")
    hass.states.async_set("sensor.test2_missing", "missing")
    hass.states.async_set("sensor.test3_unavail", "unavailable")
    hass.states.async_set("sensor.test4_avail", "42")

    # Initialize Integration with ignored label
    config_entry = await async_init_integration(
        hass, add_params={
            CONF_IGNORED_LABELS: "ignore_watchman",
            CONF_INCLUDED_FOLDERS: str(config_dir)
        }
    )
    
    coordinator = hass.data[DOMAIN][config_entry.entry_id]

    # Verify Results
    assert coordinator.data[COORD_DATA_MISSING_ENTITIES] == 2
    
    # Verify specific entities in the report
    entity_attrs = coordinator.data.get(COORD_DATA_ENTITY_ATTRS, [])
    missing_ids = [e["id"] for e in entity_attrs]
    
    assert "sensor.test1_unknown" not in missing_ids, "Labeled entity should be ignored"
    assert "sensor.test2_missing" in missing_ids
    assert "sensor.test3_unavail" in missing_ids