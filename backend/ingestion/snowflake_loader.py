import os
import snowflake.connector
from dotenv import load_dotenv
from typing import List, Dict

load_dotenv()

# ── DDL ───────────────────────────────────────────────────────────────────────

CREATE_DOCUMENTS = """
CREATE TABLE IF NOT EXISTS DOCUMENTS (
    chunk_id    VARCHAR         PRIMARY KEY,
    company     VARCHAR,
    filing_date DATE,
    chunk_text  TEXT,
    chunk_index INT,
    embedding   VECTOR(FLOAT, 768),
    created_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP()
)
"""

CREATE_STAGING = """
CREATE OR REPLACE TEMPORARY TABLE DOCUMENTS_STAGING (
    chunk_id    VARCHAR,
    company     VARCHAR,
    filing_date DATE,
    chunk_text  TEXT,
    chunk_index INT
)
"""

# ── The Cortex moment ─────────────────────────────────────────────────────────
# Snowflake runs the embedding model server-side; no Python ML code needed.
# One SQL statement stages raw text and writes 768-dim vectors into DOCUMENTS.

EMBED_AND_INSERT = """
INSERT INTO DOCUMENTS (chunk_id, company, filing_date, chunk_text, chunk_index, embedding)
    SELECT
        chunk_id,
        company,
        filing_date,
        chunk_text,
        chunk_index,
        SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', chunk_text)
    FROM DOCUMENTS_STAGING
"""


# ── Connection ────────────────────────────────────────────────────────────────

def _get_connection() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
        schema=os.environ["SNOWFLAKE_SCHEMA"],
    )


# ── Main entry point ──────────────────────────────────────────────────────────

def load_chunks(chunks: List[Dict]) -> None:
    """
    Insert SEC filing chunks into Snowflake and embed them with Cortex.

    chunks: list of { company, filing_date, chunk_text, chunk_index }
    """
    conn = _get_connection()
    cur = conn.cursor()

    try:
        # 1. Ensure the permanent table exists
        cur.execute(CREATE_DOCUMENTS)
        print("DOCUMENTS table ready.")

        # 2. Temp staging table (session-scoped, auto-dropped on disconnect)
        cur.execute(CREATE_STAGING)

        # 3. Bulk-load raw text into staging (no embeddings yet)
        rows = [
            (
                f"{c['company']}_{c['filing_date']}_{c['chunk_index']}",
                c["company"],
                c["filing_date"],
                c["chunk_text"],
                c["chunk_index"],
            )
            for c in chunks
        ]
        cur.executemany(
            "INSERT INTO DOCUMENTS_STAGING (chunk_id, company, filing_date, chunk_text, chunk_index) "
            "VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
        print(f"Staged {len(rows)} chunks.")

        # 4. Cortex does all the embedding work in a single SQL round-trip
        print("Running SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', ...) ...")
        cur.execute(EMBED_AND_INSERT)
        print(f"Embedded and inserted {cur.rowcount} rows into DOCUMENTS.")

        conn.commit()

    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    # Quick smoke-test with two synthetic chunks
    sample = [
        {
            "company": "AAPL",
            "filing_date": "2024-11-01",
            "chunk_text": "Apple reported record revenue driven by iPhone 16 sales.",
            "chunk_index": 0,
        },
        {
            "company": "AAPL",
            "filing_date": "2024-11-01",
            "chunk_text": "Services segment grew 12 percent year-over-year.",
            "chunk_index": 1,
        },
    ]
    load_chunks(sample)
