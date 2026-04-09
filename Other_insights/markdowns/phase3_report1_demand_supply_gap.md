# Phase 3 — Narrative Report: Demand-Supply Gap Analysis

## Objective

Generate a plain-language markdown report (`report_demand_supply_gap.md`) that a senior state bureaucrat can read, understand, and act on without needing to interpret charts or data tables. The report should read like a briefing note — clear findings, specific locations named, and actionable implications.

**Audience:** State-level health officials (Principal Secretary, Mission Director, SHA CEO) and district-level officers (CMOs, District Magistrates). Assume they understand the PM-JAY scheme but are not data analysts.

**Tone:** Factual, direct, professional. No jargon. No hedging unless genuinely uncertain. Use phrases like "X block has Y problem" not "the data suggests there may be an indication of a potential issue."

**Length target:** 3,000–5,000 words for the main report body. Annexures can be longer.

---

## Input Files

All from `./analytics/`:
- `gap_utilization_scores.parquet` — 641 rows (block-level utilization and supply flags)
- `gap_specialty_matrix.parquet` — 7,138 rows (block × specialty gaps)
- `gap_disease_burden.parquet` — 3,717 rows (block × disease category infrastructure mismatch)
- `gap_portability_flows.parquet` — 641 rows (block-level patient retention/leakage)
- `gap_district_patient_flows.parquet` — 5,080 rows (district-to-district flow matrix)
- `gap_card_dropoff.parquet` — 641 rows (block-level enrolment-to-card drop-off)
- `gap_repeat_utilization.parquet` — 641 rows (block-level repeat visit patterns)
- `gap_seasonal_patterns.parquet` — 23,076 rows (block × month surge flags)
- `gap_seasonal_summary.parquet` — 641 rows (block-level seasonal profile)
- `gap_delisted_impact.parquet` — 23 rows (delisted hospital impact)

Also reference for context:
- `../intermediate/int_demand_supply.parquet` — for state-level aggregate numbers
- `../intermediate/int_enrolment_monthly.parquet` — for enrolment trend context

---

## Report Structure

### Title Page

```
AYUSHMAN BHARAT PM-JAY — UTTAR PRADESH
Demand-Supply Gap Analysis Report

Prepared for: State Health Agency, Uttar Pradesh
Data Period: [MIN month] to [MAX month from int_demand_supply]
Report Generated: [current date]
```

---

### Section 1: Executive Summary (400-600 words)

**Purpose:** Give the reader the full picture in 2 minutes.

**Content — compute these from the data:**

Opening paragraph — state-level context:
- Total beneficiaries enrolled across UP (from gap_utilization_scores: SUM of total_beneficiaries_enrolled)
- Total cases over the data period (SUM of total_cases_all_months)
- State-wide utilization rate (total distinct beneficiaries with cases / total enrolled)
- Total hospitals and beds (SUM from supply columns)

Second paragraph — headline findings (the 3-4 most important findings, prioritized by population impact):
- How many blocks have the `high_enrolment_low_utilization` flag? What share of total enrolled beneficiaries do they represent?
- How many blocks have `zero_supply` (no hospital at all)? Name the top 2-3 by enrolled population.
- Top specialty with the most unmet demand across the state (from gap_specialty_matrix where gap_flag = True, summed by specialty).
- How many blocks have critical infrastructure mismatches (from gap_disease_burden where infrastructure_mismatch = True)?

Third paragraph — what this means:
- A plain-language statement like: "An estimated [X] enrolled families live in blocks where the nearest empanelled hospital offering [specialty] is in a different block or district. These families must travel for care or go without."

Final paragraph — what the report covers:
- Brief roadmap of the sections that follow.

---

### Section 2: Where People Can't Access Care (800-1200 words)

**Purpose:** The core finding — where are the biggest access gaps?

**Prioritization logic:** Rank findings by number of affected beneficiaries, not by statistical extremity.

