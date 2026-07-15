# apply-training-tab.ps1
# Run from the neurodrug-fixed directory:
#   cd C:\Users\pinoy\Downloads\neurodrug-fixed
#   .\apply-training-tab.ps1

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$copies = @(
    @{ Src="training_endpoint.py";  Dst="backend\app\api\v1\endpoints\training.py" },
    @{ Src="api_v1_patched.py";     Dst="backend\app\api\v1\api.py" },
    @{ Src="trainer_patched.py";    Dst="backend\app\ml\trainer.py" },
    @{ Src="model-training.tsx";    Dst="frontend\components\model-training.tsx" },
    @{ Src="page_patched.tsx";      Dst="frontend\app\page.tsx" },
    @{ Src="neurodrug_patched.ps1"; Dst="neurodrug.ps1" }
)

$ok = $true
foreach ($c in $copies) {
    $src = Join-Path $here $c.Src
    $dst = Join-Path $here $c.Dst
    if (Test-Path $src) {
        Copy-Item $src $dst -Force
        Write-Host "OK  $($c.Src) -> $($c.Dst)"
    } else {
        Write-Host "MISSING  $src"
        $ok = $false
    }
}

if ($ok) {
    Write-Host ""
    Write-Host "All files applied. Rebuild:"
    Write-Host "  docker compose up -d --build api worker scheduler flower frontend"
    Write-Host ""
    Write-Host "After rebuild, reload neurodrug.ps1 to pick up the ND-Predict fix:"
    Write-Host "  . .\neurodrug.ps1"
} else {
    Write-Host ""
    Write-Host "One or more source files missing. Make sure all downloaded files are in:"
    Write-Host "  $here"
}
