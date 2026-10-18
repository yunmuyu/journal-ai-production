import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
const runtime=new URL('../production-runtime/',import.meta.url);
test('image export passes an exact fractional width to Photoshop',()=>{
 const code=fs.readFileSync(new URL('lib/render.mjs',runtime),'utf8');
 const branch=code.slice(code.indexOf("  if(p.route==='image'){"),code.indexOf('  for(const file of [ai,output,preview])'));
 let request;const ctx={p:{route:'image',widthMm:79.9},directory:'fixture',preview:'preview.png',heightMm:40,path,adobe:(app,req)=>{request=req;return {widthMm:79.9,heightMm:40,heightPx:472};}};
 vm.runInNewContext(branch,ctx);assert.equal(request.widthMm,79.9);
});
test('Photoshop numeric width uses 300 dpi without an action preset',()=>{
 const code=fs.readFileSync(new URL('adobe/photoshop.jsx',runtime),'utf8');const branch=code.slice(code.indexOf('var presetWidths='),code.indexOf("if(req.format==='jpg')"));let resize;
 const ctx={req:{widthMm:79.9,grayscale:false},doc:{mode:'RGB',resizeImage:(...args)=>resize=args},UnitValue:function(n,unit){return {n,unit};},DocumentMode:{GRAYSCALE:'GRAY'},ResampleMethod:{BICUBIC:'bicubic'}};
 vm.runInNewContext(branch,ctx);assert.equal(resize?.[0].n,79.9);assert.equal(resize[2],300);
});
test('source-artboard overlays retain the full source coordinate frame',()=>{
 const code=fs.readFileSync(new URL('adobe/illustrator.jsx',runtime),'utf8');const begin=code.indexOf('doc=app.open(new File(req.input));if(p.grayscale');const branch=code.slice(begin,code.indexOf('if(p.strokeWidthPt',begin));
 const doc={artboards:[{artboardRect:[0,432,720,0]}]},frames=[];const ctx={p:{normalizeWidth:true,overlayFrame:'source-artboard',texts:[{x:.5,y:.1}]},req:{input:'source.pdf'},W:226.5,File:function(p){return p;},app:{open:()=>doc},stage:()=>{},snapshot:()=>({}),artworkBounds:()=>[48,405,709,42],normalizeVector:(w,b)=>{frames.push(Array.from(b));doc.artboards[0].artboardRect=[0,0,w,-432*w/720];return w/720;}};
 vm.runInNewContext(branch,ctx);assert.equal(frames.length,2);assert.deepEqual(frames[0],[0,432,720,0]);assert.deepEqual(frames[1],[0,0,720,-432]);assert.equal(ctx.vectorScale,226.5/720);assert.deepEqual(Array.from(doc.artboards[0].artboardRect),[0,0,226.5,-432*226.5/720]);
});
