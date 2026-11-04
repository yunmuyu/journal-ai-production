param([Parameter(Mandatory=$true)][string]$Python, [Parameter(Mandatory=$true)][string]$RuntimeDirectory)
$ErrorActionPreference = 'Stop'
$repoDirectory = Split-Path $PSScriptRoot -Parent
& $Python -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12 or newer required"'
if ($LASTEXITCODE -ne 0) { throw 'Python version check failed' }
$pythonExecutable = Join-Path $RuntimeDirectory 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExecutable)) {
    & $Python -m venv $RuntimeDirectory
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
}
& $pythonExecutable -m pip install -r (Join-Path $repoDirectory 'portable-production\dependencies.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $pythonExecutable -c 'import pypdf,pymupdf,PIL,numpy,cairosvg; print("Python dependencies loaded")'
if ($LASTEXITCODE -ne 0) { throw 'Dependency probe failed; check Cairo native DLL availability on Windows' }
Write-Output "Runtime prepared: $pythonExecutable"
Write-Output 'Next: install licensed fonts, restore private data, then run scripts/configure-local.mjs. See docs/NEW-COMPUTER.md.'
