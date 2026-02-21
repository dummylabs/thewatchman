"""Tests for handling 'disabled' and other problematic states."""
from unittest.mock import MagicMock, patch
from homeassistant.core import HomeAssistant, State
from custom_components.watchman.coordinator import (
    check_single_entity_status, 
    renew_missing_items_list, 
    FilterContext
)
from custom_components.watchman.const import (
    TRACKED_STATE_MISSING,
    TRACKED_STATE_UNKNOWN,
    TRACKED_STATE_UNAVAILABLE,
    TRACKED_STATE_REGISTRY_DISABLED,
)

def test_active_entity_with_disabled_state():
    """Test that an active entity with 'disabled' state value is NOT reported as missing."""
    hass = MagicMock()
    
    # Mock context
    ctx = MagicMock(spec=FilterContext)
    ctx.ignored_labels = set()
    ctx.ignored_states = []
    ctx.exclude_disabled = False
    ctx.automation_map = {}
    ctx.script_map = {}
    ctx.entity_registry = MagicMock()
    
    entry = "sensor.ups_beeper"
    data = {"locations": {"test.yaml": [10]}, "automations": [], "occurrences": [{"path": "test.yaml", "line": 10}]}
    
    # Setup: Entity EXISTS in state machine with state "disabled"
    hass.states.get.return_value = State(entry, "disabled")
    
    # Setup: Entity is NOT disabled in registry
    mock_reg_entry = MagicMock()
    mock_reg_entry.disabled_by = None
    ctx.entity_registry.async_get.return_value = mock_reg_entry
    
    with (
        patch("custom_components.watchman.coordinator.is_action", return_value=False),
        patch("custom_components.watchman.coordinator._is_safe_to_report", return_value=True)
    ):
        
        # Action: Check entity status
        result = check_single_entity_status(hass, entry, data, ctx, "entity")
        
        # Assertion: Result should be None (entity is NOT missing)
        assert result is None, f"Expected None for active entity with 'disabled' state, got {result}"

def test_registry_disabled_entity_is_still_reported():
    """Test that an entity disabled in registry (and missing from state machine) is still reported."""
    hass = MagicMock()
    
    # Mock context
    ctx = MagicMock(spec=FilterContext)
    ctx.ignored_labels = set()
    ctx.ignored_states = []
    ctx.exclude_disabled = False
    ctx.automation_map = {}
    ctx.script_map = {}
    ctx.entity_registry = MagicMock()
    
    entry = "sensor.truly_disabled"
    data = {"locations": {"test.yaml": [20]}, "automations": [], "occurrences": [{"path": "test.yaml", "line": 20}]}
    
    # Setup: Entity is MISSING from state machine
    hass.states.get.return_value = None
    
    # Setup: Entity IS disabled in registry
    mock_reg_entry = MagicMock()
    mock_reg_entry.disabled_by = "user"
    ctx.entity_registry.async_get.return_value = mock_reg_entry
    
    with (
        patch("custom_components.watchman.coordinator.is_action", return_value=False),
        patch("custom_components.watchman.coordinator._is_safe_to_report", return_value=True)
    ):
        
        # Action: Check entity status
        result = check_single_entity_status(hass, entry, data, ctx, "entity")
        
        # Assertion: Result should NOT be None (entity should be reported)
        assert result == data["occurrences"], f"Expected occurrences for truly disabled entity, got {result}"

def test_ignored_states_configuration_is_respected():
    """Test that ignored_states configuration is respected for all problematic states."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    
    # Setup Entity Registry
    mock_registry = MagicMock()
    
    # Mock hass.states.get
    def get_state_side_effect(entity_id):
        if entity_id == "sensor.test_unavail":
            return State(entity_id, TRACKED_STATE_UNAVAILABLE)
        if entity_id == "sensor.test_unknown":
            return State(entity_id, TRACKED_STATE_UNKNOWN)
        # others are missing from state machine
        return None
    
    hass.states.get.side_effect = get_state_side_effect
    
    # Mock entity_registry.async_get
    def get_registry_side_effect(entity_id):
        if entity_id == "sensor.test_disabled":
            entry = MagicMock()
            entry.disabled_by = "user"
            entry.entity_id = entity_id
            return entry
        # Others are not in registry or not disabled
        if entity_id in ["sensor.test_unavail", "sensor.test_unknown"]:
            entry = MagicMock()
            entry.disabled_by = None
            entry.entity_id = entity_id
            return entry
        return None
    
    mock_registry.async_get.side_effect = get_registry_side_effect
    
    # Patch er.async_get used in utils
    with patch("custom_components.watchman.utils.utils.er.async_get", return_value=mock_registry):
        # Context setup: Ignore ALL these states
        ctx = MagicMock(spec=FilterContext)
        ctx.ignored_states = {
            TRACKED_STATE_UNAVAILABLE, 
            TRACKED_STATE_UNKNOWN, 
            TRACKED_STATE_MISSING, 
            TRACKED_STATE_REGISTRY_DISABLED
        }
        ctx.ignored_labels = set()
        ctx.exclude_disabled = False
        ctx.automation_map = {}
        ctx.script_map = {}
        ctx.entity_registry = mock_registry
        
        # Input data
        parsed_list = {
            "sensor.test_unavail": {"locations": {"t.yaml": [1]}, "automations": [], "occurrences": []},
            "sensor.test_unknown": {"locations": {"t.yaml": [2]}, "automations": [], "occurrences": []},
            "sensor.test_missing": {"locations": {"t.yaml": [3]}, "automations": [], "occurrences": []},
            "sensor.test_disabled": {"locations": {"t.yaml": [4]}, "automations": [], "occurrences": []},
        }
        
        # Action: Renew missing items list
        # We expect an EMPTY dict because all states are ignored
        missing_items = renew_missing_items_list(hass, parsed_list, ctx, item_type="entity")
        
        # Assertion
        assert missing_items == {}, f"Expected empty dict, got {missing_items}"
