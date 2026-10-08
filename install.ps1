# Local-repo installer for the workflo CLI (Windows).
# Same experience as install.sh: typed commands, progress messages, a
# working `workflo` command afterward - from this checkout, not PyPI.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   .\.workflo-venv\Scripts\Activate.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path "packages\workflo-schema\pyproject.toml") -or -not (Test-Path "apps\workflo-cli\pyproject.toml")) {
    throw "install.ps1 must be run from a workflo checkout (packages/ and apps/ missing)"
}

function Resolve-Python {
    $candidates = @(
        @{ Cmd = "python"; ExtraArgs = @() },
        @{ Cmd = "python3"; ExtraArgs = @() },
        @{ Cmd = "py"; ExtraArgs = @("-3") }
    )
    foreach ($c in $candidates) {
        $cmd = Get-Command $c.Cmd -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        & $cmd.Source @($c.ExtraArgs) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return @{ Exe = $cmd.Source; ExtraArgs = $c.ExtraArgs }
        }
    }
    throw "Python 3.11+ is required but was not found on PATH"
}

$Python = Resolve-Python

Write-Host "Installing workflo..."
Write-Host "  -> Setting up environment..."
& $Python.Exe @($Python.ExtraArgs) -m venv .workflo-venv
if ($LASTEXITCODE -ne 0) { throw "python -m venv failed" }

$VenvPython = Join-Path $Root ".workflo-venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    throw "Installation failed - venv python not found at $VenvPython"
}

# Hide pip's "new release available" nags so the demo narration stays clean.
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

# One resolver graph for the four local packages so pip does not try to
# fetch workflo-schema / sandbox-isolation / etc. from PyPI.
Write-Host "  -> Installing core packages..."
& $VenvPython -m pip install --quiet `
    -e packages\workflo-schema `
    -e packages\sandbox-isolation `
    -e apps\sandbox-executor `
    -e packages\probe-engine
if ($LASTEXITCODE -ne 0) { throw "pip install of core packages failed" }

Write-Host "  -> Installing workflo CLI..."
& $VenvPython -m pip install --quiet -e apps\workflo-cli
if ($LASTEXITCODE -ne 0) { throw "pip install of workflo CLI failed" }

Write-Host "  -> Verifying installation..."
$Workflo = Join-Path $Root ".workflo-venv\Scripts\workflo.exe"
if (-not (Test-Path $Workflo)) {
    throw "Installation failed - workflo not found at $Workflo"
}

$version = & $Workflo --version
if ($LASTEXITCODE -ne 0) { throw "workflo --version failed" }

Write-Host "OK workflo installed ($version)"
Write-Host ""
Write-Host "Activate this environment in new shells:"
Write-Host "  .\.workflo-venv\Scripts\Activate.ps1"
Write-Host ""
Write-Host "Get started (no Docker - validates the CLI is actually installed):"
Write-Host "  workflo run --repo https://github.com/pallets/click.git --test --security --dry-run"
Write-Host ""
Write-Host "Live sandbox run still needs Docker Desktop + the worker image"
Write-Host "(see docs/workflo/sandbox_contract.md). Do not use psf/requests."
