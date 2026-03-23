CREATE TABLE IF NOT EXISTS DOCUMENTS (
    chunk_id    VARCHAR         PRIMARY KEY,
    company     VARCHAR         NOT NULL,
    filing_date DATE            NOT NULL,
    chunk_text  TEXT            NOT NULL,
    embedding   VECTOR(FLOAT, 768),
    created_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP()
);
