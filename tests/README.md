# Prerequisites

Install uv using instructions from their site: https://docs.astral.sh/uv/getting-started/installation/

## Run tests 
`uv run pytest tests`

## Run tests on a specific HA version
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
