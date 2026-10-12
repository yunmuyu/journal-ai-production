import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {preflightRender,preflightAggregate,requirePreflight} from '../lib/production-preflight.mjs';
const directory=path.dirname(fileURLToPath(import.meta.url));
const hash=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function fixture(){
 const dir=fs.mkdtempSync(path.join(directory,'preflight-fixture-'));
 function file(name,text='fixture'){const p=path.join(dir,name);fs.writeFileSync(p,text);return p;}
 const source=file('source.svg'),output=file('candidate.pdf'),ai=file('candidate.ai'),formal=file('formal.pdf'),author=file('author.ai');
 const record={ok:true,output,outputHash:hash(output),ai,aiHash:hash(ai),pdfAudit:{ok:true},adobe:{mechanicalIssues:[],snapshot:{texts:[{size:8}]}}};
 const recordFile=file('render.json',JSON.stringify(record));file('plan.json',JSON.stringify({fontSize:8,sourceHash:hash(source)}));
 const input={articleId:'A-test',number:'1',source,sourceHash:hash(source),plan:{fontSize:8}};
 const context={registry:{articles:{'A-test':{ai:author,aiHash:hash(author)}},figures:{'A-test-F1':{output:formal,outputHash:hash(formal),ai:author,aiHash:'obsolete-per-figure-ai-hash'}}},templates:{'A-test':{path:author,sha256:'original-template-hash'}}};
 const config={articleId:'A-test',figures:[{figureId:'A-test-F1',number:'1',source,sourceHash:hash(source),record:recordFile}]};
 return {dir,input,context,config,record,recordFile,formal,author,writeRecord(){fs.writeFileSync(recordFile,JSON.stringify(record));}};
}
test('existing legal render and aggregate inputs continue without new required fields',()=>{
 const f=fixture();assert.equal(preflightRender([f.input],f.context).status,'可继续');assert.equal(preflightAggregate(f.config,f.context).status,'可继续');
 assert.equal(preflightAggregate(f.config,f.context).finalPdfReviewRequired,true);
});
test('changed actual source or registered formal file requires confirmation before execution',()=>{
 for(const target of ['source','formal','author']){const f=fixture();fs.writeFileSync(target==='source'?f.input.source:f[target],'changed user file');const result=preflightRender([f.input],f.context);assert.equal(result.status,'源已变需确认');assert.throws(()=>requirePreflight(result),/源已变需确认/);}
});
test('a changed unselected split export is caught before author aggregate',()=>{
 const f=fixture();f.context.registry.figures['A-test-F2']={subfigures:[{number:'2.1',output:f.formal,outputHash:'old hash'}]};
 assert.equal(preflightAggregate(f.config,f.context).status,'源已变需确认');
});
test('known eight-point reused artwork cannot silently become seven-point',()=>{
 const f=fixture();f.input.plan.fontSize=7;const priorRows=[{...f.input,record:f.recordFile}];
 const result=preflightRender([f.input],f.context,{priorRows});assert.equal(result.status,'必须修单图');assert.equal(result.issues[0].actualSizesPt[0],8);
 f.input.preflight={fontSizeChangeReason:'Verified current compact capacity requires seven-point and is explicitly authorized'};
 assert.equal(preflightRender([f.input],f.context,{priorRows}).status,'可继续');
});
test('planned valid seven-point figure stays legal rather than inventing an eight-point rule',()=>{
 const f=fixture();f.record.adobe.snapshot.texts[0].size=7;f.writeRecord();fs.writeFileSync(path.join(f.dir,'plan.json'),JSON.stringify({fontSize:7,sourceHash:f.input.sourceHash}));
 assert.equal(preflightAggregate(f.config,f.context).status,'可继续');
});
test('using the last delivered output as a new source still reads its actual eight-point snapshot',()=>{
 const f=fixture(),priorRows=[{...f.input,record:f.recordFile,result:{outputHash:f.record.outputHash,aiHash:f.record.aiHash}}];
 f.input.source=f.record.output;f.input.sourceHash=f.record.outputHash;f.input.plan.fontSize=7;
 assert.equal(preflightRender([f.input],f.context,{priorRows}).status,'必须修单图');
});
test('unresolved mechanical problem or absent actual PDF audit blocks aggregate',()=>{
 for(const defect of ['mechanical','pdf','font']){const f=fixture();if(defect==='mechanical')f.record.adobe.mechanicalIssues=[{type:'overlap'}];if(defect==='pdf')f.record.pdfAudit.ok=false;if(defect==='font')f.record.adobe.snapshot.texts[0].size=7;f.writeRecord();const result=preflightAggregate(f.config,f.context);assert.equal(result.status,'必须修单图');assert.throws(()=>requirePreflight(result),/必须修单图/);}
});
test('stale candidate AI or missing output is not falsely accepted',()=>{
 const f=fixture();fs.writeFileSync(f.record.ai,'edited candidate AI');assert.equal(preflightAggregate(f.config,f.context).status,'必须修单图');
});
test('preflight leaves authority and all files unchanged',()=>{
 const f=fixture();const before=JSON.stringify(f.context),bytes=fs.readFileSync(f.formal);preflightAggregate(f.config,f.context);preflightRender([f.input],f.context);assert.equal(JSON.stringify(f.context),before);assert.deepEqual(fs.readFileSync(f.formal),bytes);
});
