# =====================================================================
# NeuroDrug v4 — full stack startup
# Run from the project root (the folder containing docker-compose.yml)
#   .\run-neurodrug.ps1
#
# What this does, in order:
#   1. docker-compose up -d --build
#   2. wait for api + postgres health checks
#   3. alembic upgrade head
#   4. seed diseases / drugs / roles / admin user (idempotent)
#   5. register the existing checkpoints/best_model.pt as ModelVersion 1
#   6. defensive fix for the old Temozolomide/Pyrazinamide chembl_id mixup
#      (FIXES_ROUND2.md, C9) — no-op on a fresh DB, fixes it if you're
#      reusing an old postgres_data volume
#   7. load the neurodrug.ps1 API helpers (ND-Predict, ND-ETL, etc.)
#   8. clear any stale prediction rows and re-run inference for all five
#      diseases — REQUIRED after C7 (the drug-embedding misattribution
#      fix), since old Prediction rows in the DB still hold pre-fix scores
# =====================================================================

$ErrorActionPreference = "Stop"

function Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

Section "1) Building & starting containers"
docker-compose up -d --build

Section "2) Waiting for api + postgres health"
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    $apiHealth = docker inspect --format='{{.State.Health.Status}}' neurodrug_api 2>$null
    $pgHealth  = docker inspect --format='{{.State.Health.Status}}' neurodrug_postgres 2>$null
    if ($apiHealth -eq "healthy" -and $pgHealth -eq "healthy") { $ready = $true; break }
    Write-Host "  ...still waiting ($($i + 1)/30) api=$apiHealth postgres=$pgHealth"
    Start-Sleep -Seconds 5
}
if (-not $ready) {
    Write-Host "Containers didn't report healthy in time. Check 'docker-compose logs api' before continuing." -ForegroundColor Yellow
    Write-Host "Continuing anyway in 5s (Ctrl+C to abort)..." -ForegroundColor Yellow
    Start-Sleep -Seconds 5
}

Section "3) Running migrations"
docker-compose exec -T api alembic upgrade head

Section "4) Seeding diseases / drugs / roles / admin user"
docker-compose exec -T api python scripts/seed_initial_data.py

Section "5) Registering model checkpoint (best_model.pt)"
docker-compose exec -T api python scripts/seed_model_version.py

Section "6) Defensive fix: Temozolomide chembl_id (FIXES_ROUND2 C9, no-op if already correct)"
docker exec neurodrug_postgres psql -U neurodrug_user -d neurodrug -c "UPDATE drugs SET name = 'Temozolomide', chembl_id = 'CHEMBL810' WHERE chembl_id = 'CHEMBL614';"

Section "7) Loading PowerShell API helpers (neurodrug.ps1)"
. .\neurodrug.ps1

Section "8) Clearing stale predictions + re-running inference for all five diseases (FIXES_ROUND2 C7)"
ND-ClearPredictions
$diseases = [ordered]@{
    "Glioblastoma"    = "MONDO_0018177"
    "Neuroblastoma"   = "MONDO_0005072"
    "Ewing Sarcoma"   = "MONDO_0012817"
    "Medulloblastoma" = "MONDO_0007959"
    "Wilms Tumor"     = "MONDO_0019004"
}
foreach ($name in $diseases.Keys) {
    Write-Host "  -> running inference: $name ($($diseases[$name]))"
    try {
        $result = ND-Predict $diseases[$name]
        Write-Host "     top candidate: $($result.candidates[0].drug_name)  score=$($result.candidates[0].prediction_score)"
    } catch {
        Write-Host "     FAILED for $name : $_" -ForegroundColor Red
    }
}

Section "Done"
Write-Host "Frontend:    http://localhost:3000"
Write-Host "API docs:    http://localhost:8000/api/docs"
Write-Host "MLflow:      http://localhost:5000"
Write-Host "Flower:      http://localhost:5555"
Write-Host "Grafana:     http://localhost:3001  (admin/admin)"
Write-Host "Prometheus:  http://localhost:9090"
Write-Host "Login:       admin@neurodrug.local / ChangeMe123!"
Write-Host "`nNote: Erdafitinib, Dactinomycin, Doxorubicin, and Ifosfamide have zero" -ForegroundColor DarkGray
Write-Host "Interaction rows in the seed data, so they won't appear as candidates" -ForegroundColor DarkGray
Write-Host "for any disease until you pull real ClinicalTrials/STRING/DGIdb data" -ForegroundColor DarkGray
Write-Host "for them (see FIXES_ROUND2.md, 'Still open')." -ForegroundColor DarkGray
