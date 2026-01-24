import os
import pytest
import sqlite3
from custom_components.watchman.utils.parser_core import WatchmanParser

# Path to the test data directory created in previous steps
TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), "new_parser")

def test_file_extensions(tmp_path):
    """
    Test file extension handling:
    - txt, binary, json (with extension) should be ignored (not in DB) due to strict extension filter.
    - yaml should be processed (in DB, type yaml).
    - extensionless file (with json content) should be processed (in DB, type json).
    - No entities should be found in any of them.
    """
    # Create a temporary database path
    db_path = str(tmp_path / "watchman.db")

    # Initialize the client
    client = WatchmanParser(db_path)

    # Ensure test data exists
    assert os.path.exists(TEST_DATA_DIR)
    assert os.path.exists(os.path.join(TEST_DATA_DIR, "dummy.txt"))
    assert os.path.exists(os.path.join(TEST_DATA_DIR, "simple.yaml"))
    assert os.path.exists(os.path.join(TEST_DATA_DIR, "extensionless_json"))

    # Run scan on the test data directory
    client.scan([TEST_DATA_DIR], [], force=True)

    # Verify results directly in DB
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch processed files
    cursor.execute("SELECT path, file_type, entity_count FROM processed_files")
    files = cursor.fetchall()

    # Map filename to file_type/count for easier assertion
    file_map = {os.path.basename(path): (file_type, count) for path, file_type, count in files}

    print(f"DEBUG: Scanned files: {file_map}")

    # 1. Ignored files (should NOT be in DB)
    assert "dummy.txt" not in file_map
    assert "pixel.png" not in file_map
    assert "data.json" not in file_map # .json extension is ignored by _get_files

    # 2. simple.yaml (Should be in DB)
    assert "simple.yaml" in file_map
    ftype, count = file_map["simple.yaml"]
    assert ftype == "yaml", f"simple.yaml type mismatch. Got {ftype}"
    assert count == 0

    # 3. extensionless_json (Should be in DB)
    # _get_files accepts empty extension.
    # _detect_file_type detects json content.
    assert "extensionless_json" in file_map
    ftype, count = file_map["extensionless_json"]
    assert ftype == "json", f"extensionless_json type mismatch. Got {ftype}"
    assert count == 0

    # Verify total found items is 0
    cursor.execute("SELECT COUNT(*) FROM found_items")
    total_items = cursor.fetchone()[0]
    assert total_items == 0

    conn.close()
