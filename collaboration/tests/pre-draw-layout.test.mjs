import test from 'node:test';
import assert from 'node:assert/strict';
import {calculateLayout} from '../scripts/pre-draw-layout.mjs';

const measured=(text,widthPt=30,heightPt=8)=>({text,font:'现 宋体 1',fontSizePt:8,widthPt,heightPt});
const box=(id,text=id,extra={})=>({kind:'box',id,text,...extra});
const request=(tree,measurements,extra={})=>({version:1,fontSizePt:8,font:'现 宋体 1',widthMm:80,tree,measurements,...extra});

test('sizes text first, equalizes columns and derives enclosing frame before attached arrows',()=>{
 const tree={kind:'column',children:[box('start'),{kind:'frame',id:'outer',title:'代码区',content:{kind:'column',children:[box('a','初始化',{widthGroup:'same'}),box('b','处理',{widthGroup:'same'})]}}],gapPt:3*72/25.4};
 const r=calculateLayout(request(tree,{start:measured('start'),a:measured('初始化',50),b:measured('处理'),outer:measured('代码区')},{edges:[{id:'e',from:'start',to:'outer',fromPort:'bottom',toPort:'top'}]}));
 assert.equal(r.status,'ready');
 assert.equal(r.nodes.find(n=>n.id==='a').widthPt,r.nodes.find(n=>n.id==='b').widthPt);
 assert.equal(r.nodes.find(n=>n.id==='a').widthPt,59);
 assert.ok(r.edges[0].points[1][1]>r.edges[0].points[0][1]);
 assert.ok(Math.abs(r.edges[0].lengthPt-3*72/25.4)<1e-9);
 assert.deepEqual(r.order,['text','boxes','groups','frames','connections','fit','collision-check']);
});

test('missing or stale font/text measurement never becomes a layout pass',()=>{
 const input=request(box('a'),{}),before=structuredClone(input);
 assert.equal(calculateLayout(input).status,'needs-measurement');assert.deepEqual(input,before);
 const stale=calculateLayout(request(box('a'),{a:measured('old')}));
 assert.equal(stale.status,'needs-measurement');
 assert.match(stale.issues[0].type,/measurement/);
});

test('width constraint is preserved when final font would fall below 6 pt',()=>{
 const r=calculateLayout(request(box('a'),{a:measured('a',400)},{widthMm:40}));
 assert.equal(r.status,'needs-reflow');assert.ok(r.finalFontSizePt<6);assert.equal(r.targetWidthMm,40);
});

test('diamond and ellipse contain all corners of padded text',()=>{
 for(const shape of ['diamond','ellipse']){
  const r=calculateLayout(request(box('a','a',{shape}),{a:measured('a',50,12)}));
  assert.equal(r.status,'ready');const n=r.nodes[0];
  const x=(50+9)/n.widthPt,y=(12+5.4)/n.heightPt;
  assert.ok((shape==='diamond'?x+y:x*x+y*y)<=1+1e-9);
 }
});

test('connector crossing a different node is blocked before drawing',()=>{
 const tree={kind:'row',children:[box('a'),box('b'),box('c')],gapPt:10};
 const r=calculateLayout(request(tree,{a:measured('a'),b:measured('b'),c:measured('c')},{edges:[{id:'e',from:'a',to:'c',fromPort:'right',toPort:'left'}]}));
 assert.equal(r.status,'conflict');assert.ok(r.issues.some(x=>x.type==='edge_node_collision'));
});

test('PS is exempt; unsupported plans explicitly wait for geometric input',()=>{
 assert.equal(calculateLayout({route:'image'}).status,'exempt');
 assert.equal(calculateLayout({route:'vector-reletter'}).status,'needs-measurement');
});

test('adjacent connected boxes automatically reserve 3mm and place exterior label at fixed gap',()=>{
 const tree={kind:'column',children:[box('a'),box('b')]};
 const r=calculateLayout(request(tree,{a:measured('a'),b:measured('b'),'edge:e':measured('Bootloader代码区',80)},{edges:[{id:'e',from:'a',to:'b',fromPort:'bottom',toPort:'top',label:{text:'Bootloader代码区',side:'right',gapPt:3}}]}));
 assert.equal(r.status,'ready');const edge=r.edges[0],label=r.texts.find(t=>t.id==='edge:e');
 assert.ok(Math.abs(edge.lengthPt-3*72/25.4)<1e-9);assert.equal(label.x-edge.points[0][0],3);
 assert.ok(r.naturalWidthPt>=label.x+label.widthPt);
});

test('a large arrow label enters width capacity; final font conflict cannot be hidden by tree width',()=>{
 const tree={kind:'column',children:[box('a'),box('b')]};
 const r=calculateLayout(request(tree,{a:measured('a'),b:measured('b'),'edge:e':measured('label',400)},{widthMm:40,edges:[{id:'e',from:'a',to:'b',fromPort:'bottom',toPort:'top',label:{text:'label',side:'right'}}]}));
 assert.equal(r.status,'needs-reflow');assert.ok(r.naturalWidthPt>400);
});

test('height groups propagate to group positions before measuring total height',()=>{
 const tree={kind:'column',children:[box('a','a',{heightGroup:'same'}),box('b','b',{heightGroup:'same'})]};
 const r=calculateLayout(request(tree,{a:measured('a',30,8),b:measured('b',30,16)}));
 assert.equal(r.status,'ready');assert.equal(r.nodes[0].heightPt,r.nodes[1].heightPt);
 assert.equal(r.nodes[1].y,r.nodes[0].heightPt+3);
});

test('bidirectional arrow gap is calculated before native drawing and survives final fit',()=>{
 const tree={kind:'column',children:[box('a'),box('b')]},r=calculateLayout(request(tree,{a:measured('a'),b:measured('b')},{edges:[{id:'e',from:'a',to:'b',fromPort:'bottom',toPort:'top',both:true}]}));assert.equal(r.status,'ready');assert.ok(r.edges[0].lengthPt>=8.8);
 const tooShort=calculateLayout(request({...tree,gapPt:3*72/25.4},{a:measured('a'),b:measured('b')},{edges:[{id:'e',from:'a',to:'b',fromPort:'bottom',toPort:'top',both:true}]}));assert.equal(tooShort.status,'conflict');assert.ok(tooShort.issues.some(i=>i.type==='arrow_head_segment_too_short'));
});
