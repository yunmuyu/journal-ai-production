import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../adobe/editorial-aggregate.jsx',import.meta.url),'utf8');
const pt=72/25.4;

function runLayout(figures,artboardCount=3){
  const board=[0,677.48,490.39,0];
  const production={name:'',groupItems:{add(){
    const group={name:'',_bounds:null,
      get visibleBounds(){return this._bounds.slice();},
      translate(dx,dy){this._bounds=[this._bounds[0]+dx,this._bounds[1]+dy,this._bounds[2]+dx,this._bounds[3]+dy];},
      pathItems:{rectangle(){return {move(){}};}}};
    return group;
  }},textFrames:{add(){return {contents:'',height:20,left:0,top:0,textRange:{characterAttributes:{}}};}}};
  const artboards=Array.from({length:artboardCount},()=>({artboardRect:board.slice()}));
  artboards.setActiveArtboardIndex=function(){};
  const template={textFrames:[],artboards,pageItems:[],layers:{add(){return production;}},activate(){},close(){},saveAs(){},exportFile(){}};
  const openFigure=(figure)=>{
    const b=[0,figure.height,figure.width,0];
    const root={parent:{typename:'Layer'},guides:false,visibleBounds:b,
      duplicate(){return {visibleBounds:b.slice(),move(group){group._bounds=b.slice();}};}};
    return {artboards:[{artboardRect:b}],visibleBounds:b,layers:[{pageItems:[root]}],close(){},activate(){}};
  };
  const context={
    JFW:{bounds(value){return Array.prototype.slice.call(value);},stringify(value){return JSON.stringify(value);},editorialFont(){return {}; }},
    File:function(path){this.path=path;},
    app:{open(file){return file.path==='template.ai'?template:openFigure(figures.find(f=>f.ai===file.path));}},
    DocumentColorSpace:{CMYK:'CMYK',RGB:'RGB'},SaveOptions:{DONOTSAVECHANGES:1},ElementPlacement:{PLACEATBEGINNING:1},
    RGBColor:function(){},IllustratorSaveOptions:function(){},PDFSaveOptions:function(){},
    ExportOptionsPNG24:function(){},ExportType:{PNG24:1}
  };
  vm.runInNewContext(source,context);
  const req={layout:'legacy',template:'template.ai',ai:'out.ai',pdf:'out.pdf',preview:'out.png',items:figures.map((figure,index)=>({ai:figure.ai,author:figure.author||'作者',number:index+1}))};
  const result=context.JFW.aggregateEditorial(req,()=>{});
  return JSON.parse(JSON.stringify(result.placements));
}

function assertBelow(upper,lower,gap=0.01){
  assert.ok(lower.bounds[1]<=upper.bounds[3]-gap,
    `${lower.name} top ${lower.bounds[1]} must be below ${upper.name} bottom ${upper.bounds[3]}`);
}

test('wide then two narrow figures share one page without overlapping the wide figure',()=>{
  const placements=runLayout([
    {ai:'wide.ai',width:300,height:150},
    {ai:'left.ai',width:150,height:350},
    {ai:'right.ai',width:150,height:150}
  ]);
  assert.equal(placements.length,3);
  assert.deepEqual(placements.map(p=>p.page),[1,1,1]);
  assert.deepEqual(placements.map(p=>p.column),['double',1,2]);
  assertBelow(placements[0],placements[1]);
  assertBelow(placements[0],placements[2]);
  assert.ok(placements[1].bounds[2]<placements[2].bounds[0], 'left and right column bounds must remain separate');
});

test('right column begins below a wide figure when the left column fills',()=>{
  const placements=runLayout([
    {ai:'wide.ai',width:300,height:150},
    {ai:'tall-left.ai',width:150,height:430},
    {ai:'right.ai',width:150,height:100}
  ]);
  assert.deepEqual(placements.map(p=>p.page),[1,1,1]);
  assert.deepEqual(placements.map(p=>p.column),['double',1,2]);
  assertBelow(placements[0],placements[2]);
});

test('narrow-only layout still fills left then right and starts a new page when both are full',()=>{
  const placements=runLayout([
    {ai:'one.ai',width:150,height:400},
    {ai:'two.ai',width:150,height:400},
    {ai:'three.ai',width:150,height:400}
  ]);
  assert.deepEqual(placements.map(p=>p.page),[1,1,2]);
  assert.deepEqual(placements.map(p=>p.column),[1,2,1]);
});

test('layout reports exhausted template artboards when another page is required',()=>{
  assert.throws(()=>runLayout([
    {ai:'one.ai',width:150,height:400},
    {ai:'two.ai',width:150,height:400},
    {ai:'three.ai',width:150,height:400}
  ],1),/Template empty artboards exhausted/);
});
