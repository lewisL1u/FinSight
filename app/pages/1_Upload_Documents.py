"""Page 1: Upload and manage financial documents."""

import streamlit as st

from app.services.snowflake_client import get_session
from app.services.document_processor import (
    ingest_document,
    delete_document,
    list_documents,
)

st.set_page_config(page_title="Upload Documents — FinSight", page_icon="📂", layout="wide")
st.title("📂 Upload Documents")

session = get_session()

# ── Upload section ──────────────────────────────────────────────────────────
st.header("Ingest New Documents")
uploaded_files = st.file_uploader(
    "Upload financial documents (PDF or TXT)",
    type=["pdf", "txt"],
    accept_multiple_files=True,
)

if uploaded_files:
    if st.button("📥 Ingest Selected Files", type="primary"):
        for uploaded_file in uploaded_files:
            with st.spinner(f"Processing **{uploaded_file.name}**..."):
                try:
                    n_chunks = ingest_document(
                        session,
                        filename=uploaded_file.name,
                        file_bytes=uploaded_file.read(),
                    )
                    st.success(
                        f"✅ **{uploaded_file.name}** — {n_chunks} chunks ingested."
                    )
                except Exception as e:
                    st.error(f"❌ Failed to ingest **{uploaded_file.name}**: {e}")

# ── Existing documents ──────────────────────────────────────────────────────
st.divider()
st.header("Indexed Documents")

docs = list_documents(session)

if not docs:
    st.info("No documents indexed yet. Upload some files above.")
else:
    for doc in docs:
        col1, col2 = st.columns([5, 1])
        col1.write(f"📄 {doc}")
        if col2.button("Delete", key=f"del_{doc}"):
            with st.spinner(f"Deleting **{doc}**..."):
                delete_document(session, doc)
            st.success(f"Deleted **{doc}**.")
            st.rerun()
