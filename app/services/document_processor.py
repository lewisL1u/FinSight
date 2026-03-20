"""Document ingestion: parse, chunk, embed, and store in Snowflake."""

from __future__ import annotations

import io
import uuid
from typing import Iterator

from snowflake.snowpark import Session
from snowflake.snowpark.functions import col, lit, call_function

from app.utils.config import settings


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract plain text from a PDF file."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def extract_text_from_txt(file_bytes: bytes) -> str:
    return file_bytes.decode("utf-8", errors="replace")


def extract_text(filename: str, file_bytes: bytes) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return extract_text_from_pdf(file_bytes)
    return extract_text_from_txt(file_bytes)


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_text(text: str, chunk_size: int, overlap: int) -> Iterator[str]:
    """Yield overlapping word-based chunks."""
    words = text.split()
    step = chunk_size - overlap
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk:
            yield chunk


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_document(
    session: Session,
    filename: str,
    file_bytes: bytes,
) -> int:
    """
    Extract, chunk, embed, and insert a document into DOCUMENT_CHUNKS.
    Returns the number of chunks inserted.
    """
    text = extract_text(filename, file_bytes)
    chunks = list(
        chunk_text(text, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
    )

    if not chunks:
        return 0

    rows = []
    for idx, chunk in enumerate(chunks):
        rows.append(
            {
                "CHUNK_ID": str(uuid.uuid4()),
                "SOURCE_FILE": filename,
                "CHUNK_INDEX": idx,
                "CHUNK_TEXT": chunk,
            }
        )

    # Write chunks without embeddings first, then update embeddings via SQL
    # (Snowpark doesn't support VECTOR literals directly from Python dicts)
    df = session.create_dataframe(rows)
    df.write.mode("append").save_as_table("DOCUMENT_CHUNKS", column_order="name")

    # Update embeddings using Cortex embed function
    session.sql(
        f"""
        UPDATE DOCUMENT_CHUNKS
        SET chunk_embedding = SNOWFLAKE.CORTEX.EMBED_TEXT_768(
            'e5-base-v2', chunk_text
        )
        WHERE source_file = '{filename}'
          AND chunk_embedding IS NULL
        """
    ).collect()

    return len(chunks)


def delete_document(session: Session, filename: str) -> None:
    """Remove all chunks for a given source file."""
    session.sql(
        f"DELETE FROM DOCUMENT_CHUNKS WHERE source_file = '{filename}'"
    ).collect()


def list_documents(session: Session) -> list[str]:
    """Return distinct source file names currently stored."""
    rows = session.sql(
        "SELECT DISTINCT source_file FROM DOCUMENT_CHUNKS ORDER BY source_file"
    ).collect()
    return [r["SOURCE_FILE"] for r in rows]
