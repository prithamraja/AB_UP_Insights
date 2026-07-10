from dotenv import load_dotenv; load_dotenv()
import os, json, io, sys, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from openai import OpenAI
from db_factory import get_adapter
from query_router.entity_validator  import EntityValidator
from query_router.router            import route
from query_router.vector_retriever  import VectorRetriever
from query_router.dashboard_catalog import DASHBOARD_CATALOG
from query_router.template_catalog  import TEMPLATE_CATALOG

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["vector", "intent", "both"], default="vector",
                 help="vector = template-direct retrieval (new default), "
                      "intent = legacy classify_intent path, "
                      "both = run every question through both and diff the query_id")
args = ap.parse_args()

adapter = get_adapter()

# Auto-seed cache (in-memory adapter starts fresh each run)
from startup import seed as seed_cache
seed_cache(adapter, force=False)

client  = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
val     = EntityValidator(adapter)

d_res = {}
for qid, rj in adapter.execute("SELECT query_id, result FROM dashboard_cache WHERE status='FRESH'").fetchall():
    if rj:
        try: d_res[qid] = json.loads(rj)
        except: pass

d_q   = {k: v["question"] for k,v in DASHBOARD_CATALOG.items()}
t_map = dict(TEMPLATE_CATALOG)

retriever = None
if args.mode in ("vector", "both"):
    retriever = VectorRetriever(client, DASHBOARD_CATALOG, TEMPLATE_CATALOG)
    print(f"[vector] index ready — {len(retriever.ids)} catalog entries")


def _route(q, use_retriever: bool):
    return route(q, validator=val, openai_client=client, cache_conn=adapter,
                 dashboard_results=d_res, template_map=t_map, dashboard_questions=d_q,
                 retriever=(retriever if use_retriever else None))


def _print_result(r, label=None):
    rows = len(r.result) if r.result else 0
    qid  = r.query_id or "—"
    intent = (r.intent or "fallback")[:32]
    entities = ", ".join(f"{e.slot_name}={e.resolved_value}({e.confidence})"
                         for e in (r.entities or []))
    tier = r.tier.value
    prefix = f"[{label}] " if label else ""
    print(f"  ->  {prefix}[{tier}] {qid} | {intent}")
    if entities: print(f"      entities: {entities}")
    if r.result and rows > 0:
        print(f"      result ({rows} rows): {list(r.result[0].items())[:4]}")
    if tier == "fallback":
        print(f"      msg: {(r.fallback_message or '')[:120]}")
    print(f"      {r.total_latency_ms:.0f}ms")


def run(label, questions):
    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"{'='*80}")
    for q in questions:
        print(f"\n  Q:  {q}")
        if args.mode == "both":
            r_vec    = _route(q, use_retriever=True)
            r_intent = _route(q, use_retriever=False)
            _print_result(r_vec, "vector")
            _print_result(r_intent, "intent")
            if r_vec.query_id != r_intent.query_id:
                print(f"      *** MISMATCH: vector={r_vec.query_id} intent={r_intent.query_id}")
        else:
            r = _route(q, use_retriever=(args.mode == "vector"))
            _print_result(r)

# ── Test suites ───────────────────────────────────────────────────────────────

run("1. ENROLLMENT — state & district level", [
    "How many households and beneficiaries are enrolled in UP?",
    "How many beneficiaries are enrolled in Gorakhpur?",
    "What is the gender breakdown of beneficiaries in Varanasi?",
    "What is the age distribution of enrolled beneficiaries?",
    "How many beneficiaries have mobile numbers?",
])

run("2. HOSPITALS — counts, performance, specialties", [
    "How many hospitals are public vs private?",
    "How many hospitals are in Agra?",
    "How many hospitals have expired licenses?",
    "What specialties does District Hospital Lucknow offer?",
    "What is the performance summary of Urban Community Health Centre Chandauli Block 1?",
])

run("3. CLAIMS — summaries, trends, status", [
    "What is the total number of cases and claim amount?",
    "What is the monthly case volume trend?",
    "What is the claims summary for Lucknow?",
    "What is the claim status breakdown for Kanpur Nagar?",
    "Which districts had the most cases in 2023?",
])

run("4. SPECIALTY & DIAGNOSIS", [
    "What is the OBG utilization across UP?",
    "What is the CARD utilization in Varanasi?",
    "Which hospitals handle the most orthopaedics cases?",
    "What is the disease burden in Gorakhpur?",
    "What is the trend for maternal and neonatal cases?",
])

run("5. FINANCIAL & TAT", [
    "What is the settlement TAT distribution?",
    "What is the settlement TAT in Lucknow?",
    "What is the rejection rate in Agra?",
    "What was the rejection rate in July 2023?",
    "What is the total amount paid, pending, and rejected?",
    "What are the top 10 hospitals by claim amount?",
])

run("6. PORTABILITY", [
    "How many portability cases are there?",
    "What is the portability volume from Lucknow?",
    "What is the portability claim amount vs intrastate?",
])

run("7. EDGE CASES — typos, aliases, ambiguity, out-of-scope", [
    "How many hospitals in Allahabad?",        # alias: Allahabad -> Prayagraj
    "What is the OBG utilization in Gorkhpur?", # typo: Gorkhpur -> Gorakhpur
    "Lucknow mein kitne hospitals hain?",       # Hindi-English mix
    "Compare claims between Lucknow and Agra",  # two districts
    "What is the weather today?",               # out of scope
])
