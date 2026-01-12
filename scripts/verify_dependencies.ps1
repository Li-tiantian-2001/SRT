# Verification script for packaging dependencies
# Checks if all required dependencies are installed before building

Write-Host "========================================"
Write-Host "  Packaging Dependency Verification"
Write-Host "========================================"
Write-Host ""

$ErrorActionPreference = "Continue"

# 1. Check if .spec file exists
$specFile = Join-Path $PSScriptRoot "..\app\launcher\字幕生成工具.spec"
if (Test-Path $specFile) {
    Write-Host "[OK] Found .spec file: $specFile"
} else {
    Write-Host "[ERROR] .spec file not found"
    exit 1
}

# 2. Check virtual environment dependencies
Write-Host ""
Write-Host "Checking virtual environment dependencies..."
$venvPython = Join-Path $PSScriptRoot "..\venv\Scripts\python.exe"

if (Test-Path $venvPython) {
    Write-Host "[OK] Virtual environment exists"
    
    $requiredPackages = @("numpy", "sherpa-onnx", "opencv-python", "pyinstaller")
    
    foreach ($pkg in $requiredPackages) {
        $result = & $venvPython -m pip show $pkg 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] $pkg is installed"
        } else {
            Write-Host "[ERROR] $pkg is NOT installed"
        }
    }
} else {
    Write-Host "[ERROR] Virtual environment not found. Please run setup script first."
    exit 1
}

# 3. Check requirements.txt
Write-Host ""
Write-Host "Checking requirements.txt..."
$reqFile = Join-Path $PSScriptRoot "..\requirements.txt"
if (Test-Path $reqFile) {
    $content = Get-Content $reqFile
    if ($content -match "numpy" -and $content -match "sherpa-onnx") {
        Write-Host "[OK] requirements.txt contains necessary dependencies"
    } else {
        Write-Host "[WARNING] requirements.txt may be missing some dependencies"
    }
} else {
    Write-Host "[ERROR] requirements.txt not found"
}

# 4. Next steps
Write-Host ""
Write-Host "========================================"
Write-Host "  Verification Complete"
Write-Host "========================================"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Run build script: .\scripts\build_portable.ps1"
Write-Host "2. Test the generated SubtitleMaker-Windows-Portable.zip on another computer"
Write-Host ""

pause

