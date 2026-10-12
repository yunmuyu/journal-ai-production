import test from'node:test';import assert from'node:assert/strict';import{readFileSync}from'node:fs';import vm from'node:vm';
const code=readFileSync(new URL('../adobe/vector-labels.jsx',import.meta.url),'utf8');
test('unequal grouped vector lines center independently and retain the block leading',()=>{
 const targets=[],refs=[{contents:'GhostBottleneck',geometricBounds:[10,30,70,10],remove(){}}];
 refs.add=()=>{const target={textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate(){return{createOutline:()=>({visibleBounds:[0,8,this.contents.length*4,0],remove(){}})};},translate(x,y){this.move=[x,y];}};targets.push(target);return target;};
 runtime().reletterGroups({textFrames:refs},[{indices:[0],expected:['GhostBottleneck'],text:'Ghost\rBottleneck',align:'center'}]);
 assert.deepEqual(targets.map(t=>t.contents),['Ghost','Bottleneck']);
 assert.deepEqual(targets.map(t=>t.move[0]+t.contents.length*2),[40,40]);
 assert.ok(Math.abs(targets[0].move[1]-targets[1].move[1]-9.6)<1e-9);
 assert.equal(targets.every(t=>t.textRange.characterAttributes.size===8),true);
});
function runtime(){const ctx={app:{textFonts:{getByName:name=>({name})}},JFW:{editorialFont:()=>({name:'composite'})},Justification:{CENTER:'center'},RGBColor:function(){this.typename='RGBColor';}};vm.createContext(ctx);vm.runInContext(code,ctx);return ctx.JFW;}
test('a native variable label uses explicit italic font before measuring ink',()=>{
 const target={textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate(){return{createOutline:()=>{assert.equal(this.textRange.characterAttributes.textFont.name,'TimesNewRomanPS-ItalicMT');return{visibleBounds:[0,8,5,0],remove(){}};}};},translate(){}};
 const refs=[{contents:'X',geometricBounds:[0,10,10,0],duplicate(){return target;},remove(){}}];
 runtime().reletterGroups({textFrames:refs},[{indices:[0],expected:['X'],text:'X',font:'TimesNewRomanPS-ItalicMT'}]);
 assert.equal(target.contents,'X');
});
test('invalid font in a later group fails before any mutation',()=>{
 let changes=0;const refs=[{contents:'X',duplicate(){changes++;}},{contents:'y'}];
 assert.throws(()=>runtime().reletterGroups({textFrames:refs},[{indices:[0],expected:['X'],text:'X'},{indices:[1],expected:['y'],text:'y',font:'Unknown'}]),/group font/);
 assert.equal(changes,0);
});
test('explicit rotation replaces a rotated source with fresh text instead of accumulating transforms',()=>{
 const rotations=[],target={textRange:{characterAttributes:{},paragraphAttributes:{}},rotate(a){rotations.push(a);},duplicate(){return{createOutline:()=>({visibleBounds:[0,20,8,0],remove(){}})};},translate(){}};
 const refs=[{contents:'Concat',geometricBounds:[0,20,8,0],duplicate(){throw Error('Must not inherit source rotation');},remove(){}}];refs.add=()=>target;
 runtime().reletterGroups({textFrames:refs},[{indices:[0],expected:['Concat'],text:'Concat',rotation:-90}]);
 assert.deepEqual(rotations,[-90]);
});
test('A later mismatched fragment prevents all document mutations',()=>{let count=0;const doc={textFrames:[{contents:'软',duplicate(){count++;}},{contents:'件'}]};assert.throws(()=>runtime().reletterGroups(doc,[{indices:[0],expected:['软'],text:'软'},{indices:[1],expected:['错'],text:'件'}]),/identity mismatch/);assert.equal(count,0);});
test('Duplicate fragment ownership is rejected before mutation',()=>{const doc={textFrames:[{contents:'软'}]};assert.throws(()=>runtime().reletterGroups(doc,[{indices:[0,0],expected:['软','软'],text:'软软'}]),/duplicate/);});
test('Fragments join into editable composite text at their shared visual center',()=>{const removed=[],moves=[];let outlineRemoved=false;const target={textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate:()=>({createOutline:()=>({visibleBounds:[0,8,20,0],remove(){outlineRemoved=true;}})}),translate:(x,y)=>moves.push([x,y])};const refs=[{contents:'软件',geometricBounds:[10,20,30,10],remove:()=>removed.push(0)},{contents:'23级',geometricBounds:[30,20,50,10],remove:()=>removed.push(1)}];refs.add=()=>target;runtime().reletterGroups({textFrames:refs},[{indices:[0,1],expected:['软件','23级'],text:'软件23级'}]);assert.equal(target.contents,'软件23级');assert.equal(target.textRange.paragraphAttributes.justification,'center');assert.equal(target.textRange.characterAttributes.size,8);assert.equal(target.textRange.characterAttributes.textFont.name,'composite');assert.deepEqual(moves,[[20,11]]);assert.deepEqual(removed,[1,0]);assert.equal(outlineRemoved,true);});
test('Grayscale preserves different luminances and leaves coordinates alone',()=>{const points=[[1,2],[3,4]],items=[{filled:true,stroked:false,fillColor:{typename:'RGBColor',red:255,green:0,blue:0},points},{filled:true,stroked:false,fillColor:{typename:'RGBColor',red:0,green:0,blue:255},points}];runtime().grayscaleArtwork({pathItems:items});assert.equal(items[0].fillColor.red,76.24499999999999);assert.equal(items[0].fillColor.red,items[0].fillColor.green);assert.ok(items[0].fillColor.red>items[1].fillColor.red);assert.equal(items[0].points,points);});
test('Non-finite label offsets fail before document mutation',()=>{assert.throws(()=>runtime().reletterGroups({textFrames:[{contents:'标签'}]},[{indices:[0],expected:['标签'],text:'标签',offsetPt:[0,NaN]}]),/offset/);});
for(const size of [6,7])test('Grouped vector labels honor whole-figure '+size+'pt before measuring',()=>{
 const attrs={},target={textRange:{characterAttributes:attrs,paragraphAttributes:{}},duplicate:()=>({createOutline:()=>{assert.equal(attrs.size,size);return{visibleBounds:[0,8,20,0],remove(){}};}}),translate(){}};
 const refs=[{contents:'软',geometricBounds:[0,10,10,0],remove(){}},{contents:'件',geometricBounds:[10,10,20,0],remove(){}}];refs.add=()=>target;
 runtime().reletterGroups({textFrames:refs},[{indices:[0,1],expected:['软','件'],text:'软件'}],size);
 assert.equal(attrs.size,size);assert.equal(attrs.leading,size===6?7:8.4);
});
test('Editorial text moves above artwork without skipping live collection entries',()=>{
 const moved=[],live=[],layer={name:''};
 for(let i=0;i<3;i++)live.push({contents:'标签'+i,geometricBounds:[i,10,i+3,2],move(parent,placement){assert.equal(parent,layer);assert.equal(placement,'end');moved.push(this.contents);live.splice(live.indexOf(this),1);}});
 const doc={textFrames:live,layers:{0:layer,add:()=>layer}};
 const ctx={JFW:{},ElementPlacement:{PLACEATEND:'end'}};vm.createContext(ctx);vm.runInContext(code,ctx);
 const result=ctx.JFW.raiseEditorialText(doc);
 assert.deepEqual(moved,['标签0','标签1','标签2']);assert.equal(result.topmost,true);assert.equal(result.textCount,3);assert.equal(layer.name,'期刊文字');
});
for(const [align,dx]of [['left',10],['right',30]])test('Ink '+align+' edge aligns to fragment bounds after font replacement',()=>{const moves=[],target={textRange:{characterAttributes:{},paragraphAttributes:{}},duplicate:()=>({createOutline:()=>({visibleBounds:[0,8,20,0],remove(){}})}),translate:(x,y)=>moves.push([x,y])};const refs=[{contents:'a',geometricBounds:[10,20,30,10],remove(){}},{contents:'b',geometricBounds:[30,20,50,10],remove(){}}];refs.add=()=>target;runtime().reletterGroups({textFrames:refs},[{indices:[0,1],expected:['a','b'],text:'ab',align}]);assert.deepEqual(moves,[[dx,11]]);});
test('Invalid label alignment is rejected before mutations',()=>{let changes=0;assert.throws(()=>runtime().reletterGroups({textFrames:[{contents:'a',duplicate(){changes++;}}]},[{indices:[0],expected:['a'],text:'a',align:'diagonal'}]),/alignment/);assert.equal(changes,0);});
test('Invalid later rotation rejects the batch before any document mutation',()=>{let changes=0;const refs=[{contents:'MCC',geometricBounds:[0,10,20,0],duplicate(){changes++;},remove(){changes++;}},{contents:'MCC2',geometricBounds:[0,10,20,0],duplicate(){changes++;},remove(){changes++;}}];assert.throws(()=>runtime().reletterGroups({textFrames:refs},[{indices:[0],expected:['MCC'],text:'MCC',rotation:90},{indices:[1],expected:['MCC2'],text:'MCC2',rotation:45}]),/rotation/);assert.equal(changes,0);});
test('Rotated label uses its rotated ink bounds for centering',()=>{const events=[],target={textRange:{characterAttributes:{},paragraphAttributes:{}},rotate(degrees){events.push(['rotate',degrees]);},duplicate(){return{createOutline(){events.push(['outline']);return{visibleBounds:[6,14,14,-6],remove(){}};}};},translate(x,y){events.push(['translate',x,y]);}},ref={contents:'MCC',geometricBounds:[0,10,20,0],duplicate(){return target;},remove(){}};const frames=[ref];frames.add=()=>target;runtime().reletterGroups({textFrames:frames},[{indices:[0],expected:['MCC'],text:'MCC',rotation:90}]);assert.deepEqual(events,[['rotate',90],['outline'],['translate',0,1]]);});
for(const rotation of [-90,0,90])test('Explicit label rotation '+rotation+' is supported',()=>{const target={textRange:{characterAttributes:{},paragraphAttributes:{}},rotate(){},duplicate(){return{createOutline:()=>({visibleBounds:[0,8,20,0],remove(){}})};},translate(){}},ref={contents:'MCC',geometricBounds:[0,10,20,0],duplicate(){return target;},remove(){}};const frames=[ref];frames.add=()=>target;runtime().reletterGroups({textFrames:frames},[{indices:[0],expected:['MCC'],text:'MCC',rotation}]);});
test('Labels without rotation keep the existing horizontal behavior',()=>{const events=[],target={textRange:{characterAttributes:{},paragraphAttributes:{}},rotate(){events.push('rotate');},duplicate(){events.push('outline');return{createOutline:()=>({visibleBounds:[0,8,20,0],remove(){}})};},translate(x,y){events.push(['translate',x,y]);}},ref={contents:'MCC',geometricBounds:[0,10,20,0],duplicate(){return target;},remove(){}};const frames=[ref];frames.add=()=>target;runtime().reletterGroups({textFrames:frames},[{indices:[0],expected:['MCC'],text:'MCC'}]);assert.deepEqual(events,['outline',['translate',0,1]]);});
