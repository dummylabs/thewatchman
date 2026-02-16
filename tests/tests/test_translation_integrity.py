"""Test translation file integrity."""
import json
import os
from pathlib import Path
import pytest

from custom_components.watchman.const import DOMAIN

TRANSLATION_DIR = Path(f"custom_components/{DOMAIN}/translations")

def get_keys(d, prefix=""):
    """Recursively extract all keys from a dictionary."""
    keys = set()
    for k, v in d.items():
        key_path = f"{prefix}.{k}" if prefix else k
        keys.add(key_path)
        if isinstance(v, dict):
            keys.update(get_keys(v, key_path))
    return keys

def test_translation_keys_match_en():
    """Test that all translation files have the same keys as en.json."""
    if not TRANSLATION_DIR.exists():
        pytest.fail(f"Translation directory not found: {TRANSLATION_DIR}")

    en_file = TRANSLATION_DIR / "en.json"
    if not en_file.exists():
        pytest.fail("en.json not found")

    with open(en_file, "r", encoding="utf-8") as f:
        en_data = json.load(f)
    
    en_keys = get_keys(en_data)
    
    files = list(TRANSLATION_DIR.glob("*.json"))
    failures = []

    for file_path in files:
        if file_path.name == "en.json":
            continue
            
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        keys = get_keys(data)
        
        missing = en_keys - keys
        extra = keys - en_keys
        
        if missing:
            failures.append(f"{file_path.name} missing keys: {missing}")
        if extra:
            failures.append(f"{file_path.name} has extra keys: {extra}")

    if failures:
        pytest.fail("\n".join(failures))
