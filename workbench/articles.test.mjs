import test from 'node:test';
import assert from 'node:assert/strict';
import {articleCategory,groupArticles} from './articles.mjs';
const f=status=>({status});
test('混合文章优先验收、其余图级状态保留',()=>{assert.equal(articleCategory([f('待终检'),f('待制作'),f('暂缓')]),'待验收');assert.equal(articleCategory([f('终检通过'),f('暂缓')]),'暂缓');assert.equal(articleCategory([f('终检通过'),f('待制作')]),'待制作');assert.equal(articleCategory([f('终检通过'),f('终检通过')]),'已封存');assert.equal(articleCategory([f('异常')]),'待制作');assert.equal(articleCategory([]),'待制作');});
test('同名文章显示不同标题片段并保留各自唯一ID',()=>{const input=[{id:'A-1',author:'李明',editor:'甲',article:'李明 第一项研究.docx'},{id:'A-2',author:'李明',editor:'乙',article:'李明 第二项研究.docx'}];const articles=groupArticles([{id:'A-1-F1',status:'待终检',number:'1',outputs:[]}],input);assert.notEqual(articles[0].label,articles[1].label);assert.equal(articles[0].id,'A-1');assert.equal(articles[0].figures.length,1);assert.equal(articles[1].figures.length,0);});

test('联合作者首页只显示首作者，身份仍使用文章ID',()=>{const items=groupArticles([],[{id:'A-x',author:'周紫微 夏倩雯',editor:'李颖',article:'原稿.docx'}]);assert.equal(items[0].label,'周紫微');assert.equal(items[0].author,'周紫微');assert.equal(items[0].id,'A-x');});
