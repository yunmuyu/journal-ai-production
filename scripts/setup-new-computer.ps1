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
& $pythonExecutable -c 'import importlib.util,sys; sys.exit(0 if importlib.util.find_spec("pip") else 1)'
if ($LASTEXITCODE -ne 0) {
    & $pythonExecutable -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed; use a standard Python 3.12 installation' }
}
& $pythonExecutable -m pip install -r (Join-Path $repoDirectory 'portable-production\dependencies.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& $pythonExecutable -c 'import pypdf,pymupdf,pypdfium2,PIL,numpy,cairosvg,shapely; print("Python dependencies loaded")'
if ($LASTEXITCODE -ne 0) { throw 'Dependency probe failed; check Cairo native DLL availability on Windows' }
Write-Output "Runtime prepared: $pythonExecutable"
Write-Output 'Next: install licensed fonts, restore private data, then run node journal.mjs configure. See docs/NEW-COMPUTER.md.'
