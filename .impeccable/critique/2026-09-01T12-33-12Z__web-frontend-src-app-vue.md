---
target: web-frontend/src/App.vue
total_score: 29
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 3
timestamp: 2026-09-01T12-33-12Z
slug: web-frontend-src-app-vue
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Toasts confirm commit/delete well; Save/Settings fetches show no in-flight or failure state |
| 2 | Match System / Real World | 3 | Verified/estimated vocabulary is precise and consistent throughout |
| 3 | User Control and Freedom | 3 | Cancel + backdrop-click + Undo all work; no keyboard Escape on either sheet |
| 4 | Consistency and Standards | 4 | Badge/button/field/sheet styling applied identically everywhere |
| 5 | Error Prevention | 3 | Cart-staging model is real error prevention; macro inputs have no min/max validation |
| 6 | Recognition Rather Than Recall | 4 | Recent/frequent foods as one-tap toggles, live search |
| 7 | Flexibility and Efficiency of Use | 2 | No keyboard shortcuts, no bulk actions, no "repeat yesterday" shortcut |
| 8 | Aesthetic and Minimalist Design | 4 | One accent, one glow, two elevation tiers, nothing decorative found |
| 9 | Error Recovery | 2 | loadToday/loadRecent/openSettings fetches have no try/catch or res.ok check |
| 10 | Help and Documentation | 1 | No help/tooltip/onboarding anywhere; scored on merits (Operate surface) |
| **Total** | | **29/40** | **Good** |

## Design Specificity Verdict

As shipped, genuinely specific work: coordinated dial-gauge state change, honest non-reverting toggle, brushed-hatch bezel, cart-tray staging model, all authored for one repeated action. Against this request, the metaphor runs out of room: DESIGN.md states "no navigation" and "does not gain new information at wider viewports." A dial gauge has no idiom for an 8-week trend line. Three architecture collisions to resolve as explicit decisions before component work:
1. "Toggle" is the wrong shape for Hevy sync — sync_workouts/sync_activities are one-shot pulls with no persistent state and no HTTP endpoint today.
2. shadcn is React+Radix+Tailwind; this app is Vue 3 with zero UI deps. shadcn-vue is a separate community port. Framework fork, not a visual refresh.
3. In-app Claude chat reopens ADR-0005 (stdio-over-SSH instead of a public HTTPS agent endpoint).

Deterministic scan: detect.mjs --json against source returned 0 findings (exit 0). Live-DOM browser scan found 30 anti-pattern findings: ai-color-palette (cyan-neon text) x28, flat-type-hierarchy (8 distinct sizes, 11.2-21.6px, 1.9:1 ratio) x1, em-dash-overuse x1. The em-dash finding is a likely false positive (structural separators in catalog product/brand names, not authored prose). The cyan-neon flag is plausibly real but unmapped to a specific rule/line.

No visual overlay in a [Human] tab — no native browser tool this session; Assessment B used a hand-rolled Playwright script with direct screenshots/console capture instead.

## Overall Impression

Well-crafted for the narrow job it was built for. The problem isn't craft, it's scope: trends (browsing task), sync (status/action task), chat (conversational task), and a component-library swap are being asked of a single-screen "device you check, not browse" panel. Landing all four without first deciding how this panel gets a second kind of screen will produce four ad hoc patterns instead of one coherent one.

## What's Working

1. Cart-staging model — real error-prevention engineering built as a direct fix to an actual accidental-log incident.
2. The dial gauge — a true signature idiom, not a generic progress ring.
3. Verified/estimated fidelity — threaded through every surface with a fixed, non-recolorable pairing.

## Priority Issues

**[P1] No information architecture exists to hold this scope, and DESIGN.md explicitly forbids the obvious fixes.** Trends, sync, and chat are all new destinations on a system built to have none. Fix: design the navigation model itself before drawing a single trend chart. Suggested command: /impeccable shape.

**[P1] "Hevy sync as a toggle" doesn't match what sync is, and no backend surface exists for it yet.** One-shot, network-bound pull, no persistent state, no HTTP endpoint today. Fix: design as a triggered action with visible status (button + last-synced timestamp + error state). Suggested command: /impeccable clarify, then /impeccable shape.

**[P1] shadcn is architecturally incompatible with the current Vue/Vite stack.** Full React rewrite vs. shadcn-vue community port vs. keep Vue and extend the hand-built system with shadcn's visual conventions are three very different projects. No suggested command yet — needs resolving first.

**[P2] In-app Claude chat reopens ADR-0005's transport decision.** Confirm scope (narrow human-only HTTP chat vs. broader) before building. Suggested command: /impeccable audit once resolved.

**[P2] Silent failure paths on most read fetches.** loadToday/loadRecent/openSettings have no try/catch/res.ok handling. Suggested command: /impeccable harden.

## Persona Red Flags

**Alex (Power User)**: no keyboard shortcuts, no bulk-delete, no "repeat yesterday's breakfast" shortcut despite the data existing. Risk that a low-density "glance" trends screen frustrates power-user analysis needs.

**Sam (Accessibility-Dependent User)**: no keyboard Escape on either sheet-backdrop; Toast (the only write-confirmation mechanism) lacks aria-live="polite".

**Daniel (project-specific)**: the value proposition of "comprehensive trends" is cross-referencing food against training (per PRODUCT.md Positioning). Two disconnected screens would satisfy the literal request while missing the actual job.

## Minor Observations

- Restoring a deleted one-off entry re-derives per-100g macros from entry.kcal/entry.grams, can drift across repeated delete/undo cycles.
- Settings sheet and log sheet are visually identical apart from heading text.
- Search results show no per-100g macro preview.
- "Only drawn SVG icons, single stroke weight" rule held everywhere checked — worth protecting explicitly if a charting library is introduced.

## Questions to Consider

- Is "comprehensive trends" two separate views or one correlated view (food vs. training, same timeline)?
- Does a trends dashboard belong inside "a device you check, not a page you browse," or is it a second, differently-designed surface reachable from the panel?
- Is "toggle" literal for Hevy sync, or is visible status + manual "sync now" the real want? Does the web backend get Hevy credentials it doesn't have today?
- Is chat read-only or write-capable?
- Is "still very basic UI" really about wanting shadcn specifically, or about wanting more visual richness that could be answered without a framework swap?
