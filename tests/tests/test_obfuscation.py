"""Test obfuscation logic."""
from custom_components.watchman.utils.utils import obfuscate_id

def test_obfuscate_id():
    """Test various obfuscation cases."""
    
    # Test case from user
    assert obfuscate_id("sensor.z2m_btn_0a36_action") == "sensor.z2m_***_****_******"
    
    # Simple case
    assert obfuscate_id("light.living_room") == "light.liv***_****"
    
    # Short name (<=3 chars)
    assert obfuscate_id("sensor.abc") == "sensor.abc"
    assert obfuscate_id("sensor.ab") == "sensor.ab"
    
    # No domain
    assert obfuscate_id("invalid") == "invalid"
    
    # Non-string input
    assert obfuscate_id(None) is None
    assert obfuscate_id(123) == 123
    
    # Special characters
    assert obfuscate_id("domain.abc-def") == "domain.abc-***"
    
    # Dots in name (only first split is domain)
    assert obfuscate_id("sensor.name.with.dots") == "sensor.nam*.****.****"
