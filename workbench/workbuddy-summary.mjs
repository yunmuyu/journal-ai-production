const identity=j=>{
 const number=j.figureNumber||j.number||(j.articleId&&j.figureId?.startsWith(j.articleId+'-F')?j.figureId.slice(j.articleId.length+2):null);
 return j.articleId&&number?`${j.articleId}\0${number}`:j.figureId||null;
};
export function summarizeProduction(jobs,figures=null){
 const latest=new Map();
 for(const job of [...jobs].sort((a,b)=>(a.createdAt||'').localeCompare(b.createdAt||''))) {
  const key=identity(job);if(job.kind!=='inventory'&&key)latest.set(key,job);
 }
 const current=[...latest.values()],count=states=>current.filter(j=>states.includes(j.state)).length;
 const rows=figures===null?null:[...new Map(figures.map(f=>[identity({...f,figureNumber:f.number}),f]).filter(([key])=>key)).values()];
 return {figures:rows?.length??current.length,returned:count(['ready']),pendingReview:rows?.filter(f=>f.pendingReview===true).length??null,
  userDecisions:rows?.filter(f=>f.needsUserDecision===true).length??null,problems:count(['failed','needs_input','interrupted']),
  active:count(['running','pausing']),queued:count(['queued']),paused:count(['paused']),internalReview:count(['review_pending']),
  tasks:jobs.length,attempts:jobs.reduce((n,j)=>n+(j.attempt||0),0)};
}
