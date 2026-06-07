# ---- parse args ----
param(
    [string]$Version = "",        # e.g. "14", "1.0.0", or "latest"
    [switch]$SkipZip,             # skip ZIP creation
    [switch]$NoPause,             # no Read-Host at end (CI mode)
    [switch]$SkipUPX              # skip UPX compression even if available
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$isCI = $NoPause -or ($env:CI -eq 'true')
$isInteractive = (-not $PSBoundParameters.ContainsKey('Version')) -and
                 (-not $PSBoundParameters.ContainsKey('SkipZip')) -and
                 (-not $PSBoundParameters.ContainsKey('NoPause')) -and
                 (-not $PSBoundParameters.ContainsKey('SkipUPX')) -and
                 ($env:CI -ne 'true')

# ---- find venv ----
$venvCandidates = @(
    "$ScriptDir\..\..\.venv\Scripts\python.exe",
    "D:\Projects\.venv\Scripts\python.exe",
    "C:\Projects\.venv\Scripts\python.exe"
)
$VENV = $null
foreach ($c in $venvCandidates) { if (Test-Path $c) { $VENV = $c; break } }
if (-not $VENV) {
    Write-Host "ERROR: venv not found. Run:" -ForegroundColor Red
    Write-Host "  python -m venv D:\Projects\.venv"
    Write-Host "  D:\Projects\.venv\Scripts\python.exe -m pip install -r requirements.txt"
    if (-not $NoPause) { Read-Host "  Press Enter to exit" }
    exit 1
}

# ---- find versions ----
$devFiles = Get-ChildItem "$ScriptDir\versions\v*_*.py" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^v(\d+)_.+\.py$' } |
    ForEach-Object { [PSCustomObject]@{ Num = [int]($_.Name -replace '^v(\d+)_.+', '$1'); Name = $_.Name; Source = 'versions' } } |
    Sort-Object Num

$relFiles = Get-ChildItem "$ScriptDir\releases\*.py" -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^v\d+\.\d+\.\d+\.py$' } |
    ForEach-Object { [PSCustomObject]@{ Num = [int]([version]($_.BaseName.TrimStart('v'))).Major * 1000; Name = $_.Name; Source = 'releases' } } |
    Sort-Object Num -Descending

$pyFiles = @()
if ($relFiles) { $pyFiles += $relFiles }
$pyFiles += $devFiles

if (-not $pyFiles) { Write-Host "ERROR: No .py found in versions/ or releases/" -ForegroundColor Red; if (-not $NoPause) { Read-Host "  Press Enter to exit" }; exit 1 }

if ($isInteractive) {
    # ---- pick version ----
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  InkDrop  /  build & package" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    for ($i = 0; $i -lt $pyFiles.Count; $i++) {
        $label = "$($pyFiles[$i].Source)/$($pyFiles[$i].Name)"
        $color = if ($pyFiles[$i].Source -eq 'releases') { "Green" } else { "Gray" }
        $tag = if ($i -eq 0 -and $pyFiles[$i].Source -eq 'releases') { "  <-- latest" } else { "" }
        Write-Host "    [$($i+1)]  $label$tag" -ForegroundColor $color
    }
    Write-Host ""
    $choice = Read-Host "  Pick version [Enter = latest]"
    if ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $pyFiles.Count) {
        $selected = $pyFiles[[int]$choice - 1]
    } else {
        $selected = $pyFiles[0]
    }

    # ---- ZIP ----
    Write-Host ""
    $zipChoice = Read-Host "  Generate ZIP? [Y]es (default)  or  [N]o"
    $SkipZip = ($zipChoice -eq 'n' -or $zipChoice -eq 'N')
    Write-Host ""

} else {
    # non-interactive: resolve version param
    if ($Version -eq '' -or $Version -eq 'latest') {
        $selected = $pyFiles[0]
    } elseif ($Version -match '^\d+$') {
        $match = $pyFiles | Where-Object { $_.Source -eq 'versions' -and $_.Num -eq [int]$Version }
        if ($match) { $selected = $match }
        else { Write-Host "ERROR: versions/v${Version}_*.py not found" -ForegroundColor Red; exit 1 }
    } elseif ($Version -match '^\d+\.\d+\.\d+$') {
        $match = $pyFiles | Where-Object { $_.Source -eq 'releases' -and $_.Name -eq "v$Version.py" }
        if ($match) { $selected = $match }
        else { Write-Host "ERROR: releases/v${Version}.py not found" -ForegroundColor Red; exit 1 }
    } else {
        Write-Host "ERROR: -Version must be a number, semver (1.0.0), or 'latest'" -ForegroundColor Red; exit 1
    }
}

$ENTRY_SOURCE = $selected.Source
$ENTRY = $selected.Name

# ---- banner ----
$banner = @"
==================================================
  InkDrop  /  build & package
==================================================
  Source : $ENTRY_SOURCE/$ENTRY
  Venv   : $VENV
"@
Write-Host $banner -ForegroundColor Cyan

# ---- locate UPX ----
$UPX_DIR = $null
if (-not $SkipUPX) {
    $upxExe = Get-Command upx -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    if ($upxExe) {
        $UPX_DIR = Split-Path -Parent $upxExe
        Write-Host "  UPX    : $upxExe" -ForegroundColor Green
    } else {
        $candidates = @(
            "D:\Tools\upx\upx.exe",
            "C:\Tools\upx\upx.exe",
            "$ScriptDir\tools\upx\upx.exe"
        )
        foreach ($c in $candidates) { if (Test-Path $c) { $UPX_DIR = Split-Path -Parent $c; break } }
        if ($UPX_DIR) {
            Write-Host "  UPX    : $UPX_DIR\upx.exe" -ForegroundColor Green
        } elseif ($isCI) {
            Write-Host "  UPX    : not found (CI: skip)" -ForegroundColor Yellow
        } else {
            Write-Host "  UPX    : not found. Skipping compression." -ForegroundColor Yellow
            Write-Host "           Download from https://github.com/upx/upx/releases"
            Write-Host "           Extract to D:\Tools\upx\ for auto-detect."
        }
    }
}

