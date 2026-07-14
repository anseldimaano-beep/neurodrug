# NeuroDrug v4 — Deployment Guide

## Option 1: Local (docker-compose)

### Prerequisites
- Docker >= 24.0
- Docker Compose >= 2.20
- 8 GB RAM, 4 CPU cores

### Steps

```bash
cp .env.example .env
# Edit .env:
#   SECRET_KEY  — generate with: python -c "import secrets; print(secrets.token_hex(32))"
#   POSTGRES_PASSWORD — set a strong password

docker-compose up -d
docker-compose exec api alembic upgrade head
docker-compose exec api python scripts/seed_initial_data.py
```

### Verify

```bash
curl http://localhost:8000/health
# {"status":"healthy","version":"4.0.0"}

curl http://localhost:8000/api/v1/health/ready
# {"status":"ready","checks":{"postgres":"ok","redis":"ok"}}
```

---

## Option 2: Kubernetes (kubectl)

### Prerequisites
- kubectl >= 1.28
- Kubernetes cluster (EKS/GKE/AKS or local kind/minikube)
- Container registry (Docker Hub or ECR)

### Steps

```bash
# 1. Build and push images
docker build -t neurodrug/api:4.0.0 ./backend
docker push neurodrug/api:4.0.0

docker build -t neurodrug/frontend:4.0.0 ./frontend
docker push neurodrug/frontend:4.0.0

# 2. Create namespace and secrets
kubectl apply -f infrastructure/k8s/namespace.yaml

# Edit infrastructure/k8s/secret.yaml with real values first!
kubectl apply -f infrastructure/k8s/secret.yaml

# 3. Apply all manifests
kubectl apply -f infrastructure/k8s/

# 4. Wait for rollout
kubectl rollout status deployment/neurodrug-api -n neurodrug

# 5. Run migrations (one-off job)
kubectl exec -n neurodrug deployment/neurodrug-api -- alembic upgrade head
kubectl exec -n neurodrug deployment/neurodrug-api -- python scripts/seed_initial_data.py
```

---

## Option 3: Helm

```bash
helm upgrade --install neurodrug ./infrastructure/helm \
  --namespace neurodrug --create-namespace \
  --set image.tag=4.0.0 \
  --set secrets.postgresPassword="<your_password>" \
  --set secrets.secretKey="<your_key>"
```

---

## Option 4: AWS (Terraform)

```bash
cd infrastructure/terraform

cat > terraform.tfvars <<EOF
environment = "production"
region      = "us-east-1"
db_password = "<strong_password>"
EOF

terraform init
terraform plan
terraform apply
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POSTGRES_USER` | Yes | neurodrug_user | DB username |
| `POSTGRES_PASSWORD` | Yes | — | DB password |
| `POSTGRES_DB` | Yes | neurodrug | Database name |
| `POSTGRES_HOST` | Yes | localhost | DB host |
| `SECRET_KEY` | **Yes** | — | JWT signing key (≥32 chars) |
| `REDIS_URL` | Yes | redis://localhost:6379/0 | Redis connection |
| `CELERY_BROKER_URL` | Yes | redis://localhost:6379/1 | Celery broker |
| `SENTRY_DSN` | No | — | Sentry error tracking |
| `MLFLOW_TRACKING_URI` | No | http://localhost:5000 | MLflow server |

---

## Database Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create new migration
alembic revision --autogenerate -m "add new table"

# Rollback one step
alembic downgrade -1

# Show history
alembic history --verbose
```

---

## Model Training

```bash
# Run training script
cd backend
python scripts/run_training.py \
  --disease-efo EFO_0000519 \
  --hidden-channels 128 \
  --num-layers 3 \
  --epochs 200 \
  --lr 3e-4

# Monitor training in MLflow
open http://localhost:5000
```

---

## Health Checks

| Endpoint | Type | Expected |
|----------|------|----------|
| `GET /health` | Liveness | `{"status":"healthy"}` |
| `GET /api/v1/health/ready` | Readiness | `{"status":"ready","checks":{...}}` |
| `GET /metrics` | Prometheus | Prometheus text format |
