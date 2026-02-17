"""Tests for utils functions."""
from custom_components.watchman.utils.utils import format_locations

def test_format_locations_dict():
    """Test formatting a dictionary of file locations."""
    data = {
        "/config/file1.yaml": [10, 15],
        "/config/file2.yaml": [20],
    }
    expected = "/config/file1.yaml:10,15\n/config/file2.yaml:20"
    assert format_locations(data, 0) == expected

def test_format_locations_string():
    """Test formatting a simple string value."""
    data = "some_value"
    assert format_locations(data, 0) == "some_value"

def test_format_locations_string_with_extra():
    """Test formatting a string value with extra info."""
    data = "entity_id"
    extra = "Friendly Name"
    assert format_locations(data, 0, extra) == "entity_id ('Friendly Name')"

def test_format_locations_wrapping():
    """Test line wrapping behavior."""
    data = "very_long_line_that_should_be_wrapped_because_it_exceeds_width"
    width = 10
    # wrap function behavior: split into list of lines of max width
    # fill/format_locations joins them with newline and ljust(width)
    result = format_locations(data, width)
    lines = result.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) >= width
