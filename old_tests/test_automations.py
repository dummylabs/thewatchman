import pytest
from pathlib import Path
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.watchman.const import (
    CONF_EXCLUDE_DISABLED_AUTOMATION,
    CONF_INCLUDED_FOLDERS,
    DOMAIN,
    HASS_DATA_MISSING_ENTITIES,
)
from . import async_init_integration

# Путь к папке с файлом complex_cases.yaml
INCLUDED = str(Path(__file__).parent / "input_automations")

# Test cases.
# Format: (HA automation id, unique sensor to test, automation state, reported missing?)
TEST_CASES = [
    # Case 1: ID + Alias
    ("automation.explicit_id_case", "sensor.missing_case_id_only", "off", False),
    ("automation.explicit_id_case", "sensor.missing_case_id_only", "on", True),
    # Case 2: Alias only.
    ("automation.only_alias_latin", "sensor.missing_case_alias_latin", "off", False),
    ("automation.only_alias_latin", "sensor.missing_case_alias_latin", "on", True),
    # Case 3: Non-latin alias
    ("automation.testovaia_avtomatizatsiia", "sensor.missing_case_alias_cyrillic", "off", False),
    ("automation.testovaia_avtomatizatsiia", "sensor.missing_case_alias_cyrillic", "on", True),
    # Case 4: ID + Alias. ID has higher priority.
    ("automation.priority_id", "sensor.missing_case_priority", "on", True),
    ("automation.priority_id", "sensor.missing_case_priority", "off", False),
    # Case 5: complex symbols.
    ("automation.complex_alias_with_brackets_symbols", "sensor.missing_case_complex", "off", False),
    ("automation.complex_alias_with_brackets_symbols", "sensor.missing_case_complex", "on", True),
]

@pytest.mark.parametrize("auto_entity_id, missing_entity, automation_state, should_be_present", TEST_CASES)
async def test_regex_parsing_and_disabled_logic(
    hass: HomeAssistant,
    auto_entity_id,
    missing_entity,
    automation_state,
    should_be_present
) -> None:
    """
    Test that the parser correctly extracts IDs/Aliases to match HA Entity IDs,
    and respects the disabled state for various naming conventions.
    """

    hass.states.async_set(auto_entity_id, automation_state)

    await async_init_integration(
        hass,
        add_params={
            CONF_INCLUDED_FOLDERS: INCLUDED,
            CONF_EXCLUDE_DISABLED_AUTOMATION: True,
        },
    )

    missing_list = hass.data[DOMAIN][HASS_DATA_MISSING_ENTITIES]

    if should_be_present:
        assert missing_entity in missing_list, (
            f"Entity {missing_entity} should be reported because {auto_entity_id} is {automation_state}"
        )
    else:
        assert missing_entity not in missing_list, (
            f"Entity {missing_entity} should NOT be reported because {auto_entity_id} is {automation_state}. "
            f"Parser likely failed to match regex for this ID/Alias."
        )
