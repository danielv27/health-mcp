-- Single-row app settings, same pattern as 005_targets.sql. Currently just the
-- Hevy background-sync toggle surfaced in the web UI.
CREATE TABLE settings (
    id                 INTEGER PRIMARY KEY CHECK (id = 1),
    hevy_auto_sync     INTEGER NOT NULL DEFAULT 0 CHECK (hevy_auto_sync IN (0, 1))
);
INSERT INTO settings (id, hevy_auto_sync) VALUES (1, 0);

INSERT INTO schema_version (version) VALUES (7);
