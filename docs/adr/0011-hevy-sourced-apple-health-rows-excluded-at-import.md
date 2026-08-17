# Hevy-sourced Apple Health rows excluded at import

Hevy writes every strength workout it records into HealthKit, so an Apple Health export
of workout history carries the same strength sessions twice: once under `sourceName ==
'Hevy'`, and once already sitting in `workouts` via the direct Hevy API sync
([ADR-0003](./0003-own-the-data-rather-than-compose-external-mcp-servers.md)). Confirmed
on a real export (2026-08-14): 105 `TraditionalStrengthTraining` rows tagged `Hevy`,
against 104 rows already in `workouts` covering the same 2025-04-15–2026-08-12 range —
close enough (the one-row gap is a session that hadn't synced one way or the other yet)
to leave no doubt these are the same underlying training, not a second data source.

## Considered Options

- **Import everything, tag `source`** — rejected. Leaves a table that structurally *can*
  double-count the exact thing this project exists to answer accurately ("did intake
  track with volume") unless every future query remembers to filter Hevy out. A mistake
  here isn't cosmetic — it inflates real training-volume numbers.
- **Drop Hevy-sourced rows at import time** — chosen. `apple_workouts` becomes a table
  that cannot contain Hevy's strength data, not one that merely shouldn't. The import
  result reports `skipped_hevy` so the exclusion is visible, not silent.

## Consequences

`apple_workouts` ends up holding two kinds of rows: genuine Apple Watch-native sessions
(cardio and the handful of pre-Hevy strength workouts from early 2025) that exist nowhere
else, and Strava-sourced sessions that are a stopgap for not having the live Strava sync
connected yet ([PLAN.md "Status"](../../PLAN.md)). The Strava-sourced rows are a known,
accepted future duplication risk: once Strava is connected, the same runs will also
arrive via `activities` with richer data (speed, heart rate, Strava's own id) and no
natural key ties an `apple_workouts` row to its `activities` counterpart. Reconciling that
is deferred until Strava is actually connected — solving it now would be guessing at a
shape for data this database doesn't have yet.

A second, smaller wrinkle worth naming rather than silently absorbing: Strava has been
observed writing the same physical run to HealthKit twice, a few hundred milliseconds
apart, with slightly different final distance/duration (GPS recalculation). The importer
doesn't try to detect or merge near-duplicates like this — each HealthKit row gets its own
synthetic id (`source:start_date`), so a genuine near-duplicate pair imports as two rows.
Worth a manual `DELETE` if it shows up in a query, not worth a fuzzy-matching heuristic for
one observed occurrence.
