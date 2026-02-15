from unittest.mock import MagicMock, patch
from custom_components.watchman.coordinator import renew_missing_items_list, FilterContext
from homeassistant.core import HomeAssistant, State

def test_ignored_states_bug():
    """Test that ignored_states configuration is respected for missing/unavailable entities."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.services = MagicMock()
    hass.services.has_service.return_value = False
    
    # Setup Entity Registry
    mock_registry = MagicMock()
    
    # ... (rest of setup) ...
    
    # Mock hass.states.get
    def get_state_side_effect(entity_id):
        if entity_id == "sensor.test_unavail":
            return State(entity_id, "unavailable")
        if entity_id == "sensor.test_unknown":
            return State(entity_id, "unknown")
        # sensor.test_missing and sensor.test_disabled are not in state machine
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
        # Watchman maps 'unavailable' -> 'unavail' internally
        ctx.ignored_states = {"unavail", "unknown", "missing", "disabled"}
        ctx.ignored_labels = set()
        ctx.exclude_disabled = False # handled via ignored_states for this test
        ctx.automation_map = {}
        ctx.entity_registry = mock_registry
        
        # Input data: The parser found these 4 entities
        parsed_list = {
            "sensor.test_unavail": {"locations": [{"path": "t.yaml", "line": 1}], "automations": [], "occurrences": []},
            "sensor.test_unknown": {"locations": [{"path": "t.yaml", "line": 2}], "automations": [], "occurrences": []},
            "sensor.test_missing": {"locations": [{"path": "t.yaml", "line": 3}], "automations": [], "occurrences": []},
            "sensor.test_disabled": {"locations": [{"path": "t.yaml", "line": 4}], "automations": [], "occurrences": []},
        }
        
        # Action: Renew missing items list
        # We expect an EMPTY dict because all states are ignored
        missing_items = renew_missing_items_list(hass, parsed_list, ctx, item_type="entity")
        
        # Assertion
        assert missing_items == {}, f"Expected empty dict, got {missing_items}"
