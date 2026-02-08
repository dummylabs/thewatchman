"""Test UI defaults for existing users (Migration Check)."""
import pytest
from custom_components.watchman.const import (
    CONF_LOG_OBFUSCATE,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

@pytest.mark.asyncio
async def test_options_flow_missing_key_behavior(hass: HomeAssistant):
    """Test that missing log_obfuscate key results in incorrect default (repro issue)."""
    # Create an entry representing an existing user (v2.2) without the new key
    config_entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test_entry",
        version=2,
        minor_version=2,
        data={}, # Missing CONF_LOG_OBFUSCATE
    )
    config_entry.add_to_hass(hass)

    # Setup the entry to trigger migration
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    # Initialize options flow
    result = await hass.config_entries.options.async_init(config_entry.entry_id)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    # Check the schema description (suggested values)
    # The key CONF_LOG_OBFUSCATE should NOT be in suggested_values if missing from data
    # OR if it is, it might be False/None depending on implementation.
    # We want to prove that it is NOT True (which is our desired default).
    
    data_schema = result["data_schema"]
    
    # In vol.Schema, we can't easily inspect suggested values injected by add_suggested_values_to_schema
    # effectively because it wraps the schema.
    # However, HA's add_suggested_values_to_schema modifies the schema elements.
    
    # We can inspect the field.
    # We need to find the field corresponding to CONF_LOG_OBFUSCATE
    field = data_schema.schema[CONF_LOG_OBFUSCATE]
    
    # If no suggested value, it defaults to what?
    # Ideally, we want the migration to have PUT the value in config_entry.data, 
    # so add_suggested_values_to_schema would pick it up.
    
    # Since migration ran during setup, we expect config_entry.data to HAVE the key.
    assert CONF_LOG_OBFUSCATE in config_entry.data
    
    # And it should be True (default)
    assert config_entry.data.get(CONF_LOG_OBFUSCATE) is True
