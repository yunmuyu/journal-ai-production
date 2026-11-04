import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {testRef} from './route-test-fixture.mjs';
import {prepareRasterPlan,rasterReuseKey,findAcceptedRasterReuse} from './raster-preparation.mjs';

test('confirmed preserve plan uses real shared-engine measurements and explicit crop', {skip:!process.env.WORKSPACE_TEST_PYTHON}, async t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'raster-preparation-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const file=path.join(root,'source.png');fs.writeFileSync(file,Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=','base64'));
 const route={method:'raster-preserve',processing:{operation:'preserve',basis:'Confirmed photo'},sourceReview:{selected:testRef(file)},requirements:{widthMm:80}};
 const result=await prepareRasterPlan({route,options:{crop:null},python:process.env.WORKSPACE_TEST_PYTHON});
 assert.deepEqual(result.plan.inputs,[{...testRef(file),crop:null}]);assert.equal(result.plan.width_mm,80);
 assert.deepEqual(result.measurement.cropped_pixels,[1,1]);assert.equal(result.measurement.effective_source_dpi,25.4/80);
 assert.equal(result.plan.target_dpi,null);assert.equal(result.measurement.semantic_verified,false);
 const cache=new Map(),pair=await Promise.all([80,40].map(widthMm=>prepareRasterPlan({route:{...route,requirements:{widthMm}},options:{crop:null},python:process.env.WORKSPACE_TEST_PYTHON,cache})));
 assert.equal(cache.size,1);assert.deepEqual(pair.map(r=>r.plan.width_mm),[80,40]);
 await assert.rejects(()=>prepareRasterPlan({route:{...route,processing:{operation:'raster-reletter',basis:'needs lettering'}},options:{crop:null},python:'must-not-run'}),/保留/);
 await assert.rejects(()=>prepareRasterPlan({route,options:{},python:'must-not-run'}),/explicit_crop_required/);
 await assert.rejects(()=>prepareRasterPlan({route,options:{crop:[0,0,2,1]},python:process.env.WORKSPACE_TEST_PYTHON}),/crop_bounds/);
});

test('reuse separates crop, manuscript, processing and runtime; withdrawn or changed output never matches',t=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'raster-reuse-'));t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const file=path.join(root,'old.jpg');fs.writeFileSync(file,'fixture');
 const input={identity:{batchHash:'batch',articleId:'article',figureId:'figure',number:'1'},wordSha256:'word',processing:{operation:'preserve',basis:'photo'},plan:{inputs:[{sha256:'source',crop:null}],layout:{mode:'single',gap_px:0},width_mm:80,quality:95,target_dpi:null},runtime:{pythonSha256:'python',engineSha256:'engine'},policySha256:'policy'};
 const key=rasterReuseKey(input),record={key,figureId:'figure',acceptanceVersion:'review-1',output:testRef(file)};
 assert.equal(findAcceptedRasterReuse(input,[record],{figure:{accepted:true,version:'review-1'}})?.output.sha256,record.output.sha256);
 for(const mutate of [x=>x.plan.inputs[0].crop=[0,0,10,10],x=>x.wordSha256='new',x=>x.runtime.engineSha256='new',x=>x.processing.operation='rebuild',x=>x.identity.articleId='another']){const changed=structuredClone(input);mutate(changed);assert.notEqual(rasterReuseKey(changed),key);}
 assert.equal(findAcceptedRasterReuse(input,[record],{figure:{accepted:false,version:'review-1'}}),null);
 assert.equal(findAcceptedRasterReuse(input,[record],{figure:{accepted:true,version:'review-2'}}),null);
 fs.appendFileSync(file,'changed');assert.equal(findAcceptedRasterReuse(input,[record],{figure:{accepted:true,version:'review-1'}}),null);
});
