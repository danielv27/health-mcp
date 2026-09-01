-- Meals: food is never logged standalone in practice — it's logged as part of a
-- meal (see /impeccable critique, 2026-08-31, P1 "no concept of a meal anywhere").
-- A meal groups one or more food_log entries created together in a single commit
-- (see tools/meals.py log_meal); meal_type is inferred from time of day at the
-- moment of logging but is editable in the UI before commit.
--
-- food_log.meal_id is nullable: existing rows predate this migration and stay
-- ungrouped ("Other" in the UI) rather than being backfilled with a guessed meal.

CREATE TABLE meals (
    id        INTEGER PRIMARY KEY,
    date      TEXT NOT NULL,   -- 04:00 Amsterdam day rule, same as food_log.date
    meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    logged_at TEXT NOT NULL
);
CREATE INDEX meals_date ON meals(date);

ALTER TABLE food_log ADD COLUMN meal_id INTEGER REFERENCES meals(id);
CREATE INDEX food_log_meal_id ON food_log(meal_id);

INSERT INTO schema_version (version) VALUES (6);
