import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
test('batch copy crosses documents once and excludes guides',()=>{
 const moves=[],duplicates=[],group={name:'',duplicate(parent){duplicates.push(parent);return {name:'copied'};}};
 const roots=[{name:'front',parent:{typename:'Layer'},guides:false,move(){moves.push(this.name);}},{name:'guide',parent:{typename:'Layer'},guides:true},{name:'back',parent:{typename:'Layer'},guides:false,move(){moves.push(this.name);}}];
 const layers=[{pageItems:roots}];layers.add=()=>({groupItems:{add:()=>group}});
 const context={JFW:{},ElementPlacement:{PLACEATBEGINNING:1}};
 vm.runInNewContext(fs.readFileSync(new URL('../adobe/editorial-copy.jsx',import.meta.url),'utf8'),context);
 const production={name:'production'};const result=context.JFW.copyArtwork({layers,activate(){}},production);
 assert.deepEqual(moves,['back','front']);assert.equal(duplicates.length,1);assert.equal(duplicates[0],production);assert.equal(result.rootCount,2);
});
