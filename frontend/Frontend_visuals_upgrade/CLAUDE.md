# PM-JAY Assistant — Redesign Implementation Brief

You are implementing a redesign of the PM-JAY Assistant (Uttar Pradesh) — a data-query tool for India's Ayushman Bharat Pradhan Mantri Jan Arogya Yojana scheme. The current live version is at https://frontend-production-4eb9.up.railway.app/.

## Your task

Port the three main views — **Ask**, **Discover**, and **Track** — from the mockup into the existing codebase, preserving the existing data layer, routing, and backend integration while swapping in the new visual design.

## Authoritative references

1. **`DESIGN_SPEC.md`** — the design brief. Read this first. It explains the design direction, tokens, typography, and per-mode layout intent.
2. **`mockup/pmjay-redesign.jsx`** — the working visual mockup as a single React file. Treat it as the source of truth for visual specifics (spacing, colors, typography, component structure). All data in it is hardcoded — your job is to wire up real data without changing the visual design.

## Implementation order

1. Set up design tokens in `tailwind.config.js` (`ivory`, `ink`, `line`, `muted`, `accent`, `teal-deep`) — do not leave them as inline CSS variables.
2. Load Fraunces and Inter from Google Fonts; register them as `font-display` and `font-sans` in Tailwind config.
3. Enable `font-variant-numeric: tabular-nums` globally on body.
4. Build the shared `Shell` component (top bar with logo, segmented-control nav, docs link). This is used by all three modes.
5. Port **Ask** — split cleanly into landing (empty) state and conversation state. Wire up to your existing SQL-generation endpoint.
6. Port **Discover** — wire up to your existing insights endpoint. Preserve the inline-bolded numbers pattern (`{value}` syntax) when processing insight headlines.
7. Port **Track** — keep your existing Leaflet + OpenStreetMap setup; only change the surrounding UI (reports column, specialty list with new search, underserved panel, legend color ramp, map header overlay).

## Critical constraints — do not deviate without asking

- **Single accent color.** `--accent` (saffron) appears *only* on eyebrow labels, active-state indicators on tabs, and a few priority signals. Never use it for buttons, links, or decorative elements.
- **Ink is the primary button color, not teal.** The live version uses teal for primary CTAs — in the redesign, teal is demoted to structural use only (logo, chart marks).
- **Charts use a single color** (`--teal-deep`) across all series. Do not introduce per-category coloring even if the query returns typed data. This is an explicit product decision — the query surface is too varied for reliable color semantics.
- **No decorative icons with assigned colors** on suggestion rows or similar. Categories get monospaced text labels, not colored icons.
- **Typography hierarchy is strict.** Headlines use Fraunces. Eyebrow labels are 11px uppercase with 0.14em tracking in accent color. Body is Inter 15px. Numbers everywhere use tabular-nums.
- **No page sidebar.** The redesign uses a top-bar-only navigation. Do not reintroduce a persistent left sidebar.

## Things the mockup doesn't include (and you shouldn't add yet)

- Per-result "Show SQL" / "Download CSV" buttons
- Follow-up suggestion chips after result cards
- A "Priority Insights" featured band at the top of Discover
- Filter / Export buttons on the Discover page head
- Session timestamp / "Clear session" controls on Ask
- Data-freshness indicators in the top bar

These were considered and explicitly cut. Don't re-add them unless the user asks.

## Accessibility requirements

- Segmented-control nav: `role="tablist"`, each tab `role="tab"` with `aria-selected`.
- All icon-only buttons: `aria-label`.
- Collapsible insight rows: `aria-expanded`, managed focus.
- Keyboard: Enter submits Ask input; Escape clears; arrow keys cycle category chips on Discover.

## Responsive behavior

Desktop-first. On <768px:
- Brand metadata in top bar collapses; keep only logo + nav.
- Ask result card stacks table above chart vertically.
- Track: reports and specialty columns become a drawer pattern; map takes the viewport.

## Questions you should ask me before committing

- Which routing library is in use? The mockup uses local state; paths should probably be `/ask`, `/discover`, `/track/:report/:specialty`.
- Does the existing insights API already return the `{value}` inline-bolding syntax, or will we need to add a transform?
- Are there existing Storybook entries or design-system components to align with?
