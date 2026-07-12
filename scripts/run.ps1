$ErrorActionPreference = "Stop"
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Repo
$Runtime = Join-Path $Repo ".runtime"
$TempDir = Join-Path $Runtime "temp"
$ModelDir = Join-Path $Runtime "models\rembg"
New-Item -ItemType Directory -Force -Path $TempDir,$ModelDir | Out-Null
$env:TMP = $TempDir
$env:TEMP = $TempDir
$env:TMPDIR = $TempDir
$env:U2NET_HOME = $ModelDir
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
if (!(Test-Path $Python)) {
    Write-Error "未找到 .venv。请先运行：powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1"
}
& $Python -m sticker_preprocessor
if ($LASTEXITCODE -ne 0) {
    throw "APPLICATION_EXITED_WITH_CODE_$LASTEXITCODE"
}
