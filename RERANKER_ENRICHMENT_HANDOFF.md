# Handoff: Enrich the reranker with curated descriptions (cheap interim)

## Goal

The query router (`Chatbot/backend/query_router/`) has two front-ends. The **vector path** (default) retrieves the top-30 catalog questions by embedding cosine, then an **LLM reranker** picks the final `query_id`. Right now the reranker sees only bare `id: question` text. This task **adds a curated description (and a couple of examples) for each candidate**, plus **global disambiguation rules in the reranker's system prompt**, so it makes fewer wrong picks between *different* templates that look similar.

This is the **cheap, code-only interim version**. It reuses descriptions that already exist in the intent-classifier catalog. It does **not** involve writing new catalog content, changing embeddings, or touching retrieval.

---

## Why (the failure this fixes)

The reranker sometimes picks the wrong template even when the correct one is in the top-30. Example: for "cardiology cases in Jhansi", both `T24` (`Which hospitals handle the most {specialty} cases?` — intent `top_hospitals_by_specialty`) and `T25` (`What is the {specialty} utilization in {district}?` — intent `specialty_utilization`) can be retrieved, and the reranker may pick `T24` because its wording ("...most {specialty} cases?") surface-matches "cases". A one-line description contrast —
- T24: *"Which hospitals handle most cases for a NAMED specialty. Only use when a specialty is explicitly mentioned."*
- T25: *"Utilization of a specialty or all specialties (state, district, or block)."*

— gives the LLM the semantic signal to disambiguate. This is a **reranker-precision** fix.

**Scope boundary / expectation:** This only helps when the correct `query_id` is already in the top-30. It does **NOT** fix *retrieval* misses (e.g. the correct template never being retrieved because user vocabulary differs from catalog wording). That's a separate, later "catalog vocabulary" content pass.

---

## Where things live

All paths under `Chatbot/backend/query_router/`:

- **`reranker.py`** — the file you'll mainly edit.
  - `_RERANK_SYS` (system prompt, ~lines 16-29).
  - `rerank(query, candidates, client)` (~lines 56-88). Candidates are `list[tuple[str, str]]= (query_id, question)`. The candidate list is built at ~line 63:
    ```python
    listing = "\n".join(f"{qid}: {question}" for qid, question in candidates)
    ```
  - `parse_rerank_response(...)` — pure JSON→(query_id, near_misses) projection. **Do not change its behavior**; there's a unit test (`tests/test_reranker_parse.py`).

- **`intent_classifier.py`** — source of the curated descriptions.
  - `_INTENT_CATALOG: dict[str, dict]` (~line 30) maps `intent_name -> {"desc": str, "examples": [str, ...]}`. This is the description text to reuse.
  - `_build_classification_prompt()` (~line 516) contains a `Rules:` block (~lines 524-533) with **global disambiguation heuristics**. These are the rules to port into the reranker system prompt (see Step 3).

- **`intent_catalog.py`** — `INTENT_LOOKUP: dict[(intent, frozenset(entities)), query_id]`. Invert it to get `query_id -> intent`. See `router.py` ~lines 54-56 for the exact pattern already used:
  ```python
  _QID_TO_INTENT: dict[str, str] = {}
  for (_intent, _entities), _qid in INTENT_LOOKUP.items():
      _QID_TO_INTENT.setdefault(_qid, _intent)
  ```

- **`test_router.py`** — run with `python test_router.py --mode both` to compare vector-path vs legacy-intent-path picks and count `*** MISMATCH` lines. This is your before/after signal.

---

## Coverage reality (important)

Of the **410** catalog query_ids, only **324 map to an intent** (and thus have a description); **86 have none** (mostly newer `D`-dashboards: D49, D65, D99, D110, …). So:

- Attach a description where one exists.
- For the 86 without one, **fall back to bare `id: question`** (current behavior).
- Accept the mild asymmetry for now. Do **not** invent descriptions for the 86 in this task — that's the later content pass. (If you want, add a `# TODO` noting the gap.)

---

## Implementation steps

### Step 1 — Build a `query_id -> description string` map (module load, in `reranker.py`)

Derive it once at import time:

