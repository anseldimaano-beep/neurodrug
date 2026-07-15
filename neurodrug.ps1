$ND_BASE  = "http://localhost:8000/api/v1"
$ND_USER  = "admin@neurodrug.local"
$ND_PASS  = "ChangeMe123!"

function Get-NDToken {
    $r = Invoke-RestMethod -Method Post `
        -Uri "$ND_BASE/auth/login" `
        -ContentType "application/x-www-form-urlencoded" `
        -Body "username=$ND_USER&password=$ND_PASS"
    return $r.access_token
}

# FIX: Content-Type removed from headers dict.
# Passing Content-Type in BOTH -Headers and -ContentType conflicts in PS5
# and silently drops the request body (causing 422 "body field required").
# Only the -ContentType parameter is used on the call that needs it.
function Get-NDHeaders {
    $t = Get-NDToken
    return @{ Authorization = "Bearer $t" }
}

function Invoke-ND {
    param([string]$Method="GET", [string]$Path, [object]$Body=$null)
    $h = Get-NDHeaders
    $uri = "$ND_BASE$Path"
    if ($Body) {
        $json = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 5 }
        return Invoke-RestMethod -Method $Method -Uri $uri -Headers $h -ContentType "application/json" -Body $json
    }
    return Invoke-RestMethod -Method $Method -Uri $uri -Headers $h
}

function ND-Predict($diseaseId, $topK=20, $modelVersionId=1) {
    return Invoke-ND -Method POST -Path "/predictions/run" `
        -Body @{ disease_efo_id=$diseaseId; top_k=$topK; model_version_id=$modelVersionId }
}

function ND-ETL($source) { return Invoke-ND -Method POST -Path "/etl/ingest/$source" }

function ND-ClearPredictions {
    docker exec neurodrug_postgres psql -U neurodrug_user -d neurodrug -c "
        DELETE FROM literature_evidence WHERE prediction_id IN (SELECT id FROM predictions);
        DELETE FROM clinical_evidence   WHERE prediction_id IN (SELECT id FROM predictions);
        DELETE FROM predictions;"
}

Write-Host "NeuroDrug helpers loaded."
$global:ND_HEADERS = Get-NDHeaders
Write-Host "Token acquired."
