import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import path from 'node:path';
const source=readFileSync(new URL('../lib/fit.mjs',import.meta.url),'utf8');
function run(plan,accept=()=>false,measuredFont=8){
 const calls=[],files=new Map();
 const ctx={path,readJson:()=>({figureId:'example',route:'vector-reletter',fontSize:8,...plan}),writeJson(file,value){files.set(file,value);},logEvent(){},render(root,file,options){if(options?.reuseOnly)return null;const p=files.get(file);calls.push([p.widthMm,p.fontSize]);return {adobe:{snapshot:{artboard:[0,0,p.widthMm*72/25.4,-100],texts:[{size:measuredFont}]},mechanicalIssues:accept(p)?[]:[{type:'text_overlap'}]},planHash:'hash'};}};
 vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('function fitInternal(')),ctx);
 return {result:ctx.fitInternal('job','plan'),calls,files};
}
test('Collisions stop for layout revision rather than redrawing at 7pt and 6pt',()=>{
 const r=run({});assert.deepEqual(r.calls,[[80,8]]);assert.equal(r.result.decision.widthMm,null);
});
test('Native measured fractional font size is recorded',()=>{
 const r=run({},()=>true,7.25);assert.deepEqual(r.calls,[[80,8]]);assert.equal(r.result.decision.fontSize,7.25);
});
test('Double-column needs revision evidence and does not regenerate smaller font plans',()=>{
 const r=run({doubleColumnRationale:'readability',singleColumnRevisionEvidence:'compact redraw still fails'},p=>p.widthMm===160);
 assert.deepEqual(r.calls,[[80,8],[160,8]]);assert.equal(r.result.decision.widthMm,160);
});
test('Explicit single-column constraint overrides older double-column evidence',()=>{
 const r=run({columnConstraint:'single',doubleColumnRationale:'old',singleColumnRevisionEvidence:'old'},p=>p.widthMm===160);
 assert.deepEqual(r.calls,[[80,8]]);assert.equal(r.result.decision.reason,'layout_revision_required');
});
test('Rebuilt graph follows whole-figure size without a second rendering plan',()=>{
 const r=run({route:'rebuild',graph:{fontSize:8}});
 for(const p of r.files.values())if(p.graph)assert.equal(p.graph.fontSize,p.fontSize);
});
