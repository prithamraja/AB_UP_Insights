"""
Single-call intent classifier with few-shot examples.

One LLM call returns {"domain": "...", "intent": "..."} as structured JSON.
All 123 intents are grouped by domain in the prompt with 1-2 example queries each.
"""
import json
from openai import OpenAI
from .config import (
    ABSTRACTION_MODEL, LLM_TEMPERATURE, LLM_TIMEOUT_SECONDS,
    LLM_MAX_TOKENS_CLASSIFY, REASONING_MODELS,
)
from .intent_catalog import INTENT_LIST_BY_DOMAIN

# ── Domain descriptions ──────────────────────────────────────────────────────

_DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "ENROLMENT":    "Beneficiary registration, households, cards, duplicates, profile completeness, utilization gaps, enrolment trends",
    "HOSPITAL":     "Hospital infrastructure, capacity, accreditation, staff, beds, licensing, compliance",
    "CLAIMS":       "Case volumes, claim status, approval/rejection rates, settlement TAT, financial summaries, pre-auth",
    "SPECIALTY":    "Medical specialty utilization, procedures, diagnoses, disease categories, seasonal patterns",
    "PORTABILITY":  "Portability cases (patients treated outside home district or state)",
    "OUTCOMES":     "Patient outcomes: mortality, LAMA/DAMA, readmissions, biometric auth, medicine provision",
    "ACCESS_EQUITY":"Geographic access, patient flows, gender equity, elderly utilization, underperforming districts",
    "COMPLIANCE":   "Violations: diagnosis-package mismatches, reserved procedures, unauthorized billing, duplicate anomalies",
}

# ── Intent descriptions + few-shot examples ──────────────────────────────────

