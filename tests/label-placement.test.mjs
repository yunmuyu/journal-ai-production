import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const scope={};vm.runInNewContext(readFileSync(new URL('../adobe/label-placement.jsx',import.meta.url),'utf8'),scope);
const solve=input=>JSON.parse(JSON.stringify(scope.JFWLabelPlacement.solve(input)));
const path=(index,vertices,extra={})=>({index,closed:true,stroked:true,strokeWidthPt:.5,points:vertices.map(([x,y])=>[[x,y,x,y],[x,y]]),...extra});
const box=(index,l,t,r,b,extra={})=>path(index,[[l,t],[r,t],[r,b],[l,b]],extra);
const label=(inkBounds,extra={})=>({id:'label',inkBounds,ownerPathIndex:0,placements:['inside','left','right','above','below'],clearancePt:1.5,maxDistancePt:8,allowFrameExpansionPt:0,...extra});
const run=(paths,labels,extra={})=>solve({paths,labels,fixedTexts:[],artboard:[-30,60,100,-30],...extra});
test('large filled owner surface accepts centered text without treating fill as an obstacle',()=>{
 const r=run([box(0,0,30,40,0,{filled:true})],[label([2,9,22,1])]);assert.equal(r.ok,true);assert.equal(r.placements[0].placement,'inside');assert.equal(r.placements[0].dx,8);assert.equal(r.placements[0].dy,10);
});
test('a slanted narrow face cannot contain a label merely because its bounding box can',()=>{
 const r=run([path(0,[[0,30],[20,40],[20,10],[0,0]])],[label([0,0,17,-25],{placements:['inside']})]);assert.equal(r.ok,false);assert.equal(r.placements.length,0);
});
test('exterior label avoids a connector and a filled arrowhead',()=>{
 const paths=[box(0,0,20,10,0),path(1,[[5,20],[5,45]],{closed:false}),path(2,[[12,40],[35,10],[12,-20]],{filled:true,stroked:false})];
 const r=run(paths,[label([0,0,18,-8],{placements:['above','right','left']})]);assert.equal(r.ok,true);assert.notEqual(r.placements[0].placement,'above');assert.notEqual(r.placements[0].placement,'right');
});
test('fixed and already placed text are obstacles and decisions are deterministic',()=>{
 const input={paths:[box(0,0,20,20,0)],labels:[label([0,0,10,-5],{placements:['inside']}),label([0,0,10,-5],{id:'second',placements:['inside']})],fixedTexts:[{inkBounds:[3,17,17,12]}],artboard:[-30,60,100,-30]};
 const a=solve(input),b=solve(input);assert.deepEqual(a,b);assert.equal(a.ok,false);assert.equal(a.issues.length>0,true);
});
test('external candidates remain nearby and fail rather than escaping artboard',()=>{
 const r=run([box(0,0,20,10,0)],[label([0,0,20,-10],{placements:['left'],maxDistancePt:1})],{artboard:[0,20,10,0]});assert.equal(r.ok,false);
});
test('curved boundary bowed into a label rejects inside placement',()=>{
 const p=box(0,0,30,30,0);p.points[0][1]=[10,0];p.points[1][0][2]=20;p.points[1][0][3]=0;
 const r=run([p],[label([0,0,20,-16],{placements:['inside']})]);assert.equal(r.ok,false);
});
test('explicit dashed rectangular frame can expand just enough and records its control points',()=>{
 const p=box(0,0,10,10,0,{strokeDashes:[3,2]});const r=run([p],[label([0,0,12,-8],{placements:['inside'],allowFrameExpansionPt:6})]);assert.equal(r.ok,true);assert.equal(r.frameEdits.length,1);assert.deepEqual(r.frameEdits[0].beforePoints,p.points);assert.equal(r.frameEdits[0].pathIndex,0);
});
test('solid, overflowing, or obstructed frame never expands',()=>{
 const l=label([0,0,12,-8],{placements:['inside'],allowFrameExpansionPt:3});
 assert.equal(run([box(0,0,10,10,0)],[l]).ok,false);
 assert.equal(run([box(0,0,10,10,0,{strokeDashes:[3,2]})],[l],{artboard:[0,10,10,0]}).ok,false);
 assert.equal(run([box(0,0,10,10,0,{strokeDashes:[3,2]}),path(1,[[-1,20],[-1,-10]],{closed:false})],[l]).ok,false);
});
test('solver preserves input and accepts premeasured rotated or mixed style ink without typography changes',()=>{
 const input={paths:[box(7,0,40,20,0)],labels:[label([2,32,9,6],{id:'rotated-mixed',ownerPathIndex:7,placements:['inside']})],fixedTexts:[],artboard:[-30,60,100,-30]};
 const before=JSON.stringify(input),r=solve(input);assert.equal(r.ok,true);assert.equal(JSON.stringify(input),before);assert.equal(r.placements[0].inkBounds[2]-r.placements[0].inkBounds[0],7);assert.equal(r.placements[0].inkBounds[1]-r.placements[0].inkBounds[3],26);
});
test('explicit path identity is required and unresolved owners are not guessed from proximity',()=>{
 const r=run([box(8,0,20,20,0)],[label([0,0,8,-5])]);assert.equal(r.ok,false);assert.equal(r.issues[0].type,'missing_closed_owner');
});
test('containing filled backgrounds and duplicated owner faces contribute edges, not full fill exclusion',()=>{
 const owner=box(0,0,20,30,0,{filled:true});
 for(const background of [box(1,-10,40,50,-20,{filled:true}),box(1,0,20,30,0,{filled:true})]) {
  const r=run([owner,background],[label([0,0,12,-6],{placements:['inside']})]);assert.equal(r.ok,true);
 }
});
test('successive expansion is limited relative to the original frame, and cannot cross an earlier label',()=>{
 const frame=box(0,0,10,10,0,{strokeDashes:[3,2]});
 const first=label([0,0,12,-8],{placements:['inside'],allowFrameExpansionPt:6});
 const second=label([0,0,16,-8],{id:'second',placements:['inside'],allowFrameExpansionPt:6});
 const accumulated=run([frame],[first,second]);assert.equal(accumulated.ok,false);assert.equal(accumulated.frameEdits.length,1);
 const outside=label([0,0,6,-5],{placements:['left']});
 const expand=label([0,0,14,-5],{id:'expand',placements:['inside'],allowFrameExpansionPt:5});
 const crossing=run([frame],[outside,expand]);assert.equal(crossing.ok,false);assert.equal(crossing.frameEdits.length,0);
});
test('bounded measured rotation variants fit a narrow tall face at unchanged text dimensions',()=>{
 const ink=[-10,4,10,-4],rotated=[-4,10,4,-10],owner=box(0,0,30,18,0);
 const plain=label(ink,{placements:['inside']});assert.equal(run([owner],[plain]).ok,false);
 const variant=label(ink,{placements:['inside'],variants:[{rotation:0,inkBounds:ink},{rotation:-90,inkBounds:rotated},{rotation:90,inkBounds:rotated}]});
 const r=run([owner],[variant]);assert.equal(r.ok,true);assert.equal(r.placements[0].rotation,-90);assert.equal(r.placements[0].inkBounds[2]-r.placements[0].inkBounds[0],8);assert.equal(r.placements[0].inkBounds[1]-r.placements[0].inkBounds[3],20);assert.equal(r.placements[0].dx,9);assert.equal(r.placements[0].dy,15);
 const noVariants=run([box(0,0,30,30,0)],[plain]);assert.equal('rotation' in noVariants.placements[0],false);
});
test('a placed or raster image footprint remains a solid obstacle even when it contains the owner',()=>{
 const r=run([box(0,0,20,30,0),box(1,-10,40,50,-20,{filled:true,solidObstacle:true})],[label([0,0,12,-6],{placements:['inside']})]);assert.equal(r.ok,false);
});
test('a fully covering opaque foreground face hides only the rear obstacle at the protected text region',()=>{
 const owner=box(0,0,30,30,0),rear=path(1,[[15,5],[15,25]],{closed:false,paintOrder:3}),face=box(2,0,30,30,0,{filled:true,stroked:false,paintOrder:2,opaqueFill:true});
 assert.equal(run([owner,rear,face],[label([0,0,12,-6],{placements:['inside']})]).ok,true);
 const stackRear={...rear,paintOrder:undefined,paintStack:[0,3]},stackFace={...face,paintOrder:undefined,paintStack:[0,2]};
 assert.equal(run([owner,stackRear,stackFace],[label([0,0,12,-6],{placements:['inside']})]).ok,true);
});
test('a foreground line is never hidden by a face behind it',()=>{
 const owner=box(0,0,30,30,0),line=path(1,[[15,0],[15,30]],{closed:false,paintOrder:1}),face=box(2,0,30,30,0,{filled:true,stroked:false,paintOrder:2,opaqueFill:true});
 assert.equal(run([owner,line,face],[label([0,0,12,-6],{placements:['inside']})]).ok,false);
});
test('transparent, orderless, or partially covering faces cannot excuse a blocking line',()=>{
 const owner=box(0,0,30,30,0),rear=path(1,[[15,0],[15,30]],{closed:false,paintOrder:3});
 for(const face of [box(2,2,28,28,2,{filled:true,stroked:false,paintOrder:2,opaqueFill:false}),box(2,2,28,28,2,{filled:true,stroked:false,opaqueFill:true}),box(2,10,20,20,10,{filled:true,stroked:false,paintOrder:2,opaqueFill:true})])assert.equal(run([owner,rear,face],[label([0,0,12,-6],{placements:['inside']})]).ok,false);
});

test('inside placement reserves editorial padding before export and scales it with typography',()=>{
 const p=box(0,0,20,20,0),large=label([0,0,12,-6],{placements:['inside'],fontSize:8});
 assert.equal(run([p],[large]).ok,false);
 assert.equal(run([p],[{...large,fontSize:6}]).ok,true);
});
