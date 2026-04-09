# ── Models ────────────────────────────────────────────────────────────────────
ABSTRACTION_MODEL    = "gpt-4.1-mini"
EXTRACTION_MODEL     = "gpt-4.1-mini"

# ── Startup-only (used by startup.py, not at runtime) ────────────────────────
EMBEDDING_MODEL      = "text-embedding-3-large"
EMBEDDING_DIMENSIONS = 3072

# ── LLM parameters ───────────────────────────────────────────────────────────
LLM_TEMPERATURE           = 0.0
LLM_MAX_TOKENS_CLASSIFY   = 60     # JSON: {"domain":"...","intent":"..."}
LLM_MAX_TOKENS_EXTRACT    = 200
LLM_TIMEOUT_SECONDS       = 30

# Reasoning models require max_completion_tokens (not max_tokens) and reject temperature=0.0
REASONING_MODELS = {"gpt-5-mini", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5", "gpt-5.4"}

# ── Caching ──────────────────────────────────────────────────────────────────
RESULT_CACHE_DEFAULT_TTL    = 600    # Tier 2 result cache (in-memory dict)

# ── Entity validation ────────────────────────────────────────────────────────
DEFAULT_FUZZY_THRESHOLD = 85
