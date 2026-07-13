# ── Models ────────────────────────────────────────────────────────────────────
ABSTRACTION_MODEL    = "gpt-4.1-mini"
EXTRACTION_MODEL     = "gpt-4.1-mini"
RERANK_MODEL         = "gpt-4.1-mini"   # picks the best query_id from the vector top-K

# ── Embeddings / vector retrieval ────────────────────────────────────────────
EMBEDDING_MODEL      = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072

# Template-direct vector retrieval: embed the catalog, retrieve top-K candidates,
# then let an LLM re-ranker pick the query_id. Set False to use the legacy
# intent-classification path (classify_intent + INTENT_LOOKUP).
USE_VECTOR_RETRIEVAL = True
VECTOR_TOP_K         = 30    # validated at k=30 (English & Hinglish recall@30 = 97%)

# ── LLM parameters ───────────────────────────────────────────────────────────
LLM_TEMPERATURE           = 0.0
LLM_MAX_TOKENS_CLASSIFY   = 60     # JSON: {"domain":"...","intent":"..."}
LLM_MAX_TOKENS_EXTRACT    = 200
LLM_TIMEOUT_SECONDS       = 30

# Reasoning models require max_completion_tokens (not max_tokens) and reject temperature=0.0
REASONING_MODELS = {"gpt-5-mini", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5", "gpt-5.4"}

# ── Three-zone confidence handling (cosine similarity on catalog embeddings) ─
# Tunables — calibrate against logged accuracy data once available.
NO_MATCH_LOWER_THRESHOLD = 0.30   # best candidate below this → "can't answer, but here's what I can"
CLARIFY_UPPER_THRESHOLD  = 0.50   # best candidate above this → trust the reranker outright
CLARIFY_SCORE_MARGIN     = 0.015  # top-2 gap below this (and top1 below upper) → ask the user
MAX_CLARIFY_OPTIONS      = 3
MAX_MISS_SUGGESTIONS     = 3
MAX_SUGGESTION_CHIPS     = 3      # next-question chips per answer (8b)

# ── Caching ──────────────────────────────────────────────────────────────────
RESULT_CACHE_DEFAULT_TTL    = 600    # Tier 2 result cache (in-memory dict)

# ── Entity validation ────────────────────────────────────────────────────────
DEFAULT_FUZZY_THRESHOLD = 85