1. Invert `INTENT_LOOKUP` (from `intent_catalog`) to get `query_id -> intent` (use `setdefault` so the first intent wins, matching `router.py`).
2. For each query_id with an intent present in `_INTENT_CATALOG` (imported from `intent_classifier`), format a compact context string from `desc` + 1-2 `examples`. Suggested format (keep it short — tokens matter, but this is cheap; see note below):
   ```
   <desc>  e.g. "<example1>"
   ```
3. Store as `_QID_TO_CONTEXT: dict[str, str]`. query_ids not covered simply won't be in the dict.

Import note: `reranker.py` importing `intent_classifier` and `intent_catalog` is safe (no import cycle — `intent_classifier` does not import `reranker`; `router` imports both). `intent_classifier` already gets imported by `router` today, so no new startup cost.

### Step 2 — Use the map when building the candidate listing (in `rerank()`)

Change the listing construction (~line 63) so each candidate shows its description when available:

```python
lines = []
for qid, question in candidates:
    ctx = _QID_TO_CONTEXT.get(qid)
    if ctx:
        lines.append(f"{qid}: {question}\n    ↳ {ctx}")
    else:
        lines.append(f"{qid}: {question}")
listing = "\n".join(lines)
```

(Exact formatting is flexible; the two requirements are: description appears inline with its candidate, and missing-description candidates degrade to bare text.)

### Step 3 — Port global disambiguation rules into `_RERANK_SYS`

Copy the **cross-cutting** heuristics from `intent_classifier.py`'s `Rules:` block into the reranker system prompt (`_RERANK_SYS`). These are rules that aren't tied to one candidate, e.g.:
- "rejection" near "claims"/"hospitals" → CLAIMS sense; "rejection" near "enrolment" → ENROLMENT sense.
- "public vs private utilization share" → hospital-type utilization; "public vs private approval rate / TAT" → access-equity comparison.
- A specific named hospital → prefer the hospital-performance / hospital-specialties templates.

Keep the existing reranker rules (the `{placeholder}` variant-preference rules and the `no_match` + near-miss `candidates` behavior) **unchanged** — just add the global heuristics.

### Step 4 — Do NOT change

- Retrieval / embeddings / `vector_retriever.py`.
- The `zone()` confidence gating in `router.py` (`_route_vector`).
- `parse_rerank_response` behavior / the JSON output contract `{"query_id": ..., "candidates": [...]}`.
- The `rerank()` signature (keep it `(query, candidates, client)`), unless you have a strong reason — building `_QID_TO_CONTEXT` inside `reranker.py` avoids touching `router.py` at all.

---

## Token / latency note

This adds ~40-55 input tokens per described candidate (~+1.2-1.5k input tokens total) and **zero** output tokens (reranker still returns a tiny JSON, `max_tokens=80`). Expect **~50-150ms** extra per question — negligible vs. the existing round-trip. Empirical anchor: the legacy classifier already sends *all 123* intents with descriptions+examples (~5k+ tokens) at comparable latency, so 30 enriched candidates is well within budget. No need to optimize.

---

## Testing / acceptance

1. Ensure `OPENAI_API_KEY` is set (`Chatbot/backend/.env`).
2. From `Chatbot/backend/`, run **before** your change: `python test_router.py --mode both 2>&1 | grep MISMATCH` and record the count (baseline was **3/34**).
3. Apply the change, run again. **Acceptance:** mismatch count does not increase, and ideally decreases; spot-check that any newly-changed vector picks are *correct* (the enriched reranker should move toward the legacy/deterministic answer on cross-intent cases like the T24-vs-T25 family, not away from it).
4. Sanity-check a few queries directly (gender/specialty/hospital-count/out-of-scope) to confirm nothing regressed and `no_match` still works for "What is the weather today?".
5. Confirm `tests/test_reranker_parse.py` still passes (you shouldn't have touched its surface).

Do **not** re-run `recall_eval.py` for this — it measures retrieval recall, which this task does not change.

---

## Key facts

- Models: `RERANK_MODEL` / `EMBEDDING_MODEL` in `query_router/config.py`. Reranker currently `gpt-4.1-mini`.
- Flag: `USE_VECTOR_RETRIEVAL = True` in `config.py` (vector path is the default; legacy intent path is the fallback).
- Branch: work is on `new_features` (already pushed to origin). The deploy branch is `railway` — don't touch it.
- `.tmp/` (embedding cache, ~50MB) and `.claude/` are gitignored; don't commit them.
