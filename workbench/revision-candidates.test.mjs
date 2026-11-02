import test from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import {activateRevision} from './revision-candidates.mjs';

test('multiple unaccepted revisions keep the original entry and preserve feedback',()=>{
 const original=[{number:'1',file:{path:path.resolve('original.pdf')}}],feedback={text:'用户意见',revision:2};
 const figure={id:'F1',author:'测试',number:'1',outputs:original,feedback};
 const context={rows:[figure],metadata:{},pending:{},link:url=>({path:fileURLToPath(url)})};
 for(const n of [1,2])activateRevision(context,{figureId:'F1',feedbackRevision:2,result:{summary:'修订',outputs:[{number:'1',path:path.resolve(`candidate-${n}.pdf`),sha256:String(n),preview:path.resolve(`preview-${n}.png`)}]}});
 assert.equal(figure.previousOutputs,original);assert.equal(figure.revisionHistory.length,2);
 assert.equal(figure.feedback,feedback);assert.equal(figure.outputs[0].file.path,path.resolve('candidate-2.pdf'));
 assert.equal(context.pending['测试-1'].addressedFeedbackRevision,2);
 assert.equal(figure.status,undefined); // Candidate activation must not grant acceptance.
});
