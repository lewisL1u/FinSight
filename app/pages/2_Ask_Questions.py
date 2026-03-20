"""Page 2: Chat-style Q&A over ingested financial documents."""

import streamlit as st

from app.services.snowflake_client import get_session
from app.services.document_processor import list_documents
from app.services.cortex_search import retrieve_chunks
from app.services.cortex_llm import complete
from app.utils.config import settings

st.set_page_config(page_title="Ask Questions — FinSight", page_icon="💬", layout="wide")
st.title("💬 Ask Questions")

session = get_session()

# ── Sidebar options ──────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Options")

    docs = list_documents(session)
    filter_doc = st.selectbox(
        "Filter by document (optional)",
        options=["All documents"] + docs,
    )
    selected_file = None if filter_doc == "All documents" else filter_doc

    top_k = st.slider("Chunks to retrieve", min_value=1, max_value=10, value=settings.CORTEX_TOP_K)
    model = st.selectbox(
        "Cortex LLM model",
        options=["mistral-large2", "llama3.1-70b", "llama3.1-8b", "snowflake-arctic"],
        index=0,
    )
    show_sources = st.toggle("Show source chunks", value=True)

    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.rerun()

# ── Chat history ─────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and show_sources and msg.get("sources"):
            with st.expander("📚 Source chunks"):
                for i, chunk in enumerate(msg["sources"], 1):
                    st.markdown(f"**[{i}] {chunk['source_file']}** (chunk {chunk['chunk_index']})")
                    st.caption(chunk["chunk_text"][:400] + "...")

# ── Input ─────────────────────────────────────────────────────────────────────
if not docs:
    st.warning("No documents indexed yet. Please upload documents first.")
else:
    question = st.chat_input("Ask a question about your financial documents...")

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Searching documents and generating answer..."):
                try:
                    chunks = retrieve_chunks(
                        session,
                        query=question,
                        top_k=top_k,
                        filter_file=selected_file,
                    )
                    if not chunks:
                        answer = "No relevant content found in the indexed documents."
                        sources = []
                    else:
                        answer = complete(session, question, chunks, model=model)
                        sources = chunks
                except Exception as e:
                    answer = f"An error occurred: {e}"
                    sources = []

            st.markdown(answer)

            if show_sources and sources:
                with st.expander("📚 Source chunks"):
                    for i, chunk in enumerate(sources, 1):
                        st.markdown(
                            f"**[{i}] {chunk['source_file']}** (chunk {chunk['chunk_index']})"
                        )
                        st.caption(chunk["chunk_text"][:400] + "...")

        st.session_state.messages.append(
            {"role": "assistant", "content": answer, "sources": sources}
        )
