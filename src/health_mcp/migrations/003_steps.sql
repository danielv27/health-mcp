-- Daily step counts, imported from Apple Health CSV exports. See PLAN.md "Step import"
-- and docs/adr/0010 for why this is a per-day max across sources, not a sum.

CREATE TABLE daily_steps (
    date   TEXT PRIMARY KEY,   -- 04:00 Amsterdam day rule, same as everywhere else
    steps  INTEGER NOT NULL,
    source TEXT                -- which HealthKit sourceName's daily total won the max
);

INSERT INTO schema_version (version) VALUES (3);
