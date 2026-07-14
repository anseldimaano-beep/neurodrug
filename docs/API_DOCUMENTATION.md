# NeuroDrug v4 — API Documentation

Base URL: `http://localhost:8000`
Interactive Docs: `http://localhost:8000/api/docs`
OpenAPI JSON: `http://localhost:8000/api/openapi.json`

---

## Authentication

All endpoints (except `/health` and `/api/v1/auth/login`) require a JWT bearer token.

```http
POST /api/v1/auth/login
Content-Type: application/x-www-form-urlencoded

username=admin%40neurodrug.local&password=ChangeMe123!
```

Response:
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

Use the token in subsequent requests:
```http
Authorization: Bearer eyJhbGci...
```

---

## Core Endpoints

### Drug Repurposing

```http
POST /api/v1/predictions/run
```
```json
{
  "disease_efo_id": "EFO_0000519",
  "model_version_id": 1,
  "top_k": 20
}
```

Returns ranked drug candidates with prediction scores, novelty, and confidence.

---

### Knowledge Graph

```http
GET /api/v1/graph/subgraph/{node_id}?hops=2
```

Returns the local subgraph around a node.

```http
GET /api/v1/graph/stats
```

Returns node/edge counts by type.

---

### ETL Pipelines

```http
POST /api/v1/etl/ingest/opentargets?efo_id=EFO_0000519
```

Triggers async ETL pipeline. Returns `job_id`.

```http
GET /api/v1/etl/jobs/{job_id}
```

Poll job status.

---

### Validation

```http
POST /api/v1/validation/run
```
```json
{
  "prediction_id": 42,
  "validation_types": ["biological", "literature", "clinical"]
}
```

---

## Rate Limits

- Default: 60 requests / minute per IP
- Configurable via `RATE_LIMIT_PER_MINUTE` env var

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Bad request / validation error |
| 401 | Unauthorized — missing or invalid token |
| 403 | Forbidden — insufficient role |
| 404 | Resource not found |
| 422 | Unprocessable entity |
| 429 | Rate limit exceeded |
| 500 | Internal server error |
