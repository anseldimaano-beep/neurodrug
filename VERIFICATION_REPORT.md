# NeuroDrug v4-Fixed — Verification Report

**Date:** 2026-06-05  
**Archive:** `neurodrug-v4-fixed.zip`  
**Audited against:** Prior audit findings (C1–C10 critical, H1–H6 high)

---

## Score Delta

| Dimension                | Previous | After v4-fixed | Δ  |
|--------------------------|----------|----------------|----|
| Architecture             | 71/100   | 71/100         | 0  |
| Backend correctness      | 44/100   | 48/100         | +4 |
| Frontend correctness     | 42/100   | 48/100         | +6 |
| Deployment readiness     | 38/100   | 44/100         | +6 |
| **Overall production**   | **48/100** | **53/100**   | +5 |

Three issues were fixed; eleven remain unresolved.

---

## Issue Scorecard

### CRITICAL issues (deployment blockers)

| ID  | Description                                               | Status       |
|-----|-----------------------------------------------------------|--------------|
| C1  | `DrugRepurposingPredictor.load_checkpoint` method missing | ❌ NOT FIXED |
| C2  | `drug_id=None` when drug not found → NOT NULL violation   | ❌ NOT FIXED |
| C3  | `fetchGraphData` path param vs backend query param        | ❌ NOT FIXED |
| C4  | `/validation/run` POST endpoint missing from backend      | ❌ NOT FIXED |
| C5  | Frontend volume overlay removed ✅; backend `./backend:/app` remains (dev-only intent) | ✅ FIXED (frontend) |
| C6  | `NEXT_PUBLIC_API_URL=http://localhost:8000` ← browser-reachable | ✅ FIXED |
| C7  | Helm `_helpers.tpl` missing; `deployment.yaml` is a broken stub | ❌ NOT FIXED |
| C8  | Alembic `env.py` passes sync `psycopg2` URL to `async_engine_from_config` | ❌ NOT FIXED |
| C9a | `metadata` column renamed to `extra_metadata` ✅ | ✅ FIXED |
| C9b | `ApiLog`/`AuditLog` `Index(..., "timestamp")` references column that doesn't exist | ❌ NOT FIXED |
| C10 | `builder.py._get_node_id` accesses lazy-loaded `inter.source_gene.symbol` in async context → `MissingGreenlet` crash | ❌ NOT FIXED |

### HIGH-PRIORITY issues

| ID  | Description                                               | Status       |
|-----|-----------------------------------------------------------|--------------|
| H1  | `PredictionDashboard` reads `data?.predictions` but `/predictions` returns an array directly | ❌ NOT FIXED |
| H2  | Validation page calls `/validation/${predictionId}` which doesn't exist | ❌ NOT FIXED |
| H3  | `predictions/page.tsx` passes no `diseaseId` prop (blank dashboard) | ⚠️ MINOR |
| H4  | `graph/page.tsx` passes no `diseaseId` prop (explorer always empty) | ⚠️ MINOR |
| H5  | `redis_data` volume declared in compose but redis service never mounts it — data lost on restart | ❌ NOT FIXED |

---

## Detailed Findings for Remaining Issues

### C1 — `DrugRepurposingPredictor.load_checkpoint` missing

`repurposing.py:73` calls `predictor.load_checkpoint(model_version.checkpoint_path)` but
`DrugRepurposingPredictor` has only `predict_all_pairs` and `rank_candidates`. Every inference
call raises `AttributeError` immediately.

**Fix:** Add `load_checkpoint` to `DrugRepurposingPredictor`. See `backend/app/ml/predictor.py`.

---

### C2 — `Prediction.drug_id` NOT NULL violated

`repurposing.py:87`:
```python
pred = Prediction(
    drug_id=drug.id if drug else None,   # ← None when drug is unknown
```

`domain.py:225`:
```python
drug_id: Mapped[int] = mapped_column(ForeignKey("drugs.id"), nullable=False, ...)
```

When the model produces a candidate whose name doesn't match any `Drug` row, the INSERT fails
with `IntegrityError: NOT NULL constraint failed: predictions.drug_id`. The entire inference run
is rolled back.

**Fix:** Skip predictions whose drug is not found in the DB. See `backend/app/services/repurposing.py`.

---

### C3 — `fetchGraphData` wrong URL pattern

`frontend/lib/api.ts:33`:
```ts
apiClient.get(`/graph/subgraph/${encodeURIComponent(diseaseId)}`, { params: { hops: 2 } })
// Produces: GET /api/v1/graph/subgraph/EFO_0000674?hops=2
```

Backend `graph.py:10`:
```python
@router.get("/subgraph")
async def get_subgraph(disease_id: str, hops: int = 2, ...):
# Expects: GET /api/v1/graph/subgraph?disease_id=EFO_0000674&hops=2
```

The path-parameterised URL hits a 404. The same bug affects `api.getSubgraph`.

**Fix:** Change both calls to use `params: { disease_id: diseaseId, hops }`. See `frontend/lib/api.ts`.

---

### C4 — `/validation/run` endpoint missing