**Sub-section 2.1: Blocks with High Enrolment but Low Utilization**

From `gap_utilization_scores`:
- Count blocks where `high_enrolment_low_utilization` = True.
- List the top 10, showing: block name, district, enrolled beneficiaries, utilization rate.
- Group these blocks by district — are there districts with multiple problem blocks? Name them.
- Provide context: "The state average utilization rate is [X%]. These blocks are at [Y%] or below, meaning [interpret: for every 100 enrolled families, only Y have used the scheme]."

**Sub-section 2.2: Blocks with No Hospital or Single Hospital Dependency**

From `gap_utilization_scores`:
- Count blocks with `zero_supply` = True. List them with enrolled population.
- Count blocks with `single_hospital_dependency` = True.
- For single-hospital blocks, note total enrolled beneficiaries depending on that one facility.
- Connect to delisted impact: from `gap_delisted_impact`, are any of the single-hospital blocks' only hospitals delisted? If so, call this out as an emergency.

**Sub-section 2.3: Where Patients Are Travelling for Care**

From `gap_portability_flows`:
- State the overall local retention rate (mean of `local_retention_rate` across all blocks).
- List the 10 blocks with the lowest `local_retention_rate` — these are blocks where most patients leave for care elsewhere.
- From `gap_district_patient_flows` (FILTER OUT rows where origin_district = destination_district): identify the top 10 cross-district flows by flow_count. Present as: "[X] patients from [origin district] travelled to [destination district] for treatment."
- Identify net exporter districts (negative net_flow from the flow table): "Districts that are losing patients include [list]. This suggests inadequate local capacity."
- Identify net importer districts: "Districts receiving patients from elsewhere include [list], indicating they serve as regional hubs."

---

### Section 3: What's Missing Where (800-1200 words)

**Purpose:** Specific gaps — which specialties and infrastructure are absent where they're needed.

**Sub-section 3.1: Specialty Gaps**

From `gap_specialty_matrix`:
- State-level summary: How many block × specialty combinations have `gap_flag` = True? How many have `gap_severity` = NO_SUPPLY?
- Rank specialties by total unmet cases (SUM of `cases_demanding` where `gap_flag` = True, grouped by specialty).
- For the top 5 specialties with the most unmet demand:
  - Name the specialty (use full name, not code — e.g., "Obstetrics & Gynaecology" not "OBG").
  - State unmet cases and estimated revenue leakage.
  - List the top 3 blocks by unmet cases for that specialty.
- Write a connecting sentence: "Obstetrics & Gynaecology has the highest unmet demand, with [X] cases across [Y] blocks where no local hospital offers this specialty. These [Z] women had to travel outside their block or go without care."

**Sub-section 3.2: Infrastructure Mismatches**

From `gap_disease_burden`:
- Count blocks where `infrastructure_mismatch` = True, grouped by disease category.
- Highlight the most critical mismatches — prioritize by:
  1. Maternal/Neonatal cases with no labour room (life-threatening)
  2. Injury cases with no casualty/OT (time-critical)
  3. Surgical cases with no OT
  4. NCD cases with no ICU/HDU
  5. Communicable with no general ward (least critical since these are more common)
- For each critical category, name the top 3-5 blocks affected and the number of cases.
- Frame it: "In [X] blocks, patients presented with conditions requiring surgery, but no hospital in the block has a fully equipped operating theatre."

**Sub-section 3.3: Impact of Delisted Hospitals**

From `gap_delisted_impact`:
- How many hospitals are delisted? (COUNT rows)
- How many blocks lost their sole provider? (COUNT where `sole_provider_delisted` = True)
- How many blocks lost majority capacity? (COUNT where `majority_capacity_lost` = True)
- List specific blocks where delisting created critical gaps, with bed counts before and after.
- List specialties lost (from `specialties_lost` column) — "Block X in District Y lost its only [specialty] provider when [hospital name] was delisted."

---

### Section 4: Administrative Barriers (400-600 words)

