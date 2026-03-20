# FinSight — Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER (Browser)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    KUBERNETES CLUSTER                           │
│                                                                 │
│  ┌──────────────┐    ┌─────────────────────────────────────┐   │
│  │   ArgoCD     │───▶│         finsight namespace          │   │
│  │  (GitOps)    │    │                                     │   │
│  │              │    │  ┌─────────────────────────────┐   │   │
│  │  Watches Git │    │  │   Deployment: finsight       │   │   │
│  │  repo, auto- │    │  │                             │   │   │
│  │  syncs Helm  │    │  │  ┌───────────────────────┐  │   │   │
│  │  chart       │    │  │  │  Streamlit App        │  │   │   │
│  └──────────────┘    │  │  │  (Python 3.11)        │  │   │   │
│                      │  │  │                       │  │   │   │
│  ┌──────────────┐    │  │  │  • main.py (home)     │  │   │   │
│  │  Helm Chart  │    │  │  │  • Upload page        │  │   │   │
│  │  (values.yaml│    │  │  │  • Q&A chat page      │  │   │   │
│  │   + templates│    │  │  └───────────┬───────────┘  │   │   │
│  └──────────────┘    │  │              │               │   │   │
│                      │  │  ┌───────────▼───────────┐  │   │   │
│                      │  │  │  K8s Secret           │  │   │   │
│                      │  │  │  (Snowflake creds)    │  │   │   │
│                      │  │  └───────────────────────┘  │   │   │
│                      │  │  ┌───────────────────────┐  │   │   │
│                      │  │  │  ConfigMap            │  │   │   │
│                      │  │  │  (warehouse, DB, etc) │  │   │   │
│                      │  │  └───────────────────────┘  │   │   │
│                      │  └─────────────────────────────┘   │   │
│                      └─────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                             │
                             │ Snowpark (TLS)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SNOWFLAKE CLOUD                             │
│                                                                 │
│  FINSIGHT_DB / FINSIGHT_SCHEMA                                  │
│                                                                 │
│  ┌──────────────────┐   ┌──────────────────────────────────┐   │
│  │   DOCS_STAGE     │   │      DOCUMENT_CHUNKS table       │   │
│  │  (internal stage)│   │                                  │   │
│  │                  │   │  chunk_id    VARCHAR  (PK)        │   │
│  │  Raw PDF/TXT     │   │  source_file VARCHAR             │   │
│  │  files stored    │   │  chunk_index INTEGER             │   │
│  │  here            │   │  chunk_text  TEXT                │   │
│  └──────────────────┘   │  chunk_embedding VECTOR(768)     │   │
│                          └──────────────┬───────────────────┘   │
│                                         │                       │
│            ┌────────────────────────────┼──────────────────┐   │
│            │                            │                   │   │
│            ▼                            ▼                   │   │
│  ┌──────────────────┐       ┌───────────────────────┐      │   │
│  │  Cortex Search   │       │    Cortex LLM         │      │   │
│  │  Service         │       │  CORTEX.COMPLETE()    │      │   │
│  │                  │       │                       │      │   │
│  │  Semantic search │       │  Model: mistral-large2│      │   │
│  │  over chunk_text │       │  (or llama3.1-70b,    │      │   │
│  │  Returns top-K   │       │   snowflake-arctic)   │      │   │
│  │  relevant chunks │       │                       │      │   │
│  └──────────────────┘       └───────────────────────┘      │   │
│                                                             │   │
│  ┌──────────────────────────────────────────────────────┐  │   │
│  │  CORTEX.EMBED_TEXT_768('e5-base-v2', chunk_text)    │  │   │
│  │  (called during ingestion to generate embeddings)   │  │   │
│  └──────────────────────────────────────────────────────┘  │   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Document Ingestion Flow

```
User uploads PDF/TXT
        │
        ▼
[Streamlit: Upload page]
        │  file bytes
        ▼
[document_processor.py]
  ├── extract_text()       ← pypdf / plain text decode
  ├── chunk_text()         ← 500-word windows, 50-word overlap
  └── INSERT into DOCUMENT_CHUNKS (chunk_id, source_file, chunk_index, chunk_text)
        │
        ▼
[Snowflake SQL]
  UPDATE DOCUMENT_CHUNKS
  SET chunk_embedding = CORTEX.EMBED_TEXT_768('e5-base-v2', chunk_text)
  WHERE chunk_embedding IS NULL
```

### Q&A (RAG) Flow

```
User types question
        │
        ▼
[Streamlit: Q&A page]
        │
        ▼
[cortex_search.py]
  CORTEX.SEARCH_PREVIEW(service, query, top_k)
  → returns top-K chunks with source citations
        │
        ▼
[cortex_llm.py]
  Build RAG prompt:
    SYSTEM:  "You are FinSight..."
    CONTEXT: [chunk 1] [chunk 2] ... [chunk K]
    QUESTION: user's question
        │
        ▼
  CORTEX.COMPLETE('mistral-large2', prompt)
  → returns answer text
        │
        ▼
[Streamlit: displays answer + expandable source chunks]
```

---

## Component Responsibilities

| Component | Technology | Responsibility |
|---|---|---|
| `app/main.py` | Streamlit | App home, navigation |
| `app/pages/1_Upload_Documents.py` | Streamlit | File upload UI, ingestion trigger |
| `app/pages/2_Ask_Questions.py` | Streamlit | Chat UI, answer display |
| `app/services/snowflake_client.py` | Snowpark | Cached DB session |
| `app/services/document_processor.py` | Python + SQL | Parse, chunk, embed, store |
| `app/services/cortex_search.py` | Cortex Search | Semantic retrieval |
| `app/services/cortex_llm.py` | Cortex LLM | RAG prompt + answer generation |
| `sql/setup.sql` | Snowflake SQL | Provision all Snowflake objects |
| `helm/finsight/` | Helm | Templated K8s deployment |
| `argocd/application.yaml` | ArgoCD | GitOps sync from repo → cluster |

---

## Key Design Decisions

- **No external vector DB** — Cortex Search Service manages indexing natively inside Snowflake
- **No LangChain** — direct SQL calls to Cortex keep dependencies minimal and latency low
- **Snowpark session cached** via `@st.cache_resource` — single connection reused across all user interactions
- **ArgoCD + Helm** — full GitOps: push to `main` → ArgoCD auto-syncs → cluster updates
- **Secrets separated** — Snowflake credentials live in K8s Secrets, never in ConfigMaps or the Helm chart
