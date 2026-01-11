param(
    [string]$AppRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\\app")).Path,
    [string]$OutZip = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path + "\\SubtitleMaker-Windows-Portable.zip"
)

$ErrorActionPreference = "Stop"

$launcher = Join-Path $AppRoot "launcher"
$exeName = "字幕生成工具.exe"
$exePath = Join-Path $AppRoot $exeName

Push-Location $launcher
try {
    pyinstaller --noconsole --onefile main.py --name "字幕生成工具"
} finally {
    Pop-Location
}

$distExe = Join-Path $launcher "dist\\字幕生成工具.exe"
if (-not (Test-Path $distExe)) {
    throw "PyInstaller output not found: $distExe"
}

Copy-Item -Force $distExe $exePath

if (Test-Path $OutZip) {
    Remove-Item -Force $OutZip
}

Compress-Archive -Path (Join-Path $AppRoot "*") -DestinationPath $OutZip
