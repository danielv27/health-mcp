# Personal Health

A single agent-facing surface over one person's training and eating history, so that
questions spanning both ("did intake track with volume?") can be answered without
copying data between apps.

## Language

### Food

**Product**:
A specific, identifiable food item with known macros — a particular brand's cottage
cheese, not "cottage cheese" in general.
_Avoid_: Item, food, article, SKU

**Food Log Entry**:
A record that a quantity of one Product was eaten at one point in time. Quantity is
always expressed in **grams**; any other phrasing the user typed is kept only for
display, never for arithmetic.
_Avoid_: Meal, entry, serving

**Macros**:
The nutritional figures carried by a Product — energy, protein, carbohydrate, fat, and
the subdivisions of those. Always stated per 100 g so that any quantity scales linearly.
_Avoid_: Nutrition, nutrients, nutritional information

**Catalog**:
The set of Products this person actually eats. Small, hand-curated, and grown one
Product at a time as new foods enter the rotation.
_Avoid_: Database, products table, pantry, library

**Verified**:
Said of Macros transcribed from an actual package label. The standard for anything in
the Catalog worth trusting.
_Avoid_: Confirmed, accurate, real

**Estimated**:
Said of Macros supplied from general knowledge rather than a label — what "I ate a
banana" produces. Good enough to log, never silently equal to Verified: every rollup
that includes Estimated figures says so.
_Avoid_: Approximate, guessed, inferred

### Time

**Day**:
The unit every rollup is grouped by: 04:00 to 04:00 `Europe/Amsterdam`. A meal eaten at
01:00 belongs to the day that just ended, not the one that just began. Distinct from a
calendar date, and never a UTC date.
_Avoid_: Date, calendar day, 24-hour period

### Training

**Workout**:
One completed training session, as recorded in Hevy. Has a start and end, and contains
the exercises performed.
_Avoid_: Session, training, activity

**Volume**:
Total weight moved within some scope — a workout, an exercise, or a muscle group over a
week. The unit of comparison against intake.
_Avoid_: Tonnage, load, work
