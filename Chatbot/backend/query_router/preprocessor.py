import re

ABBREVIATIONS: dict[str, str] = {
    "what's": "what is",
    "how's":  "how is",
    "govt":   "government",
    "hosp":   "hospital",
    "dist":   "district",
    "benefic":"beneficiary",
    "ben":    "beneficiary",
    "gbn":    "gautam buddha nagar",
    "kn":     "kanpur nagar",
    "pmjay":  "ayushman bharat",
    "ab":     "ayushman bharat",
}

# Historical / colloquial district names → official name
DISTRICT_ALIASES: dict[str, str] = {
    "allahabad":    "prayagraj",
    "faizabad":     "ayodhya",
    "noida":        "gautam buddha nagar",
    "greater noida":"gautam buddha nagar",
    "bhadohi":      "sant ravidas nagar",
}


def normalize(query: str) -> str:
    """
    1. Strip whitespace & collapse spaces
    2. Lowercase
    3. Remove trailing punctuation
    4. Expand abbreviations
    5. Apply district aliases
    """
    text = query.strip()
    text = re.sub(r"\s+", " ", text)
    text = text.lower()
    text = re.sub(r"[?.!]+$", "", text).strip()

    # Abbreviation expansion (word-boundary aware)
    for abbr, expansion in ABBREVIATIONS.items():
        text = re.sub(r"\b" + re.escape(abbr) + r"\b", expansion, text)

    # District alias normalisation
    for alias, canonical in DISTRICT_ALIASES.items():
        text = re.sub(r"\b" + re.escape(alias) + r"\b", canonical, text)

    return text
