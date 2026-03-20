-- ============================================================
-- FinSight: Snowflake Setup
-- Run this once to provision all required Snowflake objects
-- ============================================================

-- 1. Database & Schema
CREATE DATABASE IF NOT EXISTS FINSIGHT_DB;
USE DATABASE FINSIGHT_DB;

CREATE SCHEMA IF NOT EXISTS FINSIGHT_SCHEMA;
USE SCHEMA FINSIGHT_SCHEMA;

-- 2. Warehouse
CREATE WAREHOUSE IF NOT EXISTS FINSIGHT_WH
    WAREHOUSE_SIZE = 'X-SMALL'
    AUTO_SUSPEND = 120
    AUTO_RESUME = TRUE
    COMMENT = 'FinSight compute warehouse';

-- 3. Internal stage for raw document uploads
CREATE STAGE IF NOT EXISTS DOCS_STAGE
    DIRECTORY = (ENABLE = TRUE)
    COMMENT = 'Stage for raw financial document files';

-- 4. Document chunks table with vector embeddings
CREATE TABLE IF NOT EXISTS DOCUMENT_CHUNKS (
    chunk_id       VARCHAR(36) DEFAULT UUID_STRING() PRIMARY KEY,
    source_file    VARCHAR(512) NOT NULL,
    chunk_index    INTEGER NOT NULL,
    chunk_text     TEXT NOT NULL,
    chunk_embedding VECTOR(FLOAT, 768),
    created_at     TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- 5. Cortex Search Service over the chunks table
-- Provides semantic retrieval without a separate vector DB
CREATE CORTEX SEARCH SERVICE IF NOT EXISTS FINSIGHT_SEARCH_SERVICE
    ON chunk_text
    ATTRIBUTES source_file, chunk_index
    WAREHOUSE = FINSIGHT_WH
    TARGET LAG = '1 minute'
    AS (
        SELECT
            chunk_id,
            source_file,
            chunk_index,
            chunk_text
        FROM DOCUMENT_CHUNKS
    );

-- 6. Grant permissions (adjust role as needed)
-- GRANT USAGE ON DATABASE FINSIGHT_DB TO ROLE <your_role>;
-- GRANT USAGE ON SCHEMA FINSIGHT_SCHEMA TO ROLE <your_role>;
-- GRANT ALL ON TABLE DOCUMENT_CHUNKS TO ROLE <your_role>;
-- GRANT ALL ON STAGE DOCS_STAGE TO ROLE <your_role>;
-- GRANT ALL ON CORTEX SEARCH SERVICE FINSIGHT_SEARCH_SERVICE TO ROLE <your_role>;
