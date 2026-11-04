import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {createRouteConfirmations} from './route-confirmations.mjs';
import {assertConfirmedRoute,assertStableRouteDecision} from './production-admission.mjs';

test('confirmation persists, binds exact sources and becomes stale on feedback or source change',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'route-confirm-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const ref=name=>{const file=path.join(root,name);fs.writeFileSync(file,name);return {path:file,sha256:createHash('sha256').update(name).digest('hex')};};
 const sourceReview={archive:ref('archive'),word:ref('word'),selected:ref('selected')};
 const figure={id:'F1',articleId:'A1',reviewVersion:'v1',feedback:null,productionRoute:{sourceReview}};
 const file=path.join(root,'decisions.json'),store=createRouteConfirmations(file);
 assert.throws(()=>store.save(figure,{method:'完整重绘',baseVersion:'old',evidence:'用户确认'}),/变化/);
 const saved=store.save(figure,{method:'完整重绘',baseVersion:'v1',evidence:'用户确认'});
 assert.equal(saved.stale,false);
 assert.deepEqual(createRouteConfirmations(file).get(figure),saved);
 const route={number:'1',productionRoute:{processing:{operation:'rebuild'},sourceReview}};
 assert.doesNotThrow(()=>assertConfirmedRoute({...figure,decision:saved},{outputRoutes:[route]}));
 assert.throws(()=>assertConfirmedRoute({...figure,decision:saved},{outputRoutes:[{...route,productionRoute:{...route.productionRoute,processing:{operation:'vector-reletter'}}}]}),/confirmed_route_conflict/);
 assert.throws(()=>assertConfirmedRoute({...figure,decision:saved},{outputRoutes:[{...route,productionRoute:{...route.productionRoute,sourceReview:{...sourceReview,selected:ref('other')}}}]}),/source_conflict/);
 assert.equal(store.get({...figure,feedback:{revision:1}}).stale,true);
 assert.equal(store.get({...figure,productionRoute:{sourceReview:{...sourceReview,selected:ref('changed')}}}).stale,true);
 const again=store.save(figure,{method:'完整重绘',baseVersion:'v1',evidence:'再次确认'});
 assert.throws(()=>assertStableRouteDecision({decision:saved},{decision:again}),/route_decision_changed/);
 assert.equal(again.history.length,1);
});
