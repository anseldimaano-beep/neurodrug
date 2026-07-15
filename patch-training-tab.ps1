# patch-training-tab.ps1
# Run from the neurodrug-fixed root directory:
#   .\patch-training-tab.ps1
#
# What this does:
#   1. Copies training endpoint into the backend (hot-reloads automatically)
#   2. Registers it in api.py
#   3. Patches trainer.py to write history per-epoch (live chart updates)
#   4. Copies new training-dashboard.tsx into frontend/components
#   5. Updates page.tsx to use the new component
#   6. Rebuilds & restarts the frontend container only

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot   # folder containing this script

function Section($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# ── 1. Copy backend endpoint ─────────────────────────────────────────
Section "1) Deploying backend training endpoint"
Copy-Item "$root\training_endpoint.py" "backend\app\api\v1\endpoints\training.py" -Force
Write-Host "  -> backend/app/api/v1/endpoints/training.py"

# ── 2. Register in api.py (idempotent) ───────────────────────────────
Section "2) Registering training router in api.py"
$apiFile = "backend\app\api\v1\api.py"
$apiContent = Get-Content $apiFile -Raw
if ($apiContent -notmatch "training") {
    $apiContent = $apiContent -replace `
        "from app\.api\.v1\.endpoints import \(", `
        "from app.api.v1.endpoints import ("
    $apiContent = $apiContent -replace `
        "    auth, assistant, reports, repurposing, validation", `
        "    auth, assistant, reports, repurposing, validation, training"
    $apiContent = $apiContent -replace `
        "api_router\.include_router\(assistant\.router", `
        "api_router.include_router(training.router,   prefix=""/training"",   tags=[""training""])`napi_router.include_router(assistant.router"
    Set-Content $apiFile $apiContent -NoNewline
    Write-Host "  -> training router added to api.py"
} else {
    Write-Host "  -> training router already registered, skipping"
}

# ── 3. Patch trainer.py: write history JSON per-epoch ────────────────
Section "3) Patching trainer.py for per-epoch JSON writes"
$trainerFile = "backend\app\ml\trainer.py"
$trainerContent = Get-Content $trainerFile -Raw

$oldBlock = @'
            if self.epochs_no_improve >= self.patience:
                logger.info(f"Early stopping triggered at epoch {epoch}")
                break

        with open(os.path.join(self.checkpoint_dir, "training_history.json"), "w") as f:
            json.dump(self.history, f, indent=2)
'@

$newBlock = @'
            if self.epochs_no_improve >= self.patience:
                logger.info(f"Early stopping triggered at epoch {epoch}")
                break

            # write after every epoch so the UI can poll live progress
            with open(os.path.join(self.checkpoint_dir, "training_history.json"), "w") as f:
                json.dump(self.history, f, indent=2)

'@

if ($trainerContent -match [regex]::Escape("# write after every epoch")) {
    Write-Host "  -> trainer.py already patched, skipping"
} elseif ($trainerContent.Contains($oldBlock.Trim())) {
    $trainerContent = $trainerContent.Replace($oldBlock.TrimEnd(), $newBlock.TrimEnd())
    Set-Content $trainerFile $trainerContent -NoNewline
    Write-Host "  -> trainer.py patched"
} else {
    Write-Host "  -> WARNING: trainer.py pattern not matched — patch manually" -ForegroundColor Yellow
    Write-Host "     Move the 'with open(training_history.json)' block inside the epoch for-loop."
}

# ── 4. Copy frontend component ───────────────────────────────────────
Section "4) Copying training-dashboard.tsx to frontend/components"
Copy-Item "$root\training-dashboard.tsx" "frontend\components\training-dashboard.tsx" -Force
Write-Host "  -> frontend/components/training-dashboard.tsx"

# ── 5. Patch page.tsx ────────────────────────────────────────────────
Section "5) Updating page.tsx training tab"
$pageFile = "frontend\app\page.tsx"
$pageContent = Get-Content $pageFile -Raw

# add import if not already there
if ($pageContent -notmatch "TrainingDashboard") {
    $pageContent = $pageContent -replace `
        'import EvidenceValidation from "@/components/evidence-validation";', `
        "import EvidenceValidation from `"@/components/evidence-validation`";`nimport TrainingDashboard from `"@/components/training-dashboard`";"

    # replace stub card content with real component
    $oldTrainingTab = @'
          <TabsContent value="training" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Model Training Center</CardTitle>
                <CardDescription>Launch HGT training jobs, monitor convergence, and compare baseline models.</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">Connect to /api/v1/training endpoints to manage experiments.</p>
              </CardContent>
            </Card>
          </TabsContent>
'@

    $newTrainingTab = @'
          <TabsContent value="training" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Model Training Center</CardTitle>
                <CardDescription>HGT training history, live convergence charts, and one-click retraining.</CardDescription>
              </CardHeader>
              <CardContent>
                <TrainingDashboard />
              </CardContent>
            </Card>
          </TabsContent>
'@

    $pageContent = $pageContent.Replace($oldTrainingTab.TrimEnd(), $newTrainingTab.TrimEnd())
    Set-Content $pageFile $pageContent -NoNewline
    Write-Host "  -> page.tsx updated"
} else {
    Write-Host "  -> page.tsx already patched, skipping"
}

# ── 6. Rebuild frontend only ─────────────────────────────────────────
Section "6) Rebuilding frontend container (api/worker untouched)"
docker-compose up -d --build frontend
Write-Host "  -> frontend rebuilding — takes ~60-90s"
Write-Host "  -> Watch progress: docker-compose logs -f frontend"

Section "Done"
Write-Host "Backend changes are live immediately (hot-reload)."
Write-Host "Frontend will be live at http://localhost:3000 once the build finishes."
Write-Host "Training tab will poll /api/v1/training/history every 3 s."
