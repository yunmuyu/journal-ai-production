import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyOperation} from './processing-evidence.mjs';

function fixture(){
 const sha='a'.repeat(64),geometry='b'.repeat(64);
 const panel={kind:'chart',source:'original.svg',series:[],legend_review:{present:false,source_sha256:sha,reason:'Original has no legend'}};
 const spec={kind:'chart',panels:[structuredClone(panel),structuredClone(panel)]};
 const report={layout:{texts:[],layout_evidence:{chart_panels:[]}},assets:[]};
 for(let i=1;i<=2;i++){
  const prefix=`panel-${i}:`;
  report.layout.layout_evidence.chart_panels.push({prefix,source:'original.svg'});
  report.layout.texts.push({id:prefix+'tick',role:'axis-tick',text:'1'});
  report.assets.push({id:prefix+'plot',source_hash:sha,mode:'svg-vector-preserve',geometry_before:geometry,geometry_after:geometry});
 }
 return {sha,spec,report};
}

test('each complete chart panel must independently preserve original data',()=>{
 const {sha,spec,report}=fixture();
 assert.doesNotThrow(()=>verifyOperation({operation:'chart-redraw'},spec,report,sha));
 const invalid=structuredClone(report);invalid.assets[1].geometry_after='c'.repeat(64);
 assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,invalid,sha),/保留/);
});

test('unbound or missing panel output cannot be smuggled into a composite',()=>{
 const {sha,spec,report}=fixture();
 const invalid=structuredClone(report);invalid.layout.texts.push({id:'orphan',role:'axis-tick',text:'99'});
 assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,invalid,sha));
 const missing=structuredClone(report);missing.assets.pop();
 assert.throws(()=>verifyOperation({operation:'chart-redraw'},spec,missing,sha));
});
