#!/usr/bin/env python3
import argparse
import subprocess
import sys
import os
from pathlib import Path

def run_tests(ha_version, pytest_args):
    """Run tests for a specific HA version using uv."""
    if ha_version:
        print(f"--- Preparing environment for Home Assistant {ha_version} ---")
    else:
        print("--- Running tests using locked environment (uv.lock) ---")

    # 1. Base command
    cmd = ["uv", "run"]
    if not ha_version:
        cmd.append("--frozen")

    if ha_version:
        # 2. Version handling and prerelease flag
        if ha_version in ["latest", "rc", "dev"]:
            cmd.extend(["--with", "homeassistant"])
            if ha_version in ["rc", "dev"]:
                cmd.append("--prerelease=allow")
        else:
            cmd.extend(["--with", f"homeassistant=={ha_version}"])

        cmd.extend(["--with", "pytest-homeassistant-custom-component"])

    # 3. Determine and print actual HA version
    version_check_cmd = cmd + [
        "python", "-c",
        "import homeassistant.const as hc; print(f'\\n[+] Testing against Home Assistant Version: {hc.__version__}\\n')"
    ]

    try:
        # Run version check (this also primes the environment)
        subprocess.run(version_check_cmd, check=True)
    except subprocess.CalledProcessError:
        print("[-] Failed to determine Home Assistant version.")

    # 4. Run tests
    test_cmd = cmd + ["pytest"] + pytest_args
    print(f"Running: {' '.join(test_cmd)}")

    try:
        result = subprocess.run(test_cmd, check=True)
        return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Tests failed with exit code {e.returncode}")
        return e.returncode

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run tests against specific HA version")
    parser.add_argument("--version", default=None, help="HA version to test against (e.g. 2026.2.0)")

    # We use parse_known_args to allow passing flags directly to pytest without --
    args, pytest_args = parser.parse_known_args()

    sys.exit(run_tests(args.version, pytest_args))
