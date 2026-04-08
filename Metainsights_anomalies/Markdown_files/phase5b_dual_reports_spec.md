# Phase 5b (Revised): Dual Executive Reports

## Overview

Generate two complementary reports from the same MetaInsight candidates:

1. **Overview Report** (γ=0.1) — Status briefing. Leadline paragraphs with bullet-point supporting details. Answers: "What's broadly true about PM-JAY in UP?"

2. **Actionable Insights Report** (γ=0.5) — Investigation brief. One-line insight headlines with numbered bullets underneath. Answers: "Where do things break, and what should we look into?"

**Inputs:**
- `metainsights/view*_candidates.json` (from Phase 4b)
- `views/view*.parquet` (for stats enrichment)
- View configs with MeasureConfig (for aggregation types)

**Outputs:**
- `reports/overview_report.md`
- `reports/actionable_insights_report.md`

**Dependencies:** Anthropic API (`claude-sonnet-4-20250514`)

---

## Step 1: Generate Two Ranked Lists

Run the Phase 5 ranking pipeline twice with different γ values:

```python
from phase5_ranker import rank_metainsights, load_candidates, prefilter_candidates
from phase2_engine import compute_conciseness  # needs gamma override

def rescore_candidates(candidates, gamma):
    """Rescore all candidates with a different gamma value."""
    for c in candidates:
        # Recompute conciseness with new gamma
        # (same formula as compute_conciseness but with gamma overridden)
        n = c.hdp_size
        tau = 0.5
        r = 1.0
        k = 3

        alphas = [cs["proportion"] for cs in c.commonness_sets]
        
        exc_categories = {}
        for exc in c.exceptions:
            cat = exc["category"]
            exc_categories[cat] = exc_categories.get(cat, 0) + 1
        betas = [count / n for count in exc_categories.values()]

        import math
        s = 0.0
        for a in alphas:
            if a > 0:
                s -= a * math.log2(a)
        for b in betas:
            if b > 0:
                s -= r * b * math.log2(b)

        has_exceptions = len(c.exceptions) > 0
        indicator = 0.0 if has_exceptions else 1.0
        s_reg = s + gamma * indicator

        threshold = (1 - tau) * math.e / (tau ** (1.0 / r))
        if k < threshold:
            tau_r = tau ** (1.0 / r)
            s_star = -math.log2(tau) + r * (k * tau_r / math.e) * math.log2(math.e / (k * tau_r))
        else:
            s_star = -tau * math.log2(tau) - r * (1 - tau) * math.log2((1 - tau) / k)

        if s_star > 0:
            c.conciseness = max(0.0, 1.0 - s_reg / s_star)
        else:
            c.conciseness = 1.0

        c.score = c.conciseness * c.impact

    return candidates


def generate_dual_rankings():
    views = ["view1", "view2", "view3", "view4"]
    
    overview_ranked = {}
    actionable_ranked = {}
    
    for view_name in views:
        path = f"metainsights/{view_name}_candidates.json"
        
        # Load fresh copies for each gamma
        candidates_01 = load_candidates(path)
        candidates_05 = load_candidates(path)
        
        # Rescore with respective gamma
        rescore_candidates(candidates_01, gamma=0.1)
        rescore_candidates(candidates_05, gamma=0.5)
        
        # Pre-filter and rank
        filtered_01 = prefilter_candidates(candidates_01, max_candidates=5000)
        filtered_05 = prefilter_candidates(candidates_05, max_candidates=5000)
        
        overview_ranked[view_name] = rank_metainsights(filtered_01, k=15)
        actionable_ranked[view_name] = rank_metainsights(filtered_05, k=15)
    
    return overview_ranked, actionable_ranked
```

---

## Step 2: Enrich Both Lists with Stats

Same `enrich_candidates_with_stats` function from the original Phase 5b spec. Run it on both ranked lists.

