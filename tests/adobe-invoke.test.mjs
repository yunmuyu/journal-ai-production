import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
const source=fs.readFileSync(new URL('../adobe/invoke.js',import.meta.url),'utf8');
function invoke(failProbe){
 const files=new Map([['/adobe/illustrator.jsx','"DRAW_BODY";'],['/adobe/common.jsx','var JFW={};']]);
 const calls=[];let exit;
 function ActiveXObject(name){
  if(name==='Scripting.FileSystemObject')return {GetParentFolderName:()=>'/adobe',FileExists:p=>files.has(p)};
  if(name==='ADODB.Stream')return {Open(){},Close(){},LoadFromFile(p){this.text=files.get(p);},ReadText(){return this.text;},WriteText(t){this.text=t;},SaveToFile(p){files.set(p,this.text);}};
  return {DoJavaScript(code){calls.push(code);if(code==='"JFW_HEALTH_OK";'){if(failProbe)throw {number:-2147417851,description:'server fault'};return 'JFW_HEALTH_OK';}files.set('/result.json','{"ok":true}');return 'JFW_FINISHED';}};
 }
 vm.runInNewContext(source,{ActiveXObject,WScript:{Arguments:i=>['illustrator','/adobe/illustrator.jsx','/request.json','/result.json'][i],Quit:n=>{exit=n;}}});
 return {files,calls,exit,bridge:JSON.parse(files.get('/result.json.bridge.json'))};
}
test('A failed health probe prevents the drawing body from being dispatched',()=>{
 const r=invoke(true);assert.deepEqual(r.calls,['"JFW_HEALTH_OK";']);assert.equal(r.exit,1);assert.equal(r.bridge.detail.during,'probing');assert.equal(r.files.has('/result.json'),false);
});
test('Healthy scripting dispatches the drawing body once and completes',()=>{
 const r=invoke(false);assert.equal(r.calls[0],'"JFW_HEALTH_OK";');assert.equal(r.calls.length,2);assert.equal(r.exit,0);assert.equal(r.bridge.stage,'complete');
});
