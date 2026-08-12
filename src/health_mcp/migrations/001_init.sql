-- Initial schema. See PLAN.md "Storage" for the table-by-table rationale and
-- docs/adr/0001 (day rule), docs/adr/0002 (food_log stores macros, not references),
-- docs/adr/0006 (query is the only read surface).

CREATE TABLE schema_version (
    version    INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE products (
    id           INTEGER PRIMARY KEY,
    name         TEXT NOT NULL,
    brand        TEXT,
    source       TEXT NOT NULL CHECK (source IN ('verified', 'estimated')),
    kcal_100g    REAL NOT NULL,
    protein_100g REAL NOT NULL,
    carbs_100g   REAL NOT NULL,
    fat_100g     REAL NOT NULL,
    fibre_100g   REAL,
    sugar_100g   REAL,
    sat_fat_100g REAL,
    salt_100g    REAL,
    note         TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Absolute kcal/protein/carbs/fat are copied in at write time, not resolved through
-- product_id at read time — see docs/adr/0002. product_id is kept for traceability only.
CREATE TABLE food_log (
    id         INTEGER PRIMARY KEY,
    logged_at  TEXT NOT NULL,
    date       TEXT NOT NULL,
    product_id INTEGER REFERENCES products(id),
    name       TEXT NOT NULL,
    source     TEXT NOT NULL CHECK (source IN ('verified', 'estimated')),
    grams      REAL NOT NULL,
    entered_as TEXT,
    kcal       REAL NOT NULL,
    protein    REAL NOT NULL,
    carbs      REAL NOT NULL,
    fat        REAL NOT NULL,
    note       TEXT
);
CREATE INDEX food_log_date ON food_log(date);

-- id is Hevy's own workout id, kept as the primary key rather than surrogate so
-- /workouts/events deletions map directly onto a DELETE by id.
CREATE TABLE workouts (
    id         TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    date       TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    raw        TEXT NOT NULL
);
CREATE INDEX workouts_date ON workouts(date);
CREATE INDEX workouts_start_time ON workouts(start_time);

CREATE TABLE exercise_templates (
    id                      TEXT PRIMARY KEY,
    title                   TEXT NOT NULL,
    primary_muscle_group    TEXT,
    secondary_muscle_groups TEXT,
    equipment               TEXT
);

CREATE TABLE workout_exercises (
    id                   INTEGER PRIMARY KEY,
    workout_id           TEXT NOT NULL REFERENCES workouts(id),
    idx                  INTEGER NOT NULL,
    exercise_template_id TEXT REFERENCES exercise_templates(id),
    title                TEXT NOT NULL
);
CREATE INDEX workout_exercises_workout_id ON workout_exercises(workout_id);

CREATE TABLE workout_sets (
    id                  INTEGER PRIMARY KEY,
    workout_exercise_id INTEGER NOT NULL REFERENCES workout_exercises(id),
    idx                 INTEGER NOT NULL,
    type                TEXT NOT NULL,
    weight_kg           REAL,
    reps                INTEGER,
    rpe                 REAL,
    duration_s          INTEGER,
    distance_m          REAL
);
CREATE INDEX workout_sets_workout_exercise_id ON workout_sets(workout_exercise_id);

CREATE TABLE body_measurements (
    date        TEXT PRIMARY KEY,
    weight_kg   REAL,
    fat_percent REAL
);

-- last_status/last_error so a cron sync that has been failing for a week is one
-- `query` away from being visible, per PLAN.md "Storage".
CREATE TABLE sync_state (
    source      TEXT PRIMARY KEY,
    cursor      TEXT,
    last_run_at TEXT,
    last_status TEXT,
    last_error  TEXT
);

INSERT INTO schema_version (version) VALUES (1);
