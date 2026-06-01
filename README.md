# AB UP Insights

A proof-of-concept analytical toolkit for India's Ayushman Bharat PM-JAY health insurance scheme, built on a synthetic replica of operational data for **Uttar Pradesh**. The repo contains three components that together turn raw scheme data into an explorable product: an automated **insight-discovery pipeline**, a natural-language **query backend**, and a **dashboard frontend** that ties them together.

The aim is to demonstrate that a state-level PM-JAY programme officer can move between three modes of working — *ask a question*, *read what the data is telling us*, *track a coverage gap on a map* — without leaving the tool, and without writing a single SQL query.

---

## Background — Ayushman Bharat PM-JAY

PM-JAY (Pradhan Mantri Jan Arogya Yojana) is India's flagship public health insurance scheme, providing cashless hospitalisation cover of up to ₹5 lakh per family per year to economically vulnerable households. It runs across empanelled public and private hospitals nationwide and generates a substantial operational data trail — beneficiary enrolment, hospital empanelment, case admission, pre-authorisation, claims, adjudication, payment.

This project models that pipeline end-to-end for Uttar Pradesh (75 districts, 18 divisions) using fully synthetic data. No real beneficiary information is included.

---

## The dataset

All three components draw from a shared synthetic dataset under [ab_data/](ab_data/) — 21 CSVs covering the full PM-JAY operational surface:

| Block | What it contains |
|---|---|
| Reference | UP geography (state → division → district → block), Health Benefit Package procedure master |
| Beneficiary | Households, individuals, identity documents, card issuance |
| Hospital | Hospital master, infrastructure, doctors, specialties, license history |
| Treatment | Cases, diagnoses, procedures performed |
| Claims | Pre-authorisation, claims, adjudication, payment, settlement |

A "medium" dataset is ~50K households / 800 hospitals / 200K beneficiaries / 22.5K cases (~300 MB on disk). Full schema and column-level docs in [ab_data/README_Dataset.md](ab_data/README_Dataset.md).

The synthetic generator deliberately preserves real-world data quality issues — duplicates, expired licences, null gaps in document fields, varying enrolment quality across districts — because those imperfections are themselves analytically meaningful.

---

## Three components

### 1. MetaInsights — automated insight discovery

[Metainsights_anomalies/](Metainsights_anomalies/) — full system overview in [README_MetaInsight_System.md](Metainsights_anomalies/README_MetaInsight_System.md).

A pipeline that exhaustively searches the space of possible "data views" of the PM-JAY data, detects statistical patterns in each, groups related patterns to find what's common and what's exceptional, scores them for importance and actionability, and emits a ranked, human-readable executive report. Built on the MetaInsight framework (Ma et al., SIGMOD 2021).

The output isn't a dashboard — it's *structured knowledge*: claims of the form **"this pattern holds broadly, except in these specific cases, which deserve investigation."**

#### Conceptual flow

```
21 raw CSVs
   │
   ▼  Phase 1 — ingest, validate, build 4 analytical views
   │
   ▼  Phase 2 — core engine on View 1 with one pattern type (Outstanding #1)
   │
   ▼  Phase 4a — expand to all 11 pattern types
   │
   ▼  Phase 4b — run across all 4 views
   │
   ▼  Phase 5a — rank and deduplicate findings per view (greedy TotalUse)
   │
   ▼  Phase 5b — generate executive report via LLM
   │
   ▼  Markdown + PDF report for a non-technical programme officer
```

#### The four analytical views

Phase 1 transforms 21 normalised tables into 4 flat views, each tuned for a different family of questions:

- **View 1 — Claims Lifecycle** (~22,500 rows). One row per case, joining beneficiary, hospital, diagnosis, pre-auth, claim, payment, discharge. The richest view: 13 categorical dimensions, 3 temporal, 12 numeric measures.
- **View 2 — District-Month Cube** (~3,600 rows). One row per district × month. Designed for temporal trend discovery.
- **View 3 — Hospital Performance** (~7,300 rows). One row per hospital × specialty. No temporal dimension — focused on structural patterns like underutilisation and specialty gaps.
- **View 4 — Beneficiary Journey** (~206,000 rows). One row per beneficiary. Focused on demographic and geographic equity in scheme uptake.

#### What a "MetaInsight" actually is

