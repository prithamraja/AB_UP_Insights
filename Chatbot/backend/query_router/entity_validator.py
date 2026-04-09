"""
Validates extracted entities against known enum values.
Cascade: exact match → alias lookup → fuzzy match → EntityNotFound.
"""
from datetime import date
from rapidfuzz import process, fuzz
from .models import ExtractedEntity, EntityNotFound, ClarificationNeeded
from .config import DEFAULT_FUZZY_THRESHOLD

# ── Registry config ───────────────────────────────────────────────────────────

_DISTRICT_ALIASES = {
    "allahabad":     "Prayagraj",
    "faizabad":      "Ayodhya",
    "noida":         "Gautam Buddha Nagar",
    "greater noida": "Gautam Buddha Nagar",
    "gbn":           "Gautam Buddha Nagar",
    "bhadohi":       "Sant Ravidas Nagar (Bhadohi)",
}

REGISTRY_CONFIG: dict[str, dict] = {
    "district":    {"fuzzy_threshold": 85, "aliases": _DISTRICT_ALIASES},
    "district_2":  {"fuzzy_threshold": 85, "aliases": _DISTRICT_ALIASES},
    "division":    {"fuzzy_threshold": 85, "aliases": {}},
    "division_2":  {"fuzzy_threshold": 85, "aliases": {}},
    "block":       {"fuzzy_threshold": 80, "aliases": {}},
    "specialty": {
        "fuzzy_threshold": 90,
        "aliases": {
            "cardiology":      "CARD", "cardiac": "CARD",
            "ortho":           "ORTH", "orthopaedics": "ORTH", "orthopedics": "ORTH",
            "eye":             "OPTH", "ophthalmology": "OPTH", "cataract": "OPTH",
            "obstetrics":      "OBG",  "gynae": "OBG", "gynaecology": "OBG",
            "maternity":       "OBG",  "delivery": "OBG",
            "cancer":          "ONCO", "oncology": "ONCO",
            "surgery":         "GS",   "general surgery": "GS",
            "paediatrics":     "PEDS", "pediatrics": "PEDS", "children": "PEDS",
            "neuro":           "NEURO","neurology": "NEURO",
            "urology":         "URO",  "kidney": "URO",
            "medicine":        "MED",  "general medicine": "MED",
        },
    },
    "hospital":    {"fuzzy_threshold": 72, "aliases": {}},
    "claim_status": {
        "values":          ["APPROVED", "SETTLED", "QUERY_RAISED", "REJECTED", "PENDING"],
        "fuzzy_threshold": 85,
        "aliases": {
            "approved":  "APPROVED", "approve": "APPROVED",
            "rejected":  "REJECTED", "reject":  "REJECTED",
            "pending":   "PENDING",
            "queried":   "QUERY_RAISED", "query raised": "QUERY_RAISED",
            "settled":   "SETTLED",
        },
    },
    "diagnosis_category": {
        "values":          ["COMMUNICABLE", "MATERNAL_NEONATAL", "NCD", "SURGICAL", "INJURY"],
        "fuzzy_threshold": 85,
        "aliases": {
            "maternal":       "MATERNAL_NEONATAL", "neonatal": "MATERNAL_NEONATAL",
            "pregnancy":      "MATERNAL_NEONATAL", "delivery": "MATERNAL_NEONATAL",
            "ncd":            "NCD", "non communicable": "NCD", "chronic": "NCD",
            "communicable":   "COMMUNICABLE", "infectious": "COMMUNICABLE",
            "tropical":       "COMMUNICABLE", "dengue": "COMMUNICABLE",
            "surgical":       "SURGICAL", "surgery": "SURGICAL",
            "injury":         "INJURY", "trauma": "INJURY", "accident": "INJURY",
        },
    },
    "year": {
        "values":          [str(y) for y in range(2022, date.today().year + 1)],
        "fuzzy_threshold": 100,
        "aliases": {},
    },
    "month": {
        "values":          ["1","2","3","4","5","6","7","8","9","10","11","12"],
        "fuzzy_threshold": 100,
        "aliases": {
            "january":"1","february":"2","march":"3","april":"4",
            "may":"5","june":"6","july":"7","august":"8",
            "september":"9","october":"10","november":"11","december":"12",
            "jan":"1","feb":"2","mar":"3","apr":"4",
            "jun":"6","jul":"7","aug":"8","sep":"9",
            "oct":"10","nov":"11","dec":"12",
        },
    },
    "hospital_type": {
        "values":          ["PUBLIC", "PRIVATE"],
        "fuzzy_threshold": 100,
        "aliases": {
            "govt": "PUBLIC", "government": "PUBLIC", "sarkari": "PUBLIC",
            "private": "PRIVATE", "niji": "PRIVATE",
        },
    },
}

