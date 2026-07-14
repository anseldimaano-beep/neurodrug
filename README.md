# 🧬 NeuroDrug v4 — AI Drug Repurposing Platform

[![CI](https://github.com/neurodrug/platform/actions/workflows/test.yml/badge.svg)](https://github.com/neurodrug/platform/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688.svg)](https://fastapi.tiangolo.com)

Production-grade drug repurposing AI platform combining heterogeneous graph neural
networks (HGT), knowledge graphs, and multi-source biomedical data to identify
novel drug–disease associations with explainability and validation.

---

## 🚀 Quickstart (Docker Compose)

```bash
# 1 — clone & configure
git clone https://github.com/neurodrug/platform.git
cd neurodrug-v4
cp .env.example .env           # edit SECRET_KEY at minimum

# 2 — launch the full stack (API, worker, postgres, redis, mlflow, prometheus, grafana)
docker-compose up -d

# 3 — run database migrations
docker-compose exec api alembic upgrade head

# 4 — seed initial data
docker-compose exec api python scripts/seed_initial_data.py

# 5 — open the UI
open http://localhost:3000      # Frontend
open http://localhost:8000/api/docs  # FastAPI Swagger
open http://localhost:9090      # Prometheus
open http://localhost:3001      # Grafana  (admin/admin)
open http://localhost:5000      # MLflow
```

---

## 🔬 Architecture

```
Next.js Frontend  →  FastAPI Gateway  →  Services  →  HGT Model  →  PostgreSQL
                                      ↓
                               Celery Workers  →  ETL Pipelines  →  7 data sources
```

### Data Sources
| Source | Type | Content |
|--------|------|---------|
| OpenTargets | GraphQL API | Gene–disease associations |
| STRING | REST | Protein–protein interactions |
| DGIdb | REST | Drug–gene interactions |
| ChEMBL | REST | Drug properties + mechanisms |
| ClinicalTrials.gov | REST | Trial status + phases |
| UniProt | REST | Protein sequences + functions |
| GDC | REST | Cancer genomics mutations |
| PubMed | NCBI eUtils | Literature evidence |

### ML Models
| Model | Type | Notes |
|-------|------|-------|
| NeuroDrugHGT | Graph Neural Network | HGT + link prediction |
| Logistic Regression | Baseline | L2 regularisation |
| Random Forest | Baseline | 200 estimators |
| XGBoost | Baseline | Gradient boosting |
| LightGBM | Baseline | Fast gradient boosting |

---

## 🏗️ Local Development (without Docker)

```bash
# Prerequisites: Python 3.11, PostgreSQL 16, Redis 7

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python scripts/seed_initial_data.py
uvicorn app.main:app --reload --port 8000

# Celery Worker (separate terminal)
celery -A celery_app worker --loglevel=info

# Frontend
cd ../frontend
npm install
npm run dev
```

---

## 🧪 Running Tests

```bash
cd backend
pytest tests/ -v --cov=app --cov-report=term-missing
```

Test suite covers:
- Unit: metrics, features, cross-validation, auth, ETL
- Integration: all API endpoints, knowledge graph builder

---

## 📡 API Reference

Full interactive docs at `/api/docs`.

### Key Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/auth/login` | Obtain JWT token |
| `GET`  | `/api/v1/auth/me` | Current user |
| `POST` | `/api/v1/repurposing/predict` | Run drug repurposing |
| `GET`  | `/api/v1/predictions/` | List predictions |
| `POST` | `/api/v1/predictions/run` | Queue repurposing job |
| `POST` | `/api/v1/etl/ingest/opentargets` | Trigger ETL pipeline |
| `GET`  | `/api/v1/etl/jobs` | List ETL jobs |
| `GET`  | `/api/v1/graph/subgraph/{node_id}` | Get knowledge subgraph |
| `GET`  | `/api/v1/graph/stats` | Graph statistics |
| `POST` | `/api/v1/validation/run` | Validate prediction |
| `GET`  | `/api/v1/reports/{prediction_id}` | Download PDF report |
| `GET`  | `/api/v1/health/` | Liveness probe |
| `GET`  | `/api/v1/health/ready` | Readiness probe |
| `GET`  | `/metrics` | Prometheus metrics |

---

## ☸️ Kubernetes Deployment

```bash
# Apply all manifests
kubectl apply -f infrastructure/k8s/

# Or use Helm
helm upgrade --install neurodrug ./infrastructure/helm \
  --namespace neurodrug --create-namespace \
  --set image.tag=4.0.0

# Check rollout
kubectl rollout status deployment/neurodrug-api -n neurodrug
```

---

## 📊 Monitoring

| Service | URL | Purpose |
|---------|-----|---------|
| Prometheus | `:9090` | Metrics collection |
| Grafana | `:3001` | Dashboards |
| MLflow | `:5000` | Experiment tracking |
| Flower | `:5555` | Celery task monitoring |

---

## 🔒 Security

- **JWT** authentication (HS256, configurable expiry)
- **RBAC** roles: admin, researcher, viewer
- **Rate limiting**: configurable per-IP (default 60 req/min)
- **Security headers**: HSTS, CSP, X-Frame-Options, etc.
- **Audit logging** on all write operations
- **Encrypted passwords** (bcrypt, cost factor 12)

---

## 📁 Repository Structure

```
neurodrug-v4/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # 9 endpoint modules
│   │   ├── core/               # config, logging, security, metrics
│   │   ├── db/                 # SQLAlchemy base + session
│   │   ├── graph/              # KG builder + HeteroData converter
│   │   ├── middleware/         # SecurityHeadersMiddleware
│   │   ├── ml/                 # HGT, baselines, trainer, CV, XAI
│   │   ├── models/             # SQLAlchemy domain models (20 tables)
│   │   ├── nlp/                # PubMed miner, evidence extractor
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic layer
│   │   └── tasks/              # Celery ETL tasks
│   ├── alembic/                # Database migrations
│   ├── scripts/                # Seed + training scripts
│   └── tests/                  # Unit + integration tests
├── frontend/                   # Next.js 14 + TypeScript + Tailwind
├── infrastructure/
│   ├── k8s/                    # Kubernetes manifests
│   ├── helm/                   # Helm chart
│   ├── terraform/              # AWS IaC
│   └── monitoring/             # Prometheus + Grafana config
├── .github/workflows/          # CI/CD (test + deploy)
├── docker-compose.yml
├── .env.example
├── MERGE_REPORT.md
└── README.md
```

---

## 📄 License

MIT © NeuroDrug Team
