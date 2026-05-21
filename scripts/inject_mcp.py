#!/usr/bin/env python3
"""Injects the event-sourcing-knowledge-base MCP server into ~/.claude.json."""

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
PYTHON_PATH = PROJECT_DIR / ".venv" / "bin" / "python"
SERVER_PATH = PROJECT_DIR / "mcp_server.py"

DEFAULT_CONFIG = Path.home() / ".claude.json"


def main():
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_CONFIG

    if not PYTHON_PATH.exists():
        print(f"Error: Python not found at {PYTHON_PATH}", file=sys.stderr)
        print("Run: python -m venv .venv && .venv/bin/pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    if not SERVER_PATH.exists():
        print(f"Error: MCP server not found at {SERVER_PATH}", file=sys.stderr)
        sys.exit(1)

    # Load existing config or start fresh
    if config_path.exists():
        config = json.loads(config_path.read_text())
    else:
        config = {}

    # Inject MCP server entry
    config.setdefault("mcpServers", {})
    config["mcpServers"]["event-sourcing-knowledge-base"] = {
        "type": "stdio",
        "command": str(PYTHON_PATH),
        "args": [str(SERVER_PATH)],
        "env": {},
    }

    config_path.write_text(json.dumps(config, indent=2) + "\n")

    print(f"Injected MCP server into {config_path}")
    print(f"  Python:  {PYTHON_PATH}")
    print(f"  Server:  {SERVER_PATH}")


if __name__ == "__main__":
    main()
