# Own the data rather than compose external MCP servers

At least seven community Hevy MCP servers exist, and several Open Food Facts ones — any
of them could be wired up with `npx` in a minute instead of writing a Hevy client. We
write our own sync into local SQLite anyway, because **every one of those servers is a
stateless read-only proxy**: none persists anything between calls.

The entire point of this project is the *join* — training volume beside protein intake,
in one answer — and a join needs both sides in one place. Composing external servers
would turn a single SQL query into "fetch from one server, fetch from another, join in
the model's head", re-hitting the upstream APIs on every question. It would also spend
22 tool descriptions of context budget (the count in the most mature Hevy server) on a
surface we don't control.

## Consequences

We maintain a small Hevy client and its sync cursor ourselves. In exchange, history
survives upstream outages, and cross-source questions cost one query against one file.
External servers remain the right answer for *lookups*; they are the wrong answer for
*history*.
