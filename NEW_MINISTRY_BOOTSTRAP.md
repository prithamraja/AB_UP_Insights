# Bootstrap guide: deploying this system for a new ministry

You are a fresh instance working in a **copy** of the AB_UP_insights codebase. Your job is
to adapt it to a new ministry/domain (e.g. a Ration/PDS ministry, an Education ministry).
This document tells you what the system is, which files are reusable engine code, which
files are domain content that must be re-authored, and the order to build in.

Alongside this document you should receive a **ministry context bundle**:
- Data dictionary (schemas, grains, PK/FK, code lists/enums, update cadence)
- Sample data extract (CSVs or DB access)
- Question catalogue material (target user questions, existing MIS report formats,
  review-meeting templates, KPI definitions with exact numerator/denominator rules)
- Reference/master data (geography hierarchy, facility master, local-language aliases)
- A named domain expert (SME) for metric sign-off and eval grading

If any of these are missing, flag it to the operator before building — especially
ratified metric definitions, which every SQL template will encode.

---

## 1. What this product is

A three-mode analytics product for government programme officers who don't write SQL:

- **Ask** — natural-language questions answered from a *curated catalogue* of vetted SQL
  queries (never free-form LLM-generated SQL). FastAPI backend in `Chatbot/backend/`.
- **Discover** — an automated insight-mining pipeline (MetaInsight framework, Ma et al.
  SIGMOD 2021) that exhaustively searches flat analytical views for statistical patterns
  and emits ranked "this holds broadly, except here" findings plus an LLM-written
  executive report. Lives in `Metainsights_anomalies/`.
- **Track** — a geographic choropleth explorer (frontend; out of scope for this guide).

The original deployment: India's PM-JAY health insurance scheme, Uttar Pradesh, on
synthetic data. Read `Archive of md files/README.md` for the full original overview.

### The two load-bearing design principles — do not violate these

1. **No free-form SQL generation.** Every answerable question maps to a pre-authored,
   validated SQL entry (a cached "dashboard" query or a parameterised template). The LLM
   only routes questions to catalogue entries and extracts parameter entities. This is
   both the accuracy story and the security/compliance story (a ministry can audit the
   finite query set).
2. **LLM as translator, never analyst.** In Discover, the mining engine does all
   analysis; the LLM only turns pre-validated structured findings into prose. It cannot
   hallucinate a pattern because every claim is grounded in engine output.

### How Ask routes a question (all generic machinery)

```
question → preprocess/normalize
         → vector retrieval: embed question, top-K nearest catalogue questions
         → LLM reranker: pick the one right query_id (or no_match)
         → entity extraction (LLM) for the template's parameter slots
         → entity validation: exact → alias → fuzzy match against the registry
         → execute: cached dashboard result OR parameterised SQL against DuckDB/Postgres
         → rows + chart hint (+ follow-up context, clarification chips, suggestions)
```

Three-zone confidence handling (`config.py` thresholds): high similarity → answer;
ambiguous → clarification chips; low → graceful fallback with suggestions.

### How Discover works

```
raw tables → config-driven view builder (domain_pack/ + src/build_views.py)
           → 3–4 flat analytical Parquet views
           → mining engine (phase4b over all views, 11 pattern types)
           → scoring + greedy diversity ranking (phase5)
           → LLM report generation with column glossary (phase5b)
           → executive markdown/PDF
```

A **view** = one denormalized table tuned for a question family. The UP archetypes,
which transfer to most social programmes:
1. *Transaction lifecycle* (one row per case/transaction — richest view),
2. *Geography × month cube* (temporal trends),
3. *Facility performance* (facility × service offered; zero-activity rows kept — that's
   the underutilisation signal),
4. *Beneficiary journey* (one row per beneficiary; equity analysis).

---

## 2. File inventory: reuse vs. re-author

Legend: **KEEP** = generic engine, use unchanged. **EDIT** = generic code with embedded
domain config/prompts — update the marked parts in place. **REWRITE** = pure domain
content, author from scratch for the new ministry. **SKIP** = don't copy at all.

### `Metainsights_anomalies/`

