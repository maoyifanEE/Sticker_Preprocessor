param(
    [switch]$SkipAI,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Expected = "Sticker_Preprocessor"
if ((Split-Path $Repo -Leaf) -ne $Expected) {
    throw "SETUP_WRONG_REPOSITORY: $Repo"
}
Set-Location $Repo

$Runtime = Join-Path $Repo ".runtime"
$TempDir = Join-Path $Runtime "temp"
$ModelDir = Join-Path $Runtime "models\rembg"
New-Item -ItemType Directory -Force -Path $TempDir,$ModelDir | Out-Null
$env:TMP = $TempDir
$env:TEMP = $TempDir
$env:TMPDIR = $TempDir
$env:U2NET_HOME = $ModelDir
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PIP_NO_CACHE_DIR = "1"

$Candidates = @(
    @("py", "-3.12"),
    @("py", "-3.11"),
    @("py", "-3.13"),
    @("python")
)
$Selected = $null
foreach ($Candidate in $Candidates) {
    $Command = $Candidate[0]
    $Args = @()
    if ($Candidate.Count -gt 1) { $Args = $Candidate[1..($Candidate.Count - 1)] }
    Write-Host "Checking Python candidate: $($Candidate -join ' ')"
    & $Command @Args -c "import struct, sys, tkinter; ok=(sys.version_info >= (3,11) and sys.version_info < (3,14) and struct.calcsize('P') * 8 == 64); print(sys.version.split()[0]); print(struct.calcsize('P') * 8); print('tkinter=ok'); raise SystemExit(0 if ok else 1)"
    if ($LASTEXITCODE -eq 0) {
        $Selected = $Candidate
        break
    }
}
if ($null -eq $Selected) { throw "COMPATIBLE_PYTHON_NOT_AVAILABLE" }
Write-Host "Selected Python: $($Selected -join ' ')"
$SelectedCommand = $Selected[0]
$SelectedArgs = @()
if ($Selected.Count -gt 1) { $SelectedArgs = $Selected[1..($Selected.Count - 1)] }

if (!(Test-Path ".venv")) {
    & $SelectedCommand @SelectedArgs -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "VENV_CREATE_FAILED" }
}

$Python = Join-Path $Repo ".venv\Scripts\python.exe"
& $Python -m pip install --no-cache-dir --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "PIP_BOOTSTRAP_FAILED" }

$Spec = "."
if (-not $SkipAI) { $Spec = ".[ai]" }
if ($Dev -and -not $SkipAI) { $Spec = ".[ai,dev]" }
if ($Dev -and $SkipAI) { $Spec = ".[dev]" }

& $Python -m pip install --no-cache-dir -e $Spec
if ($LASTEXITCODE -ne 0) { throw "PROJECT_INSTALL_FAILED" }

Write-Host "SETUP_PASS"
