import yaml
import pytest
import re
import os
from custom_components.watchman.utils.parser_core import _ENTITY_PATTERN

def load_test_data():
    """Load test cases from YAML file."""
    # Use relative path from this test file to the data file
    # This test file is in tests/tests/, data is in tests/data/
    current_dir = os.path.dirname(os.path.realpath(__file__))
    data_file = os.path.join(current_dir, "..", "..", "tests", "data", "test_regex_edge_cases.yaml")
    
    with open(data_file, 'r') as stream:
        return yaml.safe_load(stream)

@pytest.mark.parametrize("test_case", load_test_data())
def test_entity_regex_boundaries(test_case):
    """Verify that regex correctly handles boundaries defined in YAML."""
    input_str = test_case["input"]
    expected = test_case["expected"]
    description = test_case["name"]
    
    # Extract matches using the actual pattern from codebase
    # Note: Logic must match parser_core.py extraction (group 1)
    matches = [m.group(1) for m in _ENTITY_PATTERN.finditer(input_str)]
    
    # Sort matches to ensure order independence in list comparison if needed, 
    # but for these simple cases exact list match is expected as order is preserved by finditer.
    # If duplicates are possible in input, finditer returns all.
    # The expected data assumes finditer order.
    
    assert matches == expected, f"Failed case: {description}. Input: '{input_str}'"
