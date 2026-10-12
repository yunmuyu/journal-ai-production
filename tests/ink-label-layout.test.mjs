import test from 'node:test';
import assert from 'node:assert/strict';
import {positionInkLabels,verifyInkLabelGaps,refineRasterInkLayout} from '../lib/ink-label-layout.mjs';

test('a shared multiline axis title retains every line and rejects a mismatched frame',()=>{
 const plan={widthMm:25.4,texts:[{text:'0',x:.3,y:.5},{text:'像\r素',x:.1,y:.5}]};
 const roles=[{role:'y-tick',plot:'p',textIndex:0,anchorPx:[30,50]},{role:'y-axis-title',plot:['p'],textIndex:1,frameNames:['title-a','title-b']}];
 const snapshot={texts:[{name:'JFW_TEXT_1',text:'0',inkBounds:[15,-34,20,-38]},{name:'title-a',text:'像',inkBounds:[2,-25,8,-31]},{name:'title-b',text:'素',inkBounds:[1,-34,7,-40]}]};
 const result=refineRasterInkLayout(plan,roles,snapshot,[100,100]);
 const placed=positionInkLabels(result.rows),title=placed[1];
 assert.deepEqual(result.rows[1].ink,[1,-25,8,-40]);
 assert.equal(placed[0].ink[0]-title.ink[2],3);
 snapshot.texts[2].text='错';
 assert.throws(()=>refineRasterInkLayout(plan,roles,snapshot,[100,100]),/identity mismatch/);
});

test('unequal digit widths and rotated titles use visible ink, independently per panel',()=>{
 const rows=[
  {id:0,role:'y-tick',plot:'a',ink:[0,3,3,-3],anchor:[20,0]},
  {id:1,role:'y-tick',plot:'a',ink:[0,-7,13,-13],anchor:[20,-10]},
  {id:2,role:'x-tick',plot:'a',ink:[5,-20,11,-25],anchor:[40,-30]},
  {id:3,role:'x-tick',plot:'a',ink:[25,-20,35,-26],anchor:[60,-30]},
  {id:4,role:'y-axis-title',plot:'a',ink:[-30,10,-24,-10]},
  {id:5,role:'x-axis-title',plot:'a',ink:[30,-45,70,-53]},
  {id:6,role:'y-tick',plot:'b',ink:[50,0,55,-6],anchor:[100,-3]},
  {id:7,role:'y-axis-title',plot:'b',ink:[40,5,47,-15]}
 ];
 const before=JSON.stringify(rows),placed=positionInkLabels(rows);
 assert.equal(JSON.stringify(rows),before);
 assert.equal(placed[0].ink[2],17.5);assert.equal(placed[1].ink[2],17.5);
 assert.equal(placed[2].ink[1],-32.5);assert.equal(placed[3].ink[1],-32.5);
 assert.equal(placed[4].ink[2],1.5);assert.equal(placed[5].ink[1],-41.5);
 assert.equal(placed[7].ink[2],89.5);
 assert.equal(verifyInkLabelGaps(placed).ok,true);
});
test('wrong actual gap and missing real tick anchor fail explicitly',()=>{
 assert.throws(()=>positionInkLabels([{id:0,role:'x-tick',ink:[0,1,3,-1]}]),/anchor/);
 const measured=[{id:0,role:'y-tick',plot:'a',ink:[0,2,19,-2],anchor:[20,0]}];
 assert.equal(verifyInkLabelGaps(measured).ok,false);
});