```python
from phase5b_report import enrich_candidates_with_stats

all_configs = {
    "view1": VIEW1_CONFIG,
    "view2": VIEW2_CONFIG,
    "view3": VIEW3_CONFIG,
    "view4": VIEW4_CONFIG,
}

def enrich_all(ranked_dict):
    enriched = {}
    for view_name, ranked in ranked_dict.items():
        config = all_configs[view_name]
        # Convert to dicts if needed
        candidates_as_dicts = [c.to_dict() if hasattr(c, 'to_dict') else c for c in ranked]
        enriched[view_name] = enrich_candidates_with_stats(view_name, candidates_as_dicts, config)
    return enriched
```

---

## Step 3: Overview Report Prompt (γ=0.1)

```python
def build_overview_prompt(view_name: str, ranked_candidates: list[dict]) -> str:
    view_info = VIEW_DESCRIPTIONS[view_name]
    findings_json = json.dumps(
        [build_finding_dict(c) for c in ranked_candidates],
        indent=2, default=str
    )
    
    return f"""You are writing the overview section of an analytical report on the Ayushman Bharat PM-JAY health insurance scheme in Uttar Pradesh, India.

## Your Audience
A senior state programme officer who manages PM-JAY operations across UP. She is non-technical but understands healthcare operations and programme metrics. This is a status briefing — she wants to understand the overall state of the programme before a quarterly review meeting.

## This Section: {view_info['title']}

{view_info['description']}

## Column Glossary
{json.dumps(view_info['column_glossary'], indent=2)}

## Findings (ranked by importance)

{findings_json}

## Instructions

Write a clear overview section. Follow this exact format:

1. STRUCTURE: Group findings into 3-5 thematic areas. Each thematic area has:
   - A **leadline**: 2-3 sentences summarising the theme in plain English. This is a narrative paragraph, not a bullet.
   - **Supporting bullets**: 3-6 bullet points using markdown dash syntax (- ) with specific numbers from the stats field. Each bullet is one fact — concise, with the number front and centre.

2. EXAMPLE FORMAT:
   
   ### Spending is concentrated in two specialties
   
   PM-JAY spending in UP is overwhelmingly driven by Cardiology and Orthopaedics. These two specialties account for nearly two-thirds of all claim amounts, and this pattern holds across every division in the state.
   
   - Cardiology: ₹401.9 crore claimed (39.4% of total)
   - Orthopaedics: ₹260.2 crore claimed (25.5% of total)
   - Next largest: OBG at ₹8.50 crore, General Surgery at ₹7.22 crore
   - Pattern holds across all 18 divisions with no exceptions
   - Base package amounts show the same concentration: Cardiology at 42.7% of base amount

3. RULES:
   - Use plain English, spell out specialty codes on first use
   - Use ₹ and crore/lakh for financial amounts. Use plain numbers for counts, days, rates.
   - Every bullet must contain a specific number from the stats
   - Leadlines are narrative (no bullets, no numbers). Bullets are facts (numbers, concise).
   - Do NOT mention scores, conciseness, impact, HDP, extending strategies, or technical terms
   - Do NOT invent numbers not in the stats
   - Do NOT include follow-up questions or recommendations — this is a factual overview
   - Keep it to 400-700 words total
"""
```

---

## Step 4: Actionable Insights Report Prompt (γ=0.5)

