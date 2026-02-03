## Purpose
This is a command-line utility to run the Watchman parser independently of Home Assistant. I use it extensively to test the parsing algorithm on large sets of configuration files from public user repositories. It outputs all entities and services detected by the parser. Results are cached in a watchman.db file, which can be deleted to force a fresh parse.

## How to use
Install uv using instructions from the official website: https://docs.astral.sh/uv/getting-started/installation/

* Run `uv run parser.py --help` to view the help page
* Run `uv run parser.py test_config` to parse the `test_config` folder
