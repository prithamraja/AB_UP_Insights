FALLBACK_EXAMPLES: dict[str, list[str]] = {
    "Enrollment": [
        "How many households and beneficiaries are enrolled in UP?",
        "What is the district-wise enrollment summary?",
        "How many beneficiaries are enrolled in Lucknow?",
        "What is the gender breakdown of beneficiaries?",
    ],
    "Hospitals": [
        "How many hospitals are empanelled, public vs private?",
        "How many hospitals are in Gorakhpur?",
        "What specialties does District Hospital Varanasi offer?",
        "How many hospitals have expired licenses?",
    ],
    "Claims & Utilization": [
        "What is the monthly case volume trend?",
        "What is the claims summary for Agra?",
        "What are the top diagnoses in Lucknow?",
        "What is the OBG utilization in Varanasi?",
    ],
    "Financial & TAT": [
        "What is the settlement TAT distribution?",
        "What is the rejection rate in Kanpur Nagar?",
        "What is the total amount paid, pending, and rejected?",
        "What are the top 10 hospitals by claim amount?",
    ],
}


def generate_fallback_message(dashboard_questions: dict[str, str]) -> str:
    lines = [
        "I'm not sure I can answer that specific question yet.\n",
        "Here are some things I can help with:\n",
    ]
    for category, examples in FALLBACK_EXAMPLES.items():
        lines.append(f"**{category}**")
        for ex in examples[:2]:
            lines.append(f"  • {ex}")

    return "\n".join(lines)
