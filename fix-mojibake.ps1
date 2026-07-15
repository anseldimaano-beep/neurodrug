<#
  fix-mojibake.ps1
  -----------------
  Fixes double-encoded UTF-8 text (mojibake) across the NeuroDrug repo.

  Root cause: somewhere along the way, UTF-8 bytes for certain characters
  (smart punctuation, box-drawing characters, emoji) got interpreted as
  Windows-1252 and re-saved as UTF-8. That turns a single real character
  into two or three garbled Latin-1-range characters. This shows up
  directly in the rendered UI.

  Detection strategy: read each file as UTF-8. If every character in the
  file has a code point under 256, that file could not contain any
  genuinely-correct multi-byte UTF-8 text (real UTF-8 non-ASCII characters
  always decode to code points above 255) -- so if it also has at least
  one character above 127, it is very likely mojibake. Re-mapping each
  character back to its original byte value and re-decoding that byte
  sequence as UTF-8 recovers the original text.

  This script only rewrites a file if a real, valid-looking fix is found.

  USAGE (from repo root):
    .\fix-mojibake.ps1
    .\fix-mojibake.ps1 -DryRun     # preview which files would change, no writes
#>

param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

# Extensions to scan
$extensions = @(".ts", ".tsx", ".js", ".jsx", ".py", ".md", ".json", ".yml", ".yaml")

# Directories to skip
$skipDirs = @("node_modules", ".git", "__pycache__", ".next", ".venv", "venv")

Write-Host "Scanning for mojibake in $(Get-Location) ..." -ForegroundColor Cyan

$files = Get-ChildItem -Recurse -File | Where-Object {
    $keep = $true
    foreach ($seg in $_.FullName -split '[\\/]') {
        if ($skipDirs -contains $seg) { $keep = $false; break }
    }
    $keep -and ($extensions -contains $_.Extension)
}

$changed = @()

foreach ($file in $files) {
    $raw = [System.IO.File]::ReadAllText($file.FullName, [System.Text.Encoding]::UTF8)

    if ([string]::IsNullOrEmpty($raw)) { continue }

    $hasNonAscii = $false
    $bytes = New-Object System.Collections.Generic.List[byte]
    $skip = $false

    foreach ($ch in $raw.ToCharArray()) {
        $code = [int]$ch
        if ($code -gt 127) { $hasNonAscii = $true }

        if ($code -lt 256) {
            $bytes.Add([byte]$code)
        } else {
            # A genuine multi-byte UTF-8 character decodes to a code point
            # above 255. That means this file already has correct, real
            # non-ASCII text -- leave it alone.
            $skip = $true
            break
        }
    }

    if ($skip -or -not $hasNonAscii) { continue }

    try {
        $fixed = [System.Text.Encoding]::UTF8.GetString($bytes.ToArray())
    } catch {
        continue
    }

    $replacementChar = [char]0xFFFD

    if ($fixed -ne $raw -and -not $fixed.Contains($replacementChar)) {
        $changed += $file.FullName
        if (-not $DryRun) {
            $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($file.FullName, $fixed, $utf8NoBom)
        }
    }
}

if ($changed.Count -eq 0) {
    Write-Host "No mojibake found." -ForegroundColor Green
} else {
    $label = if ($DryRun) { "(dry run - not modified)" } else { "(fixed)" }
    Write-Host "`nFiles with mojibake $label`:" -ForegroundColor Yellow
    $changed | ForEach-Object { Write-Host "  $_" }

    $verb = if ($DryRun) { "would be" } else { "were" }
    Write-Host "`n$($changed.Count) file(s) $verb updated." -ForegroundColor Cyan
}
