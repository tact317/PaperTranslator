# Phase97.2 PWA local preview for Windows. No installation, no data mutation.
# On phones, HTTPS is REQUIRED for PWA installation. This localhost preview is for desktop only.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$port = 8765
Write-Host "PeperReader PWA desktop preview: http://127.0.0.1:$port/"
Write-Host 'Press Ctrl+C to stop. This is a desktop-only preview; mobile installation requires HTTPS.'
Write-Host "Open the URL in Edge/Chrome after the Python server starts."
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & py -3 -m http.server $port --bind 127.0.0.1 --directory $here
} else {
    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) { throw 'Python 3 was not found. Use python -m http.server or deploy to HTTPS.' }
    & python -m http.server $port --bind 127.0.0.1 --directory $here
}
