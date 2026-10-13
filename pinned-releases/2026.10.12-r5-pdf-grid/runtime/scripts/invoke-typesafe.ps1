param([Parameter(Mandatory)][string]$Request,[Parameter(Mandatory)][string]$Result,[Parameter(Mandatory)][string]$Python)
$ErrorActionPreference='Stop'
$keyFile=Join-Path $env:LOCALAPPDATA 'JournalFigureWorkflow/typesafe.key.dpapi'
if(-not $env:TYPESAFE_API_KEY){
 if(-not (Test-Path -LiteralPath $keyFile)){throw 'TypeSafe credential is not configured'}
 $secure=(Get-Content -LiteralPath $keyFile -Raw).Trim() | ConvertTo-SecureString
 $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
 try{$env:TYPESAFE_API_KEY=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)}finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)}
}
$env:PYTHONIOENCODING='utf-8'
try{& $Python (Join-Path $PSScriptRoot 'typesafe_call.py') $Request $Result;exit $LASTEXITCODE}finally{Remove-Item Env:TYPESAFE_API_KEY -ErrorAction SilentlyContinue}
