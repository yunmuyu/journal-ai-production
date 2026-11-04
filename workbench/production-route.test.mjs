import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {assertProductionRoute,productionInstructions,verifyProductionResult,verifyRasterPlan,verifyAutomaticCandidate} from './production-route.mjs';
const hash=p=>createHash('sha256').update(fs.readFileSync(p)).digest('hex');
function fixture(t){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'production-route-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const ref=name=>{const p=path.join(dir,name);fs.writeFileSync(p,name);return {path:p,sha256:hash(p)};};
 const source=ref('screen.png');
 const route={version:1,method:'raster-preserve',sourceReview:{archive:ref('original.zip'),word:ref('paper.docx'),inventory:ref('members.json'),candidates:[{...source,kind:'raster',decision:'selected',reason:'Original archive contains a UI screenshot; no editable counterpart'}],selected:source,basis:'Word figure matches archive screenshot including five panels',rasterReason:'Photographic application UI has no reliable editable reconstruction'},requirements:{format:'jpg',fontCheck:'none',widthMm:80}};
 return {dir,ref,task:{id:'job',attemptDir:dir,outputNumbers:['8'],productionRoute:route}};
}
test('old screenshot task without a structured route is rejected',()=>{
 assert.throws(()=>assertProductionRoute({outputNumbers:['8'],instructions:'PDF四边2pt，8pt先紧凑布局，必要时7/6pt，双栏需单栏不可行证据'}),/路线合同/);
});
test('automatic entry rejects PDF, revisions and missing bound self-check before invoking Python',t=>{
 const {task}=fixture(t);
 assert.throws(()=>verifyAutomaticCandidate(task,{}),/冻结raster计划/);
 task.kind='revision';assert.throws(()=>verifyAutomaticCandidate(task,{}),/修订/);
 delete task.kind;task.productionRoute.method='editable-pdf';
 assert.throws(()=>verifyAutomaticCandidate(task,{}),/常规JPG/);
});
test('raster route requires source alternatives review and rejects conflicting requirements',t=>{
 const {task}=fixture(t);assertProductionRoute(task);
 assert.match(productionInstructions(task.productionRoute),/JPG/);
 assert.match(productionInstructions(task.productionRoute),/不测量/);
 task.productionRoute.requirements.fontCheck='editable';assert.throws(()=>assertProductionRoute(task),/冲突/);
});
test('PNG suffix does not override an applicable editable source',t=>{
 const {task,ref}=fixture(t);task.productionRoute.sourceReview.candidates.push({...ref('source.svg'),kind:'vector',decision:'available',reason:'Editable equivalent'});
 assert.throws(()=>assertProductionRoute(task),/候选源件/);
});
test('changed sources and legacy mixed instruction templates are blocked before dispatch',t=>{
 const {task}=fixture(t);task.legacyProductionInstructions='PDF四边2pt，8pt先紧凑布局';assert.throws(()=>assertProductionRoute(task),/旧通用派单/);
 delete task.legacyProductionInstructions;fs.appendFileSync(task.productionRoute.sourceReview.selected.path,'change');assert.throws(()=>assertProductionRoute(task),/哈希/);
});
test('editable PDF route keeps editable font requirements',t=>{
 const {task}=fixture(t);task.productionRoute.method='editable-pdf';task.productionRoute.requirements={format:'pdf',fontCheck:'editable',widthMm:80};assertProductionRoute(task);
 assert.match(productionInstructions(task.productionRoute),/6 pt/);
 task.productionRoute.requirements.fontCheck='none';assert.throws(()=>assertProductionRoute(task),/冲突/);
});
test('raster return rejects PDF wrapping and fabricated raster font measurements',t=>{
 const {task,dir}=fixture(t);const p=path.join(dir,'8.pdf');fs.writeFileSync(p,'%PDF-1.4');
 task.productionRoute.processing={operation:'preserve',basis:'Synthetic screenshot needs no lettering changes'};
 const result={outputs:[{number:'8',path:p,sha256:hash(p),fontLabel:''}]};
 assert.throws(()=>verifyProductionResult(task,result),/JPG/);
 const jpg=path.join(dir,'8.jpg');fs.writeFileSync(jpg,Buffer.from([255,216,255,217]));result.outputs[0]={number:'8',path:jpg,sha256:hash(jpg),fontLabel:'字号2.76 pt'};
 assert.throws(()=>verifyProductionResult(task,result),/字号/);
 result.outputs[0].fontLabel='';assert.throws(()=>verifyProductionResult(task,result),/独立质量/);
});

test('multi-input raster selection binds every source and ordered public plan to frozen evidence',t=>{
 const {task,dir,ref}=fixture(t),s=task.productionRoute.sourceReview,second=ref('second.png');
 s.additionalSelected=[second];s.candidates.push({...second,kind:'raster',decision:'selected',reason:'Second panel in Word'});assertProductionRoute(task);
 const planPath=path.join(dir,'raster-plan.json'),output=path.join(dir,'combined.jpg');
 const plan={inputs:[s.selected,second],layout:{mode:'row'},output,width_mm:80};fs.writeFileSync(planPath,JSON.stringify(plan));
 const planRef={path:planPath,sha256:hash(planPath)},result={outputs:[{path:output}],quality:{rasterPlan:planRef}},contract={source_inputs:[planRef]};
 verifyRasterPlan(task,result,contract);
 plan.layout.mode='column-fit';fs.writeFileSync(planPath,JSON.stringify(plan));planRef.sha256=hash(planPath);verifyRasterPlan(task,result,contract);
 assert.throws(()=>verifyRasterPlan(task,result,{source_inputs:[]}),/冻结来源/);
 plan.inputs.reverse();fs.writeFileSync(planPath,JSON.stringify(plan));planRef.sha256=hash(planPath);assert.throws(()=>verifyRasterPlan(task,result,contract),/输入及顺序/);
 s.candidates[1].decision='not-applicable';assert.throws(()=>assertProductionRoute(task),/完整一致/);
});

test('single-source contracts cannot hide extra inputs in an optional raster plan or legacy aliases',t=>{
 const {task,dir,ref}=fixture(t),s=task.productionRoute.sourceReview,second=ref('unselected.png');
 s.selectedInputs=[s.selected,second];assert.throws(()=>assertProductionRoute(task),/未知字段/);delete s.selectedInputs;
 const planPath=path.join(dir,'raster-plan.json'),output=path.join(dir,'combined.jpg');
 const plan={inputs:[s.selected,second],layout:{mode:'row'},output,width_mm:80};fs.writeFileSync(planPath,JSON.stringify(plan));
 const planRef={path:planPath,sha256:hash(planPath)},result={outputs:[{path:output}],quality:{rasterPlan:planRef}},contract={source_inputs:[planRef]};
 assert.throws(()=>verifyRasterPlan(task,result,contract),/输入及顺序/);
 plan.inputs=[s.selected];plan.layout.mode='single';fs.writeFileSync(planPath,JSON.stringify(plan));planRef.sha256=hash(planPath);verifyRasterPlan(task,result,contract);
 verifyRasterPlan(task,{outputs:[{path:output}]},contract); // Existing sealed single-source contracts remain valid without a plan.
 s.additionalSelected=[second];assert.throws(()=>verifyRasterPlan(task,{outputs:[{path:output}]},contract),/缺少/);
});