Write-Host ""
$srcPath = "$ScriptDir\$ENTRY_SOURCE\$ENTRY"

# ---- step 0: update spec ----
$specPath = "$ScriptDir\InkDrop.spec"
if (Test-Path $specPath) {
    $specContent = Get-Content $specPath -Raw
    $specContent = $specContent -replace "\[.*\].*#.*build.ps1.*", "['$ENTRY_SOURCE/$ENTRY'],         # <-- build.ps1 replaces this line per version"
    $specContent | Set-Content $specPath -Encoding UTF8 -NoNewline
    Write-Host "  [0/3] Updated spec entry -> $ENTRY_SOURCE/$ENTRY" -ForegroundColor Gray
} else {
    Write-Host "  [0/3] Generating spec from $ENTRY_SOURCE/$ENTRY ..." -ForegroundColor Gray
    $makespecArgs = @(
        '--onedir', '--name', 'InkDrop', '--noconfirm', '--windowed',
        '--hidden-import', 'fitz', '--hidden-import', 'pymupdf',
        '--hidden-import', 'sniffer', '--hidden-import', 'filetype',
        '--hidden-import', 'pdf_engine', '--hidden-import', 'doc_engine',
        '--hidden-import', 'aspose.words_foss',
        '--exclude-module', 'pypdfium2', '--exclude-module', 'pypdfium2_raw',
        '--exclude-module', 'magika', '--exclude-module', 'onnxruntime',
        '--exclude-module', 'flatbuffers', '--exclude-module', 'protobuf',
        '--specpath', $ScriptDir, $srcPath
    )
    & $VENV -m PyInstaller @makespecArgs 2>&1 | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: spec generation failed" -ForegroundColor Red; exit 1 }
}

# ---- step 1: clean ----
$buildDir = "$ScriptDir\build"
$distDir  = "$ScriptDir\dist"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir -ErrorAction SilentlyContinue; Write-Host "  [1/3] Cleaned build" -ForegroundColor Green }
if (Test-Path $distDir)  { Remove-Item -Recurse -Force $distDir -ErrorAction SilentlyContinue;  Write-Host "  [1/3] Cleaned dist" -ForegroundColor Green }

# ---- step 2: build ----
Write-Host "  [2/3] PyInstaller (onedir) ..." -ForegroundColor Yellow
Write-Host ""

$sw = [System.Diagnostics.Stopwatch]::StartNew()

$pyiArgs = @($specPath, '--noconfirm', '--clean')
if ($UPX_DIR) { $pyiArgs += '--upx-dir'; $pyiArgs += $UPX_DIR }
if (-not (Test-Path $buildDir)) { New-Item -ItemType Directory -Force $buildDir | Out-Null }

$pyiFullArgs = @('-m', 'PyInstaller') + $pyiArgs + @('--distpath', $distDir, '--workpath', $buildDir)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $VENV
$psi.Arguments = $pyiFullArgs -join ' '
$psi.UseShellExecute = $false
$psi.RedirectStandardError = $true
$psi.RedirectStandardOutput = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)

while (-not $proc.StandardError.EndOfStream) {
    $line = $proc.StandardError.ReadLine()
    if ($line) { Write-Host $line }
}
$proc.WaitForExit()
$exitCode = $proc.ExitCode

if ($exitCode -ne 0) {
    Write-Host "`n  Build FAILED (exit $exitCode)" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "  Press Enter to exit" }
    exit 1
}

$sw.Stop()
Write-Host ""
Write-Host "  + Build done in $([math]::Round($sw.Elapsed.TotalMinutes, 1)) min" -ForegroundColor Green

# ---- step 3: package ----
$outDir = "$distDir\InkDrop"
$exe = "$outDir\InkDrop.exe"

if (-not (Test-Path $exe)) {
    Write-Host "  Output not found: $exe" -ForegroundColor Red
    if (-not $NoPause) { Read-Host "  Press Enter to exit" }
    exit 1
}

if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }

$folderMB = "{0:F0}" -f ((Get-ChildItem $outDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB)

if (-not $SkipZip) {
    Write-Host "  [3/3] Package" -ForegroundColor Yellow
    Write-Host "  + Folder : $folderMB MB" -ForegroundColor Green

    $zipPath = "$distDir\InkDrop.zip"
    Write-Host "  Compressing ..."
    $prevProgress = $ProgressPreference
    $ProgressPreference = 'SilentlyContinue'
    Compress-Archive -Path "$outDir\*" -DestinationPath $zipPath -Force
    $ProgressPreference = $prevProgress
    $zipMB = "{0:F0}" -f ((Get-Item $zipPath).Length / 1MB)
    Write-Host "  + ZIP    : $zipMB MB" -ForegroundColor Green
} else {
    Write-Host "  [3/3] Package (skip zip)" -ForegroundColor Yellow
    Write-Host "  + Folder : $folderMB MB" -ForegroundColor Green
}

# ---- done ----
Write-Host ""
Write-Host "==================================================" -ForegroundColor Green
Write-Host "  Done" -ForegroundColor Green
Write-Host "  $outDir\" -ForegroundColor Green
if (-not $SkipZip) { Write-Host "  $distDir\InkDrop.zip ($zipMB MB)" -ForegroundColor Green }
Write-Host "==================================================" -ForegroundColor Green

if (-not $NoPause) { Read-Host "  Press Enter to exit" }
