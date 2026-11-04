import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';

export const digest=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const samePath=(a,b)=>path.resolve(a)===path.resolve(b);
const inside=(root,file)=>{
 const actual=fs.realpathSync(file),base=fs.realpathSync(root),relative=path.relative(base,actual);
 if(relative==='..'||relative.startsWith('..'+path.sep)||path.isAbsolute(relative))throw Error('候选附件必须位于授权候选目录');
 return actual;
};
function stable(value){
 if(Array.isArray(value))return '['+value.map(stable).join(',')+']';
 if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(key=>JSON.stringify(key)+':'+stable(value[key])).join(',')+'}';
 return JSON.stringify(value);
}
const feedbackHash=feedback=>createHash('sha256').update(stable(feedback)).digest('hex');
const attachmentHashes=feedback=>(feedback.attachments||[]).map(item=>{
 const match=/^data:image\/(png|jpeg|webp);base64,(.+)$/.exec(item.data||'');
 if(!match)throw Error('用户反馈附件不是有效的图片数据');
 return createHash('sha256').update(Buffer.from(match[2],'base64')).digest('hex');
});

const pdfAuditScript=`import fitz,json,hashlib,sys,math
from pathlib import Path
import numpy as np
from PIL import Image
candidate,body,source_pdf,word,baseline=sys.argv[1:6]
item=json.loads(sys.argv[6]); dpi=int(item['dpi'])
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
for key,path in [('candidate',candidate),('body',body),('sourcePdf',source_pdf),('word',word),('baseline',baseline)]:
 expected=item['bindings'][key]
 if sha(path)!=expected['sha256']: raise SystemExit(key+' SHA256与绑定不符')
doc=fitz.open(candidate)
if len(doc)!=1: raise SystemExit('候选PDF必须为单页')
page=doc[0]; width_mm=page.rect.width*25.4/72
if abs(width_mm-item['pageWidthMm'])>0.02: raise SystemExit('候选PDF页面宽度不符')
height_mm=page.rect.height*25.4/72
if abs(height_mm-item['pageHeightMm'])>0.02: raise SystemExit('候选PDF页面高度不符')
lines=[s for s in page.get_text().splitlines() if s]
if lines!=item['expectedText']: raise SystemExit('PDF可提取标题与当前标注文本不完全一致')
spans=[span for block in page.get_text('dict')['blocks'] if 'lines' in block for line in block['lines'] for span in line['spans'] if span['text'].strip()]
if [span['text'] for span in spans]!=item['expectedText']: raise SystemExit('PDF标题未保留为两个独立文字片段')
for index,span in enumerate(spans):
 x0,y0,x1,y1=span['bbox']; mask=item['titleMasksPx'][index]
 bbox_px=[x0*item['body']['widthPx']/page.rect.width,y0*item['body']['heightPx']/page.rect.height,x1*item['body']['widthPx']/page.rect.width,y1*item['body']['heightPx']/page.rect.height]
 if bbox_px[0]<mask[0] or bbox_px[1]<mask[1] or bbox_px[2]>mask[2] or bbox_px[3]>mask[3]: raise SystemExit('矢量标题越出对应标题遮罩')
fonts=page.get_fonts(full=True)
embedded=[]
for font in fonts:
 data=doc.extract_font(font[0])[3]
 embedded.append({'type':font[2],'name':font[3],'embedded':bool(data)})
if not any(f['type']=='Type0' and item['fontName'] in f['name'] and f['embedded'] for f in embedded): raise SystemExit('缺少嵌入的指定Type0字体')
images=page.get_images(full=True)
if len(images)!=1: raise SystemExit('候选PDF必须包含且仅包含一张正文图像')
image_bytes=doc.extract_image(images[0][0])['image']
from io import BytesIO
embedded_image=Image.open(BytesIO(image_bytes))
embedded_pixels=np.asarray(embedded_image)
if embedded_pixels.ndim==3 and (embedded_pixels.shape[2]<3 or not (np.array_equal(embedded_pixels[:,:,0],embedded_pixels[:,:,1]) and np.array_equal(embedded_pixels[:,:,1],embedded_pixels[:,:,2]))): raise SystemExit('PDF正文图像包含彩色像素')
if embedded_pixels.ndim not in (2,3): raise SystemExit('PDF正文图像通道格式不受支持')
embedded_gray=embedded_image.convert('L')
body_image=Image.open(body).convert('L')
if embedded_gray.size!=body_image.size or not np.array_equal(np.asarray(embedded_gray),np.asarray(body_image)): raise SystemExit('嵌入正文图像与绑定的原工作台灰度图不逐像素一致')
baseline_image=Image.open(baseline).convert('L')
if baseline_image.size!=body_image.size or not np.array_equal(np.asarray(baseline_image),np.asarray(body_image)): raise SystemExit('PDF正文与当前工作台原输出不逐像素一致')
source_doc=fitz.open(source_pdf)
if len(source_doc)!=1 or len(source_doc[0].get_images(full=True))!=1: raise SystemExit('原稿PDF结构与登记来源不符')
pix=page.get_pixmap(dpi=dpi,colorspace=fitz.csRGB,alpha=False)
rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
if not (np.array_equal(rgb[:,:,0],rgb[:,:,1]) and np.array_equal(rgb[:,:,1],rgb[:,:,2])): raise SystemExit('PDF页面存在彩色渲染像素')
actual=rgb[:,:,0]
base=fitz.open(); bp=base.new_page(width=page.rect.width,height=page.rect.height); bp.insert_image(bp.rect,filename=baseline)
bpix=bp.get_pixmap(dpi=dpi,colorspace=fitz.csRGB,alpha=False)
base_rgb=np.frombuffer(bpix.samples,dtype=np.uint8).reshape(bpix.height,bpix.width,3)
expected=base_rgb[:,:,0]
if actual.shape!=expected.shape: raise SystemExit('候选渲染尺寸与正文基线不符')
allowed=np.zeros(actual.shape,dtype=bool)
for x0,y0,x1,y1 in item['titleMasksPx']:
 left=max(0,math.floor(x0*page.rect.width/body_image.width*dpi/72)); right=min(actual.shape[1],math.ceil(x1*page.rect.width/body_image.width*dpi/72))
 top=max(0,math.floor(y0*page.rect.height/body_image.height*dpi/72)); bottom=min(actual.shape[0],math.ceil(y1*page.rect.height/body_image.height*dpi/72))
 if left>=right or top>=bottom: raise SystemExit('标题遮罩无效')
 allowed[top:bottom,left:right]=True
diff=np.abs(actual.astype(np.int16)-expected.astype(np.int16)); outside=diff[~allowed]
if int((outside>0).sum())!=0: raise SystemExit('标题遮罩外渲染像素发生变化')
for row in item['annotations']:
 x,y=row['x'],row['y']
 if not any(x0<=x<=x1 and y0<=y<=y1 for x0,y0,x1,y1 in item['titleMasksPx']): raise SystemExit('反馈位置没有落入对应标题区域')
data=bytes(pix.samples)
return_value={'pageCount':len(doc),'pageWidthMm':width_mm,'pageHeightMm':height_mm,'textExtractedExactly':lines,'titleTextBoundsInsideMasks':len(spans),'fonts':embedded,'embeddedImageCount':len(images),'embeddedImageMode':embedded_image.mode,'embeddedImageHasColorPixels':False,'renderDpi':dpi,'renderPixels':[pix.width,pix.height],'renderColorChannelsEqual':True,'changedPixelsOutsideTitleMasks':int((outside>0).sum()),'annotationsInsideTitleMasks':len(item['annotations'])}
print(json.dumps(return_value,ensure_ascii=False))`;

