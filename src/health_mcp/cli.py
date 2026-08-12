"""`health-mcp serve` and `health-mcp sync` entry points."""

import argparse
import sys

from health_mcp.db import migrate


def main() -> None:
    parser = argparse.ArgumentParser(prog="health-mcp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="Run the MCP server over stdio")
    sync_parser = subparsers.add_parser("sync", help="Sync workouts from Hevy")
    sync_parser.add_argument(
        "--full", action="store_true",
        help="Full re-fetch instead of incremental (uses cursor)"
    )
    normalize_parser = subparsers.add_parser("normalize", help="Re-parse raw workouts")

    args = parser.parse_args()

    if args.command == "serve":
        migrate()
        from health_mcp.server import mcp

        mcp.run()
    elif args.command == "sync":
        migrate()
        from health_mcp.db import rw
        from health_mcp.tools.training import sync_workouts

        conn = rw()
        try:
            result = sync_workouts(conn, full=getattr(args, "full", False))
            if result.get("success"):
                print(f"Fetched: {result.get('fetched', 0)}, Updated: {result.get('updated', 0)}, "
                      f"Deleted: {result.get('deleted', 0)}")
            else:
                print(f"Error: {result.get('error')}", file=sys.stderr)
                sys.exit(1)
        finally:
            conn.close()
    elif args.command == "normalize":
        migrate()
        from health_mcp.db import rw
        from health_mcp.hevy import normalize_workouts

        conn = rw()
        try:
            result = normalize_workouts(conn)
            if result.get("success"):
                print(f"Normalized {result.get('exercises', 0)} exercises, {result.get('sets', 0)} sets")
            else:
                print(f"Error: {result.get('error')}", file=sys.stderr)
                sys.exit(1)
        finally:
            conn.close()
