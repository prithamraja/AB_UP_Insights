# Handoff: Make parameter-variant selection deterministic

## Goal

On the vector path, `rerank()` currently picks a **query_id** — which bundles two
decisions into one LLM call:

1. **Which question family?** (`specialty_utilization` vs `top_hospitals_by_specialty`)
   — genuinely semantic. The LLM is good at this, and the curated descriptions added
   in `RERANKER_ENRICHMENT_HANDOFF.md` (commit `2d53fd8`) measurably improved it.
2. **Which parameter variant within that family?** (`T21` = `{specialty}` state-wide vs
   `T25` = `{specialty}` + `{district}`) — **not semantic at all.** It is a deterministic
   function of which entities the query contains.

This task moves decision 2 out of the LLM and into a lookup. The reranker keeps
deciding the family; the variant is then resolved from the entities that
`extract_entities()` already extracts.

---

## Why (the structural problem)

The curated descriptions live in `intent_classifier._INTENT_CATALOG`, keyed by
**intent**. But the reranker chooses among **query_ids**, and **304 of the 324
described query_ids share their intent with at least one sibling** — the siblings
are that intent's parameter variants. So for ~94% of described candidates, the
description and its examples describe a *family*, not that candidate. Siblings
repeat the same text verbatim.

That makes the description structurally unable to separate siblings, and its
examples actively mislead: `specialty_utilization`'s example
`"CARD utilization in Varanasi"` is attached to district-less **T21** as well as to
**T25** — and it is a near-verbatim match for a real user query, so it drags the
pick onto the wrong variant. (Observed: pre-enrichment the reranker picked T70
*"% of beneficiaries who never utilized the scheme"* 5/5 trials for that query;
post-enrichment it lands in the right family 5/5 but split between T21 and T25
across runs.)

The interim fix now in `reranker.py` gives each candidate an `accepts filters:`
line derived from its `param_slots`, so the model has per-query_id ground truth.
It works on the suite — but it is still **persuading an LLM to perform a lookup**,
at temperature 0 on a model that is not deterministic (picks genuinely vary run to
run). The variant is knowable exactly. It should not be guessed.

**The codebase already contains the deterministic answer.** The legacy intent path
resolves variants with `INTENT_LOOKUP[(intent, frozenset(entities))] -> query_id`
(`intent_catalog.py`). The vector path cannot use it only because of step ordering:
`rerank()` commits to a variant at step 2, but `extract_entities()` does not know
the entities until step 3.

---

## The change

Reverse the dependency in `router._route_vector()` (`router.py` ~line 526):

```
now:      retrieve -> rerank (picks query_id) -> extract_entities(chosen.param_slots)
proposed: retrieve -> rerank (picks family)   -> extract_entities(family's slots)
                                              -> INTENT_LOOKUP[(intent, entities)] -> query_id
```

Sketch:

1. `rerank()` returns a **family** rather than a query_id. Cheapest framing: it still
   returns a query_id, and the router maps it to its intent via the `_QID_TO_INTENT`
   map it already builds (`router.py` ~line 54). No prompt change needed — the LLM's
   pick names the family implicitly, and picking the "wrong" sibling stops mattering.
2. Extract entities against the **union** of the slots across that intent's variants
   (so a query naming a district still yields `district`, even if the LLM happened to
   name the state-wide sibling).
3. Resolve the final query_id: `INTENT_LOOKUP[(intent, frozenset(found_entities))]`.
4. If that key misses (an entity combination the catalog has no template for), fall
   back to the reranker's original query_id — today's behavior.

### The 86 uncovered query_ids

The intent-less query_ids (mostly newer `D`-dashboards: D49, D65, D99, D110, …) have
no intent, so they have no `INTENT_LOOKUP` entry and cannot be resolved this way.
They are all parameterless dashboards, so they have no variants to choose between:
**if the reranker picks one, use it as-is and skip steps 2-4.** Do not block this task
on the catalog content pass.

---

## Do NOT change

- Retrieval / embeddings / `vector_retriever.py`.
- `parse_rerank_response` behavior or the `{"query_id": ..., "candidates": [...]}` contract.
- The `zone()` confidence gating.
- The curated descriptions in the reranker listing — they are what makes the *family*
  decision work, and this task depends on that decision being right.

Once variants are resolved deterministically, the `accepts filters:` line and the
"a description describes a FAMILY" paragraph in `_RERANK_SYS` become redundant and
can be dropped — but only after the lookup path is proven, not in the same step.

---

## Testing / acceptance

The comparison oracle is noisy — **read this before trusting a number.**
`python test_router.py --mode both` counts `*** MISMATCH` lines, but a mismatch only
means the vector and legacy paths disagree, *not* that the vector path is wrong. In
all three mismatches on the current 34-question suite the **vector** pick is the
better one. The legacy path is itself nondeterministic (`classify_intent` flipped
"How many hospitals are in Agra?" between T06 and D10 across identical runs).

So:

1. Baseline the **vector picks per question**, not the mismatch count. Diff vector
   picks before/after; every change should be defensible on inspection.
2. Run the suite 2-3 times before and after — a single run cannot distinguish a
   regression from LLM nondeterminism.
3. Targeted acceptance, the cases this task exists for:
   - `"What is the CARD utilization in Varanasi?"` must resolve to **T25** (specialty
     + district) on **every** run, not T21. This is the headline: it is currently
     stable in-router but varies under a raw-query harness.
   - `"OBG utilization across UP"` -> **T21** (no district named).
   - `"How many hospitals are in Agra?"` -> **T06**, `"...in UP?"` -> the state-wide variant.
4. `tests/` must stay green (76 tests): run from a local cwd, see below.
5. `"What is the weather today?"` must still return `no_match`.

### Running the harness on this machine

DuckDB cannot write its `.tmp` spill file onto the Google Drive mount
(`IOException: Cannot open file ".tmp\duckdb_temp_storage_DEFAULT-0.tmp": Access is denied`).
Run from a local working directory instead — every path inside the code is absolute,
so only the cwd needs to move:

```python
# run from e.g. C:\Users\<you>\AppData\Local\Temp\...
import os, sys, runpy
from dotenv import load_dotenv
BACKEND = r"I:\My Drive\ASC Lab\LMIC AI Code repo\AB_UP_insights\Chatbot\backend"
load_dotenv(os.path.join(BACKEND, ".env"))
sys.path.insert(0, BACKEND)
sys.argv = ["test_router.py", "--mode", "both"]
runpy.run_path(os.path.join(BACKEND, "test_router.py"), run_name="__main__")
```

`pytest` is not installed; run the unit tests with `unittest`, and set
`PYTHONIOENCODING=utf-8` (the console is cp1252 and the listing contains `↳`).

Note the router retrieves on `normalize(query)` but reranks on the raw `user_query` —
an ad-hoc harness that retrieves on the raw query will get a slightly different
candidate set than production.

---

## Key facts

- Reranker model: `RERANK_MODEL` in `config.py`, currently `gpt-4.1-mini`, temperature 0
  (still not deterministic — no seed is set).
- `USE_VECTOR_RETRIEVAL = True` in `config.py`; legacy intent path is the fallback.
- Branch: `new_features`. Deploy branch is `railway` — don't touch it.
- The retrieval gap is still open and separate: T25 is **not in the top-30** for
  "cardiology cases in Jhansi", so no reranker change can fix that query. That is the
  catalog-vocabulary content pass.