# Entity types that are state-wide scope markers, not real entities
_STATE_LEVEL_TERMS = {"up", "uttar pradesh", "state", "all", "entire state"}
_GEO_TYPES = {"district", "district_2", "block", "division", "division_2"}


class EntityValidator:
    def __init__(self, cache_conn):
        self._registry: dict[str, list[str]] = {}
        self._load(cache_conn)

    def _load(self, cache_conn) -> None:
        """Load valid values from DB for dynamic types; use static lists for enum types."""
        db_sources = {
            "district":  "SELECT DISTINCT district_name  FROM ref_up_geography",
            "division":  "SELECT DISTINCT division_name  FROM ref_up_geography",
            "block":     "SELECT DISTINCT block_name     FROM ref_up_geography",
            "hospital":  "SELECT DISTINCT hospital_name  FROM hm_hospital",
            "specialty": "SELECT DISTINCT specialty_code FROM hm_specialty_offered",
        }
        for etype, query in db_sources.items():
            rows = cache_conn.execute(query).fetchall()
            self._registry[etype] = [r[0] for r in rows if r[0]]

        # district_2 / division_2 share valid values with their base types
        self._registry["district_2"] = self._registry["district"]
        self._registry["division_2"] = self._registry["division"]

        # Static enums
        for etype, cfg in REGISTRY_CONFIG.items():
            if "values" in cfg:
                self._registry[etype] = cfg["values"]

    def validate(self, raw_value: str, entity_type: str) -> ExtractedEntity:
        if raw_value is None:
            raise EntityNotFound(entity_type, "<null>", [])

        if entity_type in _GEO_TYPES and raw_value.strip().lower() in _STATE_LEVEL_TERMS:
            raise EntityNotFound(entity_type, raw_value, [])

        cfg          = REGISTRY_CONFIG.get(entity_type, {})
        aliases      = {k.lower(): v for k, v in cfg.get("aliases", {}).items()}
        threshold    = cfg.get("fuzzy_threshold", DEFAULT_FUZZY_THRESHOLD)
        valid_values = self._registry.get(entity_type, [])
        norm         = raw_value.strip().lower()

        # 1. Exact match (case-insensitive)
        for v in valid_values:
            if v.lower() == norm:
                return ExtractedEntity(
                    slot_name=entity_type, raw_value=raw_value,
                    resolved_value=v, entity_type=entity_type, confidence="exact",
                )

        # 2. Alias lookup
        if norm in aliases:
            return ExtractedEntity(
                slot_name=entity_type, raw_value=raw_value,
                resolved_value=aliases[norm], entity_type=entity_type, confidence="alias",
            )

        # 3. Fuzzy match
        if valid_values and threshold < 100:
            match = process.extractOne(
                norm, [v.lower() for v in valid_values],
                scorer=fuzz.WRatio, score_cutoff=threshold,
            )
            if match:
                _, _, idx = match
                return ExtractedEntity(
                    slot_name=entity_type, raw_value=raw_value,
                    resolved_value=valid_values[idx], entity_type=entity_type, confidence="fuzzy",
                )

        # 4. Not found
        suggestions = []
        if valid_values:
            top = process.extract(norm, [v.lower() for v in valid_values],
                                  scorer=fuzz.WRatio, limit=3)
            suggestions = [valid_values[t[2]] for t in top]
        raise EntityNotFound(entity_type, raw_value, suggestions)
