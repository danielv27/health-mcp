---
target: web-frontend food-log UI (App.vue/DialGauge.vue/FoodToggle.vue)
total_score: 19
max_score: 40
na_heuristics: 
p0_count: 1
p1_count: 3
timestamp: 2026-08-31T23-20-36Z
slug: web-frontend-src-app-vue
---
**Method: dual-agent (A: design-review subagent · B: detector+browser-evidence subagent)**

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Search shows no loading feedback; worse, the Quick Log toggle's auto-revert animation actively hides that a write just happened |
| 2 | Match Between System & Real World | 1 | A toggle switch reads as persistent on/off to any user — here it's momentary and self-resets |
| 3 | User Control and Freedom | 1 | Zero confirmation on log, edit, or delete; only "undo" is manually locating the entry afterward |
| 4 | Consistency and Standards | 3 | Visually consistent with DESIGN.md, but the toggle's real behavior contradicts the "switch" affordance it visually claims |
| 5 | Error Prevention | 0 | A data-writing action shares the identical single-tap gesture as browsing a list |
| 6 | Recognition Rather Than Recall | 3 | Quick Log rack surfaces prior foods well, but grams fixed to last-logged value, no adjustment before firing |
| 7 | Flexibility and Efficiency | 2 | Fast for single repeat-food logging, no accelerated path for logging several foods as one meal |
| 8 | Aesthetic and Minimalist Design | 4 | Genuinely calm, low-density, on-brand |
| 9 | Error Recovery | 1 | No toast/undo pattern anywhere; recovery means scanning a flat list and hitting a 34px delete target |
| 10 | Help and Documentation | 2 | No microcopy warns a Quick Log tap is immediate and irreversible |
| **Total** | | **19/40** | **Poor — major UX overhaul required; core experience broken** |

## Design Specificity Verdict

The visual system is specific to this product; the interaction model isn't. DialGauge.vue/FoodToggle.vue/style.css faithfully execute DESIGN.md's "Instrument Panel" language, but nothing specifies what a committing action should feel like vs a browsing one. Polish substituted for interaction design at exactly the moment it mattered.

CLI detector (detect.mjs) reported zero findings but flagged itself DEGRADED (missing htmlparser2/css-select/css-tree/domutils, regex fallback, no computed contrast). The browser-injected version of the same detector against the live page found 48 anti-patterns: real low-contrast (#8a8d94 on #3d4149, 3.1:1 vs 4.5:1 floor) across every macro label; real undersized-ui-text (9.6-10.9px vs 11px floor); an ai-color-palette flag on the "verified" badge's green reading as neon-cyan on dark (plausible, not clearly a false positive); and a likely-false-positive text-occlusion flag on the dial numerals (screenshots show them legible over the ring — looks like a DOM-order vs paint-order artifact). The CLI's empty result should not be read as a clean bill of health; the browser evidence is what should govern here.

## Overall Impression

The panel earns trust visually the instant you open it, then spends that trust the moment you touch the control you'll use most: a single unconfirmed tap writes a real row, and the toggle then animates back to looking untouched, erasing the only evidence anything happened. Underneath, the data model assumes food is logged item-by-item when it's never eaten that way in reality — it's always a meal. Those two problems compound with a third: no undo anywhere in the app.

## What's Working

- The visual system itself: brushed bezels, the one-glow rule, coordinated on/over-target color switching, mono-for-numbers — faithfully executed, calm to read at a glance.
- Verified/estimated stays visible everywhere, exactly as PRODUCT.md demands.
- The Quick Log *idea* (surfacing recent/frequent foods for one-tap re-log) is the right instinct — the execution broke it.

## Priority Issues

**[P0] Quick Log fires a real, unconfirmed write — then visually lies about it**
- What: FoodToggle.vue's flip() POSTs to /api/log on a single tap with zero confirmation, then auto-reverts the lever to "off" 700ms later, erasing the only evidence a log occurred.
- Why it matters: This is the exact, traced, browser-confirmed mechanism behind the cottage-cheese incident. One tap -> dials jump -> toggle looks untouched within 3s -> recovery requires manually finding the right row among possible duplicates in a flat, timestamp-less list.
- Fix: Make the committing gesture distinct from browsing (long-press, or route quick-log through a pre-filled confirm sheet); replace the silent auto-revert with a persistent "Logged" state plus inline undo that actually deletes the row.
- Suggested command: /impeccable harden

**[P1] No concept of a "meal" anywhere — data model or UI**
- What: Every food_log write and the Today list are flat and independent; no meal_type/grouping in schema, API payloads, or template.
- Why it matters: Directly contradicts stated reality — food isn't logged standalone. Every meal costs N separate taps, Today view can't show the actual shape of the day.
- Fix: Add optional meal_type/group_id to the write path; support multi-select "log as one meal"; group Today list by meal with subtotals.
- Suggested command: /impeccable shape

**[P1] No confirmation or undo pattern anywhere in the app**
- What: Logging, editing, and deleting all fire immediately with no confirmation or toast, including the delete button meant to be the safety net.
- Why it matters: A mis-tap on delete is just as silently permanent as a mis-tap on log.
- Fix: One consistent snackbar-undo pattern applied uniformly to log, edit, and delete.
- Suggested command: /impeccable harden

**[P1] Functional text fails contrast and size floors**
- What: Browser-measured: macro labels at 3.1:1 contrast (need 4.5:1) and 9.6-10.9px type (need >=11px).
- Why it matters: This is the exact information checked at a glance multiple times a day, currently below legibility floors.
- Fix: Lighten --text-dim or its usage on bezel backgrounds; raise functional label sizes to >=11px.
- Suggested command: /impeccable audit

**[P2] No photo-based product identification**
- What: No camera/image input exists; search is text-only against a small, hand-curated catalog.
- Why it matters: Real, but secondary to the two things actually named in the complaint (misfires, meal mismatch).
- Fix: Defer until P0/P1s are fixed; if pursued, treat as a secondary entry point next to search.
- Suggested command: /impeccable shape

## Persona Red Flags

Casey (distracted mobile user): thumb grazes a Quick Log row while walking; flip() fires instantly, no distinct browse-vs-commit zone; lever reverts within a second, no reason to notice anything happened. Literal reproduction of the incident.

Riley (stress tester, logging a real meal): wants eggs+toast+coffee+OJ as "breakfast" -- no batch action, nothing tracks "3 of 4 done," rapid-tapping across rows can queue several unconfirmed writes with no batch status.

Jordan (first-timer): opens the panel, sees unlit switches with zero microcopy warning a tap is immediate and irreversible; natural exploratory tapping creates real entries with zero forgiveness.

## Minor Observations

- `searching` ref set during search but never rendered -- no loading feedback during the debounce window.
- One-off entries require re-typing per-100g macros every time; no "save as Catalog Product" shortcut despite being in PRODUCT.md's scope.
- Today entries carry no visible timestamp, which would have partially compensated for missing meal-grouping.
- The delete ("eject") icon is styled at the same low-key weight as harmless icons despite being the one destructive, unconfirmed control.

## Questions to Consider

1. Should Quick Log even use switch semantics, or would a momentary "+" chip that visibly stays logged be more honest?
2. Is a meal_type bolted onto the existing flat table enough, or does this need rethinking the primary action from "log a food" to "log a meal of N foods"?
3. Given the catalog is small and personal by design, should photo ID wait behind the misfire and meal-grouping fixes actually named in the complaint?