| Path | Status | Notes |
|---|---|---|
| `src/build_views.py` | KEEP | Generic config-driven view builder (reads `domain_pack/`). |
| `src/parity_check.py` | KEEP | View-comparison harness (useful when iterating on view SQL). |
| `src/phase2_engine.py` | EDIT | Engine is generic; the `VIEW*_CONFIG` declarations near the top (dimensions / temporal_dimensions / measures / impact_measures per view) are domain config — replace with the new views' columns. |
| `src/phase4a_engine.py`, `src/phase4b_engine.py` | EDIT | Same: engine generic, imports/declares the `VIEW*_CONFIG`s. Number of views can differ from 4; adjust the run list in phase4b. |
| `src/phase5_ranking.py` | KEEP | Generic greedy diversity ranking. |
| `src/phase5b_report.py` | EDIT | Report generator is generic; the per-view `column_glossary` dicts and the audience/tone framing in `build_view_prompt()` are domain content. Also set the report language (e.g. Bahasa Indonesia) here. |
| `src/md_to_pdf.py`, report-generation helpers | KEEP | |
| `src/data_fix.py` | SKIP | Repairs defects specific to the UP *synthetic* dataset. Never copy. |
| `domain_pack/` (sources.yaml, derived_columns.sql, views/*.sql, validation.yaml) | REWRITE | This IS the domain. The existing files are your worked example; `domain_pack/README.md` documents the format — read it first. |
| `views/`, `metainsights/`, `reports/` | SKIP | Build outputs. Regenerated per domain. |
| `Markdown_files/` | SKIP (optional reference) | UP-era phase specs; useful background only. |

### `Chatbot/backend/`

| Path | Status | Notes |
|---|---|---|
| `main.py`, `db.py`, `db_adapters.py`, `db_factory.py`, `startup.py`, `start.py`, `init_supabase.py`, `sql/`, `requirements.txt`, `railway.json` | KEEP | App shell, DB abstraction (DuckDB local / Postgres deploy), cache seeding. Point config at the new data location. |
| `query_router/router.py` | KEEP | Core routing logic. |
| `query_router/models.py`, `context_store.py`, `operations.py`, `echo.py`, `vector_retriever.py` | KEEP | |
| `query_router/config.py` | EDIT | Model names, retrieval K, confidence thresholds. Thresholds (`NO_MATCH_LOWER`, `CLARIFY_UPPER`, margin) were calibrated on the UP catalogue — re-calibrate once the new catalogue + eval set exist. |
| `query_router/column_metadata.py` + `column_types.json` | EDIT | Generic classifier; review the pattern rules in the JSON for new-domain column names. |
| `query_router/entity_validator.py` | EDIT | Validation cascade (exact→alias→fuzzy) is generic. `REGISTRY_CONFIG` + the DB queries in `_load()` + `_STATE_LEVEL_TERMS` are domain content: new entity types, new source tables, new aliases (put local-language synonyms here). |
| `query_router/entity_extractor.py` | EDIT | Generic LLM extraction; refresh the few-shot examples. |
| `query_router/preprocessor.py`, `fallback.py`, `suggestions.py`, `zones.py`, `followup_classifier.py` | EDIT | Generic logic with domain example strings and user-facing copy — light touch-ups. |
| `query_router/reranker.py` | EDIT | Reranking logic generic; the system prompt contains domain framing and disambiguation rules (e.g. "claims rejection vs enrolment rejection") — rewrite those rules for the new domain's ambiguity pairs as you discover them in evals. |
| `query_router/template_catalog.py` | REWRITE | The parameterised SQL templates. The biggest authoring task. |
| `query_router/dashboard_catalog.py` | REWRITE | Pre-computed/cached queries for the most common questions. |
| `query_router/intent_catalog.py` + `intent_classifier.py` | REWRITE (or drop) | Legacy routing path (`USE_VECTOR_RETRIEVAL=False`). The vector path is the default and primary. Recommendation: build the vector path only; keep the legacy path unbuilt unless needed. |
| `recall_eval.py` | KEEP (harness) / REWRITE (gold set) | Eval harness is generic; the gold question→query_id set is per-domain and non-negotiable — build it early. |
| `tests/` | EDIT | Test logic mostly generic, fixtures are UP-specific. |

### Not part of the bundle
`ab_data/` (replaced by ministry data), `frontend/` (separate workstream),
`Other_insights/`, `scripts/`, `Archive of md files/` (except the README as background),
`*.tif`.

---

## 3. Build order

Work in this order; each stage has an acceptance gate. Discover comes before Ask —
it ships value fastest and its findings tell you which Ask questions matter.

**Stage 0 — Understand the domain (no code).** Read the data dictionary and question
material. Produce a short mapping doc: the 3–4 views for this domain (grain, dimensions,
measures per view), the entity types users will reference (geography levels, facility,
commodity/service, program-status enums, time), and the metric definitions with SME
sign-off. *Gate: operator + SME approve the mapping doc.*

**Stage 1 — Data foundation.** Author `domain_pack/` (sources, casts, derived columns,
view SQL, validation checks). Run `build_views.py`. Send the validation report to the
ministry — data-quality findings build trust and surface issues early.
*Gate: views build clean; row counts and spot-check aggregates confirmed by SME.*

**Stage 2 — Discover.** Write the `VIEW*_CONFIG`s and the column glossary; run
phase4b → phase5 → phase5b. Hold a calibration session with the SME on the top-15
findings per view: real / already-known / spurious? Iterate dimensions, measures, and
engine params (tau, min_impact) accordingly. *Gate: SME rates the executive report
useful; no nonsense findings in the top ranks.*

**Stage 3 — Ask catalogue.** From the question material + Discover findings, author:
dashboard entries (the ~top common questions, pre-computable), templates (parameterised
variants), entity registry + aliases, reranker candidate descriptions. **Author
templates against the flat views wherever possible, not the normalized tables** — it
halves SQL authoring and keeps Ask/Discover numbers consistent. Build the gold eval set
(≥100 questions, phrased the way real officers talk, in their language(s)) as you go.
*Gate: recall@K and end-to-end routing accuracy on the gold set at parity with the UP
deployment (recall@30 ≈ 97% was the UP benchmark).*

**Stage 4 — Tune and pilot.** Re-calibrate confidence thresholds on eval data; run UAT
with real officers; feed unanswered questions back into the catalogue.

---

## 4. Hard-won lessons from the UP deployment (don't relearn these)

- **Never run npm or DuckDB writes on a Google Drive-synced directory.** DuckDB can't
  create temp files there and npm breaks. Always run pipelines and servers from a local
  working directory; sync artifacts back if needed.
- **Reranker descriptions should be family-level.** Most query_ids are parameter
  variants of one question family (state-wide vs {district} vs {block}). Write one
  strong description per family; let the reranker pick the variant from the parameter
  structure ({braces} in the abstract question). Per-variant descriptions caused
  confusion, not precision.
- **Eval mismatch counts are noisy.** Two catalogue entries can both be correct answers
  to one phrasing. Grade evals by "acceptable answer set", not exact-ID match, or you'll
  chase phantom regressions.
- **Keep zero-activity rows in the facility-performance view** (LEFT JOIN from the
  offerings/master table). Facilities with no activity are the underutilisation signal —
  an inner join silently deletes the most important finding.
- **Validation logs, never fixes.** Data-quality defects (duplicates, expired licenses,
  null gaps) are analytically meaningful; the pipeline must preserve them and report
  them, not clean them.
- **Multilingual**: local-language and code-mixed phrasings (Hinglish in UP) worked
  through the embedding retriever, but only after aliases and eval questions were
  authored bilingually. Budget for this explicitly; don't assume transfer.
- Entity aliases are where colloquial usage lives ("sarkari"→PUBLIC, "noida"→Gautam
  Buddha Nagar). Expect to grow this list continuously from query logs.

## 5. Deployment shapes (decide with the operator)

- **We host everything** (default for pilots): DuckDB in-process, data copied to our
  environment. What the UP deployment does.
- **View sync**: ministry runs `build_views.py` inside their perimeter on a schedule;
  only the flat aggregate views leave. Requires Stage-3 templates to target views only.
  Preferred when raw data can't leave the ministry.
- **Template gateway**: a small agent next to the ministry DB executes vetted catalogue
  SQL by (template_id, params) — no SQL crosses the wire. For live-freshness needs.

The LLM touches only questions, catalogue text, entity names, and aggregated findings —
never row-level data. Lead with this when clearing LLM API use with the ministry.
