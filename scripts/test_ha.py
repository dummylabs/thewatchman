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
    
    constraints_url = get_ha_constraints(ha_version)
    
    # We use uv run with dynamic dependencies
    # --with homeassistant==version
    # --with-requirements constraints_url
    
    cmd = [
        "uv", "run",
        "--upgrade",
        "--with", f"homeassistant=={ha_version}" if ha_version not in ["latest", "rc", "dev"] else "homeassistant",
        "--with", "pytest-homeassistant-custom-component",
    ]
    
    # Add other dev dependencies from pyproject.toml to ensure they are present
    # but since we are running in a project, uv run should pick them up from the dev group
    # if we don't use --no-project.
    
    # If we want to be absolutely sure about constraints:
    # cmd += ["--with-requirements", constraints_url]
    # Note: some older versions might not have package_constraints.txt or it might be named differently
    
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
    parser.add_argument("pytest_args", nargs="*", help="Arguments to pass to pytest")
    
    args = parser.parse_args()
    
    sys.exit(run_tests(args.version, args.pytest_args))
