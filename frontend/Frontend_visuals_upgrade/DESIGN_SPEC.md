# PM-JAY Assistant — Redesign Spec

A redesign brief for the PM-JAY Assistant (Uttar Pradesh) — a data-query tool for the Ayushman Bharat Pradhan Mantri Jan Arogya Yojana scheme. This document gives you the full design system and production-ready React components for the three main modes: **Ask**, **Discover**, and **Track**.

A working mockup is included as `mockup/pmjay-redesign.jsx` — treat it as the visual source of truth. This document explains the *intent* so the final implementation stays true to the design even when the underlying data/routing/state are wired up for real.

---

## Design direction

**Refined institutional.** This is a government health-data product used by officials — it should feel serious, trustworthy, and scannable. The reference points are Bloomberg Terminal, India Stack documentation, and editorial data journalism — not consumer SaaS dashboards.

Four principles drive every decision:

1. **Restraint.** One accent color, used sparingly. Dark-teal demoted from "primary" to "structural." No decorative icons with arbitrary colors.
2. **Hierarchy through typography.** Serif display face for headlines, clean sans for UI and data, tabular figures everywhere numbers appear.
3. **Density where it helps, whitespace where it doesn't.** Dense insight lists, but generous landing pages. Let the content's nature decide.
4. **The three modes are one product.** Consistent shell, consistent spacing, cross-links between modes. Discover insights should be able to open as Track reports; Track data should be queryable via Ask.

---

## Design tokens

```css
:root {
  --ivory:     #FAF7F2;  /* page background — warm, institutional */
  --ink:       #1A1A1A;  /* primary text, primary buttons */
  --line:      #E8E4DC;  /* borders, dividers */
  --muted:     #8A857B;  /* secondary text, placeholders */
  --accent:    #C8501E;  /* saffron — active states, eyebrow labels only */
  --teal-deep: #1F4E5F;  /* logo mark, chart bars, structural accents */
}
```

**Usage rules:**
- `--accent` is **precious**. Only use for active-tab indicators, eyebrow labels ("DISCOVER", "ASK"), and priority signals. Never for buttons, links, or anything that risks over-exposure.
- `--ink` is the primary CTA color. All "send", "submit", "select" buttons use ink, not accent.
- `--teal-deep` is a structural color — use for the logo square, all chart marks, and occasional semantic use (e.g. "empanelled hospital" markers). Never as a primary button.
- `--muted` is for supporting text and inactive nav. Resist using it for body copy; body copy is `--ink`.
- `--ivory` is the canvas. White is reserved for "cards" or content that needs to lift off the canvas (result cards, hero input, map panels).

---

## Typography

Two typefaces, both loaded from Google Fonts:

```css
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=Inter:wght@400;500;600&display=swap');
```

- **Fraunces** — display serif. Page titles, hero headlines, brand mark. Slightly playful but grown-up. Use the italic for emphatic phrase turns (e.g. "*PM-JAY data.*" in the landing hero).
- **Inter** — body UI. Everything else.

