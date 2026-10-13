import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
for(const location of ['adobe','production-runtime/adobe'])for(const side of ['left','right','top','bottom'])test(`${location} ${side} brace preserves curved terminals and a centered cusp`,()=>{
 const ctx={JFW:{},PointType:{CORNER:'corner'}};vm.createContext(ctx);vm.runInContext(fs.readFileSync(location+'/editorial-generator.jsx','utf8'),ctx);
 const p={setEntirePath(points){this.pathPoints=points.map(anchor=>({anchor,leftDirection:anchor,rightDirection:anchor}));}},all=[];
 ctx.JFW.drawEditorialBrace({id:'brace',left:10,right:30,top:90,bottom:20,braceSide:side},{pathItems:{add:()=>p}},'black',all,.5);
 assert.equal(p.pathPoints.length,7);assert.equal(all[0],p);assert.equal(p.closed,false);assert.equal(p.strokeWidth,.5);
 assert.ok(p.pathPoints.some(q=>JSON.stringify(q.anchor)!==JSON.stringify(q.leftDirection)),'must have curve handles');
 for(const q of p.pathPoints)for(const point of [q.anchor,q.leftDirection,q.rightDirection]){assert.ok(point[0]>=10&&point[0]<=30);assert.ok(point[1]>=20&&point[1]<=90);}
 const cusp=p.pathPoints[3].anchor;assert.ok(side==='left'||side==='right'?Math.abs(cusp[1]-55)<.2:Math.abs(cusp[0]-20)<.1);
});