_INTENT_CATALOG: dict[str, dict] = {

    # ── ENROLMENT (20 intents) ───────────────────────────────────────────────

    "enrollment_count": {
        "desc": "Total enrolled beneficiaries or households (state, district, or block level)",
        "examples": ["How many families are enrolled in UP?", "Total beneficiaries in Gorakhpur"],
    },
    "enrollment_summary_by_district": {
        "desc": "Enrollment breakdown across all 75 districts",
        "examples": ["District-wise enrollment summary", "Show enrollment for all districts"],
    },
    "enrollment_summary_by_division": {
        "desc": "Enrollment breakdown across all 18 divisions",
        "examples": ["Division-wise enrollment", "Enrollment by division"],
    },
    "enrollment_gender_breakdown": {
        "desc": "Male/female split of enrolled beneficiaries",
        "examples": ["Gender breakdown of beneficiaries", "Male female ratio in Varanasi"],
    },
    "enrollment_age_distribution": {
        "desc": "Age groups or age pyramid of beneficiaries",
        "examples": ["Age distribution of enrolled beneficiaries", "Age breakdown in Lucknow"],
    },
    "enrollment_source_breakdown": {
        "desc": "SECC vs STATE_DB vs RSBY entitlement source breakdown",
        "examples": ["Enrollment source breakdown", "How many beneficiaries from SECC?"],
    },
    "enrollment_bis_status": {
        "desc": "GOLD/SILVER/PENDING BIS verification status",
        "examples": ["BIS verification status", "How many gold-verified beneficiaries?"],
    },
    "enrollment_mobile_coverage": {
        "desc": "Beneficiaries with/without mobile numbers",
        "examples": ["How many beneficiaries have mobile numbers?", "Mobile coverage of enrolled"],
    },
    "beneficiary_utilization_gap": {
        "desc": "Beneficiaries enrolled but have NEVER used/claimed the scheme",
        "examples": ["How many beneficiaries never used the scheme?", "Utilization gap by district"],
    },
    "enrolment_to_card_lag": {
        "desc": "Time from enrolment to card issuance; how quickly cards are issued",
        "examples": ["Average time from enrolment to card?", "Card issuance lag by district"],
    },
    "enrolment_rejection_rate": {
        "desc": "Enrolment request rejection rate or reasons",
        "examples": ["What is the enrolment rejection rate?", "Enrolment rejections in Agra"],
    },
    "authentication_mode_breakdown": {
        "desc": "Breakdown of authentication modes during enrolment (IRIS, FINGERPRINT, etc.)",
        "examples": ["Authentication mode breakdown", "How many used fingerprint for enrolment?"],
    },
    "profile_completeness": {
        "desc": "Beneficiaries with incomplete profiles (missing DOB, mobile, photo, or ID)",
        "examples": ["How many beneficiaries have incomplete profiles?", "Profile completeness by district"],
    },
    "duplicate_beneficiaries": {
        "desc": "Duplicate beneficiary records count or distribution",
        "examples": ["How many duplicate beneficiaries?", "Duplicates by district"],
    },
    "card_status_distribution": {
        "desc": "Active vs inactive vs disabled card distribution",
        "examples": ["Card status distribution", "How many active Ayushman cards?"],
    },
    "enrolment_trend": {
        "desc": "Month-over-month or year-wise new enrolment trend",
        "examples": ["Monthly enrolment trend", "New enrolments over time"],
    },
    "beneficiary_hospital_ratio": {
        "desc": "Number of enrolled beneficiaries per empanelled hospital",
        "examples": ["Beneficiary to hospital ratio", "How many beneficiaries per hospital?"],
    },
    "card_issuance_speed": {
        "desc": "Percentage of beneficiaries who received cards within 30 days of enrolment",
        "examples": ["Card issuance speed", "What percent got cards within 30 days?"],
    },
    "early_admission_rate": {
        "desc": "Share of beneficiaries admitted within 30 days of enrolment",
        "examples": ["Early admission rate", "How many were admitted within 30 days of enrolling?"],
    },
    "enrolment_to_treatment_funnel": {
        "desc": "Full funnel: enrolled → card issued → admitted → claimed → paid",
        "examples": ["Enrolment to treatment funnel", "Show the full utilization funnel"],
    },

    # ── HOSPITAL (19 intents) ────────────────────────────────────────────────

    "hospital_count": {
        "desc": "How many hospitals are empanelled (total, in a district, by type)",
        "examples": ["How many hospitals are there?", "Number of hospitals in Agra"],
    },
    "hospital_count_by_district": {
        "desc": "Hospital count broken down across all 75 districts",
        "examples": ["District-wise hospital count", "Hospitals per district"],
    },
    "hospital_density": {
        "desc": "Hospitals per lakh population density ranking",
        "examples": ["Hospital density ranking", "Which districts have most hospitals per capita?"],
    },
    "specialty_coverage": {
        "desc": "Which specialties are available across hospitals",
        "examples": ["Specialty coverage across hospitals", "Which specialties are available in Varanasi?"],
    },
    "hospital_license_status": {
        "desc": "Expired or current licenses; hospitals with expired licenses",
        "examples": ["How many hospitals have expired licenses?", "License status of hospitals"],
    },
    "hospital_bed_capacity": {
        "desc": "Bed strength by hospital type or district",
        "examples": ["Hospital bed capacity", "Total beds in Lucknow hospitals"],
    },
    "hospital_staff_ratio": {
        "desc": "Staff-to-bed ratio; clinician-to-patient ratio",
        "examples": ["Staff to bed ratio", "How many doctors per bed?"],
    },
    "hospital_performance": {
        "desc": "Overall performance of a SPECIFIC named hospital",
        "examples": ["Performance of District Hospital Lucknow", "How is CHC Chandauli performing?"],
    },
    "hospital_specialties": {
        "desc": "Specialties offered by a SPECIFIC named hospital",
        "examples": ["What specialties does District Hospital Varanasi offer?", "Specialties at PHC Agra"],
    },
    "hospital_type_utilization": {
        "desc": "Public vs private UTILIZATION split (share/proportion of cases handled)",
        "examples": ["Public vs private utilization share", "What proportion of cases go to private hospitals?"],
    },
    "unauthorized_specialty_billing": {
        "desc": "Hospitals treating specialties they are NOT officially empanelled for",
        "examples": ["Which hospitals bill for unauthorized specialties?", "Hospitals treating specialties they aren't empanelled for"],
    },
    "bed_overcrowding": {
        "desc": "Hospitals where case volume exceeds bed capacity",
        "examples": ["Which hospitals are overcrowded?", "Case volume per bed"],
    },
    "accreditation_status": {
        "desc": "Hospital accreditation (NABH/NABL/JCI) status and distribution",
        "examples": ["Hospital accreditation status", "How many hospitals are NABH accredited?"],
    },
    "infrastructure_gaps": {
        "desc": "Hospitals lacking critical infrastructure (ICU, OT, HDU)",
        "examples": ["Which hospitals lack ICU?", "Infrastructure gaps in hospitals"],
    },
    "delisted_with_cases": {
        "desc": "Hospitals that have been delisted but still have recent case activity",
        "examples": ["Delisted hospitals with recent cases", "Are any delisted hospitals still treating patients?"],
    },
    "average_length_of_stay": {
        "desc": "Average length of stay by procedure, hospital, district, or specialty",
        "examples": ["Average length of stay", "LOS by specialty in Lucknow"],
    },
    "clinician_workload": {
        "desc": "Cases per doctor or clinician; clinician-level case volumes",
        "examples": ["Clinician workload", "Cases per doctor"],
    },
    "hospital_concentration": {
        "desc": "Share of total spend/cases handled by top hospitals in a district",
        "examples": ["Hospital concentration in Lucknow", "What share do top 5 hospitals handle?"],
    },
    "blocks_without_hospitals": {
        "desc": "Blocks with zero empanelled hospitals but high enrolment",
        "examples": ["Blocks without hospitals", "Which blocks have no empanelled hospitals?"],
    },

    # ── CLAIMS (32 intents) ──────────────────────────────────────────────────

    "claims_total": {
        "desc": "Total cases and total claim amount (state-wide or for a month/year)",
        "examples": ["Total claim amount", "How many cases in total?"],
    },
    "claims_summary": {
        "desc": "Claims summary for a SPECIFIC district or block",
        "examples": ["Claims summary for Lucknow", "Claim details for Gorakhpur block"],
    },
    "claims_summary_by_district": {
        "desc": "Claims summary across ALL districts",
        "examples": ["District-wise claims summary", "Claims by district"],
    },
    "claims_summary_by_division": {
        "desc": "Claims summary across all divisions",
        "examples": ["Division-wise claims summary", "Claims by division"],
    },
    "claim_status_distribution": {
        "desc": "APPROVED/SETTLED/REJECTED/PENDING breakdown (state or district)",
        "examples": ["Claim status breakdown", "How many claims are pending vs approved?"],
    },
    "claims_by_status": {
        "desc": "Claims filtered by a specific status in a district",
        "examples": ["How many rejected claims in Kanpur?", "Pending claims in Agra"],
    },
    "claim_approval_rate": {
        "desc": "Approval/rejection rate for a SPECIFIC hospital",
        "examples": ["Approval rate of District Hospital Varanasi", "Which hospitals have lowest approval rate?"],
    },
    "case_volume_trend": {
        "desc": "Monthly trend of cases (state, district, block, or hospital)",
        "examples": ["Monthly case volume trend", "Case trend in Lucknow"],
    },
    "case_volume_by_district": {
        "desc": "Which districts had most cases (optionally in a specific year)",
        "examples": ["Which districts had most cases in 2023?", "Top districts by case volume"],
    },
    "block_case_volume": {
        "desc": "Which blocks in a district have the most cases",
        "examples": ["Block-wise case volume in Gorakhpur", "Cases by block in Lucknow"],
    },
    "annual_totals": {
        "desc": "Yearly totals for a district or year",
        "examples": ["Annual totals for 2023", "Yearly claims in Agra"],
    },
    "district_comparison": {
        "desc": "Compare claims/cases between two named districts",
        "examples": ["Compare Lucknow and Agra claims", "Claims comparison between Kanpur and Varanasi"],
    },
    "settlement_tat": {
        "desc": "Settlement turnaround time (state, district, block, or by hospital type)",
        "examples": ["Settlement TAT distribution", "Average TAT in Lucknow"],
    },
    "settlement_tat_portability": {
        "desc": "TAT comparison between portability and intrastate claims",
        "examples": ["Portability vs intrastate TAT", "Is TAT longer for portability claims?"],
    },
    "settlement_tat_by_district": {
        "desc": "TAT across ALL districts (ranking table)",
        "examples": ["District-wise TAT ranking", "Which districts have slowest TAT?"],
    },
    "rejection_rate": {
        "desc": "Claim rejection rate or count of rejected claims (district, block, or month/year)",
        "examples": ["What is the claim rejection rate in Lucknow?", "Rejection rate in July 2023"],
    },
    "rejection_rate_trend": {
        "desc": "Monthly claim rejection rate trend state-wide",
        "examples": ["Monthly rejection rate trend", "Rejection rate over time"],
    },
    "financial_summary": {
        "desc": "Total amounts paid vs pending vs rejected",
        "examples": ["Total amount paid, pending, and rejected", "Financial summary"],
    },
    "top_hospitals_by_claims": {
        "desc": "Top hospitals by total case volume or claim amount in a district or state. Use this when no specific specialty is mentioned.",
        "examples": ["Top 10 hospitals by claim amount", "Which hospitals processed the most cases in Lucknow?", "Hospitals with most cases in Agra"],
    },
    "top_hospitals_by_payment": {
        "desc": "Top hospitals by actual payment received",
        "examples": ["Top hospitals by payment", "Which hospitals received the most money?"],
    },
    "claim_haircut": {
        "desc": "Gap between amount claimed and amount approved",
        "examples": ["Claim haircut by district", "How much was cut from claims?"],
    },
    "claim_value_by_procedure": {
        "desc": "Average claim value by procedure, hospital, district, or specialty",
        "examples": ["Average claim per procedure", "Claim value by specialty"],
    },
    "pending_claims_aging": {
        "desc": "Aging analysis of pending claims (0-7 days, 7-14, 14-30, 30+)",
        "examples": ["Pending claims aging", "How many unpaid claims by age bucket?"],
    },
    "failed_payments": {
        "desc": "Failed payment amount and affected hospitals",
        "examples": ["Failed payments", "How many payments failed?"],
    },
    "documents_per_claim": {
        "desc": "Average documents submitted per claim; missing-document query rate",
        "examples": ["Average documents per claim", "Missing document rate"],
    },
    "adjudication_query_rate": {
        "desc": "Query rate during adjudication; top adjudication query reasons",
        "examples": ["Adjudication query rate", "Top reasons for adjudication queries"],
    },
    "rejection_reasons": {
        "desc": "Top reasons for claim rejection",
        "examples": ["Top rejection reasons", "Why are claims being rejected?"],
    },
    "expenditure_trend": {
        "desc": "Month-over-month or yearly trend in total claims expenditure",
        "examples": ["Monthly expenditure trend", "Yearly spending trend"],
    },
    "per_beneficiary_spend": {
        "desc": "Per-beneficiary scheme expenditure by district",
        "examples": ["Per beneficiary spend by district", "How much is spent per beneficiary?"],
    },
    "preauth_analysis": {
        "desc": "Pre-authorisation workflow: auto vs manual approval, TAT, rejection rate",
        "examples": ["Pre-auth analysis", "What is the pre-auth approval rate?"],
    },
    "addon_procedures": {
        "desc": "Add-on procedure rate, payout factor distribution, procedures per case",
        "examples": ["Add-on procedure rate", "How many procedures per case?"],
    },
    "claim_submission_lag": {
        "desc": "Time from discharge to claim submission; time from approval to payment",
        "examples": ["Claim submission lag", "How long from discharge to claim?"],
    },

    # ── SPECIALTY (18 intents) ───────────────────────────────────────────────

    "specialty_utilization": {
        "desc": "Utilization of a specialty or all specialties (state, district, or block)",
        "examples": ["OBG utilization across UP", "CARD utilization in Varanasi"],
    },
    "specialty_by_district": {
        "desc": "Which districts have most cases for a specific specialty",
        "examples": ["District-wise cardiology cases", "Which districts have most ortho cases?"],
    },
    "top_hospitals_by_specialty": {
        "desc": "Which hospitals handle most cases for a NAMED specialty (e.g. OBG, cardiology, ortho). Only use when a specialty is explicitly mentioned.",
        "examples": ["Top hospitals for orthopaedics", "Which hospitals handle most OBG cases?"],
    },
    "top_procedures": {
        "desc": "Top procedures by volume (state, district, or block)",
        "examples": ["Top procedures in UP", "Most common procedures in Lucknow"],
    },
    "top_diagnoses": {
        "desc": "Top diagnoses by volume (state, hospital, district, or block)",
        "examples": ["Top diagnoses in Gorakhpur", "Most common diagnoses at a hospital"],
    },
    "disease_category_breakdown": {
        "desc": "Breakdown by disease category: COMMUNICABLE, NCD, SURGICAL, MATERNAL_NEONATAL, INJURY",
        "examples": ["Disease burden breakdown", "Disease category distribution in Lucknow"],
    },
    "disease_category_trend": {
        "desc": "Monthly trend for a specific disease category over time",
        "examples": ["Trend of NCD cases", "Communicable disease trend over time"],
    },
    "seasonal_pattern": {
        "desc": "Seasonal/monthly admission patterns (state or by diagnosis category)",
        "examples": ["Seasonal admission pattern", "Which months have most dengue cases?"],
    },
    "procedure_financials": {
        "desc": "Procedure-wise spend, claimed amount, approved amount, and haircut",
        "examples": ["Procedure-wise financials", "Spend by procedure"],
    },
    "procedure_rejection_rates": {
        "desc": "Procedures with highest query rates and rejection rates",
        "examples": ["Which procedures are rejected most?", "Procedure rejection rates"],
    },
    "specialty_performance": {
        "desc": "Specialty-wise approval rate, rejection rate, and settlement TAT",
        "examples": ["Performance by specialty", "Which specialty has highest approval rate?"],
    },
    "procedure_mix_pub_priv": {
        "desc": "Procedure mix comparison between public and private hospitals",
        "examples": ["Procedure mix public vs private", "Do public hospitals do different procedures?"],
    },
    "maternal_case_rate": {
        "desc": "Maternal/neonatal case rate per 1,000 enrolled women",
        "examples": ["Maternal case rate by district", "Neonatal admission rate"],
    },
    "communicable_case_rate": {
        "desc": "Communicable disease case rate per 1,000 enrolled beneficiaries",
        "examples": ["Communicable disease rate by district", "Infectious disease burden"],
    },
    "ncd_case_rate": {
        "desc": "NCD case rate per 1,000 enrolled beneficiaries",
        "examples": ["NCD rate by district", "Non-communicable disease burden"],
    },
    "injury_caseload": {
        "desc": "Injury caseload distribution across districts",
        "examples": ["Injury cases by district", "Trauma caseload distribution"],
    },
    "disease_mix_by_geography": {
        "desc": "Communicable vs NCD vs maternal disease mix across divisions or blocks",
        "examples": ["Disease mix by division", "How does disease profile vary across blocks?"],
    },
    "diagnosis_procedure_combos": {
        "desc": "Top diagnosis-procedure combinations by total spend",
        "examples": ["Top diagnosis-procedure combos", "Most expensive diagnosis-procedure pairs"],
    },

    # ── PORTABILITY (5 intents) ──────────────────────────────────────────────

    "portability_volume": {
        "desc": "Portability case counts (state-wide or from a specific district)",
        "examples": ["How many portability cases?", "Portability volume from Lucknow"],
    },
    "portability_financials": {
        "desc": "Portability vs intrastate claim amounts comparison",
        "examples": ["Portability claim amount vs intrastate", "How much is spent on portability?"],
    },
    "portability_trend": {
        "desc": "Monthly trend of portability cases",
        "examples": ["Portability trend over time", "Monthly portability cases"],
    },
    "discharge_distribution": {
        "desc": "Discharge types: NORMAL/LAMA/DAMA/DEATH distribution",
        "examples": ["Discharge type distribution", "Discharge outcomes by district"],
    },
    "portability_detail": {
        "desc": "Portability destination-state mix, spend leakage by district and specialty",
        "examples": ["Portability detail by district", "Where do portability patients go?"],
    },

    # ── OUTCOMES (5 intents) ─────────────────────────────────────────────────

    "readmission_rate": {
        "desc": "Rate of readmissions within 30 days for same diagnosis",
        "examples": ["Readmission rate", "Which hospitals have highest readmissions?"],
    },
    "mortality_rate": {
        "desc": "Mortality rate overall or by hospital, diagnosis, specialty, district, or block",
        "examples": ["Mortality rate", "Death rate by hospital"],
    },
    "lama_dama_rate": {
        "desc": "LAMA (left against medical advice) or DAMA rate",
        "examples": ["LAMA rate by hospital", "How many patients left against medical advice?"],
    },
    "biometric_auth_discharge": {
        "desc": "Proportion of discharges with biometric authentication",
        "examples": ["Biometric auth at discharge", "What percent of discharges have biometric?"],
    },
    "medicine_provision": {
        "desc": "Proportion of discharges where medicines were provided",
        "examples": ["Medicine provision rate", "Were medicines given at discharge?"],
    },

    # ── ACCESS_EQUITY (12 intents) ───────────────────────────────────────────

    "gender_treatment_ratio": {
        "desc": "Male vs female ratio of treated patients (by district, block)",
        "examples": ["Gender ratio of treated patients", "Male vs female treatment ratio in Lucknow"],
    },
    "elderly_utilization": {
        "desc": "Whether elderly beneficiaries (65+) utilize the scheme proportionally",
        "examples": ["Elderly utilization rate", "Are senior citizens using the scheme?"],
    },
    "zero_utilization_blocks": {
        "desc": "Blocks with zero or near-zero hospital admissions",
        "examples": ["Blocks with zero utilization", "Which blocks have no admissions?"],
    },
    "public_private_comparison": {
        "desc": "Difference in approval rates or TAT between public and private hospitals",
        "examples": ["Do public hospitals have better approval rates than private?", "Public vs private settlement TAT"],
    },
    "utilization_by_source": {
        "desc": "Utilization patterns by entitlement source (SECC vs STATE_DB vs RSBY)",
        "examples": ["Utilization by entitlement source", "Do SECC beneficiaries use the scheme more?"],
    },
    "gender_procedure_disparity": {
        "desc": "Gender disparities in types of procedures accessed",
        "examples": ["Gender procedure disparity", "Do men and women access different procedures?"],
    },
    "out_of_district_treatment": {
        "desc": "Share of cases where patients travel outside home district for treatment",
        "examples": ["Out of district treatment rate", "How many patients go outside their district?"],
    },
    "patient_flow": {
        "desc": "Net patient inflow/outflow by district; district-to-district flow matrix",
        "examples": ["Patient flow by district", "Which districts export patients?"],
    },
    "case_rate_per_beneficiary": {
        "desc": "Case rate per 1,000 enrolled beneficiaries (district or block level)",
        "examples": ["Case rate per beneficiary", "Utilization rate per 1000 enrolled"],
    },
    "bed_capacity_per_beneficiary": {
        "desc": "Bed capacity per 1,000 enrolled beneficiaries by district",
        "examples": ["Beds per 1000 beneficiaries", "Bed capacity per enrolled"],
    },
    "underperforming_districts": {
        "desc": "Districts above/below state average on utilization, approval rate, TAT",
        "examples": ["Underperforming districts", "Which districts are below average?"],
    },
    "expenditure_concentration": {
        "desc": "Concentration of scheme expenditure — what share goes to top hospitals",
        "examples": ["Expenditure concentration", "What share of spend goes to top hospitals?"],
    },

    # ── COMPLIANCE (3 intents) ───────────────────────────────────────────────

    "diagnosis_package_mismatch": {
        "desc": "Hospitals with high rate of diagnosis-package mismatch queries or rejections",
        "examples": ["Diagnosis package mismatch", "Which hospitals have mismatched diagnoses and packages?"],
    },
    "reserved_procedure_violations": {
        "desc": "Private hospitals billing procedures reserved for public hospitals only",
        "examples": ["Reserved procedure violations", "Private hospitals billing reserved procedures"],
    },
    "duplicate_enrolment_correlation": {
        "desc": "Districts with highest combination of duplicate beneficiaries and enrolment rejections",
        "examples": ["Duplicate enrolment correlation", "Districts with high duplicates and rejections"],
    },
}


