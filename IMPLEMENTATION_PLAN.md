# FinSight — Implementation Plan

## Overview

Step-by-step guide to set up, run, and deploy the FinSight Financial Document Q&A Platform.

---

## Phase 1: Prerequisites

### 1.1 Required Accounts & Tools

| Tool | Purpose | Version |
|---|---|---|
| Python | Runtime | 3.11+ |
| pip | Package manager | latest |
| Docker | Container build | 20.x+ |
| kubectl | K8s CLI | 1.28+ |
| Helm | K8s package manager | 3.x+ |
| ArgoCD CLI | GitOps management | 2.x+ |
| Snowflake account | Database + Cortex AI | Enterprise or higher |
| Git | Source control | latest |

### 1.2 Snowflake Requirements

- Account tier: **Enterprise or higher** (required for Cortex AI features)
- Cortex features enabled: `CORTEX.COMPLETE`, `CORTEX.EMBED_TEXT_768`, `CORTEX SEARCH SERVICE`
- A user with `ACCOUNTADMIN` or `SYSADMIN` + `CORTEX_USER` role

---

## Phase 2: Snowflake Setup

### 2.1 Run Setup SQL ✅

Log into Snowflake and run the canonical DDL:

```sql
-- File: backend/sql/schema.sql
CREATE TABLE IF NOT EXISTS DOCUMENTS (
    chunk_id    VARCHAR         PRIMARY KEY,
    company     VARCHAR         NOT NULL,
    filing_date DATE            NOT NULL,
    chunk_text  TEXT            NOT NULL,
    embedding   VECTOR(FLOAT, 768),
    created_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP()
);
```

> The `snowflake_loader.py` also creates this table programmatically via `CREATE TABLE IF NOT EXISTS` — `schema.sql` is the authoritative source of truth.

### 2.2 Verify Setup

```sql
USE DATABASE FINSIGHT_DB;
USE SCHEMA RAG;

SHOW TABLES;           -- Should show DOCUMENTS
SELECT COUNT(*) FROM DOCUMENTS;
```

---

## Phase 3: Local Development Setup ✅

### 3.1 Folder Structure Created ✅

```
FinSight/
├── backend/
│   ├── ingestion/
│   │   ├── sec_loader.py          ✅ SEC EDGAR fetch, parse, chunk
│   │   └── snowflake_loader.py    ✅ Cortex embed + insert
│   ├── sql/
│   │   └── schema.sql             ✅ DOCUMENTS DDL
│   ├── .env                       ✅ Snowflake credentials
│   └── requirements.txt           ✅ Python deps
├── frontend/                      🔲 TBD
├── infra/                         🔲 TBD
└── airflow/                       🔲 TBD
```

### 3.2 Configure Environment ✅

`backend/.env` is populated with:

```env
SNOWFLAKE_ACCOUNT=...
SNOWFLAKE_USER=...
SNOWFLAKE_PASSWORD=...
SNOWFLAKE_WAREHOUSE=FINSIGHT_WH
SNOWFLAKE_DATABASE=FINSIGHT_DB
SNOWFLAKE_SCHEMA=RAG
```

### 3.3 Install Dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3.4 Run SEC Ingestion

```bash
# Fetch, chunk, embed, and store all 5 tickers in one shot
cd backend
python -c "
from ingestion.sec_loader import load_sec_filings
from ingestion.snowflake_loader import load_chunks
load_chunks(load_sec_filings())
"
```

Or smoke-test the loader with synthetic data:

```bash
python ingestion/snowflake_loader.py
```

### 3.5 Start FastAPI Backend (TBD)

```bash
uvicorn api.main:app --reload --port 8000
```

---

## Phase 4: Docker Build

### 4.1 Build Image

```bash
docker build -t finsight:latest .
```

### 4.2 Run Container Locally

```bash
docker run --env-file .env -p 8501:8501 finsight:latest
```

Verify at http://localhost:8501.

### 4.3 Push to Registry

```bash
# Tag for your registry
docker tag finsight:latest your-registry/finsight:1.0.0

# Push
docker push your-registry/finsight:1.0.0
```

Update `helm/finsight/values.yaml`:

```yaml
image:
  repository: your-registry/finsight
  tag: "1.0.0"
```

---

## Phase 5: Kubernetes Deployment

### 5.1 Create Namespace

```bash
kubectl apply -f k8s/namespace.yaml
```

### 5.2 Create Snowflake Secret

Base64-encode your credentials and update `k8s/secret.yaml`, then apply:

