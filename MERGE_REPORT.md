# NeuroDrug v4 — Merge Report

## 1. Codebase Audit Summary

### Project A: neurodrug_web_research_v2
- 77 files across backend, frontend, infrastructure
- **Unique strengths**: HGT/GNN architecture, knowledge graph builder, drug repurposing
  service, ranking engine, validation services (biological/clinical/literature),
  AI assistant, explainability, reporting, NLP (PubMed miner), frontend dashboard,
  Helm/K8s/Terraform infra
- **Missing**: config.py, logging.py, db session, domain model, schemas, ETL pipelines,
  celery/tasks, alembic migrations, requirements.txt, docker-compose

### Project B: neurodrug_web_research (base)
- 47 files focused on clean engineering foundations
- **Unique strengths**: Comprehensive SQLAlchemy domain model (364 lines), async DB session,
  pydantic-settings config, structured logging, auth service, 7 ETL clients + orchestrator,
  celery tasks, Alembic migrations, docker-compose with Prometheus/Grafana, requirements.txt,
  `.env.example`
- **Missing**: ML layer, graph layer, NLP, advanced services, frontend, K8s/Helm, CI/CD

---

## 2. Shared Components (Duplicated)

| Component | Project A | Project B | Resolution |
|-----------|-----------|-----------|------------|
| `main.py` | ✅ (with SecurityHeadersMiddleware) | ✅ (simpler) | **Merged** — A's middleware + B's Sentry + metrics |
| `api/v1/api.py` | ✅ (9 routers) | ✅ (4 routers) | **Merged** — all 9 routers from A |
| FastAPI app factory | ✅ | ✅ | **Merged** — rate-limiter + security headers + Prometheus |

---

## 3. Unique Components

### Project A Only → Preserved in v4

| Component | Description |
|-----------|-------------|
| `ml/models/hgt.py` | HeteroGNN + HGT encoder + LinkPredictor |
| `ml/trainer.py` | HGTTrainer with cosine annealing, early stopping, checkpointing |
| `ml/predictor.py` | DrugRepurposingPredictor with batch inference |
| `ml/metrics.py` | AUROC, AUPRC, Hits@K, MRR, NDCG |
| `ml/features.py` | Gene/Drug/Disease feature builders |
| `ml/mlflow_tracker.py` | MLflow experiment tracking |
| `ml/registry.py` | Model registry (file-backed) |
| `ml/models/baselines.py` | LogisticRegression, RandomForest baselines |
| `graph/builder.py` | KnowledgeGraphBuilder (NetworkX + DB) |
| `graph/hetero_data.py` | HeteroData converter for PyG |
| `graph/query.py` | Graph query utilities |
| `nlp/pubmed_miner.py` | Async PubMed search + summary fetcher |
| `nlp/evidence_extractor.py` | Evidence level classification |
| `services/repurposing.py` | DrugRepurposingService (full pipeline) |
| `services/ranking.py` | PredictionRanker (novelty + confidence) |
| `services/validation/biological.py` | Gene overlap validation |
| `services/validation/clinical.py` | Clinical trial validation |
| `services/validation/literature.py` | Literature evidence validation |
| `services/reporting.py` | PDF/DOCX/HTML report generation |
| `services/ai_assistant.py` | AI research assistant |
| `services/graph_viz.py` | Graph visualization service |
| `middleware/security.py` | SecurityHeadersMiddleware (HSTS, CSP, etc.) |
| `core/security.py` | RateLimiter + APIKeyBearer |
| Frontend (Next.js) | Dashboard, KG explorer, prediction table |
| Helm chart | K8s Helm chart with autoscaling |
| Terraform | AWS EKS + RDS + ElastiCache |
| CI/CD (.github/) | GitHub Actions test + deploy |

### Project B Only → Preserved in v4

| Component | Description |
|-----------|-------------|
| `core/config.py` | Pydantic-settings with all API endpoints |
| `core/logging.py` | structlog + python-json-logger |
| `db/base.py` | AsyncAttrs DeclarativeBase with soft-delete |
| `db/session.py` | Async SQLAlchemy engine + session factory |
| `models/domain.py` | Full domain model (20 tables, 364 lines) |
| `schemas/auth.py` | UserBase, UserCreate, Token schemas |
| `schemas/etl.py` | ETLJob schemas |
| `services/auth_service.py` | JWT + bcrypt auth service |
| `services/etl/orchestrator.py` | ETL pipeline orchestrator |
| `services/etl/opentargets.py` | OpenTargets GraphQL client |
| `services/etl/string.py` | STRING PPI client |
| `services/etl/dgidb.py` | DGIdb drug-gene client |
| `services/etl/chembl.py` | ChEMBL drug client |
| `services/etl/clinicaltrials.py` | ClinicalTrials.gov client |
| `services/etl/uniprot.py` | UniProt protein client |
| `services/etl/gdc.py` | GDC cancer genomics client |
| `tasks/etl_tasks.py` | Celery ETL tasks |
| `celery_app.py` | Celery app configuration |
| `alembic/` | Async Alembic migrations |
| `docker-compose.yml` | Full local stack |
| `monitoring/prometheus.yml` | Prometheus scrape config |

