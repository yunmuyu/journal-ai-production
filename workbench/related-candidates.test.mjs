import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {activateRelatedCandidates} from './related-candidates.mjs';
import {syncRelatedReviews} from './archive-articles.mjs';
const sha=v=>createHash('sha256').update(v).digest('hex');
function fixture(t){
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'related-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const ref=(name,bytes)=>{const p=path.join(root,name);fs.writeFileSync(p,bytes);return {path:p,sha256:sha(bytes)};};
 const word=ref('word.docx','word'),output=ref('legacy-1.pdf','%PDF-fixture'),preview=ref('preview.png','preview');
 const archiveSha256=sha('archive'),member='source/word.docx',id='PKG-'+sha(archiveSha256+'\0'+member).slice(0,20);
 const context={articles:[{id,word,archiveHash:archiveSha256,author:'同名作者',editor:'编辑',figures:[],externalReviewUrl:'old'}],rows:[],metadata:{},link:u=>({path:fileURLToPath(u)}),feedbackRecords:{},acceptanceRecords:{}};
 const manifest={version:1,legacy:'http://127.0.0.1:18742/',articles:[{targetArticleId:id,oldArticleId:'ZL-2',archiveSha256,member,word,figures:[{targetFigureId:id+'-F4-1',oldFigureId:'ZL-2-F4-1',mainNumber:'4-1',legacyFeedback:null,historicalNotice:'旧FAIL，不可直接派单',outputs:[{output,preview,legacyOutputNumber:'1',proposedOutputNumber:'4-1',existingMetadata:{fontLabel:'字号3.8pt',columnLabel:'单栏约90%'}}]}]}]};
 return {context,manifest,output};
}
test('imports aliases and existing previews as candidates without old FAIL or font labels',t=>{
 const {context,manifest,output}=fixture(t),result=activateRelatedCandidates(context,manifest);
 assert.equal(result.figures,1);assert.equal(result.outputs,1);assert.equal(context.rows[0],context.articles[0].figures[0]);
 assert.equal(context.rows[0].outputs[0].number,'4-1');assert.equal(context.rows[0].status,'待终检');
 assert.equal(context.rows[0].relatedProvenance.outputs[0].number,'1');assert.equal(context.metadata[output.path].fontLabel,'');
 assert.equal(context.articles[0].externalReviewUrl,undefined);assert.doesNotMatch(JSON.stringify(context.rows[0].notices),/FAIL/);
 assert.match(JSON.stringify(context.rows[0].notices),/旧输出图1.*Word图4-1/);
});
for(const [label,expected] of [['单栏约95%','单栏约100%'],['双栏约85.2%','双栏约90%'],['单栏约60%（含留白）','单栏约60%（含留白）'],['栏宽待核对','栏宽待核对']])test('import display rounds percentages without remeasuring: '+label,t=>{
 const {context,manifest,output}=fixture(t);
 manifest.articles[0].figures[0].outputs[0].existingMetadata.columnLabel=label;
 const before=JSON.stringify(manifest);activateRelatedCandidates(context,manifest);
 assert.equal(context.metadata[output.path].columnLabel,expected);assert.equal(JSON.stringify(manifest),before);
});
test('repeated import preserves newer outputs, feedback and approval state',t=>{
 const {context,manifest}=fixture(t);activateRelatedCandidates(context,manifest);
 context.rows[0].feedback={text:'new'};context.rows[0].status='终检通过';context.rows[0].outputs=[];
 const before=JSON.stringify(context);assert.equal(activateRelatedCandidates(context,manifest).skipped.length,1);assert.equal(JSON.stringify(context),before);
});
test('persisted import receipt restores empty startup model without overwriting newer review stores',t=>{
 const {context,manifest}=fixture(t);
 const {receipt}=activateRelatedCandidates(context,manifest);
 const id=manifest.articles[0].figures[0].targetFigureId;
 context.feedbackRecords[id]={text:'new annotation',revision:3};
 context.acceptanceRecords[id]={accepted:true,version:'new-version'};
 const stores=JSON.stringify([context.feedbackRecords,context.acceptanceRecords]);
 const restart={...context,articles:context.articles.map(a=>({...a,figures:[],relatedImport:undefined})),rows:[],metadata:{}};
 const result=activateRelatedCandidates(restart,manifest,{receipt:JSON.parse(JSON.stringify(receipt))});
 assert.deepEqual(result.restored,[manifest.articles[0].targetArticleId]);
 assert.equal(restart.rows[0].feedback.text,'new annotation');
 assert.equal(restart.rows[0].status,'待终检'); // Live updater evaluates current version, not receipt.
 assert.equal(JSON.stringify([context.feedbackRecords,context.acceptanceRecords]),stores);
});
for(const change of ['manifest','word','old-id','figure-id','missing'])test('rejects mismatching import receipt before model writes: '+change,t=>{
 const {context,manifest}=fixture(t);const {receipt}=activateRelatedCandidates(context,manifest);
 const restart={...context,articles:context.articles.map(a=>({...a,figures:[],relatedImport:undefined})),rows:[],metadata:{}};
 if(change==='manifest')receipt.manifestSha256='0'.repeat(64);
 if(change==='word')receipt.articles[0].wordSha256='0'.repeat(64);
 if(change==='old-id')receipt.articles[0].oldArticleId='other';
 if(change==='figure-id')receipt.articles[0].figures[0].targetFigureId='other';
 if(change==='missing')delete receipt.articles;
 const before=JSON.stringify(restart);assert.throws(()=>activateRelatedCandidates(restart,manifest,{receipt}),/回执/);assert.equal(JSON.stringify(restart),before);
});
for(const change of ['word','output','preview','existing','feedback','approval','legacy-feedback'])test('blocks conflict without model mutation: '+change,t=>{
 const {context,manifest}=fixture(t),a=manifest.articles[0],f=a.figures[0];
 if(change==='word')fs.writeFileSync(a.word.path,'changed');
 if(change==='output'||change==='preview')fs.writeFileSync(f.outputs[0][change].path,'changed');
 if(change==='existing')context.articles[0].figures.push({number:'4-1'});
 if(change==='feedback')context.feedbackRecords[f.targetFigureId]={text:'new'};
 if(change==='approval')context.acceptanceRecords[f.targetFigureId]={accepted:true};
 if(change==='legacy-feedback')f.legacyFeedback={text:'old'};
 const before=JSON.stringify(context);assert.throws(()=>activateRelatedCandidates(context,manifest));assert.equal(JSON.stringify(context),before);
});
test('related sync cannot restore external link or remote approval after migration',async t=>{
 const {context,manifest}=fixture(t);activateRelatedCandidates(context,manifest);
 const prior=globalThis.fetch;t.after(()=>{globalThis.fetch=prior;});
 globalThis.fetch=async()=>({ok:true,json:async()=>({articles:[{word:context.articles[0].word,state:'全部通过',figures:[{}]}]})});
 await syncRelatedReviews(context.articles,['http://example.invalid']);
 assert.equal(context.articles[0].externalReviewUrl,undefined);assert.equal(context.articles[0].state,'待核验');
});
