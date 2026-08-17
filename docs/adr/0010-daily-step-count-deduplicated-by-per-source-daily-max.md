# Daily step count deduplicated by per-source daily max

An Apple Health export carries one row per raw HealthKit sample, tagged with which
source recorded it — a phone, a watch, sometimes both across the same stretch of time,
each independently counting the same walking. Measured on a real 9-year, 180,601-row
export (2026-08-14): 820 of 3,402 days had samples from more than one source, and naively
summing every row overcounted the whole history by **19%** (31.1M vs 26.0M steps).

The two sources don't agree in any simple way either — on some days the phone reports
more, on others the watch does, by no consistent ratio (a watch off the wrist for part of
the day, a phone left in a bag for another part). There's no clean signal in this data for
"which source is right today."

## Considered Options

- **Sum every row** — rejected. The default a naive importer would reach for, and
  measurably wrong by a fifth of the total.
- **Interval-level dedup** (reconcile overlapping start/end ranges across sources, the
  way Apple's own Health app approximates its displayed total) — rejected for v1. The
  correct-in-principle answer, but real complexity — overlapping-interval merging across
  an arbitrary number of sources — for a number this project uses as a rough
  cross-reference ("did I move more today"), not a precise fitness metric.
- **Max of each source's daily total, per day** — chosen. For each Day, sum each source's
  samples independently, then take whichever source's total is larger. Assumes the device
  that was actually being carried/worn caught more of the day's steps than the one that
  wasn't — true often enough to be a meaningful improvement over summing, cheap to compute,
  and easy to explain when a number looks off.

## Consequences

The number is an approximation, not a reconciled true count, and undercounts a day where
neither device caught the whole day (phone in a bag all morning, watch on wrist all
afternoon — the true total is higher than either source's total alone). `daily_steps`
keeps which source won (`source` column) specifically so a suspicious day is one `query`
away from being explainable, the same reasoning as `sync_state.last_error` for the
network syncs.

Worth revisiting if the approximation ever visibly matters — e.g. a `body_measurements`-
style cross-check against a known-accurate day — but not before then.
