import test from 'node:test';
import assert from 'node:assert/strict';
import {routingRequest,validateRoutingResponse} from '../lib/typesafe.mjs';
test('routing sends selected evidence, not file paths or credentials',()=>{
 const r=routingRequest([{id:'a',caption:'Example',observations:'Unclear arrows',originalPath:'private',apiKey:'secret'}]);assert.deepEqual(Object.keys(r.state.figures[0]).sort(),['caption','id','observations']);assert.ok(r.questions.route_0.criteria.review);
});
test('model output cannot silently invent a processing route',()=>{
 const r=routingRequest([{id:'a'}]);assert.throws(()=>validateRoutingResponse(r,{answers:{route_0:{type:'choice',choice:'delete_source',confidence:1,probabilities:{}}}}),/Invalid/);
});
test('valid routing answer remains advisory rather than an approval',()=>{
 const r=routingRequest([{id:'a'}]),probabilities=Object.fromEntries(Object.keys(r.questions.route_0.criteria).map(k=>[k,k==='review'?1:0]));const decisions=validateRoutingResponse(r,{answers:{route_0:{type:'choice',choice:'review',confidence:1,probabilities}}});assert.equal(decisions[0].advisoryOnly,true);
});