**Purpose:** Gaps that aren't about hospitals or beds but about the scheme's own processes.

**Sub-section 4.1: Enrolment-to-Card Drop-off**

From `gap_card_dropoff`:
- State-wide card activation rate (weighted average of `card_activation_rate`).
- Count blocks with `high_drop_off` = True.
- List top 10 blocks by `drop_off_rate`.
- Count blocks with `high_rejection` = True.
- Frame: "In [X] blocks, more than [Y%] of enrolled beneficiaries do not have an active Ayushman card. Without an active card, these families cannot access cashless treatment even though they are enrolled in the scheme."

**Sub-section 4.2: Repeat Visits**

From `gap_repeat_utilization`:
- State-wide repeat rate (weighted average of `repeat_rate`).
- Count blocks with `high_repeat_rate` = True.
- Count blocks with `possible_treatment_failure` = True.
- For blocks flagged for possible treatment failure, list top 5 with their repeat rates and dominant pattern.
- Frame: "In [X] blocks, a high proportion of patients return to the same hospital for the same procedure. While some repeats are expected (e.g., follow-up care), a high rate of same-procedure same-hospital readmissions may indicate incomplete initial treatment."

---

### Section 5: Seasonal Patterns (300-500 words)

**Purpose:** When do demand surges happen, and are they predictable?

From `gap_seasonal_summary`:
- How many blocks have `is_seasonal` = True?
- What are the most common peak months across blocks? (mode of `peak_months`)
- What disease category drives the most surges? (mode of `peak_disease_category`)
- List 5 blocks with the highest `seasonality_index` — these have the most volatile demand.
- Frame: "Seasonal surges are predictable. [X] blocks show clear seasonal patterns, with cases peaking in [months]. The primary driver is [disease category], consistent with [monsoon-related communicable diseases / winter respiratory infections / etc.]. Pre-positioning resources in these blocks during peak months could reduce pressure on facilities."

---

### Section 6: Division-Level Summary Table (data table)

**Purpose:** A quick-reference lookup for each of the 18 divisions.

Aggregate key metrics from the block-level data up to division level:

| Column | Source |
|--------|--------|
| Division | Roll up |
| Total Enrolled Beneficiaries | SUM |
| Utilization Rate | Weighted avg |
| Blocks with Zero Supply | COUNT |
| Top Specialty Gap | Specialty with most unmet cases |
| Patient Leakage Rate | Weighted avg of leakage_rate |
| Card Drop-off Rate | Weighted avg |
| Seasonal Blocks | COUNT where is_seasonal |

Present as a formatted markdown table.

---

### Section 7: District-Level Summary Table (data table)

Same as Section 6 but for all 75 districts:

| Column | Source |
|--------|--------|
| District | Roll up |
| Division | From geography |
| Total Enrolled | SUM |
| Utilization Rate | Weighted avg |
| Total Cases | SUM |
| Blocks with Gaps (any flag) | COUNT |
| Top Unmet Specialty | Specialty with most unmet cases in this district |
| Net Patient Flow | Net flow from gap_district_patient_flows (positive = importer, negative = exporter) |
| Card Activation Rate | Weighted avg |

Present as a formatted markdown table sorted by utilization rate ascending (worst first).

---

### Annexure A: Block-Level Detail — High Priority Blocks

List all blocks flagged as `high_enrolment_low_utilization` OR `zero_supply` OR `single_hospital_dependency`, sorted by total enrolled beneficiaries descending.

For each block, one row with: block, district, division, enrolled beneficiaries, utilization rate, total hospitals, total beds, specialty gaps (count), infrastructure mismatches (count), card drop-off rate, leakage rate, seasonal flag.

Present as a markdown table.

---

### Annexure B: Full Specialty Gap Detail

From `gap_specialty_matrix` where `gap_flag` = True, sorted by cases_demanding descending.

Columns: block, district, specialty_name, cases_demanding, hospitals_offering, gap_severity, estimated_revenue_leakage, nearest_block_with_supply.

