import {buildProgress} from './progress.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

const project=path.resolve('.');
const engine=path.join(project,'outputs/journal-figure-workflow');
const runtime=process.env.JFW_RUNTIME_PATH||'C:/Users/xdxxk/.codex/skills/journal-figure-workflow/runtime';
const digest=p=>fs.existsSync(p)?createHash('sha256').update(fs.readFileSync(p)).digest('hex'):null;
const routeDefinitions=[
 {id:'export-existing',name:'接手已有AI并导出',family:'核对与交付',stage:'已有成品',scope:'核对Word图号、顺序和内容，复用已有作者AI，分别导出主图或子图。',boundary:'不把旧AI或文件夹已完成标记当作内容正确的证据。',tools:['lib/review.mjs','adobe/editorial-copy.jsx'],evidence:['work/october-production/gongxiaoqiang/export-report.json']},
 {id:'vector-reletter',name:'保留原图，统一文字',family:'统计图与原图加工',stage:'工具已有，需逐类验证',scope:'原图线条和数据保持不动，只将文字改成期刊要求的字体、字号和位置。',boundary:'文字被拆碎、变成轮廓或位置异常时，需要另行验证；不是所有PDF都能直接处理。',tools:['lib/render.mjs','adobe/vector-labels.jsx'],evidence:['outputs/journal-figure-workflow/运行说明.md']},
 {id:'matplotlib',name:'已验证的统计图加工',family:'统计图与原图加工',stage:'已在多位作者上验证',scope:'已验证的一类统计图可以批量加工，保留真实曲线，统一字号、坐标和图例，同篇同类图保持相近大小。',boundary:'换了来源软件或图的内部结构，就先试一张；不能认为所有统计图都已支持。',tools:['lib/outlined-chart.mjs','scripts/prepare_matplotlib_svg.py'],evidence:['work/october-production/sun-benchmark/BENCHMARK-REPORT.md','work/october-production/statistics-batch-20261009-01/REPORT.md']},
 {id:'rebuild',name:'重新排流程图和框图',family:'框图与结构图',stage:'工具已有，需逐类验证',scope:'把简单流程图、框图重新排得紧凑，保留全部文字和箭头关系。',boundary:'复杂图需要先确认连接关系，不能猜箭头、删除节点来省空间。',tools:['lib/fit.mjs','lib/render.mjs'],evidence:['outputs/journal-figure-workflow/references/editorial-profile.md']},
 {id:'image',name:'处理照片和软件截图',family:'位图与混合图',stage:'已有成品',scope:'保留原像素，通过已验证Photoshop尺寸动作加工；界面示意截图按用户规则单栏。',boundary:'截图小字不等于可编辑8pt；不伪造原图没有的数据。',tools:['lib/render.mjs'],evidence:['outputs/journal-figure-workflow/运行说明.md']},
 {id:'raster-reletter',name:'给图片里的统计图换字',family:'位图与混合图',stage:'工具已有，需逐类验证',scope:'原图是图片时保留真实曲线和柱子，只替换能确认的文字。',boundary:'低清无数据不能假重绘曲线，遮罩不能遮掉数据或图例信息。',tools:['lib/render.mjs'],evidence:['outputs/journal-figure-workflow/运行说明.md']},
 {id:'compose',name:'处理图片与文字混合图',family:'位图与混合图',stage:'工具已有，需逐类验证',scope:'对混合图分区保留、换字和组合。',boundary:'只对有依据的区域修改，不把局部图例裁切扩大成整图栅格化。',tools:['lib/render.mjs'],evidence:['work/tool-iteration-20261008/迭代结论与接手.md']},
 {id:'aggregate',name:'生成作者AI和核对汇总',family:'核对与交付',stage:'已实测可用',scope:'生成可编辑的作者AI和汇总PDF，方便整篇核对；复用已通过的成果，减少重复导出。',boundary:'只更新局部图的快速方式仍有灰度差异，暂不正式使用；当前使用已验证的整篇汇总方式。',tools:['lib/aggregate-cache.mjs','adobe/editorial-aggregate.jsx','adobe/editorial-copy.jsx'],evidence:['work/october-production/sun-benchmark/BENCHMARK-REPORT.md']}
];
export function authorState(figures){
 const states=figures.map(f=>f.status);
 if(states.includes('待修订'))return '待修订';
 if(states.length&&states.every(s=>s==='终检通过'))return '全部通过';
 if(states.length&&states.every(s=>['待终检','终检通过'].includes(s)))return '待终检';
 return states.some(s=>s!=='待制作')?'制作中':'未完成';
}
export function figureType(f,record={},checked={}){
 const text=String(record.figureType||checked.type||'');
 if(/circuit|电路/i.test(text))return '电路图';
 if(/flowchart|block diagram|流程|框图|结构图/i.test(text))return '流程与框图';
 if(/plot|chart|statistic|统计|混淆矩阵/i.test(text))return '统计图';
 if(/photograph|screenshot|照片|截图/i.test(text))return '照片与截图';
 if(/mixed|混合/i.test(text))return '混合图';
 if(routeFor(record)==='matplotlib')return '统计图';
 if(/电路图/.test(f.caption||''))return '电路图';
 if(/流程图|框图|网络结构|硬件结构图/.test(f.caption||''))return '流程与框图';
 if(/混淆矩阵|散点图|雷达图|柱状图|折线图|频谱图/.test(f.caption||''))return '统计图';
 return '待分类';
}
export function queueState(f){
 if(f.status==='待修订')return '待返工';
 if(f.status==='暂缓')return '探索与暂缓';
 if(f.status==='待制作')return '待预检';
 return f.status;
}
export function routeFor(record){
 const source=String(record?.sourceAi||'').replaceAll('\\','/');
 if(/\/(sun-benchmark|statistics-cross-author-20261009|statistics-batch-20261009-01)\//.test(source))return 'matplotlib';
 if(record?.route==='photoshop-compose-images')return 'compose';
 return routeDefinitions.some(r=>r.id===record?.route)?record.route:null;
}
export function buildWorkspace(rows,production,link,inventory={}){
 const document=p=>{const absolute=path.resolve(p);let text=null;if(fs.existsSync(absolute)){if(path.extname(p)==='.md')text=fs.readFileSync(absolute,'utf8');else if(path.extname(p)==='.json'){const r=JSON.parse(fs.readFileSync(absolute,'utf8'));text=JSON.stringify({source:r.source,status:r.status,elapsedMs:r.elapsedMs,correctionElapsedMs:r.correctionElapsedMs,finalizeDurationMs:r.finalizeDurationMs,records:(r.records||[]).map(x=>({number:x.number,route:x.route,durationMs:x.durationMs,output:x.output}))},null,2);}}return {file:link(absolute),text};};
 const capabilities=routeDefinitions.map(route=>({...route,
  tools:route.tools.map(p=>({name:p,file:link(path.join(engine,p))})),
  evidence:route.evidence.map(p=>({name:path.basename(p),...document(p)})),
  cases:rows.filter(f=>route.id==='aggregate'?f.summary:routeFor(production.figures[f.id])===route.id).map(f=>({id:f.id,articleId:f.id.split('-F')[0],author:f.author,number:f.number,status:f.status}))
 }));
 const queue=rows.filter(f=>f.status!=='终检通过').map(f=>({id:f.id,articleId:f.id.split('-F')[0],author:f.author,editor:f.editor,number:f.number,state:queueState(f),status:f.status,route:capabilities.find(r=>r.id===routeFor(production.figures[f.id]))?.name||'细分类待预检',reason:f.feedback?.text||f.reason||'',attachments:f.feedback?.attachments?.length||0}));
 const compare=['scripts/jfw.mjs','lib/render.mjs','lib/outlined-chart.mjs','adobe/editorial-copy.jsx'].map(name=>{const a=digest(path.join(engine,name)),b=digest(path.join(runtime,name));return {name,state:!a||!b?'文件缺失':a===b?'一致':'不同',sourceHash:a,runtimeHash:b};});
 const locations=[
  ['生产权威记录','F:/2026年10月/_作图工作台','inventory / production-results / author-templates；Excel与HTML共用。'],
  ['工作台服务',path.join(project,'work/october-review'),'server.mjs；127.0.0.1:18741，仅允许已登记文件。'],
  ['图件引擎源码',engine,'本地Git基线已建立；当前修改不等于已发布版本。'],
  ['实际Skill运行副本',runtime,'生产前核对源码与运行副本；只比对下面列出的关键文件。'],
  ['生产任务与证据',path.join(project,'work/october-production'),'保存来源、尝试、发布、失败和审计，按原任务续接。']
 ].map(([name,p,note])=>({name,path:p,note,file:link(p)}));
 return {progress:buildProgress(rows,inventory,link),queue,figureGroups:rows.map(f=>({...queue.find(q=>q.id===f.id),id:f.id,articleId:f.articleId,author:f.author,editor:f.editor,number:f.number,status:f.status,type:f.type||'待分类'})),capabilities,runtime:{compare,locations,issues:rows.filter(f=>f.status==='异常').map(f=>({id:f.id,articleId:f.id.split('-F')[0],author:f.author,number:f.number,reason:f.reason})),handoff:document('work/october-review/PROJECT-MAP.md'),plan:document('work/october-review/WORKBENCH-PLAN.md')},experiments:[
  {name:'让更多来源的图能直接加工',stage:'受控验证',next:'先拿新来源的一张图试做，确认文字和数据能正确保留，再扩大批量。'},
  {name:'只更新改过的图，减少导出时间',stage:'实验',next:'灰度差异尚未消除；正式交付继续快速全量汇总。'},
  {name:'卞明运图4',stage:'第二阶段',next:'复杂案例，不阻塞成熟路线生产。'},
  {name:'估算一篇文章会占多少版面',stage:'独立实验',next:'目前只有17篇候选参考，实际版面和稿件版本还没核实，尚不能可靠预测。'},
  {name:'人工修改自动学习',stage:'暂不开发',next:'用户目前已基本停止人工生产，先用终检反馈与实际修复积累经验。'}
 ]};
}
