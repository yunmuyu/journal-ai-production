import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../adobe/existing-export.jsx',import.meta.url),'utf8');
function environment(){
  const makePath=(anchors,overrides={})=>({
    closed:false,clipping:false,hidden:false,stroked:true,
    strokeWidth:2,strokeCap:'ROUNDENDCAP',strokeJoin:'ROUNDENDJOIN',strokeDashes:[3,2],
    pathPoints:anchors.map(anchor=>({anchor:anchor.slice()})),
    writes:[],setEntirePath(points){this.writes.push(points.map(point=>point.slice()));this.pathPoints=points.map(point=>({anchor:point.slice()}));},
    ...overrides
  });
  const paths=[
    makePath([[0,0],[10,10]]),
    makePath([[20,20],[30,30]]),
    makePath([[40,40],[50,50]])
  ];
  const context={JFW:{bounds(value){return Array.prototype.slice.call(value);}}};
  vm.runInNewContext(source,context);
  return {correct:context.JFW.correctExistingPaths,doc:{pathItems:paths},paths};
}

test('existing path correction validates every edit before writing any path',()=>{
  const {correct,doc,paths}=environment();
  assert.equal(typeof correct,'function','existing-export.jsx must expose correctExistingPaths');
  assert.throws(()=>correct(doc,[
    {index:0,expectedAnchors:[[0,0],[10,10]],points:[[1,1],[11,11]]},
    {index:1,expectedAnchors:[[20,20],[30.2,30]],points:[[21,21],[31,31]]}
  ]),/anchor/);
  assert.deepEqual(paths.map(path=>path.writes.length),[0,0,0], 'a bad later edit must leave earlier paths untouched');
});

test('existing path correction rejects duplicate indices and invalid target coordinates',()=>{
  const {correct,doc,paths}=environment();
  assert.throws(()=>correct(doc,[
    {index:0,expectedAnchors:[[0,0],[10,10]],points:[[1,1],[11,11]]},
    {index:0,expectedAnchors:[[0,0],[10,10]],points:[[2,2],[12,12]]}
  ]),/duplicate/i);
  assert.throws(()=>correct(doc,[
    {index:0,expectedAnchors:[[0,0],[10,10]],points:[[1,1],[Infinity,11]]}
  ]),/finite|coordinate/i);
  assert.deepEqual(paths.map(path=>path.writes.length),[0,0,0]);
});

test('existing path correction edits only selected open visible stroked paths and preserves appearance',()=>{
  const {correct,doc,paths}=environment();
  const appearance={strokeWidth:paths[1].strokeWidth,strokeCap:paths[1].strokeCap,strokeJoin:paths[1].strokeJoin,strokeDashes:paths[1].strokeDashes.slice()};
  const indices=correct(doc,[{index:1,expectedAnchors:[[20.04,20],[30,30]],points:[[21,22],[31,32],[33,34]]}]);
  assert.deepEqual(JSON.parse(JSON.stringify(indices)),[1]);
  assert.deepEqual(paths.map(path=>path.writes.length),[0,1,0]);
  assert.deepEqual(JSON.parse(JSON.stringify(paths[1].pathPoints.map(point=>point.anchor))),[[21,22],[31,32],[33,34]]);
  assert.equal(paths[1].pathPoints.length,3);
  assert.equal(paths[1].closed,false);
  assert.deepEqual({strokeWidth:paths[1].strokeWidth,strokeCap:paths[1].strokeCap,strokeJoin:paths[1].strokeJoin,strokeDashes:paths[1].strokeDashes},appearance);
});

test('existing path correction rejects invalid indices, hidden, closed, clipping and unstroked paths',()=>{
  const cases=[
    {index:-1,expectedAnchors:[],points:[[0,0],[1,1]]},
    {index:1.5,expectedAnchors:[],points:[[0,0],[1,1]]},
    {index:7,expectedAnchors:[],points:[[0,0],[1,1]]}
  ];
  for(const edit of cases){const {correct,doc}=environment();assert.throws(()=>correct(doc,[edit]));}
  for(const flag of ['hidden','closed','clipping','unstroked']){
    const {correct,doc,paths}=environment();
    if(flag==='unstroked')paths[0].stroked=false;else paths[0][flag]=true;
    assert.throws(()=>correct(doc,[{index:0,expectedAnchors:[[0,0],[10,10]],points:[[1,1],[11,11]]}]),/path|invalid/i);
    assert.equal(paths[0].writes.length,0);
  }
});
