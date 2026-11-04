import test from 'node:test';
import assert from 'node:assert/strict';
import {validateColorPlan,resolveColorPolicy} from '../lib/color-policy.mjs';

test('current production rejects source-color even when an old approval ID is supplied',()=>{
 assert.throws(()=>validateColorPlan({colorPolicy:'source-color',colorApprovalId:'old-approved'}),/灰度/);
 assert.throws(()=>validateColorPlan({grayscale:false}),/灰度/);
 assert.equal(resolveColorPolicy({},'a'.repeat(64)).mode,'grayscale');
});
