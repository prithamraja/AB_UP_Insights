# Ask Module — Implementation Handoff

**Last updated:** 2026-07-13 · **Branch:** `new_features` · **Status:** spec steps 1–5 built + conversational-repair fixes + critical-findings fixes 1–2 (repeated-slot param binding, operation stale-table guard — see `CRITICAL_FINDINGS_1_2.md`); backend 93/93 tests green (incl. statistical ops, chip-fill regression, chip-routing guards, param binding — all 2026-07-13); frontend written but **unverified** (npm cannot run in this Google Drive working copy — verify on the local machine).

**Spec:** `c:\Users\prith\Downloads\ask_feature_spec.md` (Decision Aids "Ask" module, feature spec v1). Read it first — Section 0's architectural invariants govern everything: the LLM never computes or writes SQL; it only classifies, matches/slot-fills, selects from closed option sets, and verbalizes. All arithmetic is deterministic code; every executed query is a catalog template with bound parameters.

---

## Decisions taken (user-approved; do not re-litigate)

| Decision | Value |
|---|---|
| Event logging (all of it: misses, clarifications, feedback) | **Skipped entirely** — POC only, user explicitly waived the spec's "log from day one" requirement |
| Thumbs feedback (8d) | Skipped (pointless without logging) |
| Inactivity timeout / history depth | 30 min / 10 frames (spec's suggested defaults) |
| Operations invocation | Both NL and UI buttons |
| Clarify-zone thresholds | Tunables in `query_router/config.py`, **uncalibrated initial guesses** |
| Suggestion chips per answer | Max 3 |
| Column-type tags | Auto-drafted rules in `column_types.json` (standalone, editable), no sign-off gate |

---

## What is built (spec build-order steps 1–5, all done)

### Step 1 — Context frame + column metadata
- `query_router/models.py` — `ContextFrame` (template_id, template_question, bound_params, active_filters, time_range, grouping_dimension, result_set w/ typed columns, history_stack). Also `Chip`, `Clarification`, `PendingClarification`, `OperationRequest/Result`.
- `query_router/context_store.py` — thread-safe session store: frame + **actual result rows** (ops run on the exact displayed table), history stack with parallel rows (for pop-back), pending-clarification storage. All expire after 30 min inactivity; `reset()` clears everything.
- `query_router/column_metadata.py` + `column_types.json` — parses each catalog template's outer SELECT (without executing) and tags every result column: `additive_count`, `additive_value`, `ratio`, `snapshot_stock`, `dimension`, `temporal`, `identifier`, `unclassified`. The JSON rule file is the editable POC tag source.

### Step 2 — Operations layer + comparison (8a)
- `query_router/operations.py` — closed set: `sum, average, min, max, count, share_of_total, sort, filter_rows, percent_change, top_n, bottom_n, compare, median, mode, stdev, percentile, range, count_distinct`. Policy table per (aggregation × column type): ratio aggregations **never** run client-side (rejected with explanation); snapshot stocks reject sum/avg when the table has a temporal column; unclassified columns don't aggregate. All narration strings are deterministic (no LLM).
- Distribution stats (added 2026-07-13, NL-only — no UI buttons by design): `median/stdev/percentile/range` are per-row distribution statistics, client-safe on **all** measure types including ratios (unlike `average`); narration says "across the N rows shown". `mode`/`count_distinct` work on any column incl. dimensions ("most common specialty"), default to the first dimension column; mode reports ties explicitly and says so when all values are unique. `percentile` reuses the `n` field (n=90 → 90th, linear interpolation).
- `compare` = re-query of the current template with one validated parameter swapped (`router.requery_template`), merged under a `compared_<slot>` column.
- Endpoints: `POST /operation` (UI buttons; `result_set_id` is **required** and checked against the current frame **before** any computation or requery — stale table → 409, fixed 2026-07-13) and NL via `/query` (classifier below; NL ops intentionally operate on the session's current table, no ID needed). Responses use `tier: "operation"` + `operation_mode: client|requery|rejected`.

### Step 3 — Three-zone matching (Section 6)
- `query_router/zones.py` — zone decision on cosine scores: `no_match` (< `NO_MATCH_LOWER_THRESHOLD` 0.30) / `ambiguous` (top-2 gap < `CLARIFY_SCORE_MARGIN` 0.015 and top < `CLARIFY_UPPER_THRESHOLD` 0.50) / `proceed`. **Thresholds are guesses; calibrate from live behavior** (no logs exist).
- `query_router/vector_retriever.py` — `retrieve_scored()` now surfaces cosine scores.
- `query_router/reranker.py` — contract changed: returns `(query_id | "no_match", near_miss_ids)`. On no-match, the LLM names up to 3 semantically closest candidates; those (not raw embedding order) become the clarify chips. Off-topic → empty list → miss path.
- Router clarifies on: ambiguous templates, reranker no-match-with-candidates, **missing required slot** ("For which district?"), **unknown entity** (did-you-mean chips that splice the correction into the user's own query). The old silent `EntityNotFound` swallow (which executed broken SQL) is gone.
- Miss path (`_no_match`) tries broad-question elicitation (8e) first, then "I can't answer that exactly, but I can answer these:" + nearest-question chips.

### Step 4 — Follow-ups, echo-back, breadcrumb (Sections 4–5)
- `query_router/followup_classifier.py` — when a frame exists, every message is classified three ways: `frame_edit` (entity swap "what about Lucknow?" / time change "pichhle saal ka?" — executed via `router.serve_frame_edit`, same template re-query) | `operation` | `new_question` (falls through to matching). Parsing is a pure function `parse_decision()` (tested); anything dubious degrades to new_question.
- `query_router/echo.py` — echo-back states the resolved question **plus every active filter and the explicit time range** ("…— district: Lucknow; period 2025-01-01 to 2025-12-31"); "all available data" when unfiltered (spec invariant 4).
- Endpoints: `POST /context/reset` (new-question affordance), `POST /context/pop` (breadcrumb back — restores previous frame *and its exact rows*).

### Step 5 — Suggestion chips (8b) + broad-question elicitation (8e)
- `query_router/suggestions.py` — hand-authored `FAMILY_MOVES` keyed by **slot type** (district/block/hospital/specialty/diagnosis_category/year), not per template. Chips = target template's `abstract_question` formatted with the frame's params; unfillable targets skipped; current template excluded; capped at 3. `ELICITATION_MOVES` powers "How is Agra doing?" → 4 measure chips. **No per-template question text exists or is needed** — edit the move lists to tune.

### Post-step fixes (from live testing, 2026-07-11)
1. **Entity-filled clarify chips** — near-miss chips extract entities from the original utterance (`router._extract_fill_values`) and substitute them (`zones.question_chips(…, fill)`): "gender breakdown … in **Lucknow**?" instead of "…in a district?". *Bug found live 2026-07-13: the fill was only wired on the reranker near-miss branch; zone-level no-match and ambiguous-zone chips rendered bare placeholders. Fixed — all three chip sites (`_no_match`, ambiguous clarify, reranker near-miss) now pass fill; regression test in `tests/test_router_miss_path.py` (stubs `router.extract_entities`).*
2. **Pending-clarification state** — every slot/entity clarify stores `PendingClarification` (template, filled slots, missing slot, original query). Next message: if ≤6 words **and** it validates as the missing slot type → `router.serve_pending_answer` resumes the paused question (chains to the next missing slot if any). Otherwise pending is dropped (one-shot) and the message routes normally. Known trade-off: a short new question naming a valid entity while a clarify is pending will resume the pending question instead — echo-back makes it visible; if it annoys, route short replies through the followup classifier instead of the word-count heuristic.
3. **Chip taps bypass the follow-up classifier** (2026-07-13, from live testing). Two misroutes observed: a tapped suggestion chip ("monthly case trend in Lucknow?") classified as a frame_edit (LLM latched onto "Lucknow" → re-served the current template), and "How many hospitals are empanelled in Lucknow?" classified as `operation: count` ("The table has 28 rows."). Four layers now defend this, strongest first:
   - **`from_chip: true` on `/query`** — frontend sends it on every chip tap (`ChipRow` → `handleSend(text, true)`); backend skips pending-resume *and* the classifier, routes straight to matching. Chip text is generated from the catalog, so this is deterministic.
   - **Catalog-question guard** — typed messages that are word-for-word a catalog question shape (`followup_classifier.catalog_question_patterns` / `matches_catalog_question`, compiled at startup from template abstract questions + dashboard questions) also skip the classifier.
   - **No-op frame-edit guard in `parse_decision`** — a swap whose value equals the current bound value (case/space-insensitive) changes nothing → degraded to new_question; a simultaneous time edit still applies.
   - **Prompt hardening** — frame_edit defined as "a fragment meaningless without the current question"; `count` defined as counting displayed rows, not answering "how many X?" about other things. LLM-behavior only; verify live.
   Residual risk: a *typed paraphrase* naming a different entity ("monthly trend in Agra?" on a Lucknow top-hospitals frame) can still misroute as a frame edit — only the prompt layer covers it; echo-back makes it visible.

### Frontend (all written, none verified)
- `src/types/chat.ts`, `src/services/api.ts` — `ContextFrame`, `Chip`, `Clarification` types; `runOperation`, `resetContext`, `popContext`; tiers extended with `operation`/`clarify`.
- `src/components/chat/MessageBubble.tsx` — `ChipRow` renders clarification options and "Try next" suggestions. **The Compute toolbar was deliberately removed** (2026-07-13, user-requested UI change): operations remain reachable via NL only; `runOperation`/`POST /operation` intentionally kept in `api.ts` (unit-tested) with no component caller. If a toolbar is ever rebuilt: pass the message's `context_frame.result_set.id` (now **required** by `POST /operation`) and enable it only when it equals `currentFrame.result_set.id` — never gate on frontend message IDs.
- `src/components/chat/Breadcrumb.tsx` — `PM-JAY UP › question › [period] [filter chips]` + Back (pop) + New question (reset). Filter chips are display-only by design (all filters are required template params; removal can't execute within the template — that's the deferred transformation algebra).
- `src/components/chat/ChatArea.tsx`, `src/pages/Index.tsx` — wiring; `currentFrame` state drives the breadcrumb.

---

## API surface (backend, FastAPI in `Chatbot/backend/main.py`)

- `POST /query` `{message, session_id?, reset_context?, start_date?, end_date?, from_chip?}` → `{session_id, tier, answer, result, context_frame, clarification?, suggestions?, operation?, operation_mode?, date_range, …}`. Internal order: pending-clarification resume → followup classification (frame edit / operation) → catalog routing. `from_chip: true` (or a message matching a catalog question shape) skips the first two stages and goes straight to catalog routing.
- `POST /operation` — typed op from UI (`OperationRequest` fields + `session_id` + `result_set_id`, both required; stale/missing table → 409 before any execution).
- `POST /context/reset`, `POST /context/pop`.

## Tests

`cd Chatbot/backend && python -m unittest discover -s tests` — **93 tests, all green** (no pytest installed). Coverage: operations + exhaustive policy table, zones, chips executability (every authored move must exist in the catalog and fully pre-fill), followup/reranker JSON parsing (pure functions), echo invariants, context pop, pending store/resume/chaining, repeated-slot param binding (T91/T99 + whole-catalog placeholder count + normal-vs-requery parity, `tests/test_param_binding.py`). **Not covered:** LLM prompts, real SQL, HTTP endpoints — that's what the smoke test is for.

## Remaining work (in order)

1. **Local frontend verification** (do this first): `npm test` + `npm run build` in `frontend/ab-dashboard-main` **on the local machine** (never npm in the Drive copy). Smoke: "claims summary for Agra" (echo + breadcrumb + chips) → "what about Lucknow?" (frame edit) → Back → "How many women beneficiaries are enrolled in Lucknow" (expect gender-breakdown chip pre-filled with Lucknow) → tap → answer; also "For which district?" → "lucknow" resume; Compute buttons; compare.
2. **Step 6 — Result summarization (8c):** deterministic descriptive stats over one table (top/bottom, concentration, outliers, totals — reuse column types), LLM verbalizes with the Section-3 language guardrail (accounting language only; denylist causal phrases: "caused by", "due to", "because of").
3. **Step 7 — Explain-change (Section 3):** built last per spec. Deterministic decomposition (additive: exact per-member contributions; ratios: rate+mix effects), concentration scoring, LLM verbalization-only with the same guardrail + output check.
4. Threshold calibration for the three zones (manual, no logs).

## Environment quirks

- Repo lives on Google Drive; **npm/vite/vitest must run from the local copy** (`C:\dev\ab-dashboard` exists in the workspace). Backend Python runs fine in place.
- Backend LLM: OpenAI `gpt-4.1-mini` (config.py), embeddings `text-embedding-3-large`; catalog embedding index cached in `Chatbot/backend/.tmp/`.
- Frontend talks to the backend via an ngrok URL default in `api.ts` (`VITE_API_BASE_URL` overrides).
- User preference: heavier model for correctness-critical design; Sonnet for routine build/verification.