```bash
# Encode values
echo -n 'xy12345.us-east-1' | base64
echo -n 'your_username'     | base64
echo -n 'your_password'     | base64

# Edit k8s/secret.yaml with the encoded values, then:
kubectl apply -f k8s/secret.yaml
```

### 5.3 Apply Config & Workloads

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### 5.4 Verify Pods

```bash
kubectl get pods -n finsight
kubectl logs -n finsight -l app=finsight
```

### 5.5 Port-Forward for Testing

```bash
kubectl port-forward -n finsight svc/finsight 8080:80
```

Open http://localhost:8080.

---

## Phase 6: Helm Chart Deployment

### 6.1 Install via Helm

```bash
helm install finsight helm/finsight \
  --namespace finsight \
  --create-namespace \
  --set image.repository=your-registry/finsight \
  --set image.tag=1.0.0 \
  --set snowflake.existingSecret=finsight-snowflake-secret
```

### 6.2 Upgrade

```bash
helm upgrade finsight helm/finsight \
  --namespace finsight \
  --set image.tag=1.1.0
```

### 6.3 Enable Ingress (Optional)

```bash
helm upgrade finsight helm/finsight \
  --namespace finsight \
  --set ingress.enabled=true \
  --set ingress.host=finsight.your-domain.com
```

---

## Phase 7: ArgoCD GitOps Setup

### 7.1 Install ArgoCD (if not already installed)

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### 7.2 Configure the Application

Update `argocd/application.yaml`:

```yaml
source:
  repoURL: https://github.com/your-org/FinSight.git   # your actual repo URL
  targetRevision: main
```

### 7.3 Apply ArgoCD Application

```bash
kubectl apply -f argocd/application.yaml
```

### 7.4 Verify Sync

```bash
# Via CLI
argocd app get finsight
argocd app sync finsight

# Or open the ArgoCD UI
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

### 7.5 GitOps Workflow (ongoing)

```
Developer pushes to main branch
        │
        ▼
ArgoCD detects diff (polls every 3 min or via webhook)
        │
        ▼
ArgoCD syncs Helm chart to cluster
        │
        ▼
Rolling update applied — zero downtime
```

---

## Phase 8: Verification Checklist

| Step | Check | Expected Result |
|---|---|---|
| Snowflake | `SHOW CORTEX SEARCH SERVICES` | `FINSIGHT_SEARCH_SERVICE` listed |
| Local run | `streamlit run app/main.py` | App loads at localhost:8501 |
| Docker | `docker run --env-file .env ...` | App loads at localhost:8501 |
| K8s pod | `kubectl get pods -n finsight` | Pod in `Running` state |
| K8s health | Readiness probe | `/_stcore/health` returns 200 |
| ArgoCD | `argocd app get finsight` | Status: `Synced`, Health: `Healthy` |
| End-to-end | Upload PDF → Ask question | Answer with source citations returned |

---

## Troubleshooting

### Cortex features not available
- Ensure your Snowflake account is **Enterprise** tier or higher
- Run: `SELECT SNOWFLAKE.CORTEX.COMPLETE('mistral-large2', 'hello')` to verify access
- Contact Snowflake support to enable Cortex if needed

### Snowpark connection failure
- Verify `SNOWFLAKE_ACCOUNT` format: `orgname-accountname` or `accountlocator.region`
- Test credentials in Snowflake UI before using in the app

### Pod CrashLoopBackOff
```bash
kubectl describe pod -n finsight <pod-name>
kubectl logs -n finsight <pod-name> --previous
```
- Usually indicates missing or malformed Secret values

### ArgoCD out of sync
```bash
argocd app sync finsight --force
```

---

## Project File Reference

| File | Purpose | Status |
|---|---|---|
| `backend/ingestion/sec_loader.py` | Fetch & chunk SEC 10-K filings for 5 tickers | ✅ Done |
| `backend/ingestion/snowflake_loader.py` | Stage, embed via Cortex, insert into DOCUMENTS | ✅ Done |
| `backend/sql/schema.sql` | Canonical DOCUMENTS table DDL | ✅ Done |
| `backend/.env` | Snowflake connection credentials | ✅ Done |
| `backend/requirements.txt` | Python dependencies | ✅ Done |
| `backend/api/` | FastAPI Q&A endpoints | 🔲 TBD |
| `frontend/` | Chat UI | 🔲 TBD |
| `airflow/` | SEC ingestion DAG | 🔲 TBD |
| `infra/` | Helm chart + ArgoCD manifests | 🔲 TBD |
| `ARCHITECTURE.md` | System architecture overview | ✅ Updated |
