import test from 'node:test';
import assert from 'node:assert/strict';
import {summarizeProduction} from './workbuddy-summary.mjs';
test('revisions and correction attempts count one main figure, stale paused task cannot eclipse newer output',()=>{
 const jobs=[{articleId:'a',figureNumber:'1',state:'paused',createdAt:'1',updatedAt:'9',attempt:2},{articleId:'a',figureId:'a-F1',state:'ready',createdAt:'2',attempt:1},{articleId:'b',figureNumber:'1',state:'needs_input',createdAt:'2',attempt:1},{kind:'inventory',state:'ready',attempt:1}];
 const s=summarizeProduction(jobs);assert.equal(s.figures,2);assert.equal(s.returned,1);assert.equal(s.paused,0);assert.equal(s.problems,1);assert.equal(s.tasks,4);assert.equal(s.attempts,5);assert.equal(s.pendingReview,null);assert.equal(s.userDecisions,null);
 const actual=summarizeProduction(jobs,[{articleId:'a',number:'1',pendingReview:false},{articleId:'b',number:'1',pendingReview:true},{articleId:'b',number:'1',pendingReview:true}]);assert.equal(actual.pendingReview,1);assert.equal(actual.userDecisions,0);
});
