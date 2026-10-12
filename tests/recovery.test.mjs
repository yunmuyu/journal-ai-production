import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,existsSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {recoverJob,processAlive} from '../lib/recovery.mjs';
import {safeSegment} from '../lib/review.mjs';
test('Windows delivery names cannot become device names or paths',()=>{for(const value of ['CON','nul.txt','COM1','LPT9.pdf'])assert.ok(safeSegment(value).startsWith('_'));assert.equal(safeSegment('../a:b'),'.._a_b');assert.equal(safeSegment('name. '),'name');});
test('Recovery requires observation and cannot unlock a live owner',()=>{const root=mkdtempSync(path.join(tmpdir(),'jfw-recovery-'));try{writeFileSync(path.join(root,'.lock'),JSON.stringify({pid:process.pid}));assert.throws(()=>recoverJob(root),/Inspect/);assert.throws(()=>recoverJob(root,{verifiedIdle:true,adobeLock:path.join(root,'test-adobe.lock')}));assert.ok(existsSync(path.join(root,'.lock')));assert.equal(processAlive(process.pid),true);}finally{rmSync(root,{recursive:true});}});
test('Recovery preserves source and marks an interrupted rendering',()=>{const root=mkdtempSync(path.join(tmpdir(),'jfw-recovery-'));try{writeFileSync(path.join(root,'source.txt'),'original');writeFileSync(path.join(root,'job.json'),JSON.stringify({figures:[{id:'f1',status:'rendering'}]}));writeFileSync(path.join(root,'.lock'),JSON.stringify({pid:0}));const result=recoverJob(root,{verifiedIdle:true,adobeLock:path.join(root,'test-adobe.lock')});assert.equal(result.sourceFilesDeleted,false);assert.equal(readFileSync(path.join(root,'source.txt'),'utf8'),'original');assert.equal(JSON.parse(readFileSync(path.join(root,'job.json'),'utf8')).figures[0].status,'interrupted');assert.equal(existsSync(path.join(root,'.lock')),false);}finally{rmSync(root,{recursive:true});}});
test('A reused Windows PID does not keep a lease older than that process alive',{skip:process.platform!=='win32'},()=>{
 assert.equal(processAlive(process.pid,'2000-01-01T00:00:00.000Z'),false);
 assert.equal(processAlive(process.pid,new Date().toISOString()),true);
 assert.equal(processAlive(process.pid,'invalid'),true);
});
