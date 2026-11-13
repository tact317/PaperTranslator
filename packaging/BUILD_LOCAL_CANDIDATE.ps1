#requires -Version 5.1
<#
Build a *local test candidate* from the current installed Electron shell and the
GitHub backend/frontend. Does not install, launch, or alter the existing app.
This candidate is NOT independently reproducible and is NOT a release artifact.
#>
param(
    [string]$Repository = "$env:USERPROFILE\Desktop\PeperTranslator_GitHub",
    [string]$Installed = "$env:LOCALAPPDATA\Programs\PeperTranslator",
    [string]$OutputRoot = "$env:USERPROFILE\Desktop"
)
$ErrorActionPreference = 'Stop'
$expectedBackend = '8F1F922B43F86C9552234552EFDA5099AF099281B2CBB723A42DF573E550A9B2'
$expectedAsar = 'BB05795F3C2A083E0C6FC990C3E74AECFFFD36AC2146D121EAA5DD0E2435DACC'
function Assert-Path($p) { if (!(Test-Path -LiteralPath $p)) { throw "Missing required path: $p" } }
function Copy-Robo([string]$source,[string]$target,[string[]]$excludeDirs = @(),[string[]]$excludeFiles = @()) {
    $args = @($source, $target, '/E', '/R:1', '/W:1', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($excludeDirs.Count) { $args += '/XD'; $args += $excludeDirs }
    if ($excludeFiles.Count) { $args += '/XF'; $args += $excludeFiles }
    & robocopy.exe @args | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy failed ($LASTEXITCODE): $source" }
}
Assert-Path "$Repository\.git"
Assert-Path "$Repository\frontend\package-lock.json"
Assert-Path "$Repository\backend\main.py"
Assert-Path "$Repository\backend\requirements-win-py312.lock"
Assert-Path "$Installed\PeperTranslator.exe"
Assert-Path "$Installed\resources\app.asar"
if ((Get-FileHash "$Repository\backend\main.py" -Algorithm SHA256).Hash -ne $expectedBackend) { throw 'Backend SHA mismatch; do not build unknown version' }
if ((Get-FileHash "$Installed\resources\app.asar" -Algorithm SHA256).Hash -ne $expectedAsar) { throw 'Installed Electron shell SHA mismatch; stop and review' }
$node = Get-Command 'node.exe' -ErrorAction Stop
$npm = Get-Command 'npm.cmd' -ErrorAction Stop
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$candidate = Join-Path $OutputRoot "PeperTranslator_STAGE2_LOCAL_CANDIDATE_$stamp"
$build = Join-Path $env:TEMP "PeperTranslator_Stage2_CandidateBuild_$stamp"
if ((Test-Path $candidate) -or (Test-Path $build)) { throw 'Generated output already exists; no overwrite performed' }
New-Item -ItemType Directory $candidate,$build -Force | Out-Null
$report = Join-Path $candidate 'BUILD_REPORT.txt'
try {
    'Candidate status: NOT FOR DISTRIBUTION' | Set-Content $report -Encoding UTF8
    "Source repository: $Repository" | Add-Content $report
    "Installed shell: $Installed" | Add-Content $report
    "Backend sha256: $expectedBackend" | Add-Content $report
    "Electron app.asar sha256: $expectedAsar" | Add-Content $report
    "Git revision: $(& git -C $Repository rev-parse HEAD)" | Add-Content $report
    "Node: $(& node.exe --version)" | Add-Content $report
    "Npm: $(& npm.cmd --version)" | Add-Content $report
    Write-Host '[1/4] Copying installed Electron shell (without runtime or rollback)'
    Copy-Robo $Installed $candidate @('runtime','rollback','logs') @('*.log')
    Write-Host '[2/4] Copying audited Phase99 backend source'
    Copy-Robo "$Repository\backend" "$candidate\runtime\backend" @('__pycache__','.pytest_cache','venv','.venv') @('.env','.env.local','.env.production','*.pyc')
    Write-Host '[3/4] Building frontend in a separate temporary directory'
    $src = Join-Path $build 'frontend'
    Copy-Robo "$Repository\frontend" $src @('node_modules','.next','.git') @('.env','.env.local','.env.production','*.tsbuildinfo')
    Push-Location $src
    try {
        & npm.cmd ci --ignore-scripts=false
        if ($LASTEXITCODE -ne 0) { throw 'npm ci failed' }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw 'Next build failed' }
    } finally { Pop-Location }
    Assert-Path "$src\.next\BUILD_ID"
    Assert-Path "$src\.next\standalone"
    $standalone = "$src\.next\standalone"
    if (!(Test-Path "$standalone\server.js")) {
        if (Test-Path "$standalone\frontend\server.js") { $standalone = "$standalone\frontend" }
        else { throw 'standalone server.js not found at expected locations' }
    }
    Copy-Robo $standalone "$candidate\runtime\frontend_server"
    Copy-Robo "$src\.next\static" "$candidate\runtime\frontend_server\.next\static"
    if (Test-Path "$src\public") { Copy-Robo "$src\public" "$candidate\runtime\frontend_server\public" }
    Assert-Path "$candidate\runtime\frontend_server\server.js"
    Write-Host '[4/4] Adding target machine setup script and verifying candidate'
    $setup = Join-Path $PSScriptRoot 'SETUP_BACKEND_ON_TARGET.ps1'
    Assert-Path $setup
    Copy-Item $setup (Join-Path $candidate 'SETUP_BACKEND_ON_TARGET.ps1')
    "Frontend BUILD_ID: $(Get-Content "$src\.next\BUILD_ID" -Raw)" | Add-Content $report
    "Candidate: $candidate" | Add-Content $report
    'Python lock: included, installation on target pending' | Add-Content $report
    'Build result: PASS (assembly only; not a runtime or target-machine test)' | Add-Content $report
    Write-Host "LOCAL CANDIDATE READY: $candidate"
    Write-Host 'Not tested or approved for redistribution. Do not run beside the installed app (shared ports 8000 / 31337).'
} catch {
    "Build result: FAIL - $_" | Add-Content $report
    throw
} finally {
    Write-Host "Report: $report"
}
