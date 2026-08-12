# Food log entries store macros, not references

A Food Log Entry copies the Product's macros into itself at write time instead of
holding only a reference to the Product row. Products get reformulated, relabelled, and
corrected; resolving macros at read time would mean last March's protein total quietly
changes when a manufacturer tweaks a recipe. History must stay fixed once written.

## Consequences

The `products` table is a convenience for *creating* entries, not the authority behind
existing ones. Editing a Product does not — and must not — retroactively alter what the
log says was eaten. This looks like a normalization mistake to a reader who doesn't know
why; it isn't.
