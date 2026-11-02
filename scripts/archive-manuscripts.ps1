# Shared, read-only archive inspection. Never executes archive members.
function Assert-ArchiveMember([string]$Name) {
 if($Name -match '^[\\/]' -or $Name -match ':' -or $Name -match '[\x00-\x1f]'){throw "Unsafe archive member: $Name"}
 foreach($part in ($Name -split '[/\\]')){
  if($part -eq '..' -or $part -eq '.' -or $part -match '[<>"|?*]' -or $part -match '[. ]$' -or $part -match '^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)'){throw "Unsafe archive member: $Name"}
 }
}
function Read-ArchiveManuscripts([string]$Archive,[string]$Unrar) {
 $zip=$null;$result=@();$seen=@{};$total=0L
 try {
  if([IO.Path]::GetExtension($Archive) -ieq '.zip'){
   Add-Type -AssemblyName System.IO.Compression.FileSystem
   $zip=[IO.Compression.ZipFile]::Open($Archive,[IO.Compression.ZipArchiveMode]::Read,[Text.Encoding]::GetEncoding(936))
   $names=@($zip.Entries|ForEach-Object FullName)
  }else{
   if(-not(Test-Path -LiteralPath $Unrar)){throw 'RAR support requires the configured UnRAR executable'}
   $listing=[Diagnostics.ProcessStartInfo]::new();$listing.FileName=$Unrar;$listing.UseShellExecute=$false;$listing.CreateNoWindow=$true
   $listing.RedirectStandardOutput=$true;$listing.RedirectStandardError=$true;$listing.StandardOutputEncoding=[Text.Encoding]::Unicode
   $listing.Arguments='lb -scu "'+$Archive+'"'
   $process=[Diagnostics.Process]::Start($listing)
   try{$errorText=$process.StandardError.ReadToEndAsync();$output=$process.StandardOutput.ReadToEnd();$process.WaitForExit();if($process.ExitCode -ne 0){throw ('RAR listing failed: '+$errorText.Result)};$names=@($output.TrimStart([char]0xFEFF) -split '\r?\n'|Where-Object {$_ -ne ''})}finally{$process.Dispose()}
  }
  if($names.Count -gt 10000){throw 'Archive has too many members'}
  foreach($name in $names){Assert-ArchiveMember $name}
  foreach($name in $names){
   $leaf=($name -split '[/\\]')[-1]
   if($leaf -notmatch '\.docx?$' -or $leaf.StartsWith('~$')){continue}
   if($leaf -notmatch '^\d+\s*[\[【].*?[\]】]\s*\d+(?:\.\d+)?[pP]\s+(\S+)\s+(.+)\.docx?$'){throw "Unrecognized manuscript name: $leaf"}
   $author=$Matches[1];$title=$Matches[2].Trim();$key=$name.Replace('\','/').ToLowerInvariant()
   if($seen.ContainsKey($key)){throw "Duplicate manuscript member: $name"};$seen[$key]=$true
   $stream=[IO.MemoryStream]::new()
   try {
    if($zip){
     $entry=$zip.GetEntry($name);if($entry.Length -gt 100MB){throw "Manuscript too large: $name"}
     $inputStream=$entry.Open();try{$inputStream.CopyTo($stream)}finally{$inputStream.Dispose()}
    }else{
     $start=[Diagnostics.ProcessStartInfo]::new();$start.FileName=$Unrar;$start.UseShellExecute=$false;$start.CreateNoWindow=$true
     $start.RedirectStandardOutput=$true;$start.RedirectStandardError=$true;$start.Arguments='p -inul "'+$Archive+'" "'+$name+'"'
     $process=[Diagnostics.Process]::Start($start);$errorText=$process.StandardError.ReadToEndAsync();$buffer=New-Object byte[] 65536
     try {while(($n=$process.StandardOutput.BaseStream.Read($buffer,0,$buffer.Length)) -gt 0){$stream.Write($buffer,0,$n);if($stream.Length -gt 100MB){$process.Kill();throw 'Manuscript exceeds size limit'}};$process.WaitForExit();if($process.ExitCode -ne 0){throw ('RAR read failed: '+$errorText.Result)}}finally{$process.Dispose()}
    }
    $bytes=$stream.ToArray();$total+=$bytes.Length;if($total -gt 512MB){throw 'Manuscripts exceed total size limit'}
    $hasher=[Security.Cryptography.SHA256]::Create()
    try{$hash=[BitConverter]::ToString($hasher.ComputeHash($bytes)).Replace('-','').ToLowerInvariant()}finally{$hasher.Dispose()}
    $result+=[pscustomobject]@{author=$author;title=$title;member=$name;sha256=$hash;bytes=$bytes}
   }finally{$stream.Dispose()}
  }
 }finally{if($zip){$zip.Dispose()}}
 return $result
}
