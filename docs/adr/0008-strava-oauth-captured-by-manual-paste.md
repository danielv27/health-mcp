# Strava OAuth captured by manual paste, not a local listener

Connecting Strava is a one-time, interactive step: open an authorize URL, approve access
in the browser, and Strava redirects back with a `code` query param the app needs. The
usual way to catch that is a local HTTP server bound to the app's `redirect_uri`.

This project doesn't have one, and [ADR-0005](./0005-stdio-over-ssh-instead-of-public-https.md)
chose that deliberately — no HTTP transport, no port, no TLS, nothing to secure. Standing
one up just for a setup step, even briefly, even closed immediately after, reopens exactly
the question 0005 closed.

`redirect_uri` is instead set to `http://localhost/exchange_token` — a URL nothing on this
Mac answers. The browser's redirect fails to load, but the `code` is sitting right there in
the address bar regardless of whether anything caught it. `health-mcp strava-auth` prints
the authorize URL, and the person running it copies that failed-to-load URL (or just the
`code` param) back into the terminal.

## Considered Options

- **Temporary local HTTP server**, opened only for the duration of `strava-auth` and
  closed right after — rejected. Smoother (no copy-paste), but it's a port opened on
  principle in a project whose whole premise is that there isn't one.
- **Manual paste from the failed redirect** — chosen. Documented by Strava itself as the
  supported flow for a personal-use, non-server app. Extra step for the person running it,
  once, ever — no listener, ever.

## Consequences

`strava-auth` is interactive and can't be scripted end-to-end — it needs a human in the
browser and a human at the terminal. That's fine: it runs once, the resulting refresh token
is what every unattended `sync-strava` afterward actually uses.
