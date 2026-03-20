"""Snowflake Snowpark session management."""

import streamlit as st
from snowflake.snowpark import Session
from app.utils.config import settings


def _build_connection_params() -> dict:
    return {
        "account": settings.SNOWFLAKE_ACCOUNT,
        "user": settings.SNOWFLAKE_USER,
        "password": settings.SNOWFLAKE_PASSWORD,
        "role": settings.SNOWFLAKE_ROLE,
        "warehouse": settings.SNOWFLAKE_WAREHOUSE,
        "database": settings.SNOWFLAKE_DATABASE,
        "schema": settings.SNOWFLAKE_SCHEMA,
    }


@st.cache_resource(show_spinner="Connecting to Snowflake...")
def get_session() -> Session:
    """Return a cached Snowpark session shared across all Streamlit reruns."""
    return Session.builder.configs(_build_connection_params()).create()
