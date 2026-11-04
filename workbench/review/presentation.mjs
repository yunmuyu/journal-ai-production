import fs from 'node:fs';
import path from 'node:path';
function change(text,from,to){if(!text.includes(from))throw Error('Original UI anchor changed: '+from.slice(0,50));return text.replace(from,to);}
export function page(source){
 let html=fs.readFileSync(path.join(source,'index.html'),'utf8');
 html=html.replace('<title>期刊AI生产工作台</title>','<title>十一月作图</title>');
 html=html.replace(/<header class="page-header">[\s\S]*?<\/header>/,'<header class="page-header"><h1 class="page-title">十一月作图</h1><button class="btn btn-primary" id="archive-intake-open">上传作图包</button><span id="sync" hidden></span></header>');
 html=html.replace(/<nav class="nav nav-pills work-nav"[\s\S]*?<\/nav>/,'');
 html=html.replace('<script src="/decision-entry.js" defer></script>','<link rel="stylesheet" href="/figure-viewer.css">');
 html=html.replace('id="save-author"','id="save-author" title="保存本篇批注"');
 html=html.replace('</head>',`<style>#toolbar label{display:none!important}#toolbar{margin-top:1rem;padding:.75rem 1rem}#counts{margin:0}main header.page-header{justify-content:flex-start;flex-direction:row;align-items:center}.figure-preview{margin:.75rem 0}.panzoom{position:relative;overflow:hidden;height:260px;background:#eaf4ff;border:1px solid #a9cdef;touch-action:none;cursor:grab}.panzoom:active{cursor:grabbing}.panzoom img{display:block;width:100%;height:100%;object-fit:contain;transform-origin:0 0;user-select:none;pointer-events:none}.preview-controls{display:flex;align-items:center;gap:.4rem;flex-wrap:wrap;margin-top:.4rem}.panzoom:focus-visible{outline:2px solid var(--tblr-primary)}.author-header .actions{margin-top:0}</style></head>`);
 return html.replace('</head>','<link rel="stylesheet" href="/archive-intake.css"><script src="/archive-intake-ui.js" defer></script><script src="/workbuddy-ui.js" defer></script></head>');
}
export function app(source){
 let js=fs.readFileSync(path.join(source,'app.js'),'utf8');
 js=change(js,'drafts.get(id).accepted=event.target.checked;drafts.get(id).dirty=true;save(id);','setAcceptance(id,event.target.checked);');
 js=change(js,'delivered=f.outputs.some(o=>o.file)','delivered=f.outputs.some(o=>o.file)&&f.previewCurrent!==false');
 js=change(js,"(f.feedback?.revision||0)!==d.revision","((f.feedback?.revision||0)!==d.revision||f.reviewVersion!==d.reviewVersion)");
 js=change(js,"src:a.file?'/file/'+a.file.token:''", "src:a.data||(a.file?'/file/'+a.file.token:'')");
 js=change(js,':{data:im.data}',':{data:im.src}');
 js=change(js,"d.dirty=true;d.accepted=false;const cb=document.querySelector(`[data-accept=\"${id}\"]`);if(cb)cb.checked=false;",'d.dirty=true;');
 js=js.replace("'反馈已写入生产记录'", "'批注已保存'");
 js=change(js,"${button(a.summary,'作者汇总PDF','open',true)}${a.layoutFolder?button(a.layoutFolder,'排版定稿','locate'):''}${button(a.word,'原始Word')}${button(a.ai,'核对AI')}${button(a.folder,'文件夹','locate')}","${button(a.word,'打开原 Word','open',true)}");
 js=change(js,'<div data-decision-slot="${e(f.id)}"></div>',`<div class="figure-previews">\${f.outputs.filter(o=>o.file).map(o=>\`<div class="figure-preview"><div class="panzoom" tabindex="0" role="group" aria-label="图\${e(o.number)}可缩放预览"><img loading="lazy" src="/preview/\${o.file.token}" alt="\${e(a.label)} 图\${e(o.number)}成稿"></div><div class="preview-controls"><button class="btn btn-sm btn-outline-secondary" data-zoom="in" aria-label="放大图\${e(o.number)}">＋</button><button class="btn btn-sm btn-outline-secondary" data-zoom="out" aria-label="缩小图\${e(o.number)}">−</button><button class="btn btn-sm btn-outline-secondary" data-zoom="reset">复位</button><a class="btn btn-sm btn-outline-secondary" href="/file/\${o.file.token}" target="_blank" rel="noopener">打开原成稿</a></div></div>\`).join('')}</div>`);
 js=change(js,'<div class="figure-preview"><div class="panzoom"','<div class="figure-preview">${figureDetails(o)}<div class="panzoom"');
 js=js.replace("'终检通过':'全部通过'","'终检通过':'全部通过','待终检':'修订待确认'");
 js=change(js,'<div class="feedback-box">',`\${f.previousOutputs?.length?\`<details class="text-secondary mb-2"><summary>此前版本</summary>\${f.previousOutputs.filter(o=>o.file).map(o=>\`<a href="/file/\${o.file.token}" target="_blank" rel="noopener">打开此前版本</a>\`).join('')}</details>\`:''}<div class="feedback-box">`);
 js+=`\nfunction figureDetails(o){
 const m=o.file.meta;if(!m)return '<p class="text-secondary">尺寸信息待核</p>';
 return '<div class="figure-meta text-secondary mb-2"><strong>'+e(m.columnLabel)+'</strong> · '+e(m.format)+(m.fontLabel?' · '+e(m.fontLabel):'')+'</div>';
}\n`;
 js+=fs.readFileSync(new URL('./feedback-autosave.js',import.meta.url),'utf8');
 js=change(js,'<div class="panzoom" tabindex="0" role="group" aria-label="图${e(o.number)}可缩放预览">','<div class="figure-thumbnail" data-viewer-token="${o.file.token}" tabindex="0" role="button" aria-label="双击大屏预览 ${e(a.label)}图${e(o.number)}" title="双击大屏预览；右键添加位置批注">');
 js=js.replace(/<button class="btn btn-sm btn-outline-secondary" data-zoom="in"[\s\S]*?data-zoom="reset">复位<\/button>/,'<button class="btn btn-sm btn-outline-secondary" data-open-viewer="${o.file.token}">大屏预览 / 批注</button>');
 js+=fs.readFileSync(new URL('./acceptance.js',import.meta.url),'utf8');
 js=change(js,'<div class="feedback-box">','<div data-point-summary="${e(f.id)}">${pointSummary(f,d)}</div><div class="feedback-box">');
 js+=fs.readFileSync(new URL('./point-summary.js',import.meta.url),'utf8');
 js+=fs.readFileSync(new URL('./auto-review.js',import.meta.url),'utf8');
 js+=fs.readFileSync(new URL('./figure-viewer.js',import.meta.url),'utf8');
 js=change(js,'<div class="feedback-box">','${revisionControls(f)}<div class="feedback-box">');
 js+=fs.readFileSync(path.join(source,'revision-controls.js'),'utf8');
 js=change(js,'Object.assign(find(id),result.figure);','Object.assign(find(id),result.figure);syncRevisionControl(id);');
 js=js.replace('<div class="actions">','<div class="actions">${a.externalReviewUrl?`<a class="btn btn-primary" href="${e(a.externalReviewUrl)}" target="_blank" rel="noopener">打开已有图件</a>`:""}'); return js;
}