```python
def build_actionable_prompt(view_name: str, ranked_candidates: list[dict]) -> str:
    view_info = VIEW_DESCRIPTIONS[view_name]
    findings_json = json.dumps(
        [build_finding_dict(c) for c in ranked_candidates],
        indent=2, default=str
    )
    
    return f"""You are writing the actionable insights section of an analytical report on the Ayushman Bharat PM-JAY health insurance scheme in Uttar Pradesh, India.

## Your Audience
A senior state programme officer preparing for district-level review meetings. She needs to know exactly where things deviate from the norm, which districts or entities are exceptions, and what to investigate. This is an investigation brief, not a status overview.

## This Section: {view_info['title']}

{view_info['description']}

## Column Glossary
{json.dumps(view_info['column_glossary'], indent=2)}

## Findings (ranked by importance, filtered for actionability)

These findings were specifically selected to highlight patterns that hold broadly but break in specific places. The exceptions are the actionable part.

{findings_json}

## Instructions

Write a set of actionable insights. Follow this exact format:

1. STRUCTURE: Present each insight (or closely related group of 2-3 insights) as:
   - A **one-line headline** in bold that tells the full story in one sentence, including the exception. The reader should understand the insight completely from this line alone.
   - **Numbered bullets** using markdown numbered list syntax (1. 2. 3.) with 3-6 items of supporting evidence, specific numbers, and context.

2. EXAMPLE FORMAT:

   **Cardiology and Orthopaedics dominate PM-JAY spending in 17 of 18 divisions — except Basti, where General Surgery leads instead.**
   
   1. Statewide, Cardiology accounts for ₹401.9 crore (39.4%) and Orthopaedics ₹260.2 crore (25.5%) of total claim amounts
   2. This pattern holds across 17 of 18 divisions — every division except Basti
   3. In Basti, General Surgery overtakes both, accounting for 34% of local claims vs Cardiology at 28%
   4. The concentration is even stronger in base package amounts: Cardiology alone is 42.7% of total base amount
   5. Implication: Basti's different specialty mix may reflect local hospital capabilities, referral patterns, or coding practices worth reviewing

3. HEADLINE RULES:
   - Must be a single sentence
   - Must state the broad pattern AND the exception(s) by name
   - Must be self-contained — a reader who only reads headlines should get the full picture
   - For universal patterns (no exceptions), the headline states what's consistent and why it matters
   - Use specific entity names: district names, specialty names, hospital types — not "some districts"

4. BULLET RULES:
   - Every bullet must contain a specific number from the stats
   - Use ₹ and crore/lakh for financial amounts
   - The last bullet in each group should be an "Implication" — what this means operationally and what to investigate
   - Keep each bullet to one line where possible

5. GENERAL RULES:
   - Spell out specialty codes on first use (e.g., Cardiology (CARD))
   - Do NOT mention scores, conciseness, impact, HDP, extending strategies, or technical terms
   - Do NOT invent numbers not in the stats
   - Present 8-12 insights total (group related findings)
   - Keep it to 600-1000 words total
"""
```

---

## Step 5: Helper Function

```python
def build_finding_dict(candidate: dict) -> dict:
    """Extract the fields needed for the LLM prompt."""
    c = candidate if isinstance(candidate, dict) else candidate.to_dict()
    finding = {
        "pattern_type": c["pattern_type"],
        "extending_dimension": c["extending_dimension"],
        "breakdown": c["breakdown"],
        "measure": c["measure"],
        "base_subspace": c["base_subspace"],
        "hdp_size": c["hdp_size"],
        "commonness_sets": c["commonness_sets"],
        "exceptions": c["exceptions"],
    }
    if "stats" in c:
        finding["stats"] = c["stats"]
    return finding
```

---

## Step 6: Generate Both Reports