Present as a markdown table.

---

## Writing Rules

1. **Use bullet lists for all findings.** The report should read like a briefing note, not an essay. Each finding is a bullet point. Use short lead-in sentences to introduce groups of bullets, but the findings themselves should be scannable bullet lists. Example:

   **Wrong (prose):**
   "Across Uttar Pradesh, 92 blocks have high enrolment but low utilization. These blocks are concentrated in Lucknow, Varanasi, and Kanpur Nagar divisions. The state average utilization rate is 12%, but these blocks fall below 9%. This means that for every 100 enrolled families, fewer than 9 have accessed the scheme."

   **Right (bullet list):**
   92 blocks have high enrolment but low utilization:
   - These blocks are concentrated in Lucknow, Varanasi, and Kanpur Nagar divisions
   - State average utilization is 12%; these blocks fall below 9%
   - For every 100 enrolled families in these blocks, fewer than 9 have used the scheme
   - Roughly X families are enrolled but not accessing care

2. **Name names.** Always use specific block, district, and division names. Never say "some blocks" when you can say "Mohanlalganj (Lucknow), Chinhat (Lucknow), and Baragaon (Varanasi)."
3. **Translate numbers into meaning.** Don't say "utilization rate is 0.084." Say "only 8 out of every 100 enrolled families have used the scheme."
4. **Lead with the finding, not the methodology.** Wrong: "Analysis of the gap_utilization_scores dataset revealed that..." Right: "92 blocks across UP have high enrolment but low utilization, affecting approximately X families."
5. **Use round numbers in bullet points.** "Roughly 1,000 patients" not "999 patients." Exact numbers belong in tables.
6. **Group related blocks by district.** If 3 blocks in Lucknow are all flagged, say "Three blocks in Lucknow district" not list them separately without connecting them.
7. **Frame gaps as people affected.** "1,010 women needed obstetric care but had no local hospital offering it" is more impactful than "OBG specialty has 1,010 unmet cases."
8. **Don't repeat data across sections.** If a block is mentioned in Section 2, reference it briefly in Section 3 ("the same blocks flagged for low utilization also lack...") rather than restating all the numbers.
9. **Annexures can be dense.** The main report body should be scannable bullets and short tables. Annexures are for reference and can be large tables.
10. **No charts or visualizations.** This is a text report. Tables are fine. Use horizontal rules to separate sections clearly.
11. **Use INR in lakhs for large amounts.** "₹47.3 lakh" not "₹4,730,000". State monetary values in lakhs or crores as appropriate for the magnitude.
12. **Keep bullets concise.** Each bullet should be 1-2 lines. If a bullet needs 3+ lines, break it into sub-bullets.

---

## Technical Instructions

1. Load all 10 parquet files from `./analytics/` plus 2 from `./intermediate/`.
2. Compute all aggregate metrics described above (state-level sums, weighted averages, counts of flags, top-N lists).
3. For the district-to-district flow analysis, **filter out rows where origin_district = destination_district** before identifying top cross-district flows.
4. Write the full report as a single markdown file: `./reports/report_demand_supply_gap.md`.
5. Use `#` for the title, `##` for sections, `###` for sub-sections. Use `---` between major sections.
6. Tables should use standard markdown table syntax.
7. All percentages in prose should be written as whole numbers with % sign (e.g., "8%" not "0.084" or "8.4 percent").
8. After writing the report, print a word count of the main body (excluding annexures) to confirm it falls within 3,000-5,000 words.

---

## Output

Single file: `./reports/report_demand_supply_gap.md`

## Success Criteria

1. Report file exists and is valid markdown.
2. Main body is 3,000-5,000 words.
3. Every finding cites specific block/district names.
4. Executive summary can be read standalone in under 2 minutes.
5. Sections 6 and 7 contain complete division and district summary tables.
6. Annexures contain all flagged blocks and all specialty gaps.
