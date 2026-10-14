import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const code=fs.readFileSync(new URL('../production-runtime/adobe/illustrator.jsx',import.meta.url),'utf8');
const helper=code.slice(code.indexOf('function normalizeFinalStrokes('),code.indexOf('function imageBackground('));
const fitStart=code.indexOf('var editorialFit={scale:1};');
const fit=code.slice(fitStart,code.indexOf("stage('snapshot')",fitStart));

test('final layout fit resets only real path strokes to 0.5 pt',()=>{
 const paths=[
  {stroked:true,guides:false,clipping:false,strokeWidth:9},
  {stroked:true,guides:true,clipping:false,strokeWidth:3},
  {stroked:true,guides:false,clipping:true,strokeWidth:4},
  {stroked:false,guides:false,clipping:false,filled:true,strokeWidth:7},
 ];
 const doc={pathItems:paths,artboards:[{artboardRect:[]}]};
 const ctx={doc,p:{route:'vector-reletter'},W:100,result:{},JFW:{fitEditorialArtwork:()=>{paths[0].strokeWidth=12;return {scale:2};}},artworkBounds:()=>[0,100,100,0]};
 vm.runInNewContext(`${helper}\n${fit}`,ctx);
 assert.deepEqual(paths.map(p=>p.strokeWidth),[0.5,3,4,7]);
 assert.equal(ctx.result.layoutFit.scale,2);
 assert.deepEqual(Array.from(doc.artboards[0].artboardRect),[-0.25,100.25,100.25,-0.25]);
});

test('image route bypasses stroke normalization',()=>{
 const path={stroked:true,guides:false,clipping:false,strokeWidth:9};
 const ctx={doc:{pathItems:[path]},p:{route:'image'},W:100,result:{},JFW:{fitEditorialArtwork:()=>{throw Error('image fit called');}},artworkBounds:()=>{throw Error('image bounds called');}};
 vm.runInNewContext(`${helper}\n${fit}`,ctx);
 assert.equal(path.strokeWidth,9);
});