export function verifyFeedbackPdfCandidate({figure,record,item,manifestPath,candidateRoot,attemptDir,python,articleWord}){
 if(!figure||!record||!item||!manifestPath||!candidateRoot||!attemptDir||!python)throw Error('PDF反馈候选检查缺少工作台上下文或工具');
 if(figure.reviewVersion!==record.version||figure.feedback?.revision!==record.feedbackRevision||feedbackHash(figure.feedback)!==record.feedbackHash)throw Error('用户反馈revision或图稿版本已变化');
 const currentOutputs=figure.outputs.map(o=>({number:o.number,path:o.file.path,sha256:digest(o.file.path)}));
 if(JSON.stringify(currentOutputs)!==JSON.stringify(record.baseOutputs))throw Error('工作台原输出路径或哈希已变化');
 for(const [index,hash] of attachmentHashes(figure.feedback).entries())if(hash!==record.feedbackAttachmentHashes[index])throw Error('用户反馈附件已变化');
 const manifest=inside(candidateRoot,manifestPath),audit=JSON.parse(fs.readFileSync(manifest,'utf8'));
 if(!samePath(manifestPath,manifest))throw Error('候选清单路径包含符号链接');
 const entry=audit.items?.find(row=>String(row.figure)===String(figure.number));
 if(!entry||String(item.figure)!==String(figure.number)||stable(item)!==stable(entry))throw Error('PDF候选回执不对应当前图号');
 if(entry.feedbackRevision!==record.feedbackRevision||entry.feedbackSha256!==record.feedbackHash||entry.currentReviewVersion!==record.version)throw Error('候选manifest未绑定当前反馈revision、批注内容与稿件版本');
 if(!Array.isArray(entry.annotations)||entry.annotations.length!==2||!Array.isArray(entry.expectedText)||entry.expectedText.length!==2||!Array.isArray(entry.titleMasksPx)||entry.titleMasksPx.length!==2||entry.dpi!==300)throw Error('PDF候选缺少完整标题/300dpi检查契约');
 const feedbackPoints=figure.feedback.points||[];
 if(feedbackPoints.length!==entry.annotations.length||feedbackPoints.some(point=>point.text!=='矢量文字'||point.output!==String(figure.number)))throw Error('当前反馈批注已变化，不能按PDF候选登记');
 const source=figure.productionRoute?.sourceReview?.selected,routeWord=figure.productionRoute?.sourceReview?.word;
 if(!source||!routeWord||!articleWord?.path||!record.articleWord)throw Error('缺少当前图源或稿件Word绑定');
 const candidate=inside(candidateRoot,entry.pdf.path),body=entry.body.path,sourcePdf=entry.sourcePdf.path,baseline=entry.baseline.path;
 if(digest(candidate)!==entry.pdf.sha256||digest(body)!==entry.body.sha256||digest(sourcePdf)!==entry.sourcePdf.sha256||digest(baseline)!==entry.baseline.sha256)throw Error('候选、图源、原稿PDF或当前输出哈希不符');
 if(!samePath(source.path,entry.source.path)||source.sha256!==entry.source.sha256||digest(source.path)!==source.sha256)throw Error('候选图源与当前制作路线来源不一致');
 const sourcePdfRef=figure.productionRoute.sourceReview.candidates?.find(row=>samePath(row.path,sourcePdf)&&row.sha256===entry.sourcePdf.sha256);
 if(!sourcePdfRef)throw Error('候选源PDF与当前制作路线来源登记不一致');
 const baseOutput=record.baseOutputs.find(row=>row.number===String(figure.number));
 if(!baseOutput||!samePath(baseOutput.path,baseline)||baseOutput.sha256!==entry.baseline.sha256)throw Error('候选正文基线未绑定当前工作台原输出');
 const wordHash=digest(articleWord.path);
 if(!samePath(routeWord.path,articleWord.path)||routeWord.sha256!==wordHash||!samePath(record.articleWord.path,articleWord.path)||record.articleWord.sha256!==wordHash)throw Error('候选稿件Word与当前Word绑定不一致');
 if(!record.sources.some(row=>samePath(row.path,source.path)&&row.sha256===source.sha256)||!record.sources.some(row=>samePath(row.path,articleWord.path)&&row.sha256===wordHash))throw Error('终审来源未绑定当前图源与Word');
 for(const row of record.sources)if(digest(row.path)!==row.sha256)throw Error('反馈修订源件哈希已变化');
 const annotations=feedbackPoints.map(point=>({x:Math.round(point.x*entry.body.widthPx),y:Math.round(point.y*entry.body.heightPx)}));
 if(entry.annotations.some((row,index)=>row.id!==feedbackPoints[index].id||row.text!==feedbackPoints[index].text||row.output!==feedbackPoints[index].output||row.token!==feedbackPoints[index].token||row.sha256!==feedbackPoints[index].sha256||row.title!==entry.expectedText[index]||row.x!==annotations[index].x||row.y!==annotations[index].y))throw Error('候选标题与当前批注位置、身份或文字绑定不一致');
 const contract={...entry,bindings:{candidate:{sha256:entry.pdf.sha256},body:{sha256:entry.body.sha256},sourcePdf:{sha256:entry.sourcePdf.sha256},word:{sha256:wordHash},baseline:{sha256:entry.baseline.sha256}}};
 let processing;
 try{processing=JSON.parse(execFileSync(python,['-c',pdfAuditScript,candidate,body,sourcePdf,articleWord.path,baseline,JSON.stringify(contract)],{windowsHide:true,encoding:'utf8',timeout:180000,maxBuffer:1024*1024,env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'}}));}
 catch(error){throw Error('PDF候选真实检查失败：'+String(error.stderr||error.stdout||error.message).slice(0,1500));}
 fs.mkdirSync(attemptDir,{recursive:true});
 const staged=path.join(attemptDir,'candidate-'+figure.number+'.pdf');
 if(fs.existsSync(staged)){if(digest(staged)!==entry.pdf.sha256)throw Error('隔离候选目录已有不同PDF');}
 else fs.copyFileSync(candidate,staged,fs.constants.COPYFILE_EXCL);
 if(digest(staged)!==entry.pdf.sha256)throw Error('复制PDF候选后哈希不符');
 const check={kind:'feedback-vector-pdf',status:'candidate',manualStatus:'pending',figureId:figure.id,feedbackRevision:record.feedbackRevision,feedbackSha256:record.feedbackHash,feedbackAttachmentSha256:record.feedbackAttachmentHashes,manifestSha256:digest(manifest),baseOutputs:record.baseOutputs,source:{path:source.path,sha256:source.sha256},word:{path:articleWord.path,sha256:wordHash},sourcePdf:{path:sourcePdf,sha256:entry.sourcePdf.sha256},processing,outputs:[{number:figure.number,path:staged,sha256:digest(staged),preview:null}],semanticReview:'pending-user-final-review'};
 return {check,outputs:check.outputs};
}

const replayScript=`import json,sys,hashlib
from pathlib import Path
from PIL import Image,ImageChops,ImageOps,ImageStat
source,png,jpg,audit=sys.argv[1:]
item=json.loads(audit)
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
if sha(source)!=item['sourceSha256']: raise SystemExit('源图SHA256与回执不符')
original=Image.open(source).convert('RGB'); expected_source=item['sourceSizePx']
if list(original.size)!=expected_source: raise SystemExit('源图尺寸与回执不符')
x0,y0,x1,y1=item['cropBoundsLTRB']; w,h=original.size
if not (0<=x0<x1<=w and 0<=y0<y1<=h): raise SystemExit('裁剪边界越过源图')
c=item['cornerCleanup'];rx0,ry0,rx1,ry1=c['regionLTRB']
if not (0<=rx0<rx1<=w and 0<=ry0<ry1<=h): raise SystemExit('清理区域越过源图')
allowed_rules={
 'replace only neutral dark source pixels (max-min channel <=7; luminance <145) with white before grayscale',
 '(max(R,G,B)-min(R,G,B) <= 7) AND luminance < 145 AND pixel within cleanup region with luminance uint32: (R*299 + G*587 + B*114) // 1000; set matching source pixel white before crop/grayscale'
}
if c['rule'] not in allowed_rules: raise SystemExit('清理操作不在可重放白名单')
candidate=Image.open(png).convert('RGB');actual_jpg=Image.open(jpg).convert('RGB')
px=original.load();hits=0;changed=0
for y in range(ry0,ry1):
 for x in range(rx0,rx1):
  r,g,b=px[x,y]
  if max(r,g,b)-min(r,g,b)<=7 and (r*299+g*587+b*114)//1000<145:
   hits+=1
   if (r,g,b)!=(255,255,255):changed+=1
   px[x,y]=(255,255,255)
if hits!=c['pixelsReplaced']: raise SystemExit('清理像素命中数量与回执不符')
replayed=ImageOps.grayscale(original.crop((x0,y0,x1,y1))).convert('RGB')
if list(replayed.size)!=item['candidateSizePx'] or candidate.size!=replayed.size: raise SystemExit('裁剪输出尺寸不符')
if ImageChops.difference(replayed,candidate).getbbox() is not None: raise SystemExit('PNG与源/处理规则的重放结果不一致')
if actual_jpg.size!=candidate.size: raise SystemExit('JPG与PNG尺寸不一致')
for image in (candidate,actual_jpg):
 extrema=image.getextrema()
 if extrema[0]!=extrema[1] or extrema[1]!=extrema[2]: raise SystemExit('输出不是中性灰度图')
mean=ImageStat.Stat(ImageChops.difference(candidate,actual_jpg)).mean[0]
if mean>0.5: raise SystemExit('JPG与逐像素核验PNG差异过大')
print(json.dumps({'sourceDimensions':'passed','sourceSha256':sha(source),'processingReplay':'passed','cleanupAlgorithm':'declared-rule','cleanupPixelsReplayed':hits,'cleanupPixelsDeclared':c['pixelsReplaced'],'cleanupPixelCountMatch':True,'cleanupPixelsActuallyChanged':changed,'cropBounds':item['cropBoundsLTRB'],'outputDimensions':'passed','pngExactReplay':'passed','grayscale':'passed','jpgPngMeanAbsoluteDifference':mean}))`;

export function verifyFeedbackCandidate({figure,record,item,manifestPath,candidateRoot,attemptDir,python,articleWord}){
 if(!figure||!record||!item||!manifestPath||!candidateRoot||!attemptDir||!python)throw Error('反馈候选检查缺少工作台上下文或工具');
 if(figure.reviewVersion!==record.version||figure.feedback?.revision!==record.feedbackRevision||feedbackHash(figure.feedback)!==record.feedbackHash)throw Error('用户反馈revision或图稿版本已变化');
 const currentOutputs=figure.outputs.map(o=>({number:o.number,path:o.file.path,sha256:digest(o.file.path)}));
 if(JSON.stringify(currentOutputs)!==JSON.stringify(record.baseOutputs))throw Error('工作台原输出路径或哈希已变化');
 for(const [index,hash] of attachmentHashes(figure.feedback).entries())if(hash!==record.feedbackAttachmentHashes[index])throw Error('用户反馈附件已变化');
 const manifest=inside(candidateRoot,manifestPath);
 if(!samePath(manifestPath,manifest))throw Error('候选清单路径包含符号链接');
 const audit=JSON.parse(fs.readFileSync(manifest,'utf8'));
 const entry=audit.items?.find(row=>String(row.figure)===String(figure.number));
 if(!entry||String(item.figure)!==String(figure.number)||stable(item)!==stable(entry))throw Error('候选裁剪回执不对应当前图号');
 const selected=figure.productionRoute?.sourceReview?.selected;
 if(!selected||!samePath(selected.path,entry.source)||selected.sha256!==entry.sourceSha256)throw Error('候选源图与当前制作路线来源不一致');
 const routeWord=figure.productionRoute?.sourceReview?.word;
 if(!routeWord||!articleWord?.path||!record.articleWord)throw Error('缺少当前稿件Word与制作路线Word绑定');
 const currentWordHash=digest(articleWord.path);
 if(!samePath(routeWord.path,articleWord.path)||routeWord.sha256!==currentWordHash)throw Error('制作路线Word与当前稿件Word路径或哈希不一致');
 if(!samePath(record.articleWord.path,articleWord.path)||record.articleWord.sha256!==currentWordHash)throw Error('终审记录绑定的Word路径或哈希已变化');
 if(!record.sources.some(source=>samePath(source.path,routeWord.path)&&source.sha256===routeWord.sha256))throw Error('终审来源未绑定同一Word文件');
 for(const source of record.sources)if(digest(source.path)!==source.sha256)throw Error('反馈修订源件哈希已变化');
 const png=inside(candidateRoot,entry.png.path),jpg=inside(candidateRoot,entry.jpg.path);
 if(digest(entry.source)!==entry.sourceSha256||digest(png)!==entry.png.sha256||digest(jpg)!==entry.jpg.sha256)throw Error('候选源图或输出哈希不符');
 fs.mkdirSync(attemptDir,{recursive:true});
 const stagedPng=path.join(attemptDir,'candidate-'+figure.number+'.png'),stagedJpg=path.join(attemptDir,'candidate-'+figure.number+'.jpg');
 for(const [source,target,expected] of [[png,stagedPng,entry.png.sha256],[jpg,stagedJpg,entry.jpg.sha256]]){
  if(fs.existsSync(target)){if(digest(target)!==expected)throw Error('隔离候选目录已有不同文件');}
  else fs.copyFileSync(source,target,fs.constants.COPYFILE_EXCL);
  if(digest(target)!==expected)throw Error('复制候选文件后哈希不符');
 }
 let processCheck;
 try{processCheck=JSON.parse(execFileSync(python,['-c',replayScript,entry.source,stagedPng,stagedJpg,JSON.stringify(entry)],{windowsHide:true,encoding:'utf8',timeout:120000,maxBuffer:1024*1024,env:{...process.env,PYTHONUTF8:'1',PYTHONIOENCODING:'utf-8'}}));}
 catch(error){throw Error('候选真实重放失败：'+String(error.stderr||error.stdout||error.message).slice(0,1500));}
 const check={kind:'feedback-raster-replay',status:'candidate',manualStatus:'pending',figureId:figure.id,feedbackRevision:record.feedbackRevision,feedbackSha256:record.feedbackHash,feedbackAttachmentSha256:record.feedbackAttachmentHashes,manifestSha256:digest(manifest),baseOutputs:record.baseOutputs,source:{path:entry.source,sha256:entry.sourceSha256},processing:processCheck,outputs:[{number:figure.number,path:stagedJpg,sha256:digest(stagedJpg),preview:stagedPng,previewSha256:digest(stagedPng)}],semanticCropIntent:'not-automatically-verified; pending user final review'};
 return {check,outputs:check.outputs};
}

export {feedbackHash,attachmentHashes};
