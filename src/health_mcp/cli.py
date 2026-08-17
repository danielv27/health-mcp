"""`health-mcp serve`, `sync`, `normalize`, `strava-auth`, `sync-strava`, `import-steps`,
and `import-workouts` entry points.

`sync` is what a scheduler runs (PLAN.md "Hevy sync"); `normalize` re-parses stored raw
payloads without touching the network, which is the point of splitting the two phases.
`strava-auth` is the one-time interactive connection step (docs/adr/0008); `sync-strava`
is `sync`'s Strava counterpart (PLAN.md "Strava sync"). `import-steps` and
`import-workouts` have no network or cursor at all — manual Apple Health CSV exports
dropped in by hand (PLAN.md "Step import" / "Apple workout import"), always reprocessing
and upserting whatever the file(s) contain.
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
    subparsers.add_parser(
        "strava-auth", help="One-time interactive Strava connection (docs/adr/0008)"
    )
    sync_strava = subparsers.add_parser("sync-strava", help="Sync activities from Strava")
    sync_strava.add_argument(
        "--full",
        action="store_true",
        help="Re-fetch every activity instead of the delta, and reconcile deletions",
    )
    import_steps = subparsers.add_parser(
        "import-steps", help="Import an Apple Health step-count CSV export"
    )
    import_steps.add_argument("path", help="Path to the exported CSV file")
    import_workouts = subparsers.add_parser(
        "import-workouts",
        help="Import Apple Health workout CSV export(s); Hevy-sourced rows are dropped",
    )
    import_workouts.add_argument(
        "paths", nargs="+", help="Path(s) to the exported CSV file(s), one per workout type"
    )

    args = parser.parse_args()
    migrate()

    if args.command == "serve":
        from health_mcp.server import mcp

        mcp.run()
        return

    if args.command == "strava-auth":
        _strava_auth()
        return

    from health_mcp import apple_workouts, hevy, steps, strava
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
        elif args.command == "sync-strava":
            result = strava.sync(conn, full=args.full)
            if not result["ok"]:
                print(f"sync failed: {result['error']}", file=sys.stderr)
                sys.exit(1)
            print(f"{result['activities']} activities ({result['deleted']} deleted)")
        elif args.command == "import-steps":
            try:
                result = steps.import_csv(conn, args.path)
            except steps.StepsError as exc:
                print(f"import-steps failed: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"{result['rows_read']} rows -> {result['days']} days "
                  f"({result['from']} to {result['to']})")
        elif args.command == "import-workouts":
            try:
                result = apple_workouts.import_csv(conn, args.paths)
            except apple_workouts.AppleWorkoutError as exc:
                print(f"import-workouts failed: {exc}", file=sys.stderr)
                sys.exit(1)
            print(f"{result['rows_read']} rows -> {result['imported']} imported "
                  f"({result['skipped_hevy']} Hevy-sourced skipped), by type: "
                  f"{result['by_type']}")
        else:
            result = hevy.normalize(conn)
            print(f"{result['exercises']} exercises, {result['sets']} sets")
    finally:
        conn.close()


def _strava_auth() -> None:
    """Prints the authorize URL, prompts for the pasted-back redirect, exchanges the code,
    and stores the token pair. Never opens a port — see docs/adr/0008."""
    from health_mcp import strava

    try:
        url = strava.authorize_url()
    except strava.StravaError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print("Open this URL, approve access, then the browser will fail to load a page —")
    print("that's expected. Copy the URL it lands on (or just the `code` param) and")
    print("paste it back here.\n")
    print(url, "\n")
    pasted = input("Paste the redirect URL (or code): ").strip()

    try:
        code = strava.parse_code(pasted)
        tokens = strava.exchange_code(code)
        strava.store_auth(tokens["access_token"], tokens["refresh_token"], tokens["expires_at"])
    except strava.StravaError as exc:
        print(f"strava-auth failed: {exc}", file=sys.stderr)
        sys.exit(1)

    athlete = tokens.get("athlete") or {}
    name = " ".join(filter(None, [athlete.get("firstname"), athlete.get("lastname")])) or "athlete"
    print(f"\nConnected to Strava as {name}. Run `health-mcp sync-strava` to pull activities.")
