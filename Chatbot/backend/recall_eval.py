"""
Recall@K harness for the *template-direct* vector-retrieval design.

Question we are answering BEFORE any refactor:
  If we embed every catalog question (D dashboards + T templates) and retrieve
  the top-K by cosine similarity for a user query, how often is the CORRECT
  query_id in the top-K?  And how badly do near-duplicate template variants
  crowd the top-30?

Usage:
  cd Chatbot/backend
  python recall_eval.py                # English topics from the gold CSV
  python recall_eval.py --k 30         # change the headline K
  python recall_eval.py --refresh      # ignore cached catalog embeddings

Notes:
  - Uses the English `topic` column as the query proxy. This FLATTERS retrieval
    (topics are phrased like the catalog). The number that actually matters —
    Hindi/Hinglish recall — needs a labelled multilingual set we don't have yet.
  - Catalog embeddings are cached to .tmp/catalog_embeddings.json so reruns are
    free; pass --refresh after editing the catalogs.
"""
import os
import re
import csv
import sys
import json
import io
import argparse
from pathlib import Path
from collections import Counter, defaultdict

from dotenv import load_dotenv
load_dotenv()

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from openai import OpenAI

from query_router.dashboard_catalog import DASHBOARD_CATALOG
from query_router.template_catalog  import TEMPLATE_CATALOG
from query_router.intent_catalog    import INTENT_LOOKUP
from query_router.config            import EMBEDDING_MODEL, ABSTRACTION_MODEL

HERE       = Path(__file__).parent
CSV_PATH   = HERE.parent / "test_questions_query_mapping.csv"
CACHE_PATH = HERE / ".tmp" / "catalog_embeddings.json"
HINGLISH_PATH = HERE / ".tmp" / "topics_hinglish.json"

# ── query_id → representative intent family (for the crowding metric) ──────────
# INTENT_LOOKUP maps (intent, entityset) -> query_id. Invert it so we can label
# each catalog entry with the intent(s) it can serve.
QID_TO_INTENTS: dict[str, set[str]] = defaultdict(set)
for (intent, _entities), qid in INTENT_LOOKUP.items():
    QID_TO_INTENTS[qid].add(intent)


def _clean_template(text: str) -> str:
    """'utilization in {district}?' -> 'utilization in district?' so the brace
    tokens don't pollute the embedding."""
    return re.sub(r"\{(\w+?)\}", r"\1", text)


def build_catalog() -> dict[str, str]:
    """query_id -> natural-language question used for embedding."""
    catalog: dict[str, str] = {}
    for qid, entry in DASHBOARD_CATALOG.items():
        catalog[qid] = entry["question"]
    for tid, entry in TEMPLATE_CATALOG.items():
        catalog[tid] = _clean_template(entry["abstract_question"])
    return catalog


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    out: list[list[float]] = []
    B = 256
    for i in range(0, len(texts), B):
        chunk = texts[i:i + B]
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=chunk)
        out.extend(d.embedding for d in resp.data)
    return out


def load_or_build_catalog_embeddings(client: OpenAI, catalog: dict[str, str],
                                     refresh: bool) -> dict[str, list[float]]:
    if CACHE_PATH.exists() and not refresh:
        cached = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if set(cached.get("questions", {})) == set(catalog) and \
           all(cached["questions"][q] == catalog[q] for q in catalog):
            return {q: cached["vectors"][q] for q in catalog}
    ids   = list(catalog)
    vecs  = embed_batch(client, [catalog[q] for q in ids])
    store = {q: v for q, v in zip(ids, vecs)}
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(
        {"model": EMBEDDING_MODEL, "questions": catalog, "vectors": store}), encoding="utf-8")
    return store


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: list[float]) -> float:
    return sum(x * x for x in a) ** 0.5


def cosine_rank(qvec: list[float], catalog_vecs: dict[str, list[float]]) -> list[str]:
    qn = _norm(qvec) or 1.0
    scored = [(qid, _dot(qvec, v) / (qn * (_norm(v) or 1.0)))
              for qid, v in catalog_vecs.items()]
    scored.sort(key=lambda t: t[1], reverse=True)
    return [qid for qid, _ in scored]


_HINGLISH_SYS = (
    "You convert English descriptions of health-insurance data questions into "
    "natural Hinglish — the romanized Hindi-English mix an Indian government "
    "official would actually type into a chatbot. Keep place names, specialty "
    "codes, scheme terms (PM-JAY, TAT, LAMA) as-is. Make it sound like a real "
    "typed question, not a literal translation. Return ONLY a JSON object "
    'mapping each input index (as a string) to its Hinglish question.'
)


