"""`health-mcp serve`, `sync`, and `normalize` entry points.

`sync` is what a scheduler runs (PLAN.md "Hevy sync"); `normalize` re-parses stored raw
payloads without touching the network, which is the point of splitting the two phases.
"""

import argparse
import sys

from health_mcp.db import migrate


def main() -> None:
    parser = argparse.ArgumentParser(prog="health-mcp")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("serve", help="Run the MCP server over stdio")
    sync = subparsers.add_parser("sync", help="Sync workouts from Hevy")
    sync.add_argument(
        "--full",
        action="store_true",
        help="Re-fetch every workout instead of the delta, and reconcile deletions",
    )
    subparsers.add_parser(
        "normalize", help="Re-parse stored raw workouts; no network access"
    )

    args = parser.parse_args()
    migrate()

    if args.command == "serve":
        from health_mcp.server import mcp

        mcp.run()
        return

    from health_mcp import hevy
    from health_mcp.db import rw

    conn = rw()
    try:
        if args.command == "sync":
            result = hevy.sync(conn, full=args.full)
            if not result["ok"]:
                print(f"sync failed: {result['error']}", file=sys.stderr)
                sys.exit(1)
            print(
                f"{result['workouts']} workouts ({result['deleted']} deleted), "
                f"{result['exercises']} exercises, {result['sets']} sets, "
                f"{result['templates']} templates, {result['measurements']} measurements"
            )
        else:
            result = hevy.normalize(conn)
            print(f"{result['exercises']} exercises, {result['sets']} sets")
    finally:
        conn.close()
