"""Generate answers using Snowflake Cortex LLM (CORTEX.COMPLETE)."""

from __future__ import annotations

from snowflake.snowpark import Session

from app.utils.config import settings

_SYSTEM_PROMPT = """You are FinSight, an expert financial analyst assistant.
Answer the user's question using ONLY the context extracted from the provided financial documents.
If the answer cannot be determined from the context, say so clearly.
Always cite the source document name when referencing specific information.
Be concise, accurate, and professional."""


def build_prompt(question: str, chunks: list[dict]) -> str:
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        context_parts.append(
            f"[Source {i}: {chunk['source_file']}]\n{chunk['chunk_text']}"
        )
    context = "\n\n".join(context_parts)

    return f"""{_SYSTEM_PROMPT}

---CONTEXT FROM DOCUMENTS---
{context}
---END CONTEXT---

Question: {question}

Answer:"""


def complete(
    session: Session,
    question: str,
    chunks: list[dict],
    model: str | None = None,
) -> str:
    """
    Call SNOWFLAKE.CORTEX.COMPLETE with the RAG prompt and return the answer.
    """
    llm_model = model or settings.CORTEX_LLM_MODEL
    prompt = build_prompt(question, chunks)

    # Escape single quotes in prompt for SQL safety
    safe_prompt = prompt.replace("'", "''")

    sql = f"""
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            '{llm_model}',
            '{safe_prompt}'
        ) AS answer
    """

    row = session.sql(sql).collect()[0]
    return row["ANSWER"].strip()
