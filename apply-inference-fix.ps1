# apply-inference-fix.ps1
# Run from the neurodrug-fixed directory:
#   cd C:\Users\pinoy\Downloads\neurodrug-fixed
#   .\apply-inference-fix.ps1

$here = Split-Path -Parent $MyInvocation.MyCommand.Path

$copies = @(
    @{ Src="graph_convert_fixed.py"; Dst="backend\app\ml\graph_convert.py" },
    @{ Src="repurposing_fixed.py";   Dst="backend\app\services\repurposing.py" }
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
    Write-Host "Rebuild backend only (frontend unchanged):"
    Write-Host "  docker compose up -d --build api worker scheduler flower"
    Write-Host ""
    Write-Host "Then re-run predictions:"
    Write-Host "  . .\neurodrug.ps1"
    Write-Host "  @(`"MONDO_0018177`",`"MONDO_0005072`",`"MONDO_0012817`",`"MONDO_0007959`",`"MONDO_0019004`") | ForEach-Object { ND-Predict `$_ }"
} else {
    Write-Host "One or more source files missing. Place them in: $here"
}
