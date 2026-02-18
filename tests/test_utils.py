"""Tests for utils functions."""
from custom_components.watchman.utils.utils import format_column_text, format_occurrences

def test_format_column_text_string():
    """Test formatting a simple string value."""
    data = "some_value"
    assert format_column_text(data, 0) == "some_value"

def test_format_column_text_string_with_extra():
    """Test formatting a string value with extra info."""
    data = "entity_id"
    extra = "Friendly Name"
    assert format_column_text(data, 0, extra) == "entity_id ('Friendly Name')"

def test_format_column_text_wrapping():
    """Test line wrapping behavior."""
    data = "very_long_line_that_should_be_wrapped_because_it_exceeds_width"
    width = 10
    # wrap function behavior: split into list of lines of max width
    # fill/format_column_text joins them with newline and ljust(width)
    result = format_column_text(data, width)
    lines = result.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) >= width

def test_format_occurrences_ui_helpers():
    """Test formatting of UI helpers in occurrences."""
    occurrences = [
        {
            "path": "ui",
            "line": 0,
            "context": {"parent_type": "helper_group", "parent_alias": "My Group"}
        },
        {
            "path": "ui",
            "line": 0,
            "context": {"parent_type": "helper_template", "parent_alias": "My Template"}
        }
    ]
    result = format_occurrences(occurrences, 0)
    assert '👥 Group: "My Group"' in result
    assert '🧩 Template: "My Template"' in result

def test_format_occurrences_files():
    """Test formatting of standard files in occurrences."""
    occurrences = [
        {"path": "/config/automations.yaml", "line": 10},
        {"path": "/config/automations.yaml", "line": 20},
        {"path": "/config/scripts.yaml", "line": 5},
    ]
    result = format_occurrences(occurrences, 0)
    assert "📄 /config/automations.yaml:10,20" in result
    assert "📄 /config/scripts.yaml:5" in result

def test_format_occurrences_wrapping():
    """Test wrapping and padding in format_occurrences."""
    occurrences = [
        {"path": "/config/very_long_path_to_a_file_that_should_be_wrapped.yaml", "line": 100},
    ]
    width = 30
    result = format_occurrences(occurrences, width)
    lines = result.split("\n")
    assert len(lines) > 1
    for line in lines:
        assert len(line) == width
