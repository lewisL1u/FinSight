"""Retrieve relevant document chunks via Snowflake Cortex Search Service."""

from __future__ import annotations

import json

from snowflake.snowpark import Session

from app.utils.config import settings


def retrieve_chunks(
    session: Session,
    query: str,
    top_k: int | None = None,
    filter_file: str | None = None,
) -> list[dict]:
    """
    Query the Cortex Search Service and return the top-K relevant chunks.

    Returns a list of dicts with keys: source_file, chunk_index, chunk_text, score.
    """
    k = top_k or settings.CORTEX_TOP_K

    # Build optional column filter
    filter_clause = ""
    if filter_file:
        filter_clause = f", FILTER => OBJECT_CONSTRUCT('@eq', OBJECT_CONSTRUCT('source_file', '{filter_file}'))"

    sql = f"""
        SELECT PARSE_JSON(
            SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                '{settings.SNOWFLAKE_DATABASE}.{settings.SNOWFLAKE_SCHEMA}.{settings.CORTEX_SEARCH_SERVICE}',
                OBJECT_CONSTRUCT(
                    'query', $${query}$$,
                    'columns', ARRAY_CONSTRUCT('chunk_text', 'source_file', 'chunk_index'),
                    'limit', {k}
                    {filter_clause}
                )::VARCHAR
            )
        ) AS results
    """

    row = session.sql(sql).collect()[0]
    parsed = json.loads(row["RESULTS"])
    results_list = parsed.get("results", [])

    return [
        {
            "source_file": r.get("source_file", ""),
            "chunk_index": r.get("chunk_index", 0),
            "chunk_text": r.get("chunk_text", ""),
        }
        for r in results_list
    ]