**Critical:** Enable tabular numerals for all numeric content via `font-variant-numeric: tabular-nums` (or Tailwind's `tabular-nums` utility). Percentages, counts, bed totals, table data — they all need to align vertically.

Type scale (use consistently):

| Role | Size | Weight | Face |
|---|---|---|---|
| Hero headline | 44px | 400 | Fraunces |
| Page title | 34px | regular | Fraunces |
| Section title | 22px | regular | Fraunces |
| Eyebrow label | 11px uppercase, 0.14em tracking | 600 | Inter |
| Body | 15px | 400 | Inter |
| Metadata | 13px | 400 | Inter |
| Caption/micro | 11px | 400–500 | Inter |
| Tiny (kbd, badge) | 10px | 500 | Inter |

---

## Shell (global layout)

A fixed **56px top bar** is present on every page. Structure:

- **Left:** Shield logo mark (teal square, 28px) + "PM-JAY Assistant" (Fraunces 15px) + vertical divider + "Uttar Pradesh · Ayushman Bharat PMJAY" (muted 12px).
- **Center:** Segmented-control nav with three options: Ask, Discover, Track. Use the pill-in-pill pattern — outer container has a subtle ivory background and border; active item is a lifted white pill with soft shadow and `--line` border; inactive items are muted and get a light white hover background.
- **Right:** "Docs" link (muted, hover to ink).

No sidebar. No secondary nav. The three modes are the entire navigation surface.

---

## ASK mode

Ask has two distinct states:

### Empty state (landing)

When no query has been asked yet, the page is a **centered landing**, not a chat shell. No top strip, no bottom input bar — those layouts belong to the active conversation state.

Layout (vertically centered in viewport, max-width 720px):

1. **Hero block**, centered:
   - Headline: "Ask anything about" on one line, then "*PM-JAY data.*" in italic Fraunces with muted color. 44px, tight leading.
   - Subtitle: "Get answers, insights, and visual analysis in seconds — across claims, empanelment, enrolment, and specialty coverage." 15px muted, max-width ~380px, centered.
2. **Hero input** — the primary affordance on the page:
   - White background, 14px border radius, generous 14px vertical padding.
   - Magnifying-glass icon left, text input center, `↵` keyboard hint, ink-colored send button (32px square, icon only).
   - Soft shadow to lift it off the ivory canvas.
   - `autoFocus` on mount.
3. **Suggestions list**, below the input:
   - Eyebrow label "Try asking" with a horizontal rule extending right.
   - Six example queries in a list (not a grid — grids cause awkward line wrapping with variable-length questions).
   - Each row: category label on the left (10px uppercase muted, fixed 80px width) · the question text (14px ink) · an arrow icon on the right that only appears on hover.
   - Rows separated by `--line` dividers; overall block bounded by top and bottom `--line` borders.

**Categories for suggestions:** `HOSPITALS`, `CLAIMS`, `ENROLMENT`, `PERFORMANCE`. These should map to query domains in the backend so users learn the data surface.

**Anti-patterns to avoid** (these were in the original):
- No decorative colored icons next to suggestions (the original had teal/blue/green/purple/yellow/orange icons with no system).
- No 2-column suggestion grid.
- No teal send button — use ink.

### Active state (conversation)

Once a query is submitted, the layout flips:

- **Top strip** (white, `--line` bottom border): "ASK" eyebrow + "Query PM-JAY data in plain English" title.
- **Conversation area** (ivory background, scrollable): contains user bubbles (ink background, ivory text, rounded lg with rounded-br-sm corner), an assistant identity row (small teal shield + "Assistant · HH:MM"), and result cards.
- **Input bar pinned to bottom** (white, `--line` top border): smaller version of the hero input.

Max-width for conversation content: **820px**, centered.

### Result card

When a query returns tabular data, wrap it in a white card with a `--line` border:

- **Card header**: ivory-tinted strip with the query title (11px uppercase semibold ink) + meta ("by type · 7 rows" in muted).
- **Card body**: two columns split by a vertical divider — table on the left, chart on the right.
- **Table**: tabular-nums, 13px ink text, 10px uppercase muted headers. Hover row gets ivory tint.
- **Chart**: horizontal bar chart (not vertical — prevents label overlap at variable label lengths). **Single color** for all bars (`--teal-deep`) — do not color by category. With potentially 500+ different queries and unpredictable groupings, any color-by-category logic becomes a maintenance burden and produces inconsistent meaning across queries.
- **No SQL/CSV/Export buttons** in the card header for this iteration — add later if users ask.
- **No follow-up chip suggestions** for this iteration.

---

## DISCOVER mode

A feed of pre-computed insights derived weekly from state data. Max-width **860px**, centered.

### Page head

- "DISCOVER" eyebrow label (accent, 11px uppercase tracked).
- Title: "What the data is telling us" (Fraunces 34px).
- Subtitle: "Priority insights across claims, infrastructure, and enrolment — refreshed weekly." (muted 14px).
- Bottom border (`--line`) separates head from content.

**No filter or export buttons** in the head. This is a reading surface, not an action surface.

### Category chips

Below the head: a horizontal row of pill chips — "All", "Claims & Treatment", "Hospital Infrastructure", "Beneficiary Enrolment" — each showing a count.

- Active chip: ink background, ivory text, count dimmed.
- Inactive chips: white background, `--line` border, ink text, muted count. Border darkens to `ink/30` on hover.

### Insights list

A single flat list (no priority band, no grouping by category in the list itself — the chips handle filtering).

Each insight row:
- Chevron on the left (right-facing collapsed, down-facing expanded).
- Headline text with **key numbers bolded inline** via the `{value}` syntax — e.g. "NORMAL discharges account for **85.6%** of paid PM-JAY value…" The bolding is the single biggest scanability upgrade; numbers need to pop out of prose.
- Tail text in muted, separated by " — ".
- No metadata line underneath (no category/district-count/timestamp — this noise was removed intentionally).

Expanded state (only when user clicks):
- Indented with a left border in accent/40.
- Numbered detail items (01, 02, 03 in tabular-nums muted).
- Two cross-links at the bottom: "Open as Track report →" (accent) and "Ask a follow-up question" (muted).

The cross-links are important — they wire the three modes together and invite users to pivot from "I noticed this" to "tell me more" or "show me where."

---

## TRACK mode

A three-column layout, full viewport width (no centered container).

### Column 1: Reports (256px)

White-tinted sidebar with 3 reports: Speciality Coverage, Hospital Performance, Beneficiary Enrolment. Each button has:
- Small icon (MapPin, Activity, Users from lucide) at 14px.
- Report name (13px medium ink).
- One-line description below (11px muted, indented to align with the label text).
- Active state: ink background, ivory text.

At the bottom, a small muted "Download full report (PDF)" link with a FileText icon.

### Column 2: Filter (specialty list, 256px)

- Header section with "SPECIALTY" eyebrow + a **search input** (this was missing in the original — with 12+ specialties, search is necessary).
- Scrollable list below. Each item:
  - 13px ink, left-aligned, full-width button.
  - Active state: subtle accent tint background (`accent/10`), 2px accent left border, accent chevron on the right.
  - Inactive: transparent, hover to `ink/[0.03]`.

### Column 3: Map (fills remainder)

- **Title overlay** at the top-left (white-to-transparent gradient fade): eyebrow + headline "Where {specialty} care is reaching Uttar Pradesh" + subtitle explaining the visualization.
- **Zoom controls** (+/−) as a clean white card with `--line` border, not overlaid on tiles.
- **"Most underserved blocks" panel** on the top-right: white card listing top 5 blocks with rank, block name, district, and population. Each row hoverable and clickable — cursor to a different map location.
- **Legend** pinned to bottom-right of the map (not orphaned in the filter sidebar). Uses an **amber-to-deep-brown sequential ramp** (`#FEF3C7`, `#FCD34D`, `#F59E0B`, `#D97706`, `#B45309`, `#78350F`). Amber-to-brown signals "intensity/attention"; pure red reads as "error/danger" which is not the intended meaning.

The map itself should be Leaflet + OpenStreetMap tiles (already in the original). Block-level choropleth for the underservice metric (population × distance to nearest empanelled hospital for the selected specialty).

---

## Implementation notes for development

- **Framework:** the mockup is React + Tailwind (single file, no dependencies beyond `lucide-react`). For production, decompose into proper component files following your existing codebase structure.
- **State management:** the mockup uses local `useState` for mode switching and selections. For production, replace with your router (e.g. TanStack Router / React Router with paths `/ask`, `/discover`, `/track/:report`) and keep selections in URL params so views are shareable.
- **Data:** all data in the mockup is hardcoded. Wire up:
  - Ask → SQL-generation endpoint, returning `{ sql, table, chartSuggestion }`.
  - Discover → precomputed insights API returning `{ id, category, headline, tail, detail? }[]`.
  - Track → geojson + specialty coverage API.
- **Custom Tailwind config:** the mockup uses inline `<style>` to define `bg-ivory`, `text-ink`, `border-line`, etc. In production, move these to `tailwind.config.js` under `theme.extend.colors` so they're first-class utilities.
- **Accessibility:**
  - Segmented control nav needs `role="tablist"`, `role="tab"`, `aria-selected`.
  - All icon-only buttons need `aria-label`.
  - Collapsible insight rows need `aria-expanded` and proper focus management.
  - Color contrast is already compliant for all text on all backgrounds.
- **Responsiveness:** the mockup is desktop-first. For mobile/tablet:
  - Top nav: keep segmented control but collapse the brand metadata.
  - Discover: single column (already is).
  - Ask: stack table and chart vertically in result card.
  - Track: drawer pattern for reports/specialty columns, map takes full screen.
- **Tabular numerals:** add `font-variant-numeric: tabular-nums` on `body` or a root wrapper so it's the default. Override with `font-variant-numeric: normal` only for body prose that doesn't contain numbers.
- **Motion:** keep it subtle. Tab switches can have a 150ms opacity fade; chart bars can animate width on first render; hover states are instant (not delayed). No page transitions.

---

## What's intentionally *not* in this iteration

These were considered and cut, because they add complexity without clear user value at this stage. Flag them as future work:

- **SQL view / CSV download on Ask results.** The underlying SQL may be noisy; CSV export is easy to add later when users ask.
- **Follow-up suggestion chips on Ask results.** Need real data on what follow-ups users want before hardcoding them.
- **Priority insights band on Discover.** The flat list is already scannable with the bolded numbers; a separate priority band was redundant.
- **Filter and Export buttons on Discover.** The category chips already filter; export can live elsewhere.
- **Sidebar on main shell** (Recent queries, data coverage notes). Can come back as a collapsible drawer if needed.
- **Session timestamp / Clear session on Ask header.** Not useful when every conversation starts fresh from the landing.

---

## File

Component code: `mockup/pmjay-redesign.jsx` — full working React component with all three modes. Treat as reference for visual specifics; re-implement in your production structure.
