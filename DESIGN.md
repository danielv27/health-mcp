---
name: health-mcp Food Log
description: A calm, ledger-style shadcn-vue dashboard for food, training, and trends
colors:
  background: "hsl(0 0% 100%)"
  foreground: "hsl(240 10% 12%)"
  card: "hsl(0 0% 100%)"
  primary: "hsl(160 84% 28%)"
  primary-foreground: "hsl(0 0% 100%)"
  secondary: "hsl(240 5% 96%)"
  muted-foreground: "hsl(240 4% 40%)"
  destructive: "hsl(4 76% 48%)"
  success: "hsl(160 70% 32%)"
  border: "hsl(240 6% 88%)"
  chart-1: "hsl(160 70% 38%)"
  chart-2: "hsl(32 90% 52%)"
  chart-3: "hsl(217 80% 55%)"
  chart-4: "hsl(280 55% 55%)"
typography:
  sans:
    fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 400
  mono:
    fontFamily: "IBM Plex Mono, ui-monospace, SF Mono, monospace"
    fontWeight: 400
rounded:
  sm: "calc(0.6rem - 4px)"
  md: "calc(0.6rem - 2px)"
  lg: "0.6rem"
  full: "9999px"
spacing:
  xs: "0.4rem"
  sm: "0.6rem"
  md: "0.75rem"
  lg: "1rem"
  section: "1.5rem"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.primary-foreground}"
    rounded: "{rounded.md}"
  badge-verified:
    backgroundColor: "{colors.success}/10"
    textColor: "{colors.success}"
    rounded: "{rounded.full}"
  badge-estimated:
    backgroundColor: "amber-500/15"
    textColor: "amber-700"
    rounded: "{rounded.full}"
---

# Design System: health-mcp Food Log

## Overview

**Creative North Star: "Ledger"**

This is a shadcn-vue redesign, replacing the prior "Instrument Panel" cockpit build
per an `/impeccable critique` (2026-09-01) that asked for a more comprehensive,
calmer surface: full trends across food and training, a Hevy sync toggle, an
embedded chat with Claude, and shadcn's component system. The old amber/brushed-metal
cockpit identity is retired as evidence and anti-reference, not preserved — this is a
new visual world, built on shadcn-vue's neutral, Radix-based design language.

The metaphor is a well-kept personal ledger, not a gauge cluster: quiet neutral
surfaces, a single emerald accent for the primary action and on-target state, real
data visualizations instead of instrument-panel theater. Numbers are still the point
— every measured value (kcal, grams, kg, dates) renders in IBM Plex Mono with tabular
figures — but the chrome around them is shadcn's own restrained language, not a
custom material system.

**What carries forward from the prior build (behavior, not visuals):**
- **The No Silent Write Rule.** Nothing writes to the server on a bare tap. Foods are
  staged into a pending meal cart; only an explicit "Log {meal}" commits. Every commit
  and delete surfaces an undo toast (now via `vue-sonner`, shadcn's own toast
  primitive).
- **The Honest State Rule.** A control's visual state (a food row's checkmark, an
  auto-sync switch) always reflects real, current data.
