"""Test obfuscation logic."""
import pytest
from custom_components.watchman.utils.utils import obfuscate_id

def test_obfuscate_single_short():
    """Test existing behavior for short strings."""
    # len("kitchen") = 7. <= 15.
    # Existing logic: 3 visible, rest masked.
    assert obfuscate_id("light.kitchen") == "light.kit****"
    
    # Check non-alnum preservation
    # len("kit_chen") = 8.
    # kit _ ****
    assert obfuscate_id("light.kit_chen") == "light.kit_****"

def test_obfuscate_single_long():
    """Test truncation for long strings (> 15 chars)."""
    # 16 chars: "1234567890123456"
    # Should truncate to 15 chars total in name part.
    # 3 visible + 11 stars + 1 tilde = 15.
    name = "1234567890123456"
    entity_id = f"sensor.{name}"
    expected_name = "123***********~"
    assert len(expected_name) == 15
    assert obfuscate_id(entity_id) == f"sensor.{expected_name}"

    # Verify edge case: 15 chars exactly.
    # Should NOT truncate.
    name15 = "123456789012345"
    entity_id15 = f"sensor.{name15}"
    # Existing logic: 123************ (15 chars)
    # No tilde.
    assert obfuscate_id(entity_id15) == "sensor.123************"
    assert len(obfuscate_id(entity_id15).split(".")[1]) == 15
    assert "~" not in obfuscate_id(entity_id15)

def test_obfuscate_list():
    """Test list handling."""
    inputs = ["light.kitchen", "sensor.1234567890123456"]
    expected = "light.kit****, sensor.123***********~"
    assert obfuscate_id(inputs) == expected

def test_obfuscate_tuple():
    """Test tuple handling."""
    inputs = ("light.kitchen", "light.living_room")
    # living_room is 11 chars. <= 15.
    # liv ********* (8 stars)
    # living_room -> liv (3) ing_room (8)
    # ing_room has _ -> ing_****
    # wait, existing logic loops over suffix.
    # suffix = ing_room
    # i(1) n(1) g(1) _(kept) r(1) o(1) o(1) m(1)
    # ***_****
    # liv***_****
    expected = "light.kit****, light.liv***_****"
    assert obfuscate_id(inputs) == expected

def test_obfuscate_invalid():
    """Test invalid input."""
    assert obfuscate_id(123) == 123
    assert obfuscate_id(None) is None