# ── Build the classification prompt once at module load ───────────────────────

def _build_classification_prompt() -> str:
    parts = [
        'You are a query classifier for the AB PM-JAY (Ayushman Bharat) health insurance scheme database for Uttar Pradesh, India.\n'
        '\n'
        'Given a user query, return a JSON object with exactly two keys:\n'
        '- "domain": one of ENROLMENT, HOSPITAL, CLAIMS, SPECIALTY, PORTABILITY, OUTCOMES, ACCESS_EQUITY, COMPLIANCE, or "no_match"\n'
        '- "intent": the specific intent name from the list below, or "no_match"\n'
        '\n'
        'Rules:\n'
        '- Queries may be in Hindi, Hinglish (Hindi-English mix), or English. Understand the meaning regardless of language.\n'
        '  Examples: "आगरा में कितने लाभार्थी पंजीकृत हैं?" = "How many beneficiaries are enrolled in Agra?"\n'
        '  "Lucknow mein kitne hospitals hain?" = "How many hospitals are in Lucknow?"\n'
        '- Pick the MOST SPECIFIC intent that matches the query.\n'
        '- "rejection" near "claims" or "hospitals" → CLAIMS domain. "rejection" near "enrolment" → ENROLMENT domain.\n'
        '- "public vs private utilization share" → HOSPITAL (hospital_type_utilization). "public vs private approval rate/TAT" → ACCESS_EQUITY (public_private_comparison).\n'
        '- If the query asks about a specific named hospital, prefer hospital_performance or hospital_specialties.\n'
        '- If the query cannot be answered with this database, return {"domain": "no_match", "intent": "no_match"}.\n'
    ]

    for domain, intents in INTENT_LIST_BY_DOMAIN.items():
        desc = _DOMAIN_DESCRIPTIONS.get(domain, "")
        parts.append(f"\n## {domain} — {desc}")
        for intent_name in intents:
            entry = _INTENT_CATALOG.get(intent_name)
            if not entry:
                continue
            ex_str = " | ".join(f'"{e}"' for e in entry["examples"])
            parts.append(f"- {intent_name}: {entry['desc']}")
            if ex_str:
                parts.append(f"  Ex: {ex_str}")

    return "\n".join(parts)


