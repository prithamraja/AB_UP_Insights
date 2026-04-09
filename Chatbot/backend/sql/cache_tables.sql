-- DDL for cache tables used by the query router.
-- Run automatically by db.py on first connection (CREATE TABLE IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS dashboard_cache (
    query_id     VARCHAR PRIMARY KEY,   -- "D01" ... "D36"
    question     TEXT    NOT NULL,       -- canonical natural-language question
    embedding    TEXT,                   -- JSON-serialised float list (startup-only)
    sql          TEXT    NOT NULL,       -- the SQL that produces this result
    result       TEXT,                   -- JSON-serialised query result (array of objects)
    row_count    INTEGER,
    computed_at  TIMESTAMPTZ,
    status       VARCHAR DEFAULT 'STALE' -- FRESH | STALE | ERROR
);

CREATE TABLE IF NOT EXISTS query_templates (
    template_id          VARCHAR PRIMARY KEY,  -- "T01" ... "T35"
    abstract_question    TEXT    NOT NULL,      -- "How many beneficiaries in {district}?"
    abstract_embedding   TEXT,                  -- JSON-serialised float list (startup-only)
    sql_template         TEXT    NOT NULL,      -- uses ? positional placeholders
    param_slots          TEXT    NOT NULL,      -- JSON array of slot definitions
    result_ttl_seconds   INTEGER DEFAULT 600
);