Take a *subspace* (a filter, e.g. `division = Lucknow`), combine it with a *breakdown dimension* (e.g. `specialty_code`) and a *measure* (e.g. `SUM(amount_claimed)`). Run the aggregation, look at the resulting distribution, and ask: does it show one of 11 statistical patterns — Outstanding #1, Outstanding #Last, Top-Two, Last-Two, Evenness, Attribution (categorical), or Trend, Outlier, Seasonality, Change Point, Unimodality (temporal)?

If yes, ask the more interesting question: *does that pattern hold across related slices?* Extend the data scope by varying the subspace (other divisions), the measure (other money columns), or the breakdown (month vs. quarter), and check whether the same pattern type holds. The result is a **Homogeneous Data Pattern** — a set of comparable findings, partitioned into:

- a **commonness** (the pattern that holds across the majority), and
- **exceptions** (subspaces where the highlight differs, the pattern type changes, or no pattern fires at all).

A worked example:

> *Across 14 of 18 divisions, Cardiology has the highest claim amount.*
> *But in Jhansi, Orthopaedics leads (highlight-change).*
> *In Moradabad, no specialty clearly dominates (type-change).*

That's a single MetaInsight. The engine produces thousands per view; Phase 5a's greedy ranking selects a top 15 per view that maximises individual score while penalising overlap (so the final list covers different pattern types, dimensions, and measures rather than 15 variations of the same finding).

#### Phase 5b — turning findings into prose

Phase 5b is a thin LLM layer. It receives ranked, pre-validated structured findings enriched with actual quantitative statistics, plus a column glossary (translating codes like `CARD → Cardiology`) and tone instructions. The LLM does *not* re-analyse data or make analytical judgments — it only translates structured knowledge into natural prose, groups findings thematically, and ends each section with follow-up questions for the programme officer.

This split — engine does the analysis, LLM does the writing — means the LLM cannot hallucinate patterns. Every claim it makes is grounded in the structured MetaInsight data.

#### Key design decisions

- **Exhaustive search, not hypothesis-driven.** The user doesn't specify what to look for; the engine enumerates all valid combinations and lets scoring surface what's interesting.
- **Commonness + exceptions as the unit of insight.** A single fact ("Cardiology has the highest claims") is less useful than structured knowledge ("…in 14 of 18 divisions, except Jhansi where Orthopaedics leads"). The latter tells you what's generally true *and* where to look next.
- **Scoring balances conciseness, importance, and actionability.** A finding with a clean majority and a few notable exceptions scores higher than one that's true everywhere with no exceptions, because the exceptions are the entry points for further investigation.
- **Ranking favours diversity over raw score.** Greedy deduplication ensures the final list covers different pattern types and dimensions.
- **LLM as translator, not analyst.** The analytical work is done entirely by the engine; the LLM only writes prose.

---

### 2. Chatbot — natural-language data querying

[Chatbot/backend/](Chatbot/backend/) — a FastAPI service that powers the dashboard's **Ask** mode. It takes a plain-English question about PM-JAY data and returns tabular results plus a chart suggestion, without doing free-form SQL generation.

The architecture is deliberately constrained — instead of asking an LLM to write SQL against the schema, queries are routed through a curated catalogue:

```
User question
    │
    ▼  Preprocessor — date parsing, normalisation
    │
    ▼  Intent classifier — picks one of N intent labels
    │
    ▼  Entity extractor + validator — pulls districts, specialties, date ranges, hospital
    │                                  names from the message and validates against
    │                                  the reference data
    │
    ▼  Router — dispatches to either:
    │     • Dashboard catalogue — pre-computed results cached on startup (fast path)
    │     • Template catalogue — parameterised SQL templates filled with extracted
    │                            entities and run live against DuckDB
    │     • Fallback — graceful "I can't answer that" with suggestions
    │
    ▼  Result — tabular rows + chart hint, returned to frontend
```

Why this shape:

- **No free-form SQL generation.** With 21 tables and dozens of measures, an open-ended LLM-to-SQL path produces too many subtly wrong queries. Templates are validated once; entity extraction is validated against the reference data.
- **Dashboard cache for hot queries.** The 130-odd most common questions are pre-computed at startup and served from cache. Live SQL only fires for parameterised template variations and ad-hoc patterns.
- **DuckDB as the query engine.** Columnar, in-process, fast on the dataset's scale. A `dashboard_cache` table tracks freshness so re-seeds are incremental.

Templates and intents are defined in [Chatbot/backend/query_router/](Chatbot/backend/query_router/) — `intent_catalog.py`, `template_catalog.py`, `dashboard_catalog.py`. Adding a new question shape means adding an intent label, a template, and (optionally) a cached dashboard entry.

