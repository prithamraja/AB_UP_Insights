# MetaInsight Engine — System Overview

An automated insight discovery system for structured data, built on the MetaInsight framework (Ma et al., SIGMOD 2021). The system takes raw operational data from the PM-JAY health insurance scheme in Uttar Pradesh and produces a ranked, human-readable report of the most important and actionable findings — without any analyst writing a single query.

---

## What Problem Does This Solve?

A dataset with 20+ tables, 200K+ beneficiaries, 22,500 hospital cases, and dozens of measures has millions of possible "views" — slicing by district, breaking down by specialty, measuring claim amounts, and so on. An analyst can't explore all of them manually. Most BI tools show one chart at a time and leave pattern discovery to the user.

This system exhaustively searches the space of possible data views, detects statistical patterns in each one, groups related patterns to find what's common and what's exceptional, scores them for importance and actionability, and presents the top findings as a readable executive briefing. The key output isn't a dashboard — it's structured knowledge: "This pattern holds broadly, except in these specific cases, which deserve investigation."

---

## Conceptual Flow

```
Raw CSVs (21 tables)
    │
    ▼
Phase 1: Ingest, validate, build 4 analytical views
    │
    ▼
Phase 2: Build the MetaInsight engine (1 pattern type, 1 view)
    │
    ▼
Phase 4a: Expand to all 11 pattern types
    │
    ▼
Phase 4b: Run across all 4 views
    │
    ▼
Phase 5a: Rank and deduplicate findings per view
    │
    ▼
Phase 5b: Generate executive report via LLM
    │
    ▼
Final Output: A readable analytical report for a programme officer
```

---

## Phase 1 — Data Ingestion & View Construction

**Purpose:** Transform 21 normalised source tables into 4 flat analytical views optimised for pattern discovery.

The raw data is a synthetic replica of Uttar Pradesh's PM-JAY (Ayushman Bharat) health insurance records: beneficiary enrolment, hospital infrastructure, treatment cases, pre-authorisation, claims, adjudication, and payments. Phase 1 loads all CSVs, casts types, validates referential integrity, and produces a detailed validation report. It does not drop or fix any data quality issues — duplicates, expired licenses, and null rates are intentional and analytically meaningful.

The four views are:

**View 1 — Claims Lifecycle** (~22,500 rows). One row per hospital treatment case, joining the case to its beneficiary, hospital, diagnosis, pre-authorisation, claim, payment, and discharge records. This is the richest view with 13 categorical dimensions (division, district, hospital type, specialty, disease category, gender, age group, etc.), 3 temporal dimensions (month, quarter, year), and 12 numeric measures (amounts claimed/approved/paid, length of stay, settlement turnaround, death flags, etc.).

**View 2 — District-Month Cube** (~3,600 rows). One row per district × month, aggregating enrolment, card issuance, cases, claims, and payments at the district-month level. Designed for temporal trend discovery — what's changing over time in each district.

**View 3 — Hospital Performance** (~7,300 rows). One row per hospital × specialty. Captures bed capacity, staffing, licensing, and treatment volumes. No temporal dimension — focused on structural patterns like underutilisation and specialty gaps.

**View 4 — Beneficiary Journey** (~206,000 rows). One row per beneficiary. Tracks enrolment quality, documentation, card issuance, and whether the beneficiary actually used the scheme. Focused on demographic and geographic equity in scheme uptake.

Each view defines its own set of dimensions (what you can slice and break down by), measures (what you can aggregate), and impact measures (what determines importance). These definitions feed directly into the engine.

---

## Phase 2 — The MetaInsight Engine (Single Pattern Type)

