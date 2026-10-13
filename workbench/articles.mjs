export function articleCategory(figures){
 if(figures.some(f=>['待终检','待修订'].includes(f.status)))return '待验收';
 if(!figures.length||figures.some(f=>['待制作','生产中','异常'].includes(f.status)))return '待制作';
 if(figures.some(f=>f.status==='暂缓'))return '暂缓';
 return '已封存';
}
export function groupArticles(rows,inventory){
 const first=a=>String(a.author).trim().split(/[\s、，,]+/)[0];
 const names=new Map();for(const a of inventory)names.set(first(a),(names.get(first(a))||0)+1);
 return inventory.map(a=>{
  const figures=rows.filter(r=>r.id.startsWith(a.id+'-F')).sort((x,y)=>String(x.number).localeCompare(String(y.number),undefined,{numeric:true}));
  const title=String(a.article||'').split(a.author).slice(1).join(a.author).replace(/\.docx?$/i,'').trim();
  const author=first(a);
  const suffix=names.get(author)>1?(a.secondAuthor||a.authors?.[1]||String(a.author).trim().split(/[\s、，,]+/)[1]||title.slice(0,18)||a.id.slice(-6)):'';
  const summary=figures.find(r=>r.summary)?.summary||null,word=figures.find(r=>r.word)?.word||null;
  const ai=figures.find(r=>r.ai)?.ai||null,folder=figures.find(r=>r.folder)?.folder||null;
  const layoutFolder=figures.find(r=>r.layoutFolder)?.layoutFolder||null;
  return {layoutFolder,id:a.id,editor:a.editor,author,label:author+(suffix?' · '+suffix:''),category:articleCategory(figures),summary,word,ai,folder,figures};
 });
}
