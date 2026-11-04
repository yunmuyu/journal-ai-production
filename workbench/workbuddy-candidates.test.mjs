import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {activateWorkBuddy} from './workbuddy-candidates.mjs';

function fixture({method='raster-preserve',kind,extension='jpg'}={}){
 const article={id:'paper',author:'author',figures:[]},context={articles:[article],rows:[],metadata:{},link:url=>({url:String(url)})};
 const job={articleId:'paper',mainNumbers:['3'],figureNumber:'3',group:'screenshots',kind,productionRoute:{method}};
 const result={summary:'截图正文1.2—1.4pt，宽度95.79',evidence:'原始执行核验报告',outputs:[{number:'3',path:path.resolve('candidate.'+extension),preview:path.resolve('preview.png'),sha256:'fixture',fontLabel:'错误的位图字号',columnLabel:'单栏约100%'}]};
 return {context,job,result};
}

test('raster candidate uses structured pending-review notice while original report and blank JPG font label are preserved',()=>{
 const {context,job,result}=fixture(),before=structuredClone(result);activateWorkBuddy(context,job,result);
 assert.equal(context.rows[0].notices[0].text,'JPG 候选已回传，待终审。');assert.doesNotMatch(JSON.stringify(context.rows[0].notices),/1.2|95.79|正文/);
 assert.equal(context.metadata[result.outputs[0].path].fontLabel,'');assert.equal(context.rows[0].status,'待终检');assert.deepEqual(result,before);
});

test('editable PDF and revision notices retain existing behavior',()=>{
 for(const options of [{method:'editable-pdf',extension:'pdf'},{kind:'revision'}]){
  const {context,job,result}=fixture(options);activateWorkBuddy(context,job,result);assert.equal(context.rows[0].notices[0].text,result.summary);
 }
});
