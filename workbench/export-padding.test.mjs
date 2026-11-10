import test from 'node:test';
import assert from 'node:assert/strict';
import {verifyExportPadding} from './processing-evidence.mjs';
function report(target=.25){return {export_padding_audit:{rescaled:false,measurement_dpi:1200,target_padding_pt:target,tolerance_pt:.065,pages:[{rescaled:false,protection_pt:target,measured_margins_pt:[target,target,target,target]}]}};}
test('default and explicit margins accepted without imposing a production minimum',()=>{assert.ok(verifyExportPadding({},report()));for(const target of [0,.1,.25,2,12])assert.ok(verifyExportPadding({policy:{export_crop_padding_pt:target}},report(target)));});
test('all four finite measured margins and precise audit are required',()=>{for(const value of [0,NaN,Infinity,-.1,.32]){const r=report();r.export_padding_audit.pages[0].measured_margins_pt[3]=value;assert.equal(verifyExportPadding({},r),false);}for(const key of ['measurement_dpi','tolerance_pt','target_padding_pt','rescaled']){const r=report();delete r.export_padding_audit[key];assert.equal(verifyExportPadding({},r),false);}assert.equal(verifyExportPadding({},{}),false);assert.equal(verifyExportPadding({policy:{export_crop_padding_pt:2}},report()),false);});

test('invalid explicit values never become the default',()=>{for(const value of [null,true,false,'0.25',NaN,Infinity,-1,13])assert.equal(verifyExportPadding({policy:{export_crop_padding_pt:value}},report()),false);});

test('invalid specs and policy containers are not treated as default requests',()=>{for(const spec of [undefined,null,false,true,0,1,'',[],{policy:null},{policy:[]},{policy:false}])assert.equal(verifyExportPadding(spec,report()),false);});

test('diagnostic requests and invalid diagnostic flags cannot enter production',()=>{for(const diagnostic_only of [true,null,0,'false',[]])assert.equal(verifyExportPadding({policy:{diagnostic_only}},report()),false);assert.equal(verifyExportPadding({policy:{diagnostic_only:false}},report()),true);});
