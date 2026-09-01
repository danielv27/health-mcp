-- Daily macro targets for the logging UI's "today" snapshot (progress against a target,
-- not just raw totals). Single row, no history: targets are edited in place via the
-- settings view, not tracked as a series over time (see HANDOFF.md / PRODUCT.md
-- "Targets" — the simplest thing that satisfies the requirement).

CREATE TABLE targets (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    kcal         REAL NOT NULL,
    protein      REAL NOT NULL,
    carbs        REAL NOT NULL,
    fat          REAL NOT NULL,
    updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

INSERT INTO schema_version (version) VALUES (5);