_CLASSIFICATION_PROMPT = _build_classification_prompt()

# Validation: set of all known intents
_ALL_INTENTS: set[str] = set()
for _intents in INTENT_LIST_BY_DOMAIN.values():
    _ALL_INTENTS.update(_intents)
_ALL_INTENTS.add("no_match")

# Reverse lookup: intent → domain (for auto-correcting domain if LLM gets intent right but domain wrong)
_INTENT_TO_DOMAIN: dict[str, str] = {}
for _domain, _intents in INTENT_LIST_BY_DOMAIN.items():
    for _intent in _intents:
        _INTENT_TO_DOMAIN[_intent] = _domain


# ── Public API ────────────────────────────────────────────────────────────────

def classify_intent(query: str, client: OpenAI) -> tuple[str, str]:
    """
    Single-call hierarchical classification.
    Returns (domain, intent). Falls back to ("no_match", "no_match") on error.
    """
    prompt = _CLASSIFICATION_PROMPT + f'\n\nQuery: "{query}"\nJSON:'

    try:
        kwargs = dict(
            model=ABSTRACTION_MODEL,
            timeout=LLM_TIMEOUT_SECONDS,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
        )
        if ABSTRACTION_MODEL in REASONING_MODELS:
            kwargs["max_completion_tokens"] = 500
            kwargs["extra_body"] = {"reasoning_effort": "low"}
        else:
            kwargs["temperature"] = LLM_TEMPERATURE
            kwargs["max_tokens"] = LLM_MAX_TOKENS_CLASSIFY

        resp = client.chat.completions.create(**kwargs)
        parsed = json.loads(resp.choices[0].message.content.strip())

        domain = parsed.get("domain", "no_match").upper().replace("-", "_")
        intent = parsed.get("intent", "no_match").lower().replace("-", "_")

        # Validate intent exists
        if intent not in _ALL_INTENTS:
            # Partial match fallback
            for known in _ALL_INTENTS:
                if known in intent or intent in known:
                    intent = known
                    break
            else:
                return ("no_match", "no_match")

        # Auto-correct domain from the intent (intent is what matters for routing)
        if intent != "no_match":
            correct_domain = _INTENT_TO_DOMAIN.get(intent)
            if correct_domain:
                domain = correct_domain

        return (domain, intent)

    except Exception:
        return ("no_match", "no_match")