- **Verified vs. estimated stays visible** — every Catalog item and log entry still
  carries its badge; the colors change (green/amber, shadcn's palette), the
  distinction does not.

**Key Characteristics:**
- Four views behind a persistent nav (bottom tab bar on mobile, top nav on desktop):
  **Today** (the meal-logging flow), **Trends** (food, training, weight, and
  intake-vs-training charts), **Chat** (an embedded Claude conversation scoped to
  this person's own data via a backend-proxied `query` tool), **Settings** (daily
  targets, Hevy sync toggle + manual sync + status).
- No longer capped to a narrow fixed-width instrument-panel column — Today stays a
  comfortable single-column read at any width (it doesn't gain information from more
  space), but Trends uses a 2-column chart grid at desktop width.
- Real charts (Chart.js via vue-chartjs) for every trend, never a sparkline or a
  table pretending to be one.
- Light is the default use scene (checked on a phone, in daylight, multiple times a
  day); dark follows system preference (`prefers-color-scheme`), no manual toggle.

## Colors

Neutral zinc-leaning surfaces; a single emerald accent (`hsl(160 84% 28%)`) is the
only color used for the primary action and on-target progress. Status colors are
functional only: amber for "estimated" data, red for over-target values and
destructive actions.

### Primary
- **Emerald** (`hsl(160 84% 28%)` / `hsl(160 70% 42%)` dark): primary buttons, active
  nav state, on-target progress bars, the "verified" badge and success states.

### Secondary / Status
- **Amber**: the "estimated" badge and warning-style states — never the primary
  action color.
- **Red** (`hsl(4 76% 48%)`): over-target macro values, destructive buttons (delete),
  error toasts. Reserved for these; never decorative.
- **Chart palette** (`--chart-1..4`): emerald, amber, blue, violet — used only inside
  Trends' multi-series charts, never for UI chrome.

### Neutral
- **Background / Card**: white in light mode, near-black zinc in dark mode. Cards use
  a 1px `border` (not a shadow-only separation) per shadcn convention.
- **Muted foreground**: labels, secondary metadata, placeholder text — always ≥4.5:1
  against its surface.

### Named Rules
**The One Accent Rule (carried forward).** Emerald is the only color used for
emphasis or the primary action. Amber and red are status colors tied to data
meaning (estimated / over-target / destructive) — never a second decorative accent.

## Typography

**Body/UI Font:** Inter (with ui-sans-serif, system-ui, sans-serif)
**Numeral Font:** IBM Plex Mono (with ui-monospace, SF Mono, monospace) — every
measured value (macro totals, grams, kcal, dates in charts, kg) renders in mono with
`font-variant-numeric: tabular-nums` (the `.tabular` utility) so figures align in
lists and cards.

### Hierarchy
- **Macro value** (600, 1.5rem/text-2xl, mono, tabular): the four Today macro cards'
  headline numbers.
- **View title** (600, text-lg): "Today", "Trends", "Chat", "Settings" — one per view,
  not a kicker/eyebrow above it.
- **Body** (400, text-sm): entry names, chat messages, field values.
- **Label** (500, text-xs, uppercase, tracking-wide, muted-foreground): card labels
  ("CALORIES"), section headings ("Quick add to meal").

### Named Rules
**The Measurement-Only Mono Rule (carried forward).** Monospace is reserved for
numbers and directly-attached units/labels. Food and entry names — free text — always
render in Inter.

## Layout

No fixed-width panel. A `max-w-6xl` centered container holds every view. Today and
Chat stay effectively single-column (their content doesn't benefit from extra width);
Trends uses a 2-column chart grid from `lg:` up. Navigation is a bottom tab bar on
mobile (`sm:hidden`, safe-area aware) and a top nav on desktop (`hidden sm:block`) —
never both at once. The meal cart tray is a sticky panel pinned above the mobile tab
bar (`bottom-16`) or the viewport bottom on desktop (`sm:bottom-4`), appearing only
once it holds at least one item.

## Elevation & Depth

shadcn's standard two-layer system: cards are `border + shadow-sm` (a 1px border does
the primary separation; the shadow is a soft, barely-there lift, not a dramatic
material effect). The bottom sheet and cart tray use `shadow-lg` as the one stronger
elevation in the system, since they float above page content. No glow, no brushed
texture, no instrument-panel materiality — this world's depth language is
deliberately quiet.

## Shapes

shadcn "new-york" radii: `--radius: 0.6rem` as the base (`rounded-lg`), stepping down
to `rounded-md`/`rounded-sm` for nested elements, per shadcn's own scale. Badges are
fully rounded (`rounded-full`) pills. The bottom sheet rounds only its top corners on
mobile, all corners on desktop.

## Components

### Macro Card
Today's four headline numbers (calories/protein/carbs/fat): label, mono tabular
value with `/target`, and a horizontal `Progress` bar (emerald under target, red at
or past it — the whole card's value color switches with the bar, never partially).
Replaces the prior build's SVG dial-ring gauge with shadcn's own `Progress`
primitive.

### Food Row (Quick Add)
A recent/frequent food's staging control: name, verified/estimated badge, last-logged
grams, and a trailing circular icon button that swaps between a plus (not staged) and
a check (staged in the pending meal cart) with a filled emerald background when
active. Replaces the prior toggle-switch lever; keeps its exact behavioral contract
(**The Honest State Rule**).

### Meal Cart Tray
Sticky panel: meal-type chips (breakfast/lunch/dinner/snack, defaulted from time of
day), a scrollable staged-item list with per-item remove, and a primary
"Log {type} · N items · kcal" button — the only control that writes to the server.

### Trend Chart Card
A `Card` holding a chart title and a Chart.js line/bar chart (or an empty-state
sentence when there's no data yet in the selected range). A shared 4/12/26/52-week
range selector sits at the top of the Trends view and drives all six charts at once.

### Chat Panel
A message list (user bubbles right-aligned in emerald, assistant bubbles left-aligned
in muted secondary) over a text input with a send button. A dedicated "not
configured" empty state (checked via `GET /api/chat/status`, not by firing a real
message) explains what's missing rather than surfacing a raw error.

### Toast / Undo
`vue-sonner`'s toast, top-center, with an inline "Undo" action button on every commit
and delete. This is still the system's one recovery mechanism — **The No Silent Write
Rule** (carried forward).

### Buttons, Badges, Inputs, Switch
Straight shadcn-vue defaults (`Button`, `Badge`, `Input`, `Switch` built on
`radix-vue`) — see `src/components/ui/`. No project-specific reskinning beyond the
color tokens above; consistency with shadcn's own conventions is the point of this
migration.

### Named Rules
**The Honest State Rule (carried forward).** A control's visual state always reflects
real, current data — never a momentary animation that plays regardless of outcome.

**The No Silent Write Rule (carried forward).** Every action that writes to the
server (logging a meal, deleting an entry, toggling auto-sync) surfaces a toast or
immediate visible state change; a tap that changes stored data and shows nothing is a
defect.

## Do's and Don'ts

### Do:
- **Do** keep every measured number in IBM Plex Mono with tabular figures; keep every
  name/label in Inter.
- **Do** route every new food through the meal cart, never a direct write.
- **Do** use shadcn-vue's own primitives (`radix-vue` + `class-variance-authority`)
  for new components rather than hand-rolling a look-alike.
- **Do** keep charts real (Chart.js) with an explicit empty state, never a blank card
  or a fabricated placeholder series.
- **Do** keep the emerald accent reserved for the primary action / on-target state
  (**The One Accent Rule**).

### Don't:
- **Don't** reintroduce the cockpit system's amber-as-accent, brushed-metal texture,
  or dial-ring gauges — that visual world is retired, not blended with this one.
- **Don't** let a control fire a real write on a bare, undifferentiated tap with no
  undo (**The No Silent Write Rule**).
- **Don't** use monospace for free-text names (**The Measurement-Only Mono Rule**).
- **Don't** show both the mobile tab bar and the desktop top nav at the same
  breakpoint.
- **Don't** treat the chat panel's "not configured" state as a generic error — it has
  its own explanatory empty state.

---

## Deferred / not built this pass

- **Streaming chat responses** — `/api/chat` is a single non-streaming round trip per
  turn; each reply waits for the full tool-use loop to resolve server-side. Fine for
  v1, worth revisiting if replies feel slow in practice.
- **Per-exercise progression drill-down** — `GET /api/trends/exercise?title=X` exists
  and is tested, but the Trends view doesn't yet expose an exercise picker to chart
  it; the four fixed dashboards (food, training volume, weight, correlation) were the
  scoped ask.
- **Photo-based product identification** — still only the conceptual sketch from the
  prior critique round; unrelated to this pass and not built.
