-- Strava activities (cardio: runs, rides). See PLAN.md "Strava sync" and
-- docs/adr/0009 for why the OAuth tokens themselves are *not* in this file.

-- id is Strava's own activity id, kept as the primary key for the same reason
-- workouts.id is Hevy's: a --full resync's deletion reconciliation maps directly
-- onto a DELETE by id.
CREATE TABLE activities (
    id                     TEXT PRIMARY KEY,
    name                   TEXT NOT NULL,
    type                   TEXT NOT NULL,
    sport_type             TEXT NOT NULL,
    start_date             TEXT NOT NULL,
    date                   TEXT NOT NULL,
    elapsed_time_s         INTEGER NOT NULL,
    moving_time_s          INTEGER NOT NULL,
    distance_m             REAL NOT NULL,
    total_elevation_gain_m REAL,
    average_speed_mps      REAL,
    max_speed_mps          REAL,
    average_heartrate      REAL,
    max_heartrate          REAL,
    raw                    TEXT NOT NULL
);
CREATE INDEX activities_date ON activities(date);
CREATE INDEX activities_start_date ON activities(start_date);

INSERT INTO schema_version (version) VALUES (2);
