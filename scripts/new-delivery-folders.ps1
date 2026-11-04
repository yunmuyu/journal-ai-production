param(
 [Parameter(Mandatory)][string]$Archive,
 [Parameter(Mandatory)][string]$Destination,
 [Parameter(Mandatory)][ValidateRange(1,12)][int]$Month,
 [Parameter(Mandatory)][string]$Editor,
 [Parameter(Mandatory)][ValidateRange(1,999)][int]$Count,
 [string[]]$Authors,
 [string]$Unrar='C:\Program Files\WinRAR\UnRAR.exe',
 [string]$ManifestPath,
 [string]$SourceRoot
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'archive-manuscripts.ps1')
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
 $articles=@(Read-ArchiveManuscripts $Archive $Unrar)
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
if($SourceRoot){
 if($Authors){throw 'Source extraction requires verified manuscript members, not -Authors'}
 foreach($article in $articles){
  $word=Join-Path $SourceRoot $article.member
  if((Test-Path -LiteralPath $word) -and (Get-FileHash -LiteralPath $word).Hash.ToLowerInvariant() -ne $article.sha256){throw "Existing Word differs; no overwrite: $word"}
 }
}
New-Item -ItemType Directory -Path $batch -Force | Out-Null
foreach($name in $relative){New-Item -ItemType Directory -Path (Join-Path $batch $name) -Force | Out-Null}
if(-not(Test-Path -LiteralPath $copy)){Copy-Item -LiteralPath $Archive -Destination $copy}
if((Get-FileHash -LiteralPath $copy).Hash -ne $hash){throw 'Copied archive hash mismatch'}
if($SourceRoot){foreach($article in $articles){
 $word=Join-Path $SourceRoot $article.member
 if(-not(Test-Path -LiteralPath $word)){New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($word)) -Force|Out-Null;[IO.File]::WriteAllBytes($word,$article.bytes)}
}}
$receipt=[pscustomobject]@{batch=$batch;articles=$articles.Count;authors=@($articles.author|Select-Object -Unique).Count;archiveSha256=$hash.ToLowerInvariant();manuscripts=@($articles|ForEach-Object {[pscustomobject]@{author=$_.author;title=$_.title;member=$_.member;sha256=$_.sha256;wordPath=$(if($SourceRoot){Join-Path $SourceRoot $_.member}else{''})}})}
if($ManifestPath){[IO.File]::WriteAllText($ManifestPath,($receipt|ConvertTo-Json -Depth 5),[Text.UTF8Encoding]::new($false))}
$receipt|Select-Object batch,articles,authors,archiveSha256
