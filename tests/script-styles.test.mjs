import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {validatePlan} from '../lib/core.mjs';
const code=fs.readFileSync(new URL('../adobe/vector-labels.jsx',import.meta.url),'utf8');
const styles=[{start:0,length:1,font:'TimesNewRomanPS-ItalicMT'},{start:1,length:1,font:'TimesNewRomanPSMT',script:'subscript'}];
const plan=()=>({version:1,figureId:'f_probe',sourceHash:'a'.repeat(64),route:'vector-reletter',widthMm:40,fontSize:8,replacements:[],texts:[{text:'X1',x:.5,y:.5,styles}]});
test('script values are checked before accepting a production plan',()=>{
 validatePlan(plan());
 const invalid=plan();invalid.texts[0].styles=styles.map(s=>({...s,script:'unknown'}));
 assert.throws(()=>validatePlan(invalid),/local text style/);
});
test('native script styling keeps nominal size and separate fonts',()=>{
 const ctx={JFW:{},app:{textFonts:{getByName:name=>({name})}},FontBaselineOption:{SUBSCRIPT:'native-sub',SUPERSCRIPT:'native-super'}};
 vm.createContext(ctx);vm.runInContext(code,ctx);
 const tf={contents:'X1',characters:[{characterAttributes:{size:8}},{characterAttributes:{size:8}}]};
 ctx.JFW.styleText(tf,styles);
 assert.equal(tf.characters[0].characterAttributes.textFont.name,'TimesNewRomanPS-ItalicMT');
 assert.equal(tf.characters[1].characterAttributes.textFont.name,'TimesNewRomanPSMT');
 assert.equal(tf.characters[1].characterAttributes.baselinePosition,'native-sub');
 assert.equal(tf.characters[1].characterAttributes.size,8);
});
test('invalid later script rejects the full set before mutating characters',()=>{
 const ctx={JFW:{},app:{textFonts:{getByName(){throw Error('Mutation reached');}}}};
 vm.createContext(ctx);vm.runInContext(code,ctx);
 const tf={contents:'X1',characters:[]};
 assert.throws(()=>ctx.JFW.styleText(tf,[styles[0],{...styles[1],script:'unknown'}]),/local text style/);
});
