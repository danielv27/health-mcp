# One read-only SQL tool instead of narrow read tools

All reads go through a single `query(sql)` tool backed by a connection opened read-only,
with the schema embedded in the tool description. There are no `list_workouts`,
`get_workout`, `daily_nutrition`, or `exercise_history` tools.

The questions worth asking of this data are not knowable in advance — that unpredictability
is the reason for building it rather than using a tracking app. A fixed set of read tools
answers only the questions imagined on day one, and grows a new tool every time a new one
comes up. SQL answers all of them, and agents write SQL well.

## Considered Options

- **Narrow read tools per question** — rejected. Endless additions, and each one spends
  context budget in every session whether or not it's used.
- **One `query(sql)` tool** — chosen.

## Consequences

The schema becomes an interface. Renaming a column breaks queries the model would
otherwise write correctly, so migrations need the same care as a public API.

Read-only is enforced twice, deliberately: the connection is opened via a
`file:...?mode=ro` URI, *and* submitted SQL is rejected unless it is a single `SELECT` or
`WITH` statement. The first is the real defence; the second turns a confused write attempt
into a clear error instead of a silent failure. Writes stay in narrow, explicit tools
where they can be validated — logging 200 g against the wrong row is a data-corruption
bug with no error message, and that path must never be improvised.
