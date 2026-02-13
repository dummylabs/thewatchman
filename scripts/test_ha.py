#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
from pathlib import Path

def get_ha_constraints(version):
    """Return the URL for HA constraints for a given version."""
    if version in ["latest", "rc", "dev"]:
        branch = "master" if version == "dev" else "rc" if version == "rc" else "master"
        return f"https://raw.githubusercontent.com/home-assistant/core/{branch}/homeassistant/package_constraints.txt"
    return f"https://raw.githubusercontent.com/home-assistant/core/{version}/homeassistant/package_constraints.txt"

def run_tests(ha_version, pytest_args):
    """Run tests for a specific HA version using uv."""
    print(f"--- Preparing environment for Home Assistant {ha_version} ---")
    
    # We use uv run with dynamic dependencies
    # --with homeassistant==version
    
    cmd = [
        "uv", "run",
        "--upgrade",
        "--with", f"homeassistant=={ha_version}" if ha_version not in ["latest", "rc", "dev"] else "homeassistant",
        "--with", "pytest-homeassistant-custom-component",
    ]
    
    cmd += ["pytest"] + pytest_args
    
    print(f"Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Tests failed with exit code {e.returncode}")
        return e.returncode

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tests against specific HA version")
    parser.add_argument("version", nargs="?", default="2025.4.4", help="HA version to test against (e.g. 2024.12.0)")
    
    # We use parse_known_args to allow passing flags directly to pytest without --
    args, pytest_args = parser.parse_known_args()
    
    sys.exit(run_tests(args.version, pytest_args))
