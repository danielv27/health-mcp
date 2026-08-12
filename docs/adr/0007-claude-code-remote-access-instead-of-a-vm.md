# Claude Code remote access instead of a dedicated VM

Supersedes the deployment half of [ADR-0005](./0005-stdio-over-ssh-instead-of-public-https.md)
— that ADR's transport decision (stdio, no HTTP, no TLS, no token) still stands. What
changes is how a phone reaches the server at all.

ADR-0005 assumed a small always-on VM, reached by SSHing in and running Claude Code in
tmux. That VM doesn't exist yet, and for a POC it doesn't need to: Claude Code's own
remote access (the Claude phone app connecting to a session running on this Mac) already
solves "reach an agent from my phone," which was the only reason a remote host was
wanted in the first place.

So instead: `health-mcp` is registered as a project-scoped MCP server in this repo's
`.mcp.json`. Any Claude Code session opened in this directory — including one reached
via phone through remote access — loads it automatically (with a one-time approval
prompt). No SSH keys, no inbound port, no VM to provision or patch.

## Considered Options

- **Small always-on VM, SSH + mosh + tmux** (original ADR-0005 plan) — rejected for now.
  Real infrastructure to provision and keep patched, for a POC that doesn't need it yet.
- **`.mcp.json` + Claude Code remote access on this Mac** — chosen. Zero new
  infrastructure; reuses a channel that already exists.

## Consequences

This Mac, not a VM, is now the always-on assumption. If it sleeps or is offline, remote
access to the server goes with it — worth checking power/sleep settings if phone access
needs to be reliable, whereas a small cloud VM would have made that a non-issue.

`cron` (PLAN.md's sync trigger) doesn't apply to a personal Mac the way it does to a
VM; a `launchd` job or just manually invoking `sync_workouts` once Hevy sync exists are
the options, revisit when `hevy.py` is built.

Nightly `sqlite3 .backup` still applies, and matters more here: a personal Mac has more
ways to lose a day (sleep, reboot, disk fill) than a VM built for one job.

If this later needs to work from claude.ai web/mobile without Claude Code, or from a
host other than this Mac, that's the HTTP-front-end-as-addition path ADR-0005 already
left open — still not needed today.