def translate_to_hinglish(client: OpenAI, topics: list[str], refresh: bool) -> list[str]:
    if HINGLISH_PATH.exists() and not refresh:
        cached = json.loads(HINGLISH_PATH.read_text(encoding="utf-8"))
        if cached.get("topics") == topics:
            return cached["hinglish"]

    out: list[str] = [""] * len(topics)
    B = 20
    for i in range(0, len(topics), B):
        chunk = topics[i:i + B]
        payload = {str(j): t for j, t in enumerate(chunk)}
        resp = client.chat.completions.create(
            model=ABSTRACTION_MODEL,
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _HINGLISH_SYS},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        )
        parsed = json.loads(resp.choices[0].message.content)
        for j in range(len(chunk)):
            out[i + j] = parsed.get(str(j), chunk[j])

    HINGLISH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HINGLISH_PATH.write_text(
        json.dumps({"topics": topics, "hinglish": out}, ensure_ascii=False),
        encoding="utf-8")
    return out


def load_gold() -> list[dict]:
    rows = []
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            gold = (r.get("query_code") or "").strip()
            topic = (r.get("topic") or "").strip()
            if gold and topic:
                rows.append({"topic": topic, "gold": gold,
                             "intent": (r.get("intent") or "").strip()})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=30)
    ap.add_argument("--lang", choices=["english", "hinglish"], default="english")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()

    client   = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    catalog  = build_catalog()
    print(f"Catalog: {len(catalog)} entries "
          f"({sum(k.startswith('D') for k in catalog)} D, "
          f"{sum(k.startswith('T') for k in catalog)} T)")

    cat_vecs = load_or_build_catalog_embeddings(client, catalog, args.refresh)
    gold     = load_gold()

    # Gold rows whose query_code isn't in the current catalog can't be scored.
    missing  = [g for g in gold if g["gold"] not in catalog]
    scorable = [g for g in gold if g["gold"] in catalog]
    print(f"Gold rows: {len(gold)} | scorable: {len(scorable)} | "
          f"gold id not in catalog: {len(missing)}")
    if missing:
        print("  (unmatched gold ids: "
              + ", ".join(sorted({g['gold'] for g in missing})) + ")")

    if args.lang == "hinglish":
        q_texts = translate_to_hinglish(client, [g["topic"] for g in scorable], args.refresh)
        print(f"\nLanguage: HINGLISH (sample: {q_texts[0]!r})")
    else:
        q_texts = [g["topic"] for g in scorable]
        print(f"\nLanguage: ENGLISH")
    q_vecs   = embed_batch(client, q_texts)

    Ks       = sorted({5, 10, 20, args.k})
    hits     = {k: 0 for k in Ks}
    ranks    = []
    crowd    = []   # same-family entries among top-K per query
    misses   = []

    for g, qv in zip(scorable, q_vecs):
        ranked   = cosine_rank(qv, cat_vecs)
        gold_id  = g["gold"]
        rank     = ranked.index(gold_id)          # 0-based
        ranks.append(rank)
        for k in Ks:
            if rank < k:
                hits[k] += 1
        # crowding: of the top-K, how many share the gold's intent family?
        gold_intents = QID_TO_INTENTS.get(gold_id, set())
        topk = ranked[:args.k]
        same = sum(1 for qid in topk
                   if QID_TO_INTENTS.get(qid, set()) & gold_intents)
        crowd.append(same)
        if rank >= args.k:
            misses.append((g["topic"], gold_id, rank))

    n = len(scorable)
    note = "optimistic — topics phrased like the catalog" if args.lang == "english" \
        else "LLM-generated Hinglish from English topics"
    print(f"\n── Recall@K ({args.lang}; {note}) ──")
    for k in Ks:
        print(f"  recall@{k:<3}: {hits[k]/n:6.1%}  ({hits[k]}/{n})")

    ranks.sort()
    def pct(p): return ranks[min(len(ranks) - 1, int(len(ranks) * p))]
    print("\n── Gold-answer rank (0-based) ──")
    print(f"  median: {pct(0.5)}   p90: {pct(0.9)}   p99: {pct(0.99)}   worst: {ranks[-1]}")

    print(f"\n── Crowding: same-intent-family entries in top-{args.k} ──")
    c = Counter(crowd)
    print(f"  mean: {sum(crowd)/len(crowd):.1f}   max: {max(crowd)}")
    print(f"  distribution: " + ", ".join(f"{k}:{c[k]}" for k in sorted(c)))

    if misses:
        print(f"\n── Misses (gold outside top-{args.k}) — {len(misses)} ──")
        for topic, gid, rank in misses[:20]:
            print(f"  rank {rank:>3}  {gid:>5}  {topic[:70]}")


if __name__ == "__main__":
    main()
