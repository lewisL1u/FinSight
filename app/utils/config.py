"""Application configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Snowflake connection
    SNOWFLAKE_ACCOUNT: str = os.environ["SNOWFLAKE_ACCOUNT"]
    SNOWFLAKE_USER: str = os.environ["SNOWFLAKE_USER"]
    SNOWFLAKE_PASSWORD: str = os.environ["SNOWFLAKE_PASSWORD"]
    SNOWFLAKE_ROLE: str = os.getenv("SNOWFLAKE_ROLE", "ACCOUNTADMIN")
    SNOWFLAKE_WAREHOUSE: str = os.getenv("SNOWFLAKE_WAREHOUSE", "FINSIGHT_WH")
    SNOWFLAKE_DATABASE: str = os.getenv("SNOWFLAKE_DATABASE", "FINSIGHT_DB")
    SNOWFLAKE_SCHEMA: str = os.getenv("SNOWFLAKE_SCHEMA", "FINSIGHT_SCHEMA")

    # Cortex settings
    CORTEX_SEARCH_SERVICE: str = os.getenv(
        "CORTEX_SEARCH_SERVICE", "FINSIGHT_SEARCH_SERVICE"
    )
    CORTEX_LLM_MODEL: str = os.getenv("CORTEX_LLM_MODEL", "mistral-large2")
    CORTEX_TOP_K: int = int(os.getenv("CORTEX_TOP_K", "5"))

    # Document processing
    CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
    CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))


settings = Settings()
