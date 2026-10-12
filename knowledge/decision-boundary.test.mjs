import test from 'node:test';
import assert from 'node:assert/strict';
import {protectDecision} from './decision-boundary.mjs';
const local={source:{status:'match',evidence:'word+source'},regions:[{id:'whole'}],originalMarks:[]};
const raw={route:'image',delivery:{count:1,outputs:[{regionIds:['whole'],originalCaption:null}]},width:{value:'单栏'},regions:[{id:'whole',description:'whole'}]};
test('confirmed decisions cannot be overwritten by conflicting model advice',()=>{
 const locks=[{field:'route',value:'rebuild'},{field:'width',value:{value:'双栏'}},{field:'delivery',value:raw.delivery}].map(c=>({...c,confirmed:true,evidence:'user record revision 2'}));
 const r=protectDecision({...raw,delivery:{count:4,outputs:[]}}, {...local,constraints:locks});
 assert.equal(r.result.route,'rebuild');assert.equal(r.result.width.value,'双栏');assert.equal(r.result.delivery.count,1);assert.equal(r.errors.filter(e=>e.code==='USER_CONSTRAINT_CONFLICT').length,3);
});
test('unverified local requirements cannot become hard constraints',()=>assert.throws(()=>protectDecision(raw,{...local,constraints:[{field:'route',value:'rebuild'}]})));
test('invented marks and captions never become original text',()=>{
 const r=protectDecision({...raw,originalMarks:[{text:'(a)',regionId:'whole'}],delivery:{count:1,outputs:[{regionIds:['whole'],originalCaption:'(a)'}]}},local);
 assert.deepEqual(r.result.originalMarks,[]);assert.equal(r.result.delivery.outputs[0].originalCaption,null);assert.equal(r.errors.length,2);
});
test('verified source captions remain separate from region ids and delivery ids',()=>{
 const l={...local,originalMarks:[{regionId:'whole',text:'（a）模块'}]};
 const r=protectDecision({...raw,originalMarks:l.originalMarks,delivery:{count:1,outputs:[{id:'output-1',regionIds:['whole'],originalCaption:'（a）模块'}]}},l);
 assert.equal(r.result.delivery.outputs[0].originalCaption,'（a）模块');assert.equal(r.errors.length,0);
});
test('unknown width does not downgrade a supported processing route',()=>{const r=protectDecision(raw,local);assert.equal(r.result.route,'image');assert.equal(r.result.width.status,'待实排验证');});
test('model claims cannot substitute for local capacity measurements',()=>{const r=protectDecision({...raw,width:{status:'verified',capacityVerified:true}},local);assert.equal(r.result.width.capacityVerified,false);assert.equal(r.errors[0].code,'UNSUPPORTED_CAPACITY');});
test('missing and duplicated delivery regions are rejected',()=>{for(const regions of [[],['whole','whole'],['other']]){const r=protectDecision({...raw,delivery:{count:1,outputs:[{regionIds:regions}]}},local);assert.equal(r.result.delivery,null);}});
test('source mismatch stops downstream decisions even with confident models',()=>{const r=protectDecision(raw,{...local,source:{status:'mismatch',evidence:'different figure'}});assert.equal(r.result.route,'review');assert.equal(r.result.delivery,null);});

test('conflicting authoritative records fail closed instead of last writer winning',()=>assert.throws(()=>protectDecision(raw,{...local,constraints:[{field:'route',value:'rebuild',confirmed:true,evidence:'one'},{field:'route',value:'image',confirmed:true,evidence:'two'}]})));
test('visual panels alone cannot authorize split delivery',()=>{const r=protectDecision({...raw,delivery:{count:2,outputs:[{regionIds:['left']},{regionIds:['right']}]}},{...local,regions:[{id:'left'},{id:'right'}]});assert.equal(r.result.delivery,null);assert.equal(r.errors[0].code,'UNGROUNDED_SPLIT');});
