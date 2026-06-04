# Resolve README.md merge conflict
# Run from the migra repository root

Write-Host "Resolving README.md merge conflict..." -ForegroundColor Cyan

# Check if README.md exists
if (-not (Test-Path "README.md")) {
    Write-Host "ERROR: README.md not found. Are you in the migra repository?" -ForegroundColor Red
    exit 1
}

# Check if there's an ongoing merge
if (-not (Test-Path ".git/MERGE_HEAD")) {
    Write-Host "WARNING: No merge in progress. Continuing anyway..." -ForegroundColor Yellow
}

# Read the current README.md
$content = Get-Content "README.md" -Raw

# Check if conflict markers exist
if ($content -notcontains "<<<<<<" -and $content -notcontains "=======") {
    Write-Host "No conflict markers found in README.md. Already resolved?" -ForegroundColor Yellow
    exit 0
}

Write-Host "Found conflict markers. Resolving..." -ForegroundColor Yellow

# Define the resolved Quickstart section
$resolved = @'
## Quickstart

### Install

```bash
pip install migradiff
```

Requires Python 3.10+ and a running PostgreSQL instance (12+).

To install from source:

```bash
git clone https://github.com/migradiff/migra
cd migra
pip install -e .
```

> **Note:** PyPI package is available on all releases.

### Basic Usage
'@

# Replace the conflicted section
# This regex captures everything from "## Quickstart" through "### Basic Usage"
# and replaces it with the resolved version
$pattern = '## Quickstart.*?### Basic Usage'
$content = [regex]::Replace($content, $pattern, $resolved, [System.Text.RegularExpressions.RegexOptions]::Singleline)

# Remove any remaining conflict markers (just in case)
$content = $content -replace '<<<<<<< HEAD.*?=======.*?>>>>>>> origin/master', '', [System.Text.RegularExpressions.RegexOptions]::Singleline
$content = $content -replace '<<<<<<<.*?\n', ''
$content = $content -replace '=======\n', ''
$content = $content -replace '>>>>>>> .*?\n', ''

# Write back to README.md
Set-Content "README.md" -Value $content -Encoding UTF8

Write-Host "✅ README.md conflict resolved" -ForegroundColor Green

# Stage the file
git add README.md
Write-Host "✅ README.md staged" -ForegroundColor Green

# Commit
git commit -m "resolve: merge conflict in README.md"
Write-Host "✅ Committed" -ForegroundColor Green

# Push
git push origin chore/setup-cicd
Write-Host "✅ Pushed to origin" -ForegroundColor Green

Write-Host "`nDone! PR should now show 'No conflicts - ready to merge'" -ForegroundColor Green