`frontend/lib/api.ts:57`:
```ts
validatePrediction: (predictionId: number) =>
  apiClient.post("/validation/run", { prediction_id: predictionId }),
```

`backend/app/api/v1/endpoints/validation.py` only has:
- `POST /{prediction_id}/literature`
- `POST /{prediction_id}/clinical`
- `POST /{prediction_id}/biological`

No `/run` route exists. Every validation click returns 404.

**Fix:** Add a `POST /run` orchestrating endpoint. See `backend/app/api/v1/endpoints/validation.py`.

---

### C7 — Helm `_helpers.tpl` missing

`infrastructure/helm/templates/deployment.yaml` contains only:
```yaml
{{- include "neurodrug.deployment" . -}}
```

There is no `_helpers.tpl` defining `neurodrug.deployment`. `helm install` fails with
`Error: template: neurodrug/templates/deployment.yaml: ... function "neurodrug.deployment" not defined`.

**Fix:** Create `_helpers.tpl` with the full deployment template. See `infrastructure/helm/templates/`.

---

### C8 — Alembic async URL mismatch

`alembic/env.py:41`:
```python
configuration["sqlalchemy.url"] = get_url()   # returns postgresql+psycopg2://...
connectable = async_engine_from_config(configuration, ...)
```

`async_engine_from_config` requires an async driver (`asyncpg`). Passing a `psycopg2` sync URL
raises `ArgumentError: Could not load backend 'psycopg2'` at migration time.

`run_migrations_offline` (which uses the sync URL correctly) is unaffected.

**Fix:** Have `run_async_migrations` use `settings.DATABASE_URL` (the `asyncpg` URL).
See `backend/alembic/env.py`.

---

### C9b — `ApiLog` / `AuditLog` index on non-existent column

`domain.py:308`:
```python
class ApiLog(Base):
    __table_args__ = (
        Index("ix_api_log_timestamp", "timestamp"),
        ...
    )
```

`Base` provides `created_at` and `updated_at`. There is no `timestamp` column. SQLAlchemy 2.0
raises `ArgumentError: Column 'timestamp' is not a column or mapper-level relationship`
during mapper configuration, preventing the entire ORM from initialising.

**Fix:** Change index to `"created_at"` in both `ApiLog` and `AuditLog`. See `backend/app/models/domain.py`.

---

### C10 — Lazy-load crash in async builder

`builder.py:_get_node_id()`:
```python
node = self.nx_graph.nodes.get(f"Gene:{inter.source_gene.symbol}") \
       if hasattr(inter, "source_gene") else None
```

`Interaction.source_gene` is a SQLAlchemy lazy relationship. `hasattr` on a mapped attribute
always returns `True` (the descriptor exists). Accessing `.symbol` triggers a lazy SQL query
inside an async session context, raising `sqlalchemy.exc.MissingGreenlet`. The graph build
crashes the first time any interaction has a linked gene.

**Fix:** Build ID→node-id lookup tables during the node-loading phase and replace relationship
accesses with direct ID lookups. See `backend/app/graph/builder.py`.

---

### H1 — `PredictionDashboard` wrong data accessor

`frontend/components/prediction-dashboard.tsx:23`:
```ts
const predictions = data?.predictions || [];
```

`GET /api/v1/predictions/` returns a JSON array directly (FastAPI serialises
`result.scalars().all()`). `data?.predictions` is always `undefined`; the table is
always empty even when predictions exist.

**Fix:** `const predictions = Array.isArray(data) ? data : [];`

---

### H2 — Validation page wrong endpoint

`frontend/app/validation/page.tsx`:
```ts
queryFn: () => apiClient.get(`/validation/${predictionId}`),
```

No such route exists. Should POST to `/validation/run` (after C4 is fixed).

---

### H5 — Redis data not persisted

`docker-compose.yml` declares `redis_data:` in the top-level `volumes` block but the `redis`
service has no `volumes:` key. Redis data is lost on every container restart, clearing all
Celery queues and cached results.

**Fix:** Mount the volume into the redis service. See `docker-compose.yml`.

---

## Files Delivered

| Path | Change |
|------|--------|
| `backend/app/ml/predictor.py` | Add `load_checkpoint` (C1) |
| `backend/app/services/repurposing.py` | Guard None drug_id, add selectinload (C2, C10) |
| `backend/app/graph/builder.py` | Remove lazy-load access, use ID lookups (C10) |
| `frontend/lib/api.ts` | Fix fetchGraphData query param (C3) |
| `backend/app/api/v1/endpoints/validation.py` | Add `/run` endpoint (C4) |
| `backend/alembic/env.py` | Use asyncpg URL for async engine (C8) |
| `backend/app/models/domain.py` | Fix timestamp index column name (C9b) |
| `infrastructure/helm/templates/_helpers.tpl` | Create full deployment helper (C7) |
| `infrastructure/helm/templates/deployment.yaml` | Proper Helm template (C7) |
| `frontend/components/prediction-dashboard.tsx` | Fix data?.predictions accessor (H1) |
| `frontend/app/validation/page.tsx` | Call correct /validation/run endpoint (H2) |
| `docker-compose.yml` | Mount redis_data volume (H5) |