---

## 4. Conflicts Resolved

| Conflict | Resolution |
|----------|------------|
| `main.py` had different middleware | Merged: kept SecurityHeadersMiddleware (A) + rate limiter (A) + Prometheus (B) |
| `api/v1/api.py` had different router counts | Merged: v4 includes all 9 routers |
| `requirements.txt` missing from A | Used B's requirements as base, added all ML/graph deps from A |
| No `api/deps.py` in A (just inlined) | Used B's proper `deps.py` |
| Different auth approaches | B's AuthService is cleaner; used that |
| Config: A had `core/security.py`, B had `core/config.py` | Both kept — no conflict |
| Domain model: A had inline models, B had 364-line comprehensive model | B's model wins |

---

## 5. New Components Added in v4

| Component | Description |
|-----------|-------------|
| `ml/cross_validation.py` | K-fold, Nested CV, Bootstrap, Temporal validation |
| `ml/benchmark.py` | Multi-model benchmark leaderboard runner |
| `ml/explainability.py` | SHAP, IntegratedGradients, AttentionVisualizer, GraphExplainer |
| `core/metrics.py` | Prometheus metrics (request count/latency, ML metrics, ETL metrics) |
| `schemas/prediction.py` | Prediction + RepurposingRequest schemas |
| `schemas/graph.py` | Graph node/edge/subgraph schemas |
| `schemas/validation.py` | Validation request/result schemas |
| `alembic/versions/001_initial_schema.py` | Complete initial migration (all 20 tables) |
| `scripts/seed_initial_data.py` | Full seed script with diseases, drugs, data sources |
| Frontend validation page | Validation Center UI page |
| Frontend predictions page | Predictions browsing page |
| `frontend/Dockerfile` | Multi-stage Next.js Docker image |
| K8s HPA | Horizontal Pod Autoscaler |
| K8s PVC | Persistent volume for checkpoints |
| K8s ConfigMap/Secret | Environment configuration |

---

## 6. Architecture Diagram

```
Browser / API Clients
        │
   [Next.js Frontend :3000]
        │
   [FastAPI Gateway :8000]   ← rate-limiting, CORS, security headers
        │
   [API Router /api/v1/]
        │
   ┌────┴────────────────────────────────────────────────────────┐
   │  auth  │  etl  │  health  │  predictions  │  repurposing   │
   │  graph │  validation  │  reports  │  assistant             │
   └────┬────────────────────────────────────────────────────────┘
        │
   [Services Layer]
   ├── AuthService          (JWT + bcrypt)
   ├── DrugRepurposingService  (full prediction pipeline)
   ├── PredictionRanker     (novelty + confidence scoring)
   ├── ETLOrchestrator      (7 data sources)
   ├── ValidationServices   (biological / clinical / literature)
   ├── ReportingService     (PDF / DOCX / HTML)
   ├── AIAssistantService   (research assistant)
   └── GraphVizService      (subgraph visualization)
        │
   ┌────┴──────────────────────────────────────────┐
   │  Knowledge Graph Layer                         │
   │  ├── KnowledgeGraphBuilder (NetworkX + DB)     │
   │  ├── HeteroDataConverter   (PyG HeteroData)    │
   │  └── GraphQueryService                         │
   └────┬──────────────────────────────────────────┘
        │
   ┌────┴──────────────────────────────────────────┐
   │  ML Layer                                       │
   │  ├── NeuroDrugHGT (encoder + link predictor)   │
   │  ├── Baselines (LR, RF, XGBoost, LightGBM)     │
   │  ├── HGTTrainer (early stopping, checkpoints)  │
   │  ├── CrossValidator / BootstrapValidator        │
   │  ├── BenchmarkRunner (leaderboard)              │
   │  ├── SHAPExplainer / AttentionVisualizer        │
   │  └── MLflowTracker + ModelRegistry              │
   └────┬──────────────────────────────────────────┘
        │
   ┌────┴────────────────────────────────┐
   │  Data Layer                          │
   │  ├── PostgreSQL (SQLAlchemy async)   │
   │  ├── Redis (cache + Celery broker)   │
   │  └── MLflow (experiment store)       │
   └────────────────────────────────────┘
        │
   [ETL Workers (Celery)]
   ├── OpenTargets (GraphQL)
   ├── STRING PPI
   ├── DGIdb
   ├── ChEMBL
   ├── ClinicalTrials.gov
   ├── UniProt
   ├── GDC (cancer genomics)
   └── PubMed (literature)
```
