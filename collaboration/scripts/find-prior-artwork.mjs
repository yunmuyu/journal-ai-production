import fs from 'node:fs';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
// Read-only discovery. A filename hit is a candidate, never an approved source match.
const [catalogPath,outputPath,...roots]=process.argv.slice(2);
if(!catalogPath||!outputPath||!roots.length)throw Error('Usage: node find-prior-artwork.mjs catalog.json report.json root ...');
const started=performance.now(),catalog=JSON.parse(fs.readFileSync(catalogPath,'utf8'));
const authors=[...new Set(catalog.figures.map(f=>f.author))],files=[],errors=[];
function walk(dir){let entries;try{entries=fs.readdirSync(dir,{withFileTypes:true});}catch(e){errors.push({path:dir,error:e.message});return;}
 for(const entry of entries){const p=path.join(dir,entry.name);if(entry.isSymbolicLink())continue;if(entry.isDirectory())walk(p);else if(/\.(ai|pdf|pptx|vsdx|svg|docx|png|jpe?g|tiff?|eps|cdr)$/i.test(entry.name))files.push(p);}}
for(const root of roots)walk(root);
const matches=authors.map(author=>({author,files:files.filter(p=>p.includes(author)),status:'candidate-only'})).filter(x=>x.files.length);
const report={createdAt:new Date().toISOString(),roots,elapsedSeconds:(performance.now()-started)/1000,scannedFiles:files.length,authorsSearched:authors.length,authorsWithCandidates:matches.length,matches,errors,rule:'仅目录/文件名候选；必须核对文章标题、图号、实际内容和当前Word版本，不自动确认、不修改生产状态'};
fs.writeFileSync(outputPath,JSON.stringify(report,null,2));
console.log(JSON.stringify({seconds:report.elapsedSeconds,files:files.length,authors:matches.length,errors:errors.length}));
