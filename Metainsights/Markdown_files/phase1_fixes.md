# Phase 1 Pipeline — Fixes

Four issues identified during code review. Apply in order.

---

## Fix 1 (Critical): View 1 — Deduplicate preauth before joining

**Problem:** `cm_preauth_request` is joined to `cm_case` on `case_id` (line ~629), but a case can have multiple preauth requests (initial submission + re-submissions after queries). This multiplies rows and breaks the one-row-per-case grain. View 1 could end up with significantly more than 22,500 rows.

**Location:** Section 5, between Step B and Step E (around line 629-633).

**Current code:**
```python
v1 = v1.merge(
    tables["cm_preauth_request"][["preauth_id", "case_id", "status"]].rename(
        columns={"status": "preauth_status"}
    ),
    on="case_id", how="left",
)
```

**Fixed code:**
```python
# Deduplicate preauth: keep the latest preauth request per case
# (final status is the most meaningful — reflects outcome after any re-submissions)
preauth_deduped = (
    tables["cm_preauth_request"]
    .sort_values("initiated_at")
    .groupby("case_id", as_index=False)
    .last()[["preauth_id", "case_id", "status"]]
    .rename(columns={"status": "preauth_status"})
)

v1 = v1.merge(preauth_deduped, on="case_id", how="left")
```

**Verification:** After building View 1, confirm `len(view1) == len(tables["cm_case"])`. If these don't match, the dedup didn't work correctly.

---

## Fix 2 (Documentation): View 2 — Document the cumulative_beneficiaries denominator choice

**Problem:** `cumulative_beneficiaries` is a running total of beneficiaries by `created_at` (enrolment date), not by card issuance date. So `claims_per_1000_beneficiaries` measures utilization against *enrolled* population, not *card-holding* population. Both are valid — but the choice should be explicit so downstream analysis doesn't misinterpret the metric.

**Location:** Section 6, around lines 810-827.

**Fix:** Add a comment block above the cumulative calculation:

```python
# ── Cumulative enrolled beneficiaries ────────────────────────────────────
# NOTE: This counts beneficiaries by their enrolment date (created_at),
# not by card issuance date. Therefore claims_per_1000_beneficiaries
# represents: "cases per 1000 enrolled beneficiaries" (including those
# who may not yet have received their Ayushman card).
#
# Alternative: use cumulative cards_issued for a stricter denominator
# measuring utilization among card-holders only. We use enrolment as
# it gives the broader eligible-population view, which is more relevant
# for scheme coverage analysis.
v2 = v2.sort_values(["home_district_code", "month"])
v2["cumulative_beneficiaries"] = (
    v2.groupby("home_district_code")["new_beneficiaries"].cumsum()
)
```

No code logic change required — this is purely a documentation fix.

---

## Fix 3 (Validation): View 3 — Add a cross-view case count consistency check

**Problem:** The View 3 join path goes through `preauth → procedure_line → ref_hbp_procedure_master` to get `specialty_code`. Cases without a preauth or without a procedure line will have null specialty and won't appear in any hospital-specialty aggregation bucket. This means `SUM(cases_treated)` across all of View 3 could be less than View 1's row count.

This is acceptable behaviour (we can only assign cases to specialties when the procedure line exists), but we should validate and log the gap so it doesn't cause confusion later.

**Location:** Section 11 (Post-View Validation Checklist), after the existing checks (around line 1244).

**Add this check:**

```python
# ── Cross-view case count consistency ────────────────────────────────────
_v1_total = len(view1)
_v3_total = int(view3["cases_treated"].sum())
_coverage = _v3_total / _v1_total * 100 if _v1_total > 0 else 0
_chk(
    _coverage > 80,
    f"View 3 SUM(cases_treated) covers {_coverage:.1f}% of View 1 cases "
    f"({_v3_total:,} vs {_v1_total:,}). Gap = cases with no procedure line / specialty."
)
```

If coverage drops below 80%, something is wrong with the join chain. Above 80% is expected given that some cases may lack preauth or procedure data.

---

## Fix 4 (Completeness): Add missing tables to PK uniqueness check

**Problem:** `PK_MAP` in CHECK 2 (line 322) is missing two tables: `hm_hospital_bank_account` and `cm_claim_document`. These aren't view anchors, so missing them won't break anything, but the validation report should be comprehensive.

**Location:** Section 3, the `PK_MAP` dictionary (around line 322).

**Current code:**
```python
PK_MAP = {
    "bm_household":             "household_id",
    "bm_beneficiary":           "beneficiary_id",
    "bm_id_document":           "id_doc_id",
    "bm_enrolment_request":     "enrolment_request_id",
    "bm_card":                  "card_id",
    "hm_hospital":              "hospital_id",
    "hm_license_certificate":   "hospital_license_id",
    "hm_specialty_offered":     "hospital_specialty_id",
    "hm_staff":                 "staff_id",
    "cm_case":                  "case_id",
    "cm_case_diagnosis":        "case_diagnosis_id",
    "cm_preauth_request":       "preauth_id",
    "cm_preauth_procedure_line": "preauth_proc_id",
    "cm_discharge":             "discharge_id",
    "cm_claim":                 "claim_id",
    "cm_adjudication_event":    "event_id",
    "cm_payment":               "payment_id",
    "ref_hbp_procedure_master": "hbp_procedure_code",
}
```

**Fixed code:**
```python
PK_MAP = {
    "bm_household":             "household_id",
    "bm_beneficiary":           "beneficiary_id",
    "bm_id_document":           "id_doc_id",
    "bm_enrolment_request":     "enrolment_request_id",
    "bm_card":                  "card_id",
    "hm_hospital":              "hospital_id",
    "hm_hospital_bank_account": "hospital_bank_id",      # <-- added
    "hm_license_certificate":   "hospital_license_id",
    "hm_specialty_offered":     "hospital_specialty_id",
    "hm_staff":                 "staff_id",
    "cm_case":                  "case_id",
    "cm_case_diagnosis":        "case_diagnosis_id",
    "cm_preauth_request":       "preauth_id",
    "cm_preauth_procedure_line": "preauth_proc_id",
    "cm_discharge":             "discharge_id",
    "cm_claim":                 "claim_id",
    "cm_claim_document":        "claim_doc_id",           # <-- added
    "cm_adjudication_event":    "event_id",
    "cm_payment":               "payment_id",
    "ref_hbp_procedure_master": "hbp_procedure_code",
}
```

---

## Summary

| # | Severity | View | Issue | Action |
|---|----------|------|-------|--------|
| 1 | **Critical** | View 1 | Preauth join can multiply rows, breaking case grain | Dedup preauth to one-per-case before join |
| 2 | Documentation | View 2 | Unclear whether denominator is enrolled or card-holding | Add comment documenting the choice |
| 3 | Validation | View 3 | Case count gap vs View 1 not surfaced | Add cross-view consistency check |
| 4 | Completeness | Layer 0 | Two tables missing from PK check | Add `hm_hospital_bank_account` and `cm_claim_document` |

After applying all fixes, re-run the pipeline and confirm:
- View 1 row count matches `cm_case` row count exactly
- All existing validation checks still pass
- The new View 3 cross-view check reports >80% coverage
- `hm_hospital_bank_account` and `cm_claim_document` PKs are reported as unique
