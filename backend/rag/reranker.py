from sentence_transformers import CrossEncoder
from typing import List, Dict, Optional

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
TOP_N = 5

_model: Optional[CrossEncoder] = None


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        print(f"[reranker] Loading {RERANKER_MODEL}...")
        _model = CrossEncoder(RERANKER_MODEL)
        print("[reranker] Model loaded.")
    return _model


def rerank(query: str, candidates: List[Dict]) -> List[Dict]:
    """
    Cross-encoder re-ranking over retrieved candidates.

    Scores every (query, chunk_text) pair with ms-marco-MiniLM-L-6-v2,
    then returns the top 5 chunks sorted by descending cross-encoder score.

    Args:
        query:      The user's natural-language question.
        candidates: List of dicts from retriever.retrieve(), each containing
                    at minimum a 'chunk_text' key.

    Returns:
        Top-5 candidate dicts, each augmented with a 'ce_score' float.
    """
    if not candidates:
        return []

    model = _get_model()

    pairs = [(query, doc["chunk_text"]) for doc in candidates]
    scores = model.predict(pairs)

    ranked = sorted(
        zip(scores, candidates),
        key=lambda x: x[0],
        reverse=True,
    )

    return [
        {**doc, "ce_score": round(float(score), 6)}
        for score, doc in ranked[:TOP_N]
    ]


if __name__ == "__main__":
    from retriever import retrieve

    query = "What were Apple's revenue drivers in the most recent fiscal year?"
    print(f"[reranker] Query: {query}\n")

    candidates = retrieve(query)
    print(f"[reranker] Re-ranking {len(candidates)} candidates...\n")

    results = rerank(query, candidates)
    for i, r in enumerate(results, 1):
        print(f"[{i}] CE={r['ce_score']:.4f} | {r['company']} | {r['filing_date']}")
        print(f"     {r['chunk_text'][:200]}\n")
