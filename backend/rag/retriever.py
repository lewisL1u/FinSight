import os
import snowflake.connector
from dotenv import load_dotenv
from rank_bm25 import BM25Okapi
from typing import List, Dict

load_dotenv()

TOP_K = 20   # candidates per retrieval path
RRF_K = 60   # RRF constant (standard default)
FINAL_K = 10  # merged results returned to caller


# ── Snowflake connection ──────────────────────────────────────────────────────

def _get_connection() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


# ── Path 1: Vector search (Snowflake VECTOR_COSINE_SIMILARITY) ────────────────

VECTOR_SEARCH_SQL = """
SELECT
    chunk_id,
    company,
    filing_date,
    chunk_text,
    VECTOR_COSINE_SIMILARITY(
        embedding,
        SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', %s)::VECTOR(FLOAT, 768)
    ) AS score
FROM DOCUMENTS
ORDER BY score DESC
LIMIT %s
"""


def _vector_search(cur, query: str) -> List[Dict]:
    cur.execute(VECTOR_SEARCH_SQL, (query, TOP_K))
    rows = cur.fetchall()
    return [
        {
            "chunk_id": r[0],
            "company": r[1],
            "filing_date": r[2],
            "chunk_text": r[3],
            "vector_score": float(r[4]),
        }
        for r in rows
    ]


# ── Path 2: BM25 (rank-bm25, corpus fetched from Snowflake) ──────────────────

FETCH_ALL_SQL = """
SELECT chunk_id, company, filing_date, chunk_text
FROM DOCUMENTS
"""


def _bm25_search(cur, query: str) -> List[Dict]:
    cur.execute(FETCH_ALL_SQL)
    rows = cur.fetchall()

    corpus = [r[3].lower().split() for r in rows]
    bm25 = BM25Okapi(corpus)

    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:TOP_K]

    return [
        {
            "chunk_id": rows[i][0],
            "company": rows[i][1],
            "filing_date": rows[i][2],
            "chunk_text": rows[i][3],
            "bm25_score": float(scores[i]),
        }
        for i in ranked
    ]


# ── RRF merge combine and rerank search results from multiple retrievers  ─────────────────────────────────────────────────────────────────

def _rrf_merge(
    vector_results: List[Dict],
    bm25_results: List[Dict],
) -> List[Dict]:
    """
    Reciprocal Rank Fusion:  score(d) = Σ  1 / (k + rank(d))
    Ranks from both lists are 1-indexed.
    """
    rrf_scores: Dict[str, float] = {}

    for rank, doc in enumerate(vector_results, start=1):
        cid = doc["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)

    for rank, doc in enumerate(bm25_results, start=1):
        cid = doc["chunk_id"]
        rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (RRF_K + rank)

    # Build a lookup of all retrieved docs keyed by chunk_id
    all_docs: Dict[str, Dict] = {d["chunk_id"]: d for d in vector_results}
    all_docs.update({d["chunk_id"]: d for d in bm25_results})

    top_ids = sorted(rrf_scores, key=lambda cid: rrf_scores[cid], reverse=True)[:FINAL_K]

    return [
        {**all_docs[cid], "rrf_score": round(rrf_scores[cid], 6)}
        for cid in top_ids
    ]


# ── Public entry point ────────────────────────────────────────────────────────

def retrieve(query: str) -> List[Dict]:
    """
    Hybrid retrieval for a natural-language query.

    Steps:
      1. Vector search  — top 20 via VECTOR_COSINE_SIMILARITY (Snowflake Cortex)
      2. BM25 search    — top 20 via rank-bm25 over full corpus
      3. RRF merge      — fuse both ranked lists → top 10

    Returns list of dicts: {chunk_id, company, filing_date, chunk_text, rrf_score}
    """
    conn = _get_connection()
    cur = conn.cursor()

    try:
        print(f"[retriever] Running vector search...")
        vector_results = _vector_search(cur, query)
        print(f"[retriever] Vector hits: {len(vector_results)}")

        print(f"[retriever] Running BM25 search...")
        bm25_results = _bm25_search(cur, query)
        print(f"[retriever] BM25 hits: {len(bm25_results)}")

        merged = _rrf_merge(vector_results, bm25_results)
        print(f"[retriever] RRF merged → {len(merged)} candidates")
        return merged

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    results = retrieve("What were Apple's revenue drivers in the most recent fiscal year?")
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['company']} | {r['filing_date']} | RRF={r['rrf_score']}")
        print(f"    {r['chunk_text'][:200]}")
