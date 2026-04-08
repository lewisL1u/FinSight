# FinSight — Architecture Overview

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                       SEC EDGAR (free API)                       │
│  company_tickers.json  /submissions/CIK{n}.json  /Archives/...   │
└─────────────────────────────┬────────────────────────────────────┘
                              │ HTTP (requests)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                  AIRFLOW (orchestration)                         │
│                                                                  │
│  DAG: sec_ingestion_dag                                          │
│    1. sec_loader.py   — fetch & chunk 10-K filings               │
│       Tickers: AAPL, MSFT, GOOGL, JPM, GS                        │
│       Output: [{company, filing_date, chunk_text, chunk_index}]  │
│    2. snowflake_loader.py — stage + embed + insert               │
└─────────────────────────────┬────────────────────────────────────┘
                              │ snowflake-connector-python (TLS)
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│                      SNOWFLAKE CLOUD                             │
│  FINSIGHT_DB / RAG schema                                        │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   DOCUMENTS table                        │    │
│  │  chunk_id    VARCHAR  PRIMARY KEY  (company_date_index)  │    │
│  │  company     VARCHAR                                     │    │
│  │  filing_date DATE                                        │    │
│  │  chunk_text  TEXT                                        │    │
│  │  chunk_index INT                                         │    │
│  │  embedding   VECTOR(FLOAT, 768)                          │    │
│  │  created_at  TIMESTAMP                                   │    │
│  └──────────────────────────┬──────────────────────────────┘    │
│                             │                                    │
│     ┌───────────────────────┼───────────────────────┐           │
│     │                       │                       │           │
│     ▼                       ▼                       ▼           │
│  ┌──────────────┐  ┌─────────────────┐  ┌────────────────────┐ │
│  │ Cortex Embed │  │  Cortex Search  │  │    Cortex LLM      │ │
│  │ EMBED_TEXT   │  │  Service        │  │  CORTEX.COMPLETE() │ │
│  │ _768(        │  │  Semantic       │  │                    │ │
│  │ 'e5-base-v2',│  │  search over    │  │  mistral-large2    │ │
│  │  chunk_text) │  │  chunk_text,    │  │  (or llama3.1-70b) │ │
│  │ (at ingest)  │  │  returns top-K  │  │                    │ │
│  └──────────────┘  └─────────────────┘  └────────────────────┘ │
└──────────────────────────────┬───────────────────────────────────┘
                               │ REST / Snowpark (TLS)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                   BACKEND (FastAPI + uvicorn)                    │
│  backend/                                                        │
│  ├── ingestion/                                                  │
│  │   ├── sec_loader.py        — EDGAR fetch, parse, chunk        │
│  │   └── snowflake_loader.py  — stage, Cortex embed, insert      │
│  ├── sql/schema.sql           — canonical DDL                    │
│  ├── .env                     — Snowflake credentials            │
│  └── requirements.txt                                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP/JSON
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                        FRONTEND                                  │
│  frontend/                   — Q&A chat UI (TBD)                 │
└──────────────────────────────────────────────────────────────────┘
                               │
┌──────────────────────────────────────────────────────────────────┐
│                  KUBERNETES CLUSTER                              │
│                                                                  │
│  ┌──────────────┐   ┌──────────────────────────────────────┐    │
│  │   ArgoCD     │──▶│  finsight namespace                  │    │
│  │  (GitOps)    │   │  Deployment · Service · Secret       │    │
│  └──────────────┘   │  ConfigMap · Ingress                 │    │
│  ┌──────────────┐   └──────────────────────────────────────┘    │
│  │  Helm Chart  │                                                │
│  │  infra/      │                                                │
│  └──────────────┘                                                │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### SEC Ingestion Flow

```
Airflow DAG (or python sec_loader.py)
        │
        ▼
[sec_loader.py]
  ├── get_cik(ticker)            ← SEC company_tickers.json
  ├── get_latest_10k(cik)        ← /submissions/CIK{n}.json
  ├── fetch_filing_text(...)     ← /Archives/... (HTML → BeautifulSoup → plain text)
  └── chunk_text(text)           ← 400-word windows, 50-word overlap
  → List[{company, filing_date, chunk_text, chunk_index}]
        │
        ▼
[snowflake_loader.py]
  ├── CREATE TABLE IF NOT EXISTS DOCUMENTS (... embedding VECTOR(FLOAT, 768))
  ├── CREATE TEMPORARY TABLE DOCUMENTS_STAGING
  ├── executemany → bulk insert raw chunks into staging
  └── INSERT INTO DOCUMENTS                         ← single SQL round-trip
        SELECT ...,
               SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', chunk_text)
        FROM DOCUMENTS_STAGING
```

