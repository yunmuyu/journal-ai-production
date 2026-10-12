import fs from 'node:fs';import vm from 'node:vm';import test from 'node:test';import assert from 'node:assert/strict';
const context={JFW:{}};vm.runInNewContext(fs.readFileSync(new URL('../adobe/editorial-connectors.jsx',import.meta.url),'utf8'),context);const {JFW}=context;
for(const scale of [1,.7797285183])for(const direction of [[1,0],[-1,0],[0,1],[0,-1]])test(`Arrow 5 preserves 3mm shaft after scale ${scale}, direction ${direction}`,()=>{
 const items=[],layer={pathItems:{add(){const p={setEntirePath(a){this.points=a;}};items.push(p);return p;}}},gap=JFW.arrow5BoundaryGap(3,scale),points=[[0,0],[direction[0]*gap,direction[1]*gap]],original=JSON.stringify(points);
 const [shaft,head]=JFW.drawArrow5(layer,'edge',points,{},.5);assert.equal(JSON.stringify(points),original);assert.equal(items.length,2);assert.equal(head.points.length,4);assert.equal(head.closed,true);assert.equal(head.stroked,false);
 const end=shaft.points[1];assert.ok(Math.abs(Math.hypot(...end)*scale*25.4/72-3)<1e-9);
 const wing0=head.points[0],wing1=head.points[2],tip=head.points[3],notch=head.points[1],base=[(wing0[0]+wing1[0])/2,(wing0[1]+wing1[1])/2];
 assert.ok(Math.abs(Math.hypot(wing0[0]-wing1[0],wing0[1]-wing1[1])-3.7)<1e-9);assert.ok(Math.abs(Math.hypot(tip[0]-base[0],tip[1]-base[1])-4.4)<1e-9);assert.ok(Math.abs(Math.hypot(notch[0]-base[0],notch[1]-base[1])-.8)<1e-9);
});
