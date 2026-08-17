-- Apple Health workout sessions (Watch-native, or another app writing to HealthKit),
-- imported by hand from CSV — see PLAN.md "Apple workout import" and docs/adr/0011.
--
-- Deliberately not `workouts` (Hevy) or `activities` (Strava): rows sourced from Hevy are
-- excluded at import time (already covered by `workouts`), and rows sourced from Strava
-- here are a stopgap for when the live Strava sync isn't connected — see ADR-0011.

CREATE TABLE apple_workouts (
    id           TEXT PRIMARY KEY,   -- synthetic: "<source>:<start_date truncated to the minute>"
    source       TEXT NOT NULL,      -- normalized: 'Apple Watch' | 'Strava'
    workout_type TEXT NOT NULL,      -- HealthKit's activityType, e.g. 'Running', 'Cycling'
    start_date   TEXT NOT NULL,
    end_date     TEXT NOT NULL,
    date         TEXT NOT NULL,      -- 04:00 Amsterdam day rule
    duration_s   REAL NOT NULL,
    energy_kcal  REAL,
    distance_m   REAL
);
CREATE INDEX apple_workouts_date ON apple_workouts(date);
CREATE INDEX apple_workouts_source ON apple_workouts(source);

INSERT INTO schema_version (version) VALUES (4);
