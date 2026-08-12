# A day runs 04:00–04:00 Europe/Amsterdam

Every rollup — daily nutrition, training volume, weekly reports — groups by day, so the
day boundary had to be pinned down before any row was written. All timestamps are stored
as UTC, but the derived `date` column is computed at write time as the
`Europe/Amsterdam` day with a **04:00 cutoff**: anything logged before 04:00 local
belongs to the previous day.

## Considered Options

- **UTC calendar days** — rejected. Amsterdam is UTC+1/+2, so a 01:00 post-training meal
  would be filed under the previous day, and every DST changeover would silently move
  the boundary by an hour.
- **Amsterdam calendar days, midnight to midnight** — correct on timezone, but splits
  late evenings from the day they belong to.
- **Amsterdam days with a 04:00 cutoff** — chosen. Matches how the day is actually
  experienced, and gives food and training one shared rule.

## Consequences

`date` is denormalized at write time rather than derived in queries. Recomputing it
later means rewriting every historical row, so the rule is deliberately recorded here.
