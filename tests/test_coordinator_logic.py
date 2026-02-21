from unittest.mock import MagicMock, patch
from custom_components.watchman.coordinator import check_single_entity_status, FilterContext
from homeassistant.core import HomeAssistant

def test_check_single_entity_status_false_positive_action():
    """Test that an entity incorrectly identified as an action is ignored if it exists as an entity."""
    hass = MagicMock()
    
    # Mock context
    ctx = MagicMock(spec=FilterContext)
    ctx.ignored_labels = set()
    ctx.ignored_states = []
    ctx.exclude_disabled = False
    ctx.automation_map = {}
    ctx.script_map = {}
    ctx.entity_registry = MagicMock()
    
    entry = "light.living_room"
    data = {"locations": {}, "automations": [], "occurrences": []}
    
    # Simulate parser returning it as 'action' (service)
    # And it is 'missing' as an action (because it's actually an entity)
    
    # We need to patch is_action to return False (it's not a service)
    # And mock hass.states.get to return a valid state (it IS an entity)
    
    with patch("custom_components.watchman.coordinator.is_action", return_value=False):
        # Mock entity existence
        hass.states.get.return_value = MagicMock() # Entity exists
        
        # Test: item_type="action"
        # It is missing as action (is_action=False)
        # But it exists as entity (hass.states.get returns object)
        # So it should be ignored (return None)
        
        # This logic is missing, so this should return data["occurrences"] (empty list) instead of None
        result = check_single_entity_status(hass, entry, data, ctx, "action")
        
        # After fix, result should be None
        assert result is None

def test_check_single_entity_status_false_positive_entity():
    """Test that an action incorrectly identified as an entity is ignored if it exists as an action."""
    hass = MagicMock()
    
    # Mock context
    ctx = MagicMock(spec=FilterContext)
    ctx.ignored_labels = set()
    ctx.ignored_states = []
    ctx.exclude_disabled = False
    ctx.automation_map = {}
    ctx.script_map = {}
    ctx.entity_registry = MagicMock()
    
    entry = "script.turn_on"
    data = {"locations": {}, "automations": [], "occurrences": []}
    
    # Simulate parser returning it as 'entity'
    # And it is 'missing' as an entity
    
    hass.states.get.return_value = None # Missing as entity
    
    with patch("custom_components.watchman.coordinator.is_action", return_value=True):
        # It IS a valid action
        
        # This logic IS already present, so this should pass
        result = check_single_entity_status(hass, entry, data, ctx, "entity")
        
        assert result is None

def test_cross_validation_with_service_template():
    """Test defense in depth: valid service misidentified as entity is ignored."""
    hass = MagicMock()
    
    # Mock context
    ctx = MagicMock(spec=FilterContext)
    ctx.ignored_labels = set()
    ctx.ignored_states = []
    ctx.exclude_disabled = False
    ctx.automation_map = {}
    ctx.script_map = {}
    ctx.entity_registry = MagicMock()
    
    entry = "light.turn_on"
    data = {"locations": {}, "automations": [], "occurrences": []}
    
    # Simulate parser returning it as 'entity' (because it was in a template)
    # But it does NOT exist as a state (it's a service)
    hass.states.get.return_value = None 
    
    # However, it IS a valid action
    with patch("custom_components.watchman.coordinator.is_action", return_value=True):
        
        # Should be ignored (return None) because it exists as an action
        result = check_single_entity_status(hass, entry, data, ctx, "entity")
        
        assert result is None
