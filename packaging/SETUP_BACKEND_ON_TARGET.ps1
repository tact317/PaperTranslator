#requires -Version 5.1
<#
Target-machine Python 3.12 setup. Run only on a test machine, from the
candidate distribution root. Never replaces an existing venv or user data.
#>
param([string]$CandidateRoot = $PSScriptRoot)
$ErrorActionPreference = 'Stop'
$runtime = Join-Path $CandidateRoot 'runtime'
$lock = Join-Path $runtime 'backend\requirements-win-py312.lock'
$venv = Join-Path $runtime 'backend_env'
if (!(Test-Path -LiteralPath $lock)) { throw "Missing Python lock: $lock" }
if (Test-Path -LiteralPath $venv) { throw "Refusing to overwrite existing venv: $venv" }
& py.exe -3.12 -c 'import sys; assert sys.version_info[:2] == (3,12); print(sys.version)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 (64-bit) unavailable' }
& py.exe -3.12 -m venv $venv
if ($LASTEXITCODE -ne 0) { throw 'venv failed' }
$python = Join-Path $venv 'Scripts\python.exe'
& $python -m pip install --disable-pip-version-check -r $lock
if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
& $python -m pip check
if ($LASTEXITCODE -ne 0) { throw 'pip check failed' }
& $python -c 'import fastapi,uvicorn,fitz,ollama; print("BACKEND_IMPORTS_PASS")'
if ($LASTEXITCODE -ne 0) { throw 'Core backend imports failed' }
Write-Host 'PYTHON_SETUP_PASS (core imports; PDF translation not tested)'
