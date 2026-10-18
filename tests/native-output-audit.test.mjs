import test from 'node:test';
import assert from 'node:assert/strict';
import {auditNativeOutput} from '../lib/native-output-audit.mjs';
const snapshot={artboard:[0,100,220,0],texts:[{index:0,size:8}],pathGeometry:[{name:'post-curve',stroked:true,strokeWidthPt:.5,strokeDashes:[.16,.107]}]};
test('final physical dash lengths are measured rather than inferred from source units',()=>{
 const plan={widthMm:80,strokeExpectations:[{pathName:'post-curve',widthPt:.5,dashPt:[3,2]}]};
 assert.equal(auditNativeOutput(snapshot,plan).issues[0].type,'final_dash_lengths');
 assert.equal(auditNativeOutput({...snapshot,pathGeometry:[{...snapshot.pathGeometry[0],strokeDashes:[3,2]}]},plan).ok,true);
});
test('raster text is not reported as verified native typography',()=>{
 assert.equal(auditNativeOutput({...snapshot,texts:[]},{widthMm:80}).fontCoverage,'raster_or_no_text_unverified');
});
test('single column and six point are checked on actual output',()=>{
 assert.equal(auditNativeOutput({...snapshot,texts:[{size:5.99}]},{widthMm:80}).ok,false);
 assert.equal(auditNativeOutput({...snapshot,texts:[{size:6}]},{widthMm:80}).ok,true);
 assert.equal(auditNativeOutput({...snapshot,artboard:[0,100,300,0]},{widthMm:80}).issues[0].type,'final_column_width');
});
test('ordinary characters cannot hide undersized text inside an eight-point frame',()=>{
 const result=auditNativeOutput({...snapshot,texts:[{index:0,size:8,characterStyles:[{text:'x',size:8},{text:'2',size:2,baselineShift:0}]}]},{widthMm:80});
 assert.equal(result.ok,false);
 assert.equal(result.issues[0].type,'final_character_font_size');
 assert.equal(result.issues[0].characterIndex,1);
});
test('explicit native scripts retain their valid parent size while baseline shift alone proves no script',()=>{
 for(const baselinePosition of ['SUBSCRIPT','FontBaselineOption.SUPERSCRIPT']){
  const result=auditNativeOutput({...snapshot,texts:[{size:8,characterStyles:[{text:'x',size:8},{text:'2',size:5.6,baselinePosition}]}]},{widthMm:80});
  assert.equal(result.ok,true);
  assert.equal(result.minimumBaseFontPt,8);
 }
 assert.equal(auditNativeOutput({...snapshot,texts:[{size:8,characterStyles:[{size:5.6,baselineShift:-2}]}]},{widthMm:80}).ok,false);
 assert.equal(auditNativeOutput({...snapshot,texts:[{size:5.6,characterStyles:[{size:3.92,baselinePosition:'SUBSCRIPT'}]}]},{widthMm:80}).ok,false);
});