### Q&A (RAG) Flow

```
User types question  (Frontend)
        │
        ▼
[FastAPI backend]
        │
        ▼
[retriever.py]  — Hybrid retrieval (top 20 candidates each)
  ├── Path 1: VECTOR_COSINE_SIMILARITY  (Snowflake Cortex)
  └── Path 2: BM25Okapi                (rank-bm25, full corpus)
        │
        ▼ RRF merge → top 10
        │
        ▼
[reranker.py]  — Cross-encoder re-ranking
  └── CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
      scores every (query, chunk) pair → top 5
        │
        ▼
[generator.py]  — Prompt assembly + Cortex LLM
  ├── Build prompt:
  │     SYSTEM:   "You are FinSight, a financial analyst assistant..."
  │     CONTEXT:  [chunk 1] [chunk 2] ... [chunk 5]  (company + filing_date labelled)
  │     QUESTION: user's question
  └── SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-7b', prompt)
        │
        ▼
  {answer, sources, model}  →  JSON response
        │
        ▼
  Frontend displays answer + source citations
```

---

## Component Responsibilities

| Component | Technology | Responsibility | Status |
|---|---|---|---|
| `backend/ingestion/sec_loader.py` | Python, requests, BS4 | Fetch 10-K filings from SEC EDGAR, parse HTML, chunk text | ✅ Done |
| `backend/ingestion/snowflake_loader.py` | snowflake-connector, Cortex | Stage chunks, embed via Cortex, insert into DOCUMENTS | ✅ Done |
| `backend/sql/schema.sql` | Snowflake SQL | Canonical DDL for DOCUMENTS table | ✅ Done |
| `backend/rag/retriever.py` | rank-bm25, Snowflake Cortex | Hybrid BM25 + vector search, RRF merge → top 10 | ✅ Done |
| `backend/rag/reranker.py` | sentence-transformers CrossEncoder | Cross-encoder re-ranking (ms-marco-MiniLM-L-6-v2) → top 5 | ✅ Done |
| `backend/rag/generator.py` | snowflake-connector, Cortex | Prompt assembly + CORTEX.COMPLETE('mistral-7b') → {answer, sources} | ✅ Done |
| `backend/.env` | dotenv | Snowflake connection credentials | ✅ Done |
| `backend/requirements.txt` | pip | Python dependencies | ✅ Done |
| `airflow/` | Apache Airflow | Orchestrate SEC ingestion DAG | 🔲 TBD |
| `backend/api/` | FastAPI + uvicorn | REST endpoints for search and Q&A | 🔲 TBD |
| `frontend/` | TBD | Q&A chat UI | 🔲 TBD |
| `infra/` | Helm + ArgoCD | K8s deployment manifests, GitOps | 🔲 TBD |

---

## Key Design Decisions

- **SEC EDGAR as data source** — free public API, no data licensing cost; pulls latest 10-K for AAPL, MSFT, GOOGL, JPM, GS
- **No external vector DB** — `VECTOR(FLOAT, 768)` column in Snowflake; Cortex Search indexes it natively
- **No LangChain** — direct SQL calls to Cortex keep dependencies minimal and latency low
- **Cortex embedding in SQL** — `SNOWFLAKE.CORTEX.EMBED_TEXT_768('e5-base-v2', chunk_text)` runs server-side in one INSERT…SELECT; no Python ML inference
- **chunk_id as `{company}_{filing_date}_{chunk_index}`** — deterministic, human-readable PK; safe to re-run ingestion (upsert-friendly)
- **400-word chunks, 50-word overlap** — balances context richness against Cortex token limits
- **Airflow for orchestration** — scheduled re-ingestion when new filings are published
- **ArgoCD + Helm** — full GitOps: push to `main` → ArgoCD auto-syncs → cluster updates
- **Secrets separated** — Snowflake credentials live in K8s Secrets / `.env`, never in ConfigMaps or the Helm chart
