"""
Template-direct vector retrieval.

Embeds every catalog question (D dashboards + T templates) once, then for a user
query returns the top-K nearest catalog entries by cosine similarity. An LLM
re-ranker (reranker.py) picks the final query_id from these candidates.

Design notes:
  - We embed a CLEANED question ('utilization in district?') so the {brace}
    tokens don't pollute the vector, but we hand the re-ranker the ORIGINAL
    ('utilization in {district}?') so it can see the parameter structure and
    pick the right entity variant (e.g. T21 specialty-only vs T25 specialty+district).
  - Catalog embeddings are cached to .tmp/catalog_index.json keyed by a hash of
    (model + cleaned texts). Editing a catalog question invalidates the cache
    automatically; restarts are otherwise free.
"""
import re
import json
import hashlib
from pathlib import Path

import numpy as np

from .config import EMBEDDING_MODEL

_CACHE_PATH = Path(__file__).parent.parent / ".tmp" / "catalog_index.json"


def _clean(text: str) -> str:
    """'utilization in {district}?' -> 'utilization in district?'"""
    return re.sub(r"\{(\w+?)\}", r"\1", text)


class VectorRetriever:
    def __init__(self, client, dashboard_catalog: dict, template_catalog: dict):
        self.client = client
        self.ids: list[str] = []
        self.display: dict[str, str] = {}    # qid -> original question (braced)
        embed_texts: list[str] = []

        for qid, entry in dashboard_catalog.items():
            q = entry["question"]
            self.ids.append(qid)
            self.display[qid] = q
            embed_texts.append(_clean(q))
        for tid, entry in template_catalog.items():
            q = entry["abstract_question"]
            self.ids.append(tid)
            self.display[tid] = q
            embed_texts.append(_clean(q))

        self._matrix = self._load_or_build(embed_texts)   # (N, dim) L2-normalised

    # ── Embedding index ───────────────────────────────────────────────────────
    def _signature(self, embed_texts: list[str]) -> str:
        h = hashlib.sha256()
        h.update(EMBEDDING_MODEL.encode())
        for t in embed_texts:
            h.update(b"\x00")
            h.update(t.encode())
        return h.hexdigest()

    def _load_or_build(self, embed_texts: list[str]) -> np.ndarray:
        sig = self._signature(embed_texts)
        if _CACHE_PATH.exists():
            try:
                cached = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
                if cached.get("signature") == sig and cached.get("ids") == self.ids:
                    return self._normalise(np.array(cached["vectors"], dtype=np.float32))
            except Exception:
                pass  # rebuild on any cache problem

        vectors = self._embed(embed_texts)
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({
            "signature": sig,
            "ids": self.ids,
            "vectors": [v.tolist() for v in vectors],
        }), encoding="utf-8")
        return self._normalise(vectors)

    def _embed(self, texts: list[str]) -> np.ndarray:
        out: list[list[float]] = []
        B = 256
        for i in range(0, len(texts), B):
            resp = self.client.embeddings.create(
                model=EMBEDDING_MODEL, input=texts[i:i + B])
            out.extend(d.embedding for d in resp.data)
        return np.array(out, dtype=np.float32)

    @staticmethod
    def _normalise(m: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(m, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return m / norms

    # ── Query-time retrieval ──────────────────────────────────────────────────
    def retrieve_scored(self, query: str, k: int) -> list[tuple[str, str, float]]:
        """Up to k (query_id, display_question, cosine_score), most similar first."""
        resp = self.client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
        qv = np.array(resp.data[0].embedding, dtype=np.float32)
        qv = qv / (np.linalg.norm(qv) or 1.0)
        scores = self._matrix @ qv                       # cosine (rows normalised)
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], self.display[self.ids[i]], float(scores[i])) for i in top]

    def retrieve(self, query: str, k: int) -> list[tuple[str, str]]:
        """Returns up to k (query_id, display_question) pairs, most similar first."""
        return [(qid, q) for qid, q, _ in self.retrieve_scored(query, k)]
