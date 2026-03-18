#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/Library/Application Support/Claude"
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

mkdir -p "$CONFIG_DIR"

python3 - <<EOF
import json, os, sys

config_file = """$CONFIG_FILE"""
server_path = """$SCRIPT_DIR/server.py"""

config = {}
if os.path.exists(config_file):
    try:
        with open(config_file) as f:
            config = json.load(f)
    except json.JSONDecodeError:
        print(f"Error: {config_file} exists but contains invalid JSON.", file=sys.stderr)
        sys.exit(1)

config.setdefault("mcpServers", {})
project_dir = os.path.dirname(server_path)
config["mcpServers"]["chess-stockfish"] = {
    "command": "uv",
    "args": ["run", "--project", project_dir, server_path]
}

with open(config_file, "w") as f:
    json.dump(config, f, indent=2)

print(f"Added chess-stockfish to {config_file}")
print("Restart Claude Desktop to apply changes.")
EOF
