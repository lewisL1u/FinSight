import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from rag.retriever import (
    _get_connection,
    _vector_search,
    _bm25_search,
    _rrf_merge,
)
from rag.reranker import rerank
from rag.generator import generate
from api.models import QueryRequest, QueryResponse, SourceDoc

app = FastAPI(title="FinSight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest):
    conn = _get_connection()
    cur = conn.cursor()

    try:
        vector_results = _vector_search(cur, request.question)
        bm25_results = _bm25_search(cur, request.question)
        merged = _rrf_merge(vector_results, bm25_results)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Retrieval error: {exc}") from exc
    finally:
        cur.close()
        conn.close()

    if request.company_filter:
        company_lower = request.company_filter.lower()
        merged = [d for d in merged if d["company"].lower() == company_lower]

    reranked = rerank(request.question, merged)

    try:
        result = generate(request.question, reranked)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation error: {exc}") from exc

    sources = [
        SourceDoc(
            chunk_id=chunk["chunk_id"],
            company=chunk["company"],
            filing_date=chunk["filing_date"],
            excerpt=chunk["chunk_text"][:300],
        )
        for chunk in reranked
    ]

    return QueryResponse(
        answer=result["answer"],
        sources=sources,
        retrieval_stats={
            "vector_hits": len(vector_results),
            "bm25_hits": len(bm25_results),
            "reranked_count": len(reranked),
        },
    )
