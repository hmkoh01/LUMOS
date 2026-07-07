$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\..\..")

Write-Host "Building LUMOS portable prototype..."
Write-Host "This creates a closed beta onedir build, not an installer."

$buildHome = Join-Path (Get-Location) ".build_home"
New-Item -ItemType Directory -Force -Path $buildHome | Out-Null
$env:HOME = $buildHome
$env:USERPROFILE = $buildHome

$pyinstallerVersion = python -m PyInstaller --version 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "PyInstaller is not installed."
  Write-Host "Install it in your build environment, then rerun this script:"
  Write-Host "python -m pip install pyinstaller"
  exit 1
}
Write-Host "PyInstaller version: $pyinstallerVersion"

python -m PyInstaller packaging/windows/lumos_portable.spec --noconfirm
if ($LASTEXITCODE -ne 0) {
  Write-Host "PyInstaller build failed."
  exit $LASTEXITCODE
}

python packaging/windows/build_portable.py
if ($LASTEXITCODE -ne 0) {
  Write-Host "Portable package post-processing failed."
  exit $LASTEXITCODE
}

Write-Host "Portable build prepared under dist/LUMOS"
