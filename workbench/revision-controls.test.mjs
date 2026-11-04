import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('saved new feedback enables revision without blurring or replacing textarea',()=>{
 const figure={id:'F1',status:'终检通过'},wrapper={outerHTML:''};
 const context={e:String,find:()=>figure,document:{addEventListener(){},querySelector:()=>({closest:()=>wrapper})}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(new URL('./revision-controls.js',import.meta.url),'utf8'),context);
 context.syncRevisionControl('F1');assert.match(wrapper.outerHTML,/disabled/);
 figure.status='异常';context.syncRevisionControl('F1');assert.doesNotMatch(wrapper.outerHTML,/disabled/);
 figure.revisionJob={state:'running',message:'执行中'};context.syncRevisionControl('F1');assert.match(wrapper.outerHTML,/disabled/);
});
