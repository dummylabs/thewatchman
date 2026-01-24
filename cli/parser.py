import sys
import argparse
import logging
import os

CONF_IGNORED_FILES: "*/blueprints/*, */custom_components/*, */esphome/*"

# Add project root to sys.path to allow importing custom_components
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import shared core library
try:
    from custom_components.watchman.utils.parser_core import WatchmanParser
except ImportError:
    # Fallback or error handling if running in isolation without project structure
    print("Error: Could not import WatchmanParser from custom_components.watchman.utils.parser_core", file=sys.stderr)
    sys.exit(1)

def print_header(text):
    """Print a stylized header for CLI output."""
    print(f"\n\033[1;36m{text.upper()}\033[0m")
    print("\033[1;36m" + "=" * 80 + "\033[0m")

def print_table(headers, data, max_width=None):
    if not data:
        print("No data found.")
        return

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in data:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(str(val)))

    # Cap width if needed
    if max_width:
        widths = [min(w, max_width) for w in widths]

    # Create format string
    fmt = "  ".join([f"{{:<{w}}}" for w in widths])

    # Print headers
    print(fmt.format(*headers))
    print("-" * (sum(widths) + 2 * (len(widths) - 1)))

    # Print data
    for row in data:
        formatted_row = []
        for i, val in enumerate(row):
            s_val = str(val)
            if len(s_val) > widths[i]:
                header = headers[i].lower()
                if header in ["file", "path"]:
                    s_val = "..." + s_val[-(widths[i]-3):]
                else:
                    s_val = s_val[:widths[i]-3] + "..."
            formatted_row.append(s_val)
        print(fmt.format(*formatted_row))

def main():
    parser = argparse.ArgumentParser(description="Watchman Prototype Parser (CLI)")
    # list of paths divided by space
    parser.add_argument("included_folders", nargs='+', help="List of folders/files to include (glob supported)")
    # -ignore "*.log" --ignore "*.tmp"
    parser.add_argument("--ignore", action='append', help="Glob patterns to ignore")
    parser.add_argument("--force", action='store_true', help="Force rescan of all files")
    parser.add_argument("--db-path", default="watchman.db", help="Path to SQLite database")
    parser.add_argument("--no-files", action='store_true', help="Hide the list of processed files")
    parser.add_argument("--no-items", action='store_true', help="Hide the list of found items")

    if len(sys.argv) == 1:
        parser.print_help(sys.stderr)
        sys.exit(1)

    args = parser.parse_args()

    included_folders = args.included_folders
    ignored_files = args.ignore or []

    # Configure logging for CLI to show up in stderr (WatchmanParser uses 'parser_core' logger)
    logging.basicConfig(stream=sys.stderr, level=logging.ERROR)

    client = WatchmanParser(args.db_path)

    # We call scan directly. Logic for configuration change detection is inside WatchmanParser.scan
    client.scan(included_folders, ignored_files, args.force)

    # Output results matching original format
    if not args.no_files:
        print_header("Processed Files")
        rows = client.get_processed_files()
        # rows: [(file_id, path, file_type, entity_count, scan_date), ...]
        # table expects: ["ID", "Path", "Type", "Count", "Scan Date"]
        print_table(["ID", "Path", "Type", "Count", "Scan Date"], rows, max_width=60)

    # Fetch all items to compute summary and display table
    all_items = client.get_found_items('all')

    if not args.no_items:
        print_header("Found Items")
        data = []
        for r in all_items:
            # r: (entity_id, path, line, item_type, p_type, p_alias, p_id)
            entity_id, path, line, item_type, p_type, p_alias, p_id = r

            context = ""
            if p_type:
                context = f"{p_type}: {p_id or p_alias or '?'}"

            data.append((path, line, item_type, entity_id, context))

        print_table(["File", "Line", "Type", "Entity/Service", "Context"], data, max_width=60)

    print_header("Summary")
    unique_entities = len(set(i[0] for i in all_items if i[3] == 'entity'))
    unique_services = len(set(i[0] for i in all_items if i[3] == 'service'))

    print(f"Unique Entities Found: {unique_entities}")
    print(f"Unique Services Found: {unique_services}")

if __name__ == "__main__":
    main()
