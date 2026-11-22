# Build the Windows installer for the canvas app.
#
# Requires Inno Setup 6 (https://jrsoftware.org/isdl.php).
# Version is read from proto\server.py APP_VERSION so it can never drift
# from the app itself -- bump the constant, rebuild, done.
#
# Usage:  powershell -ExecutionPolicy Bypass -File installer\build-installer.ps1
#
# This file is intentionally pure ASCII: PowerShell 5.1 reads .ps1 as ANSI
# by default, so any CJK literal here would come out garbled.

$ErrorActionPreference = 'Stop'

# --- 1. locate ISCC -----------------------------------------------------------
$candidates = @(
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe')
)
$iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) {
    throw "ISCC.exe not found. Install Inno Setup 6 first: https://jrsoftware.org/isdl.php"
}
Write-Host "ISCC: $iscc"

# --- 2. read APP_VERSION from server.py --------------------------------------
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$srv  = Join-Path $root 'proto\server.py'
if (-not (Test-Path $srv)) { throw "server.py not found: $srv" }

$m = Select-String -Path $srv -Pattern 'APP_VERSION\s*=\s*"([\d.]+)"' | Select-Object -First 1
if (-not $m) { throw "APP_VERSION not found in $srv" }
$version = $m.Matches[0].Groups[1].Value
Write-Host "APP_VERSION: $version"

# --- 3. make sure an onedir build actually exists -----------------------------
$distRoot = Join-Path $root 'proto\dist'
$exe = Get-ChildItem $distRoot -Directory -ErrorAction SilentlyContinue |
       ForEach-Object { Get-ChildItem $_.FullName -Filter *.exe -ErrorAction SilentlyContinue } |
       Select-Object -First 1
if (-not $exe) {
    throw "No .exe under proto\dist -- run PyInstaller (proto\<name>.spec) first."
}
Write-Host "payload: $($exe.FullName)"

# --- 4. compile ---------------------------------------------------------------
$iss = Get-ChildItem $here -Filter *.iss | Select-Object -First 1
if (-not $iss) { throw "No .iss file next to this script." }

& $iscc "/DAppVersion=$version" $iss.FullName
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

Write-Host ""
Write-Host "Done. Look in proto\dist\installer\"
