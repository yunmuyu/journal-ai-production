import test from 'node:test';import assert from 'node:assert/strict';import{readFileSync}from'node:fs';import vm from'node:vm';
test('CMYK white background does not inflate artwork export bounds',()=>{
 const source=readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');const fn=source.slice(source.indexOf('function artworkBounds('),source.indexOf('    app.userInteractionLevel='));const ctx={};vm.createContext(ctx);vm.runInContext(fn,ctx);
 const bg={filled:true,stroked:false,fillColor:{typename:'CMYKColor',cyan:0,magenta:0,yellow:0,black:0},visibleBounds:[0,100,200,0]};const line={filled:false,stroked:true,visibleBounds:[20,80,180,20]};assert.deepEqual(Array.from(ctx.artworkBounds({pathItems:[bg,line],textFrames:[]})),[20,80,180,20]);
});
test('Illustrator GrayColor uses zero for white and 100 for black ink',()=>{
 const source=readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');
 const fn=source.slice(source.indexOf('function artworkBounds('),source.indexOf('    app.userInteractionLevel='));
 const ctx={};vm.createContext(ctx);vm.runInContext(fn,ctx);
 const white={filled:true,stroked:false,fillColor:{typename:'GrayColor',gray:0},visibleBounds:[0,200,600,0]};
 const blackArrow={filled:true,stroked:false,fillColor:{typename:'GrayColor',gray:100},visibleBounds:[100,150,200,100]};
 assert.deepEqual(Array.from(ctx.artworkBounds({pathItems:[white,blackArrow],textFrames:[]})),[100,150,200,100]);
});
test('Mixed vector artwork retains visible embedded raster clipped by its group',()=>{
 const source=readFileSync(new URL('../adobe/illustrator.jsx',import.meta.url),'utf8');const fn=source.slice(source.indexOf('function artworkBounds('),source.indexOf('    app.userInteractionLevel='));const ctx={};vm.createContext(ctx);vm.runInContext(fn,ctx);
 const group={typename:'GroupItem',clipped:true,pathItems:[{clipping:true,geometricBounds:[10,90,190,10]}]};
 const image={visibleBounds:[0,100,200,0],parent:group};const hidden={hidden:true,visibleBounds:[-100,300,500,-200]};
 assert.deepEqual(Array.from(ctx.artworkBounds({pathItems:[],textFrames:[{visibleBounds:[30,60,70,40]}],rasterItems:[image,hidden],placedItems:[]})),[10,90,190,10]);
});
