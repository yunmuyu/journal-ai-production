import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('../adobe/editorial-aggregate.jsx',import.meta.url),'utf8');
const transition=source.slice(source.indexOf('  if(wide&&column===1)'),source.indexOf('  if(needLabel){label'));

test('tall single-column figure starts a new page when neither remaining column fits',()=>{
 const ctx={wide:false,column:0,y:573,height:323,needLabel:false,board:[0,1022,490,344],marginY:14,columnTop:573,page:0,
  newPage(){this.page++;this.column=0;this.y=1008;},
  nextColumn(){if(this.column===0){this.column=1;this.y=this.columnTop;}else this.newPage();}};
 // The real aggregate transition runs on the geometry exposed by the failed PDF.
 vm.createContext(ctx);vm.runInContext('newPage=newPage.bind(this);nextColumn=nextColumn.bind(this);'+transition,ctx);
 assert.equal(ctx.page,1);
 assert.ok(ctx.y-ctx.height-34>=ctx.board[3]+ctx.marginY);
});

test('single-column figure uses the next column when its remaining height is sufficient',()=>{
 const ctx={wide:false,column:0,y:390,height:120,needLabel:false,board:[0,1022,490,344],marginY:14,columnTop:650,page:0,
  newPage(){this.page++;this.column=0;this.y=1008;},
  nextColumn(){if(this.column===0){this.column=1;this.y=this.columnTop;}else this.newPage();}};
 vm.createContext(ctx);vm.runInContext('newPage=newPage.bind(this);nextColumn=nextColumn.bind(this);'+transition,ctx);
 assert.equal(ctx.page,0);assert.equal(ctx.column,1);
});