```python
from anthropic import Anthropic

def generate_dual_reports(
    overview_enriched: dict[str, list],
    actionable_enriched: dict[str, list],
    overview_path: str,
    actionable_path: str,
):
    client = Anthropic()
    
    view_order = [
        ("view1", "Claims Processing & Treatment Patterns"),
        ("view2", "District-Level Monthly Performance Trends"),
        ("view3", "Hospital Infrastructure & Specialty Capacity"),
        ("view4", "Beneficiary Enrolment & Scheme Uptake"),
    ]
    
    # --- Overview Report ---
    overview_sections = [
        "# PM-JAY Uttar Pradesh — Programme Overview\n\n"
        "*Key patterns and structural findings across the scheme*\n\n---\n"
    ]
    
    for view_name, view_title in view_order:
        print(f"Overview: {view_title}...")
        prompt = build_overview_prompt(view_name, overview_enriched[view_name])
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        overview_sections.append(f"\n## {view_title}\n\n")
        overview_sections.append(response.content[0].text)
        overview_sections.append("\n\n---\n")
    
    with open(overview_path, "w") as f:
        f.write("".join(overview_sections))
    print(f"Overview report -> {overview_path}")
    
    # --- Actionable Insights Report ---
    actionable_sections = [
        "# PM-JAY Uttar Pradesh — Actionable Insights\n\n"
        "*Patterns that hold broadly but break in specific places — for investigation and follow-up*\n\n---\n"
    ]
    
    for view_name, view_title in view_order:
        print(f"Actionable: {view_title}...")
        prompt = build_actionable_prompt(view_name, actionable_enriched[view_name])
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2500,
            messages=[{"role": "user", "content": prompt}],
        )
        actionable_sections.append(f"\n## {view_title}\n\n")
        actionable_sections.append(response.content[0].text)
        actionable_sections.append("\n\n---\n")
    
    with open(actionable_path, "w") as f:
        f.write("".join(actionable_sections))
    print(f"Actionable report -> {actionable_path}")
```

---

## Step 7: Run

```python
if __name__ == "__main__":
    import os
    os.makedirs("reports", exist_ok=True)
    
    # Step 1: Generate dual rankings
    overview_ranked, actionable_ranked = generate_dual_rankings()
    
    # Step 2: Enrich with stats
    overview_enriched = enrich_all(overview_ranked)
    actionable_enriched = enrich_all(actionable_ranked)
    
    # Step 3: Generate reports
    generate_dual_reports(
        overview_enriched,
        actionable_enriched,
        "reports/overview_report.md",
        "reports/actionable_insights_report.md",
    )
```

---

## Output Format Comparison

### Overview Report (γ=0.1)

```
### Spending is concentrated in two specialties

PM-JAY spending in UP is overwhelmingly driven by Cardiology and 
Orthopaedics. These two specialties account for nearly two-thirds 
of all claim amounts, and this holds across every division.

- Cardiology: ₹401.9 crore claimed (39.4% of total)
- Orthopaedics: ₹260.2 crore claimed (25.5% of total)
- Next largest: OBG at ₹8.50 crore, General Surgery at ₹7.22 crore
- Pattern holds across all 18 divisions with no exceptions
```

### Actionable Insights Report (γ=0.5)

```
**Cardiology and Orthopaedics dominate PM-JAY spending in 17 of 18 
divisions — except Basti, where General Surgery leads instead.**

1. Statewide, Cardiology accounts for ₹401.9 crore (39.4%) and 
   Orthopaedics ₹260.2 crore (25.5%) of total claim amounts
2. This pattern holds across 17 of 18 divisions
3. In Basti, General Surgery overtakes both at 34% of local claims
4. Implication: Basti's different specialty mix may reflect local 
   hospital capabilities or referral patterns worth reviewing
```

---

## Validation

- [ ] Overview report has leadline paragraphs + bullet points (no standalone bullets)
- [ ] Overview report contains no exceptions or investigation recommendations
- [ ] Actionable report has bold one-line headlines with exception names
- [ ] Actionable report headlines are self-contained (readable without bullets)
- [ ] Every bullet in both reports contains a specific number
- [ ] No technical jargon in either report
- [ ] No hallucinated numbers
- [ ] Overview is 400-700 words per view section
- [ ] Actionable is 600-1000 words per view section

### What to bring back
1. `reports/overview_report.md`
2. `reports/actionable_insights_report.md`
3. Any headlines that don't fully capture the insight in one sentence
4. Any bullets without numbers
5. Your assessment: would these two reports together serve a programme officer well?