**Purpose:** Implement the full mining pipeline end-to-end on View 1 with one pattern type (Outstanding #1) to validate the architecture before scaling.

The engine follows the paper's framework closely. It works in five stages:

### Stage 1: Enumerate subspaces

A subspace is a filter on the data — like `{division: Lucknow}` or `{gender: M, hospital_type: PUBLIC}`. The engine generates all possible subspaces up to depth 2 (two simultaneous filters), plus the unfiltered dataset (`{*}`). With 13 dimensions of varying cardinality, this produces thousands of subspaces.

### Stage 2: Compute impact and prioritise

For each subspace, compute what fraction of the total dataset it represents using the impact measures (e.g., what share of total cases or total amount paid does Lucknow account for?). Subspaces below 1% impact are pruned. The rest are placed in a priority queue so high-impact slices get analysed first within the time budget.

### Stage 3: Generate data scopes and detect patterns

For each subspace, combine it with every valid breakdown dimension and every measure to form data scopes. A data scope like `⟨{division: Lucknow}, specialty_code, SUM(amount_claimed)⟩` translates to: "Group Lucknow's cases by specialty and sum the claim amounts." The engine runs the aggregation query, then checks whether the resulting distribution has an Outstanding #1 pattern — does one breakdown value (e.g., Cardiology) significantly dominate the rest? Both query results and pattern evaluations are cached to avoid redundant computation.

### Stage 4: Extend patterns into HDPs and identify MetaInsights

When a pattern is found, the engine asks: does this pattern hold across related slices? It extends the data scope in three ways:

- **Subspace extending:** Lucknow has Cardiology as top specialty → do other divisions also have Cardiology on top? Generate sibling data scopes for all 18 divisions.
- **Measure extending:** Cardiology is top by amount_claimed → is it also top by amount_paid, case_count, etc.?
- **Breakdown extending:** Cardiology is top when broken down by month → still top when broken down by quarter?

Each extension produces a Homogeneous Data Pattern (HDP) — a set of comparable patterns. The engine then partitions the HDP using similarity: patterns sharing the same type and highlight are grouped. If a group exceeds τ (default 50%) of the HDP, it's a **commonness**. The rest are **exceptions**, categorised as highlight-change (different top value), type-change (a different pattern type holds), or no-pattern.

The result is a MetaInsight candidate: "Across 14 of 18 divisions, Cardiology has the highest claim amount. But in Jhansi, Orthopaedics leads (highlight-change). In Moradabad, no specialty clearly dominates (type-change)."

### Stage 5: Score each candidate

Each candidate is scored as `conciseness × impact`. Conciseness measures how clean the commonness/exception split is (one dominant commonness with a few exceptions scores higher than a fragmented split). An actionability penalty (controlled by γ) slightly reduces the score of candidates with no exceptions, since they're less actionable. Impact reflects how important the underlying data slice is.

---

## Phase 4a — All 11 Pattern Types

**Purpose:** Expand from one pattern evaluator to eleven, covering both categorical and temporal distributions.

The 11 pattern types are divided into two groups:

**Categorical patterns** (applied when the breakdown is a categorical dimension like specialty or district): Outstanding #1 (one value dominates), Outstanding #Last (one value is notably lowest), Top-Two, Last-Two, Evenness (all values roughly equal), and Attribution (one value accounts for the majority share).

**Temporal patterns** (applied when the breakdown is a temporal dimension like month or quarter): Trend (monotonic direction over time via Mann-Kendall test), Outlier (values exceeding 3 standard deviations from a fitted baseline), Seasonality (repeating cycles detected via autocorrelation), Change Point (significant shift in mean detected via Welch's t-test), and Unimodality (U-shaped valley or inverted-U peak).

Each pattern type has its own statistical evaluator with specific thresholds and minimum data requirements. The engine now iterates over all eligible pattern types for each data scope, and the detect_pattern function implements the paper's fallback logic: if the requested type doesn't match but another type does, the pattern is tagged as OTHER_PATTERN, which becomes a TYPE_CHANGE exception in an HDP.

---

## Phase 4b — All Four Views

**Purpose:** Run the full engine (11 pattern types) independently on each of the four analytical views.

Each view has its own configuration specifying which columns are dimensions, which are temporal, which are measures, and how each measure should be aggregated (SUM for volumes and counts, AVG for rates and pre-computed averages). The configurations also vary in max subspace depth — View 2 uses depth 1 because its two categorical dimensions (division, district) at depth 2 would filter to a single district with no siblings for HDP extension.

View 3 has no temporal dimensions, so only categorical pattern types apply. View 4 is the largest (206K rows) and tests the engine's scalability. Each view runs with its own time budget and produces its own candidate JSON file.

---

## Phase 5a — Ranking & Deduplication

**Purpose:** Take thousands of raw candidates per view and select the top 15 that are individually important and collectively diverse.

The raw mining phase produces massive candidate lists (potentially tens of thousands per view) with significant redundancy — many candidates describe similar findings from slightly different angles. Phase 5a implements the paper's ranking algorithm to select a curated subset.

### Overlap calculation

Two MetaInsight candidates can only overlap if they share the same extending strategy (subspace, measure, or breakdown) and the same pattern type. If they do, the overlap ratio is a weighted combination of how similar their base subspaces are, whether they use the same extending dimension, the same breakdown, and the same measure. The actual overlap penalty between two candidates is `min(score_A, score_B) × overlap_ratio`.

### Greedy selection

The algorithm maximises TotalUse — the sum of individual scores minus all pairwise overlaps. It uses a greedy approximation: start with the highest-scoring candidate, then at each step add whichever remaining candidate increases TotalUse the most. This means a slightly lower-scoring candidate that covers a completely different dimension or pattern type can beat a higher-scoring one that's redundant with what's already selected.

### Presentation layers

**Layer 2P** is a diagnostic report of all raw candidates — score distributions, pattern type breakdowns, and extending strategy distributions per view.

**Layer 3P** is the ranked dashboard — each of the top 15 per view with full structural detail (commonness sets, exceptions, scores) and a template-based natural language summary.

---

## Phase 5b — Executive Report via LLM

**Purpose:** Transform the ranked findings from structured data into a readable executive briefing for a non-technical audience.

The template-based summaries from Phase 5a are technically accurate but read like database output: "Across all division values, CARD and ORTH lead in amount_claimed among specialty_code values." Phase 5b uses Claude to rewrite these into natural prose, guided by a carefully constructed prompt.

Each view's ranked findings are first enriched with quantitative statistics — actual values, percentages, and shares computed from the underlying data. These enriched findings, along with a view description, a column glossary (translating codes like CARD → Cardiology), and detailed instructions on tone and formatting, are sent to the LLM.

The LLM does not re-analyse data or make analytical judgments. The ranking and pattern detection are pre-computed; the LLM is purely a translation layer from structured knowledge to prose. It groups findings thematically (e.g., "Financial Patterns", "Geographic Variations"), highlights exceptions as the actionable story, cites specific numbers, and ends each section with follow-up questions for the programme officer.

The output is a single Markdown report with four sections — one per view — readable by a state-level PM-JAY programme officer with no data science background.

---

## Key Design Decisions

**Exhaustive search, not hypothesis-driven.** The system doesn't require the user to specify what patterns to look for. It enumerates all valid combinations of subspace × breakdown × measure × pattern type and lets the scoring surface what's interesting. Domain knowledge is encoded in the view configuration (which columns to include, which measures to prioritise) rather than in the search.

**Commonness + exceptions as the unit of insight.** A single pattern ("Cardiology has the highest claims") is a fact. A MetaInsight ("Cardiology has the highest claims in 14 of 18 divisions, except Jhansi where Orthopaedics leads") is structured knowledge — it tells you what's generally true AND where to look for anomalies. This is the core contribution of the MetaInsight framework.

**Scoring balances conciseness, importance, and actionability.** A finding that's true everywhere with no exceptions is concise and important but not actionable. A finding with a clean majority and a few notable exceptions scores highest because it gives the user both general knowledge and specific entry points for further investigation.

**Ranking favours diversity over raw score.** The greedy deduplication ensures the final top-15 list covers different pattern types, different dimensions, and different measures — not 15 variations of the same finding.

**LLM as translator, not analyst.** The LLM receives pre-validated, pre-ranked structured findings and converts them to prose. It cannot hallucinate patterns because every claim it makes is grounded in the structured MetaInsight data. The analytical work is done entirely by the engine.
