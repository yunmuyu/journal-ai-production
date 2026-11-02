param(
 [Parameter(Mandatory)][string]$Archive,
 [Parameter(Mandatory)][string]$Destination,
 [Parameter(Mandatory)][ValidateRange(1,12)][int]$Month,
 [Parameter(Mandatory)][string]$Editor,
 [Parameter(Mandatory)][ValidateRange(1,999)][int]$Count,
 [string[]]$Authors,
 [string]$Unrar='C:\Program Files\WinRAR\UnRAR.exe'
)
$ErrorActionPreference='Stop'
function SafeName([string]$value){
 if([string]::IsNullOrWhiteSpace($value) -or $value -match '[<>:"/\\|?*\x00-\x1f]' -or $value -match '[. ]$' -or $value -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)'){throw "Unsafe folder name: $value"}
}
$Archive=(Get-Item -LiteralPath $Archive).FullName
$ext=[IO.Path]::GetExtension($Archive).ToLowerInvariant()
if($ext -notin @('.zip','.rar')){throw 'Only ZIP and RAR archives are supported'}
SafeName $Editor
$articles=@()
if($Authors){
 foreach($author in $Authors){$articles+= [pscustomobject]@{author=$author;title=''}}
}else{
 if($ext -eq '.zip'){
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip=[IO.Compression.ZipFile]::Open($Archive,[IO.Compression.ZipArchiveMode]::Read,[Text.Encoding]::GetEncoding(936))
  try {$names=@($zip.Entries | ForEach-Object FullName)}finally{$zip.Dispose()}
 }else{
  if(-not(Test-Path -LiteralPath $Unrar)){throw 'Supply -Unrar or an explicitly verified -Authors list'}
  $names=@(& $Unrar lb -scu $Archive)
  if($LASTEXITCODE -ne 0){throw 'RAR listing failed'}
 }
 foreach($name in $names){
  $leaf=($name -split '[/\\]')[-1]
  if($leaf -notmatch '\.docx?$' -or $leaf.StartsWith('~$')){continue}
  if($leaf -notmatch '^\d+\s+\[.*?\]\s*\d+(?:\.\d+)?[pP]\s+(\S+)\s+(.+)\.docx?$'){throw "Unrecognized manuscript name; supply verified -Authors: $leaf"}
  $articles+=[pscustomobject]@{author=$Matches[1];title=$Matches[2].Trim()}
 }
}
if($articles.Count -ne $Count){throw "Expected $Count articles, found $($articles.Count); no delivery files created"}
$relative=@()
foreach($group in ($articles | Group-Object author)){
 SafeName $group.Name
 $relative+=$group.Name
 if($group.Count -gt 1){
  if(@($group.Group.title|Select-Object -Unique).Count -ne $group.Count){throw 'Repeated author requires distinct manuscript titles'}
  foreach($article in $group.Group){SafeName $article.title; $relative+=Join-Path $group.Name $article.title}
 }
}
$batch=Join-Path $Destination "$Month`月-$Editor-$Count`篇"
$copy=Join-Path $batch ([IO.Path]::GetFileName($Archive))
$hash=(Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash
if((Test-Path -LiteralPath $copy) -and (Get-FileHash -LiteralPath $copy).Hash -ne $hash){throw 'An archive with the same name but different content already exists'}
New-Item -ItemType Directory -Path $batch -Force | Out-Null
foreach($name in $relative){New-Item -ItemType Directory -Path (Join-Path $batch $name) -Force | Out-Null}
if(-not(Test-Path -LiteralPath $copy)){Copy-Item -LiteralPath $Archive -Destination $copy}
if((Get-FileHash -LiteralPath $copy).Hash -ne $hash){throw 'Copied archive hash mismatch'}
[pscustomobject]@{batch=$batch;articles=$articles.Count;authors=@($articles.author|Select-Object -Unique).Count;archiveSha256=$hash}
