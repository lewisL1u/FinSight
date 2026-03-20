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

### 2.1 Run Setup SQL

Log into Snowflake and execute the setup script:

```sql
-- In Snowflake UI (Worksheets) or SnowSQL CLI:
-- File: sql/setup.sql
```

This provisions:
- `FINSIGHT_DB` database and `FINSIGHT_SCHEMA` schema
- `FINSIGHT_WH` warehouse (X-Small, auto-suspend 120s)
- `DOCS_STAGE` internal stage for raw files
- `DOCUMENT_CHUNKS` table with `VECTOR(FLOAT, 768)` embedding column
- `FINSIGHT_SEARCH_SERVICE` Cortex Search Service (target lag: 1 minute)

### 2.2 Verify Setup

```sql
USE DATABASE FINSIGHT_DB;
USE SCHEMA FINSIGHT_SCHEMA;

SHOW TABLES;                          -- Should show DOCUMENT_CHUNKS
SHOW STAGES;                          -- Should show DOCS_STAGE
SHOW CORTEX SEARCH SERVICES;          -- Should show FINSIGHT_SEARCH_SERVICE
```

---

## Phase 3: Local Development Setup

### 3.1 Clone & Configure

```bash
cd D:/projects/python/FinSight

# Copy environment template
cp .env.example .env
```

Edit `.env` with your Snowflake credentials:

```env
SNOWFLAKE_ACCOUNT=xy12345.us-east-1
SNOWFLAKE_USER=your_username
SNOWFLAKE_PASSWORD=your_password
SNOWFLAKE_ROLE=ACCOUNTADMIN
SNOWFLAKE_WAREHOUSE=FINSIGHT_WH
SNOWFLAKE_DATABASE=FINSIGHT_DB
SNOWFLAKE_SCHEMA=FINSIGHT_SCHEMA
```

### 3.2 Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 3.3 Run Locally

```bash
streamlit run app/main.py
```

Open http://localhost:8501 in your browser.

### 3.4 Smoke Test

1. Navigate to **Upload Documents**
2. Upload a small PDF or TXT financial document
3. Wait for ingestion confirmation (chunk count shown)
4. Navigate to **Ask Questions**
5. Type: _"What are the key financial highlights?"_
6. Verify an answer is returned with source citations

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

| File | Purpose |
|---|---|
| `sql/setup.sql` | Provision Snowflake objects |
| `sql/teardown.sql` | Destroy all Snowflake objects |
| `.env.example` | Environment variable template |
| `requirements.txt` | Python dependencies |
| `Dockerfile` | Container image definition |
| `k8s/` | Raw Kubernetes manifests |
| `helm/finsight/` | Helm chart for parameterized deployment |
| `argocd/application.yaml` | ArgoCD GitOps Application manifest |
| `ARCHITECTURE.md` | System architecture overview |
