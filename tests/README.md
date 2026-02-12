# Prerequisites

Install uv using instructions from their site: https://docs.astral.sh/uv/getting-started/installation/

## Run tests 
`uv run pytest tests`

## Run tests on a specific HA version
You can use the helper script to run tests against any specific Home Assistant version. This will automatically set up an isolated environment with the correct dependencies.

```bash
# Run against the default version (2025.4.4)
./scripts/test_ha.py

# Run against a specific version
./scripts/test_ha.py 2026.1.1

# Run specific tests with extra arguments
./scripts/test_ha.py 2026.1.1 tests/tests/test_init.py -vv
```

Alternatively, using raw `uv` command:
`uv run --with homeassistant==2026.1.0 pytest`


# Useful commands

Command | Description
------- | -----------
`uv cache prune` | clear uv cache from unused package versions
`uv run pytest tests` | This will run all tests in `tests/` and tell you how many passed/failed
`uv run pytest --durations=10 --cov-report term-missing --cov=custom_components.watchman tests` | This tells `pytest` that your target module to test is `custom_components.integration_blueprint` so that it can give you a [code coverage](https://en.wikipedia.org/wiki/Code_coverage) summary, including % of code that was executed and the line numbers of missed executions.
`uv run pytest tests/test_init.py -k test_setup_unload_and_reload_entry` | Runs the `test_setup_unload_and_reload_entry` test function located in `tests/test_init.py`
`uv run pytest --capture=no --log-cli-level=DEBUG tests/` | Do not hide command line output and set log level to debug
`uv run pytest --log-file=pytest1.log --log-file-level=DEBUG tests/tests/test_exclude_disabled.py` | save debug logs in pytest1.log
