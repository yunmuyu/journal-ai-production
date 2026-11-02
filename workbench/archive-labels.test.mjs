import test from 'node:test';
import assert from 'node:assert/strict';
import {registerArchiveArticles} from './archive-articles.mjs';

test('duplicate names use persisted short labels without changing manuscript identity',()=>{
 const batch={archiveSha256:'fixture',editor:'编辑',manuscripts:[
  {author:'作者甲',title:'融合检测方法',member:'a.docx',wordPath:'a.docx',displaySequence:1,displayLabel:'作者甲1融合'},
  {author:'作者甲',title:'基于学习方法',member:'b.docx',wordPath:'b.docx',displaySequence:2,displayLabel:'作者甲2基于'}
 ]};
 const register=b=>{const articles=[];registerArchiveArticles({articles,link:url=>({path:url.pathname,token:url.pathname}),wordTokens:new Set()},b);return articles;};
 const first=register(batch),second=register({...batch,manuscripts:[...batch.manuscripts].reverse()});
 assert.deepEqual(first.map(a=>a.label),['作者甲1融合','作者甲2基于']);
 for(const a of first){const b=second.find(b=>b.id===a.id);assert.equal(b.label,a.label);assert.deepEqual(b.word,a.word);assert.equal(a.author,'作者甲');}
});

test('new duplicate labels skip a shared 基于 prefix and remain stable after reorder',()=>{
 const batch={archiveSha256:'fixture',editor:'编辑',manuscripts:[
  {author:'作者乙',title:'基于视觉的方法',member:'b.docx',wordPath:'b.docx'},
  {author:'作者乙',title:'基于学习的方法',member:'a.docx',wordPath:'a.docx'}
 ]};
 const register=()=>{const articles=[];registerArchiveArticles({articles,link:url=>({path:url.pathname,token:url.pathname}),wordTokens:new Set()},batch);return articles;};
 const first=register();assert.deepEqual(new Set(first.map(a=>a.label)),new Set(['作者乙1学习','作者乙2视觉']));
 batch.manuscripts.reverse();assert.deepEqual(register().map(a=>a.label).sort(),first.map(a=>a.label).sort());
});
