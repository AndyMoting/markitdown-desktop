# ---- parse args ----
param(
    [string]$Version = "",        # e.g. "13" or "latest" (default: latest if non-interactive, else prompt)
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
    if (-not $NoPause) { Read-Host }
    exit 1
}

# ---- find versions ----
$pyFiles = Get-ChildItem "$ScriptDir\v*_*.py" |
    Where-Object { $_.Name -match '^v(\d+)_.+\.py$' } |
    ForEach-Object { [PSCustomObject]@{ Num = [int]($_.Name -replace '^v(\d+)_.+', '$1'); Name = $_.Name } } |
    Sort-Object Num

if (-not $pyFiles) { Write-Host "ERROR: No v*_*.py found in $ScriptDir" -ForegroundColor Red; if (-not $NoPause) { Read-Host }; exit 1 }

if ($isInteractive) {
    # ---- pick version ----
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  MarkItDown GUI  /  build & package" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Available versions:" -ForegroundColor White
    Write-Host ""
    for ($i = 0; $i -lt $pyFiles.Count; $i++) {
        $tag = if ($i -eq $pyFiles.Count - 1) { "  <-- latest" } else { "" }
        Write-Host "    [$($i+1)]  $($pyFiles[$i].Name)$tag" -ForegroundColor Gray
    }
    Write-Host ""
    $choice = Read-Host "  Pick version [Enter = latest]"
    if ($choice -match '^\d+$' -and [int]$choice -ge 1 -and [int]$choice -le $pyFiles.Count) {
        $ENTRY = $pyFiles[[int]$choice - 1].Name
    } else {
        $ENTRY = $pyFiles[-1].Name
    }

    # ---- ZIP ----
    Write-Host ""
    $zipChoice = Read-Host "  Generate ZIP? [Y]es (default)  or  [N]o"
    $SkipZip = ($zipChoice -eq 'n' -or $zipChoice -eq 'N')

    Write-Host ""
    Write-Host "  -> $ENTRY" -ForegroundColor Cyan
    Write-Host ""

} else {
    # non-interactive: resolve version param
    if ($Version -eq '' -or $Version -eq 'latest') {
        $ENTRY = $pyFiles[-1].Name
    } elseif ($Version -match '^\d+$') {
        $match = $pyFiles | Where-Object { $_.Num -eq [int]$Version }
        if ($match) { $ENTRY = $match.Name }
        else { Write-Host "ERROR: v${Version}_*.py not found" -ForegroundColor Red; if (-not $NoPause) { Read-Host }; exit 1 }
    } else {
        Write-Host "ERROR: -Version must be a number or 'latest'" -ForegroundColor Red; if (-not $NoPause) { Read-Host }; exit 1
    }
}

# ---- banner ----
$banner = @"
==================================================
  MarkItDown GUI  /  build & package
==================================================
  Source : $ENTRY
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
        # check common locations
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

# ---- step 0: update spec ----
$specPath = "$ScriptDir\MarkItDown.spec"
if (Test-Path $specPath) {
    $specContent = Get-Content $specPath -Raw
    $specContent = $specContent -replace "\[.*v\d+_.+\.py.*\]", "['$ENTRY']"
    $specContent | Set-Content $specPath -Encoding UTF8 -NoNewline
    Write-Host "  [0/3] Updated spec entry -> $ENTRY" -ForegroundColor Gray
} else {
    Write-Host "  [0/3] Generating spec from $ENTRY ..." -ForegroundColor Gray
    $makespecArgs = @(
        '--onedir', '--name', 'MarkItDown', '--noconfirm', '--windowed',
        '--hidden-import', 'fitz', '--hidden-import', 'pymupdf',
        '--hidden-import', 'sniffer', '--hidden-import', 'filetype',
        '--hidden-import', 'pdf_engine', '--hidden-import', 'doc_engine',
        '--hidden-import', 'aspose.words_foss',
        '--exclude-module', 'pypdfium2', '--exclude-module', 'pypdfium2_raw',
        '--exclude-module', 'magika', '--exclude-module', 'onnxruntime',
        '--exclude-module', 'flatbuffers', '--exclude-module', 'protobuf',
        '--specpath', $ScriptDir, "$ScriptDir\$ENTRY"
    )
    & $VENV -m PyInstaller @makespecArgs 2>&1 | Select-Object -Last 3
    if ($LASTEXITCODE -ne 0) { Write-Host "  ERROR: spec generation failed" -ForegroundColor Red; exit 1 }
}

# ---- step 1: clean ----
$buildDir = "$ScriptDir\build"
$distDir  = "$ScriptDir\dist"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir; Write-Host "  [1/3] Cleaned build" -ForegroundColor Green }
if (Test-Path $distDir)  { Remove-Item -Recurse -Force $distDir;  Write-Host "  [1/3] Cleaned dist" -ForegroundColor Green }

# ---- step 2: build ----
Write-Host "  [2/3] PyInstaller (onedir) ..." -ForegroundColor Yellow
Write-Host ""

$sw = [System.Diagnostics.Stopwatch]::StartNew()

$pyiArgs = @($specPath, '--noconfirm', '--clean')
if ($UPX_DIR) { $pyiArgs += '--upx-dir'; $pyiArgs += $UPX_DIR }
if (-not (Test-Path $buildDir)) { New-Item -ItemType Directory -Force $buildDir | Out-Null }

# PyInstaller writes all progress to stderr. PS 5.1 wraps native stderr as
# NativeCommandError. Use .NET Process directly to stream stderr in real-time
# without PS interference.
$pyiFullArgs = @('-m', 'PyInstaller') + $pyiArgs + @('--distpath', $distDir, '--workpath', $buildDir)
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $VENV
$psi.Arguments = $pyiFullArgs -join ' '
$psi.UseShellExecute = $false
$psi.RedirectStandardError = $true
$psi.RedirectStandardOutput = $false
$psi.CreateNoWindow = $true
$proc = [System.Diagnostics.Process]::Start($psi)

# Read stderr line-by-line, print in real-time
while (-not $proc.StandardError.EndOfStream) {
    $line = $proc.StandardError.ReadLine()
    if ($line) { Write-Host $line }
}
$proc.WaitForExit()
$exitCode = $proc.ExitCode

if ($exitCode -ne 0) {
    Write-Host "`n  Build FAILED (exit $exitCode)" -ForegroundColor Red
    if (-not $NoPause) { Read-Host }
    exit 1
}

$sw.Stop()
Write-Host ""
Write-Host "  + Build done in $([math]::Round($sw.Elapsed.TotalMinutes, 1)) min" -ForegroundColor Green

# ---- step 3: package ----
$outDir = "$distDir\MarkItDown"
$exe = "$outDir\MarkItDown.exe"

if (-not (Test-Path $exe)) {
    Write-Host "  Output not found: $exe" -ForegroundColor Red
    if (-not $NoPause) { Read-Host }
    exit 1
}

if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }

$folderMB = "{0:F0}" -f ((Get-ChildItem $outDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB)

if (-not $SkipZip) {
    Write-Host "  [3/3] Package" -ForegroundColor Yellow
    Write-Host "  + Folder : $folderMB MB" -ForegroundColor Green

    $zipPath = "$distDir\MarkItDown.zip"
    Write-Host "  Compressing ..."
    Compress-Archive -Path "$outDir\*" -DestinationPath $zipPath -Force
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
if (-not $SkipZip) { Write-Host "  $distDir\MarkItDown.zip ($zipMB MB)" -ForegroundColor Green }
Write-Host "==================================================" -ForegroundColor Green

if (-not $NoPause) { Read-Host }
