import os
import json
import snowflake.connector
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

MODEL = "mistral-7b"

SYSTEM_PROMPT = (
    "You are FinSight, an expert financial analyst assistant. "
    "Answer the user's question using ONLY the provided context excerpts from SEC 10-K filings. "
    "Be precise and cite figures directly from the context. "
    "If the context does not contain enough information to answer, say so clearly."
)


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


# ── Prompt assembly ───────────────────────────────────────────────────────────

def _build_prompt(query: str, chunks: List[Dict]) -> str:
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        header = f"[{i}] {chunk['company']} — {chunk['filing_date']}"
        context_blocks.append(f"{header}\n{chunk['chunk_text'].strip()}")

    context = "\n\n---\n\n".join(context_blocks)

    return (
        f"{SYSTEM_PROMPT}\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION: {query}\n\n"
        f"ANSWER:"
    )


# ── Cortex LLM call ───────────────────────────────────────────────────────────

COMPLETE_SQL = "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s)"


def _call_cortex(cur, prompt: str) -> str:
    cur.execute(COMPLETE_SQL, (MODEL, prompt))
    row = cur.fetchone()
    raw = row[0]

    # CORTEX.COMPLETE returns either a plain string or a JSON object
    # depending on the Snowflake region / version — handle both.
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed["choices"][0]["messages"].strip()
        except (json.JSONDecodeError, KeyError, TypeError):
            return raw.strip()
    return str(raw).strip()


# ── Source metadata ───────────────────────────────────────────────────────────

def _build_sources(chunks: List[Dict]) -> List[Dict]:
    return [
        {
            "chunk_id": chunk.get("chunk_id"),
            "company": chunk["company"],
            "filing_date": str(chunk["filing_date"]),
            "ce_score": chunk.get("ce_score"),
        }
        for chunk in chunks
    ]


# ── Public entry point ────────────────────────────────────────────────────────

def generate(query: str, chunks: List[Dict]) -> Dict:
    """
    Generate an answer from the top-5 re-ranked chunks via Snowflake Cortex.

    Args:
        query:  The user's natural-language question.
        chunks: Top-5 dicts from reranker.rerank() — must contain
                'company', 'filing_date', and 'chunk_text'.

    Returns:
        {
            "answer":  str,            # LLM-generated answer text
            "sources": List[Dict],     # chunk_id, company, filing_date, ce_score
            "model":   str,            # model used
        }
    """
    prompt = _build_prompt(query, chunks)
    print(f"[generator] Prompt length: {len(prompt)} chars — calling Cortex {MODEL}...")

    conn = _get_connection()
    cur = conn.cursor()

    try:
        answer = _call_cortex(cur, prompt)
        print(f"[generator] Answer length: {len(answer)} chars")
    finally:
        cur.close()
        conn.close()

    return {
        "answer": answer,
        "sources": _build_sources(chunks),
        "model": MODEL,
    }


if __name__ == "__main__":
    from retriever import retrieve
    from reranker import rerank

    query = "What were Apple's revenue drivers in the most recent fiscal year?"
    print(f"Query: {query}\n")

    candidates = retrieve(query)
    top5 = rerank(query, candidates)
    result = generate(query, top5)

    print(f"\nAnswer ({result['model']}):\n{result['answer']}\n")
    print("Sources:")
    for s in result["sources"]:
        print(f"  {s['company']} | {s['filing_date']} | CE={s['ce_score']}")
