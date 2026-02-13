# Testing Guide

## 🚀 Running Tests Locally (Recommended)
To ensure snapshot consistency with Linux CI, run tests using the Docker wrapper. This works on macOS, Windows, and Linux.

```bash
# Run against default HA version
./scripts/test_local

# Run against specific version
./scripts/test_local 2026.2.0

# Update snapshots
./scripts/test_local -- --snapshot-update
```

This command automatically:
1. Builds the test Docker image from `.devcontainer/Dockerfile`.
2. Runs the tests inside an isolated Linux container.

## 🐳 DevContainer Workflow
If you open the project in VS Code DevContainer, you are already inside the Linux environment. You can use the direct runner:

```bash
./scripts/test_ha.py
```

## ⚙️ CI / Advanced
The `scripts/test_ha.py` script is the low-level test runner. It assumes the current environment (local or container) is correctly set up with `uv`.

- **CI:** Uses `scripts/test_ha.py` directly inside the GitHub Actions runner.
- **Local (Advanced):** Use `scripts/test_ha.py` only if you are on Linux or debugging non-snapshot tests.

# Useful commands

Command | Description
------- | -----------
`./scripts/test_local` | **Standard way to run tests**
`./scripts/test_local -- --durations=10` | Show slowest 10 tests
`./scripts/test_local -- tests/tests/test_init.py` | Run specific test file
