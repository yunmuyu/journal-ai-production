import test from 'node:test';
import assert from 'node:assert/strict';
import {renderingPlanKey,fitSourcePlanKey} from '../lib/render-reuse.mjs';
test('trial explanation and object order do not create new artwork',()=>{
 assert.equal(renderingPlanKey({fontSize:8,texts:[{text:'A',x:.5}],widthDecision:'first'}),renderingPlanKey({texts:[{x:.5,text:'A'}],widthDecision:'trial',fontSize:8}));
});
test('fit can discover prior artwork after a single-column correction without weakening normal cache identity',()=>{
 const old={widthMm:100,fontSize:8,texts:[{text:'A',x:.5}],graph:{fontSize:8,widthClass:'double'}};
 const corrected={...old,widthMm:80,columnConstraint:'single',singleColumnRevisionEvidence:'user requested single',graph:{...old.graph,widthClass:'single'}};
 assert.equal(fitSourcePlanKey(old),fitSourcePlanKey(corrected));
 assert.notEqual(renderingPlanKey(old),renderingPlanKey(corrected));
 assert.notEqual(fitSourcePlanKey(old),fitSourcePlanKey({...corrected,texts:[{text:'B',x:.5}]}));
});
test('all drawing changes still invalidate artwork reuse',()=>{
 const p={fontSize:8,texts:[{text:'A',x:.5}],widthMm:80,sourceHash:'a'};
 for(const q of [{...p,fontSize:7},{...p,widthMm:160},{...p,texts:[{text:'B',x:.5}]},{...p,sourceHash:'b'}])assert.notEqual(renderingPlanKey(p),renderingPlanKey(q));
});
