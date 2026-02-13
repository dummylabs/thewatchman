import yaml
import pytest
import os
from custom_components.watchman.utils.parser_core import _scan_string_for_entities, _ENTITY_PATTERN, ParserContext

def load_test_data():
    """Load test cases from YAML file."""
    current_dir = os.path.dirname(os.path.realpath(__file__))
    data_file = os.path.join(current_dir, "..", "data", "test_parser_template_prefix.yaml")
    
    with open(data_file, 'r') as stream:
        return yaml.safe_load(stream)

@pytest.mark.parametrize("test_case", load_test_data())
def test_template_prefix_heuristics(test_case):
    """Verify that parser ignores entities followed by template markers."""
    input_str = test_case["input"]
    expected = test_case["expected"]
    description = test_case["name"]
    
    results = []
    ctx = ParserContext()
    _scan_string_for_entities(
        content=input_str,
        results=results,
        line_no=1,
        key_name=None,
        context=ctx,
        entity_pattern=_ENTITY_PATTERN
    )
    
    matches = [r["entity_id"] for r in results]
    assert matches == expected, f"Failed case: {description}. Input: '{input_str}'"
