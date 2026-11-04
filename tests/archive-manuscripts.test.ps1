$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('archive-inspect-'+[guid]::NewGuid())
New-Item -ItemType Directory -Path $root|Out-Null
try {
 Add-Type -AssemblyName System.IO.Compression.FileSystem
 . (Join-Path $PSScriptRoot '../scripts/archive-manuscripts.ps1')
 function MakeZip($name,$members){
  $file=Join-Path $root $name
  $zip=[IO.Compression.ZipFile]::Open($file,[IO.Compression.ZipArchiveMode]::Create)
  try{foreach($member in $members){$entry=$zip.CreateEntry($member);$writer=[IO.StreamWriter]::new($entry.Open());try{$writer.Write('test Word bytes')}finally{$writer.Dispose()}}}finally{$zip.Dispose()}
  return $file
 }
 $good=MakeZip 'good.zip' @('1 [图] 2p 作者 标题一.docx','2【图】2P 作者 标题二.docx')
 $articles=@(Read-ArchiveManuscripts $good '')
 if($articles.Count -ne 2 -or $articles[0].author -ne '作者'){throw 'Word parsing failed'}
 $bad=MakeZip 'bad.zip' @('../escape.docx')
 $rejected=$false;try{Read-ArchiveManuscripts $bad ''|Out-Null}catch{$rejected=$true};if(-not $rejected){throw 'Traversal accepted'}
 $dest=Join-Path $root 'delivery';$source=Join-Path $root 'source';$manifest=Join-Path $root 'receipt.json'
 $script=Join-Path $PSScriptRoot '../scripts/new-delivery-folders.ps1'
 $rejected=$false;try{& $script -Archive $good -Destination $dest -Month 11 -Editor 编辑 -Count 3|Out-Null}catch{$rejected=$true}
 if(-not $rejected -or (Test-Path $dest)){throw 'Count mismatch mutated destination'}
 & $script -Archive $good -Destination $dest -Month 11 -Editor 编辑 -Count 2 -SourceRoot $source -ManifestPath $manifest|Out-Null
 & $script -Archive $good -Destination $dest -Month 11 -Editor 编辑 -Count 2 -SourceRoot $source -ManifestPath $manifest|Out-Null
 $receipt=Get-Content $manifest -Raw|ConvertFrom-Json
 if($receipt.authors -ne 1 -or $receipt.articles -ne 2){throw 'Duplicate author mapping failed'}
 [IO.File]::WriteAllText($receipt.manuscripts[0].wordPath,'changed')
 $rejected=$false;try{& $script -Archive $good -Destination $dest -Month 11 -Editor 编辑 -Count 2 -SourceRoot $source|Out-Null}catch{$rejected=$true}
 if(-not $rejected -or [IO.File]::ReadAllText($receipt.manuscripts[0].wordPath) -ne 'changed'){throw 'Existing Word overwritten'}
 'PASS: parsing, traversal, count-before-write, duplicate author, retry and changed Word preservation'
}finally{
 $resolved=[IO.Path]::GetFullPath($root)
 if($resolved.StartsWith([IO.Path]::GetFullPath([IO.Path]::GetTempPath()),[StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($resolved).StartsWith('archive-inspect-')){Remove-Item -LiteralPath $resolved -Recurse -Force}
}