---

### 3. Frontend — three-mode dashboard

[frontend/ab-dashboard-main/](frontend/ab-dashboard-main/) — a Vite + React + TypeScript single-page app, styled with Tailwind. The design intent is *refined institutional* — serious and trustworthy like Bloomberg Terminal, with editorial typography and a restrained palette, not a consumer SaaS dashboard.

Full design system and component-level spec in [frontend/Frontend_visuals_upgrade/DESIGN_SPEC.md](frontend/Frontend_visuals_upgrade/DESIGN_SPEC.md). The redesign is in active development.

#### Three modes, one product

The shell is a fixed top bar with a three-tab segmented control. The modes cross-link — a Discover insight can open as a Track report; a Track view can be queried via Ask — so the product feels like one tool, not three.

**Ask** — type a question in plain English, get an answer.
- Empty state is a centred landing with a hero input and six suggested questions across categories (Hospitals, Claims, Enrolment, Performance).
- Once a query is submitted, the layout flips to a chat-style conversation with the input pinned to the bottom.
- Result cards show a table on the left and a horizontal bar chart on the right (single colour, not coloured-by-category — query shapes are too varied for reliable colour semantics).
- Powered by the Chatbot backend.

**Discover** — a feed of pre-computed insights, refreshed periodically.
- A flat list of one-line headlines with key numbers bolded inline (the biggest scanability upgrade — numbers need to pop out of prose).
- Category chips at the top filter by theme (Claims & Treatment, Hospital Infrastructure, Beneficiary Enrolment).
- Each row expands on click to show numbered detail items and two cross-links: "Open as Track report" and "Ask a follow-up question".
- The insights themselves are sourced from the MetaInsights pipeline.

**Track** — a three-column geographic explorer.
- Reports column on the left (Specialty Coverage, Hospital Performance, Beneficiary Enrolment).
- Specialty filter list with search in the middle.
- Leaflet + OpenStreetMap choropleth map on the right, showing block-level coverage for the selected specialty, with a "Most underserved blocks" panel and an amber-to-deep-brown intensity legend.

#### Design principles

- **Restraint.** One accent colour (saffron), used only on eyebrow labels and active-state indicators. Ink, not teal, is the primary CTA colour.
- **Hierarchy through typography.** Fraunces (display serif) for headlines, Inter for UI; tabular figures everywhere numbers appear.
- **Density where it helps, whitespace where it doesn't.** Dense insight lists; generous landing pages.
- **No decorative icons with assigned colours**, no per-category chart colouring, no left sidebar — top bar is the entire navigation surface.

---

## How the pieces fit together

```
ab_data/ (synthetic CSVs)
    │
    ├──► Metainsights_anomalies/ ──► ranked findings + executive report
    │                                       │
    │                                       ▼
    │                                Frontend "Discover" feed
    │
    └──► Chatbot/backend/ (DuckDB query engine)
                            │
                            ▼
                    Frontend "Ask" mode
                            │
                            ▼
                    Frontend "Track" mode (geographic explorer)
```

The three components share the dataset but are otherwise loosely coupled — each can be developed and run independently.

---

## Repo layout

```
AB_UP_insights/
├── ab_data/                       # 21 synthetic CSVs + dataset README
├── Metainsights_anomalies/        # automated insight-discovery pipeline
│   ├── src/                       # phase1_pipeline, phase2_engine, phase4a/b, phase5_ranking, phase5b_report
│   ├── views/                     # 4 analytical Parquet views built by phase 1
│   ├── metainsights/              # candidate + ranked JSON per view
│   ├── reports/                   # executive markdown / PDF + diagnostic reports
│   ├── Markdown_files/            # per-phase spec sheets
│   └── README_MetaInsight_System.md
├── Chatbot/
│   └── backend/                   # FastAPI + DuckDB query router
│       ├── query_router/          # intent classifier, entity extractor, dashboard + template catalogues
│       ├── sql/                   # cache table DDL
│       └── main.py                # FastAPI app
├── frontend/
│   ├── ab-dashboard-main/         # Vite + React dashboard (Ask / Discover / Track)
│   └── Frontend_visuals_upgrade/  # in-progress redesign — DESIGN_SPEC + mockup
├── scripts/                       # utility scripts
└── README.md                      # this file
```

---

## Status

Proof of concept. The dataset is synthetic, the analytical pipeline is implemented end-to-end, and the dashboard is functional with an in-progress visual redesign. Designed to demonstrate the workflow and validate the architecture; not production-hardened.
