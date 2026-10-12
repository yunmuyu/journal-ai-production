import fs from 'node:fs';
import path from 'node:path';
const cache=new Map();
function read(file){
 try{const stat=fs.statSync(file),key=stat.size+':'+stat.mtimeMs,old=cache.get(file);if(old?.key===key)return old.value;
  const value=JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));cache.set(file,{key,value});return value;
 }catch{return null;}
}
export function comparison(runs=[]){
 const rounds=[...new Set(runs.map(r=>r.round))].map(round=>{const a=runs.find(r=>r.round===round&&r.mode==='original'),b=runs.find(r=>r.round===round&&r.mode==='candidate');return a&&b?{beforeMs:a.durationMs,afterMs:b.durationMs}:null;}).filter(Boolean);
 return {rounds,consistentImprovement:rounds.length>=2&&rounds.every(r=>r.afterMs<r.beforeMs)};
}
export function timingRow(row,status){
 const r=row.result||{};if(!Number.isFinite(r.durationMs)||r.durationMs<0)return null;
 return {articleId:row.articleId,author:row.author,number:String(row.number),processingMs:r.durationMs,cached:r.cached===true,
  status:status||'实验加工记录',totalMs:null,reworkCount:null,firstPassRate:null,geometryReused:r.adobe?.snapshot?.geometryEvidence?.mode==='reused'};
}
export function buildProgress(rows,inventory,link,{project=path.resolve('.')}={}){
 const evidence=p=>{const file=path.join(project,p);return {file:link(file),name:path.basename(file)};};
 const priorities=(inventory.articles||[]).filter(a=>a.productionPriority).sort((a,b)=>a.productionPriority.rank-b.productionPriority.rank).map(a=>({
  articleId:a.id,author:a.author,rank:a.productionPriority.rank,next:a.productionPriority.nextStep,
  figures:rows.filter(r=>r.articleId===a.id).map(r=>({number:r.number,status:r.status})),reason:a.productionPriority.reason}));
 const recent=[];const productionRoot=path.join(project,'work/october-production');
 if(fs.existsSync(productionRoot))for(const dir of fs.readdirSync(productionRoot,{withFileTypes:true}).filter(d=>d.isDirectory()))for(const name of ['plan-results.json','image-results.json']){
  const file=path.join(productionRoot,dir.name,name),entries=read(file);if(!Array.isArray(entries))continue;
  for(const item of entries){const record=timingRow(item,rows.find(r=>r.id===item.articleId+'-F'+String(item.number).split('.')[0])?.status);if(!record)continue;
   let updated=0;try{updated=fs.statSync(item.record||item.result.ai).mtimeMs;}catch{}
   recent.push({...record,updated,record:item.record});
  }
 }
 const distinct=new Map();for(const r of recent.sort((a,b)=>b.updated-a.updated)){const key=r.articleId+':'+r.number;if(!distinct.has(key))distinct.set(key,r);}
 const timings=[...distinct.values()].slice(0,24);
 const root='work/speed-next-20261010',native=read(path.join(project,root,'snapshot-array-native-evidence/result.json')),measured=comparison(native?.runs);
 const circuit=read(path.join(project,'work/circuit-clearance-20261010/experiment/inputs-8pt-clearance.json'));
 const probe=read(path.join(project,root,'guxun-vector/probe-result.json'));
 const reused=timings.filter(r=>r.geometryReused);
 const improvements=[
  {id:'layout',title:'减少布局试排与返工',stage:'正在验证',problem:'文字碰连线、器件或图例，直到看成品才发现，导致重复制作。',action:'先用实际字形和真实线条寻找空位；图例问题用小探针定位，再决定修复方式。',effect:circuit?'两张电路已有8 pt避线候选；仍需实际PDF确认。':'离线避线候选尚未取得。',limitation:probe?.ok?'定位探针已完成，不等于整张成图已通过。':'图例定位仍在诊断，尚不能宣称修复。',evidence:[evidence('work/circuit-clearance-20261010/experiment/HANDOFF.md'),evidence(root+'/guxun-vector/probe-result.json')]},
  {id:'trim',title:'减少矢量图重复扫描',stage:reused.length?'已用于受控实验':'受控实验',problem:'仅裁掉白边也会再次扫描整张图的全部曲线点，重复读取很耗时。',action:'只在同次制作、文件未变且曲线保真检查通过时，裁边复用已有几何证据。',effect:reused.length?`最近${reused.length}条加工记录明确标记已复用几何证据。`:'门禁测试已完成，等待实际加工记录验证。',limitation:'仍为实验；最终PDF检查保留，全流程提速比例尚未核实。',evidence:[evidence(root+'/trim-reuse-worktree/HANDOFF-trim-reuse.md')]},
  {id:'preflight',title:'把可避免的失败挡在制作之前',stage:'已接入前置检查',problem:'字号判断错误或用户文件已变化，制作、汇总后才发现要重来。',action:'制作前确认原稿和成品是否被改过、实际字号是否合规，以及已有反馈和PDF检查结果。',effect:'9项针对性回归通过；实际减少的返工次数尚未完整记录。',limitation:'不能自动判断原稿内容冲突，也不能代替最终视觉检查。',evidence:[evidence(root+'/HANDOFF.md')]},
  {id:'array',title:'减少坐标读取：无稳定收益，未采用',stage:'未采用',problem:'曲线路径扫描耗时，尝试减少重复坐标读取。',action:'同一文档交错比较两种实现，完整几何字段必须一致。',effect:native?.ok?measured.rounds.map((r,i)=>`第${i+1}轮 ${(r.beforeMs/1000).toFixed(1)}秒 → ${(r.afterMs/1000).toFixed(1)}秒`).join('；'):'真实对照结果未取得。',limitation:measured.consistentImprovement?'单次扫描对照不能证明整批交付提速。':'第二轮未更快，不能用第一轮暖机差异宣称提速。',evidence:[evidence(root+'/snapshot-array-native-evidence/result.json')]}
 ];
 return {priorities,improvements,timings,coverage:'只展示已记录的最近加工耗时（含实验），不代表完整生产历史；从接手到合格交付总耗时、人工等待和返工次数尚未完整记录。'};
}
