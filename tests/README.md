# Getting Started

1. Install devcontainer cli
`npm install -g @devcontainers/cli`

2. Build and run dev devcontainer
`devcontainer build --workspace-folder .
devcontainer up --workspace-folder .`

3. Run tests
`devcontainer exec --workspace-folder . scripts/test`

4. To change target HA version, modify requirements.txt and run:
`devcontainer exec --workspace-folder . scripts/setup`

# Useful commands
Can be run with devcontainer exec.

Command | Description
------- | -----------
`pytest tests/` | This will run all tests in `tests/` and tell you how many passed/failed
`pytest --durations=10 --cov-report term-missing --cov=custom_components.watchman tests` | This tells `pytest` that your target module to test is `custom_components.integration_blueprint` so that it can give you a [code coverage](https://en.wikipedia.org/wiki/Code_coverage) summary, including % of code that was executed and the line numbers of missed executions.
`pytest tests/test_init.py -k test_setup_unload_and_reload_entry` | Runs the `test_setup_unload_and_reload_entry` test function located in `tests/test_init.py`
`pytest --capture=no --log-cli-level=DEBUG tests/` | Do not hide command line output and set log level to debug
