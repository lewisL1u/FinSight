"""FinSight — Financial Document Q&A Platform (Streamlit entry point)."""

import streamlit as st

st.set_page_config(
    page_title="FinSight",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 FinSight")
st.subheader("Financial Document Intelligence Platform")

st.markdown(
    """
    Welcome to **FinSight** — your AI-powered assistant for financial document analysis.

    **Getting started:**
    1. Go to **Upload Documents** to ingest your financial PDFs or text files.
    2. Go to **Ask Questions** to query your documents using natural language.

    > Powered by **Snowflake Cortex Search** + **Cortex LLM**
    """
)

col1, col2 = st.columns(2)
with col1:
    st.info("📂 **Upload Documents**\nIngest financial reports, filings, and statements.")
with col2:
    st.info("💬 **Ask Questions**\nGet instant answers backed by your documents.")
