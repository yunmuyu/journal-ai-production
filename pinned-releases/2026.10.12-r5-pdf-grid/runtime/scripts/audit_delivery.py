"""Verify figure-page identity, physical scale, font sizes and RGB content against single PDFs."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,re,sys
from PIL import Image,ImageChops,ImageFilter
import numpy as np
import pypdfium2 as pdfium
import pdfplumber
from pypdf import PdfReader

DELIVERY_RULE_VERSION='jfw-delivery-2026-10-11-v1'
COLOR_RULE_VERSION='jfw-color-2026-10-11-v1'
NEUTRAL_TOLERANCE=2
COLOR_DISTANCE_TOLERANCE=10
COLOR_MISMATCH_FRACTION=0.005
request=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
directory=Path(request['directory']);directory.mkdir(parents=True,exist_ok=True)
sha=lambda file:hashlib.sha256(Path(file).read_bytes()).hexdigest()
summary=pdfium.PdfDocument(request['pdf']);summary_boxes=PdfReader(request['pdf']);summary_text=pdfplumber.open(request['pdf']);scale=300/72
items=request['items'];results=[];page_images={};page_sizes={};allowed_color={}
for index in range(len(summary)):
 page=summary[index];page_sizes[index]=page.get_size();allowed_color[index]=[];page.close()

def compact(value):return re.sub(r'\s+','',value)
def font_name(value):return re.sub(r'^[A-Z]{6}\+','',value or '')
def glyphs(page,physical_size,box=None):
 factor=physical_size[0]/page.width;output=[]
 for c in page.chars:
  x=(c['x0']+c['x1'])/2*factor;y=(c['top']+c['bottom'])/2*factor
  if box and not (box[0]-0.1<=x<=box[2]+0.1 and box[1]-0.1<=y<=box[3]+0.1):continue
  if not box and not (-0.1<=x<=physical_size[0]+0.1 and -0.1<=y<=physical_size[1]+0.1):continue
  if not c['text'].strip():continue
  output.append((c['text'],font_name(c.get('fontname')),float(c['size'])*factor))
 return output

def font_inventory_matches(expected,actual):
 a=defaultdict(list);b=defaultdict(list)
 for text,font,size in expected:a[(text,font)].append(size)
 for text,font,size in actual:b[(text,font)].append(size)
 if set(a)!=set(b):return False
 return all(len(a[key])==len(b[key]) and all(abs(x-y)<=0.05 for x,y in zip(sorted(a[key]),sorted(b[key]),strict=True)) for key in a)

def preserved_rgb(expected,actual,thin_expected=None,thin_actual=None):
 source8=expected;target8=actual;h,w=expected.height,expected.width;count=0;bad=0
 for start in range(0,h,64):
  end=min(start+64,h);height=end-start;lo=max(0,start-1);hi=min(h,end+1);padding=((1 if start==0 else 0,1 if end==h else 0),(1,1),(0,0))
  source=np.asarray(source8.crop((0,start,w,end)),dtype=np.int16);padded=np.pad(np.asarray(target8.crop((0,lo,w,hi))),padding,constant_values=255).astype(np.int16);distance=np.full((height,w),255,dtype=np.int16)
  for y in range(3):
   for x in range(3):np.minimum(distance,np.max(np.abs(source-padded[y:y+height,x:x+w]),axis=2),out=distance)
  local=np.pad(np.asarray(source8.crop((0,lo,w,hi))),padding,constant_values=255).astype(np.int16);low=source.copy();high=source.copy()
  for y in range(3):
   for x in range(3):np.minimum(low,local[y:y+height,x:x+w],out=low);np.maximum(high,local[y:y+height,x:x+w],out=high)
  ink=(np.min(source,axis=2)<245)&(np.max(high-low,axis=2)<=8);count+=int(np.count_nonzero(ink));bad+=int(np.count_nonzero(ink&(distance>COLOR_DISTANCE_TOLERANCE)))
  del source,padded,distance,local,low,high,ink
 del source8,target8
 fraction=bad/count if count else 0
 result={'ok':count>0 and fraction<=COLOR_MISMATCH_FRACTION,'method':'pdfium-rgb-300dpi-solid-interior-phase-1px-v1','channelTolerance':COLOR_DISTANCE_TOLERANCE,'phaseTolerancePixels':1,'sampleRule':'nonwhite pixels with 3x3 local per-channel range <=8; antialias edges excluded','maxMismatchFraction':COLOR_MISMATCH_FRACTION,'checkedInkPixels':count,'mismatchedInkPixels':bad,'mismatchFraction':fraction}
 if count:return result
 if thin_expected is None or thin_actual is None:return thin_rgb(expected,actual)
 if abs(thin_expected.width-expected.width)>1 or abs(thin_expected.height-expected.height)>1:return {**result,'error':'Thin full source differs by more than1px'}
 return {**thin_rgb(thin_expected,thin_actual),'solidInteriorSamples':0,'roundedCropPixels':list(expected.size),'fullSourcePixels':list(thin_expected.size)}

def thin_rgb(expected,actual):
 source8=expected;target8=actual
 if source8.size!=target8.size:return {'ok':False,'method':'pdfium-rgb-300dpi-thin-coverage-phase-1px-v1','error':'Thin comparison shapes differ'}
 h,w=expected.height,expected.width;count=target_count=bad=target_bad=local_bad=local_target_bad=0;source_mass=np.zeros(3);target_mass=np.zeros(3);source_density=target_density=0.0;source_xy=np.zeros(2);target_xy=np.zeros(2)
 def deficit_rows(v,start,end,columns):
  lo=max(0,start);hi=min(h,end);return 255-np.pad(np.asarray(v.crop((0,lo,w,hi))),((max(0,-start),max(0,end-h)),(columns,columns),(0,0)),constant_values=255).astype(np.float64)
 def local_mean(v,start,end):
  lo=max(0,start);hi=min(h,end);pad=deficit_rows(v,lo-3,hi+3,3);cs=np.pad(pad,((1,0),(1,0),(0,0))).cumsum(0).cumsum(1);means=(cs[7:,7:]-cs[:-7,7:]-cs[7:,:-7]+cs[:-7,:-7])/49;return np.pad(means,((max(0,-start),max(0,end-h)),(2,2),(0,0)))
 for start in range(0,h,64):
  end=min(start+64,h);height=end-start;source=deficit_rows(source8,start,end,0);target=deficit_rows(target8,start,end,0);source_strength=np.max(source,axis=2);target_strength=np.max(target,axis=2);source_ink=source_strength>10;target_ink=target_strength>10;count+=int(np.count_nonzero(source_ink));target_count+=int(np.count_nonzero(target_ink))
  source_local=np.zeros_like(source);target_local=np.zeros_like(target);sp=deficit_rows(source8,start-1,end+1,1);tp=deficit_rows(target8,start-1,end+1,1)
  for y in range(3):
   for x in range(3):source_local+=sp[y:y+height,x:x+w];target_local+=tp[y:y+height,x:x+w]
  tolerance=COLOR_DISTANCE_TOLERANCE/255;bad+=int(np.count_nonzero(source_ink&np.any(source-target_local>source_strength[:,:,None]*tolerance,axis=2)));target_bad+=int(np.count_nonzero(target_ink&np.any(target-source_local>target_strength[:,:,None]*tolerance,axis=2)))
  del source_local,target_local,sp,tp
  smp=local_mean(source8,start-2,end+2);tmp=local_mean(target8,start-2,end+2);sm=smp[2:2+height,2:2+w];tm=tmp[2:2+height,2:2+w];sd=np.full((height,w),np.inf);td=sd.copy()
  for dy in [-1,-.5,0,.5,1]:
   for dx in [-1,-.5,0,.5,1]:
    iy=int(np.floor(dy));ix=int(np.floor(dx));fy=dy-iy;fx=dx-ix;y=2+iy;x=2+ix
    for base,ref,dist in [(tmp,sm,sd),(smp,tm,td)]:
     shifted=(1-fy)*((1-fx)*base[y:y+height,x:x+w]+fx*base[y:y+height,x+1:x+1+w])+fy*((1-fx)*base[y+1:y+1+height,x:x+w]+fx*base[y+1:y+1+height,x+1:x+1+w]);np.minimum(dist,np.max(np.abs(ref-shifted),axis=2),out=dist)
  local_bad+=int(np.count_nonzero(source_ink&(sd>COLOR_DISTANCE_TOLERANCE)));local_target_bad+=int(np.count_nonzero(target_ink&(td>COLOR_DISTANCE_TOLERANCE)));source_mass+=np.sum(source,axis=(0,1));target_mass+=np.sum(target,axis=(0,1));source_density+=float(np.sum(source_strength));target_density+=float(np.sum(target_strength));yy,xx=np.indices((height,w));yy+=start;source_xy+=np.array([np.sum(xx*source_strength),np.sum(yy*source_strength)]);target_xy+=np.array([np.sum(xx*target_strength),np.sum(yy*target_strength)])
  del source,target,source_strength,target_strength,source_ink,target_ink,smp,tmp,sm,tm,sd,td,base,ref,dist,shifted,yy,xx
 if not count or not target_count:return {'ok':False,'method':'pdfium-rgb-300dpi-thin-coverage-phase-1px-v1','checkedInkPixels':count,'checkedTargetInkPixels':target_count,'error':'No comparable RGB ink samples'}
 fraction=max(bad/count,target_bad/target_count);local_fraction=max(local_bad/count,local_target_bad/target_count);mass_errors=np.abs(source_mass-target_mass)*255/source_density;centroid=(source_xy/source_density-target_xy/target_density).tolist()
 return {'ok':local_fraction<=COLOR_MISMATCH_FRACTION and fraction<=COLOR_MISMATCH_FRACTION and bool(np.all(mass_errors<=COLOR_DISTANCE_TOLERANCE)),'method':'pdfium-rgb-300dpi-thin-coverage-phase-1px-v1','channelTolerance':COLOR_DISTANCE_TOLERANCE,'phaseTolerancePixels':1,'sampleRule':'Both directions: 7x7 local RGB mean comparison within +/-1px using half-pixel interpolation; 3x3 RGB ink deficit support within1px; per-channel total RGB ink conservation normalized by source full-black-equivalent coverage','maxMismatchFraction':COLOR_MISMATCH_FRACTION,'checkedInkPixels':count,'checkedTargetInkPixels':target_count,'mismatchedInkPixels':bad,'mismatchedTargetInkPixels':target_bad,'mismatchFraction':fraction,'localWindowPixels':7,'localMismatchedInkPixels':local_bad,'localMismatchedTargetInkPixels':local_target_bad,'localMismatchFraction':local_fraction,'sourceInkMassRGB':source_mass.tolist(),'targetInkMassRGB':target_mass.tolist(),'normalizedChannelMassErrors':mass_errors.tolist(),'centroidDeltaPixels':centroid,'centroidIsDiagnosticOnly':True,'comparisonPixels':[w,h],'fallbackOnlySolidSampleCountZero':True}


for item in items:
 placement=item['placement'];page_index=placement['page']-1
 if page_index not in page_sizes:results.append({'name':placement.get('name'),'page':page_index+1,'ok':False,'error':'Missing declared page'});continue
 page=summary[page_index];page_images[page_index]=page.render(scale=scale).to_pil().convert('RGB');page_images[page_index].save(directory/f'pdf-page-{page_index+1}.png');page.close()
 x0,y0,x1,y1=placement['bounds'];origin,top,right,bottom=placement['artboardRect'];crop_box=tuple(round(value*scale) for value in (x0-origin,top-y0,x1-origin,top-y1));actual_rgb=page_images[page_index].crop(crop_box)
 original=pdfium.PdfDocument(item['pdf']);source_page=original[0];source_size=source_page.get_size();source_rgb=source_page.render(scale=scale).to_pil().convert('RGB');expected_rgb=Image.new('RGB',actual_rgb.size,(255,255,255));expected_rgb.paste(source_rgb,(0,0))
 expected=expected_rgb.convert('L');actual=actual_rgb.convert('L');expected_ink=expected.point(lambda v:255 if v<160 else 0);actual_ink=actual.point(lambda v:255 if v<160 else 0);covered=ImageChops.multiply(expected_ink,actual_ink.filter(ImageFilter.MaxFilter(5)));total=sum(expected_ink.histogram()[1:]);recall=sum(covered.histogram()[1:])/total if total else 1
 media=summary_boxes.pages[page_index].mediabox;unit=float(summary_boxes.pages[page_index].get('/UserUnit',1));media_size=(float(media.width)*unit,float(media.height)*unit)
 if summary_boxes.pages[page_index].rotation%180:media_size=media_size[::-1]
 page_size_ok=all(abs(a-b)<=0.1 for a,b in zip(media_size,(right-origin,top-bottom),strict=True)) and all(abs(a-b)<=0.1 for a,b in zip(page_sizes[page_index],(right-origin,top-bottom),strict=True))
 source_size_ok=all(abs(a-b)<=0.1 for a,b in zip(source_size,(x1-x0,y0-y1),strict=True));bounds_ok=page_size_ok and source_size_ok and x0-origin>=-0.1 and x1<=right+0.1 and y0<=top+0.1 and y1>=bottom-0.1
 identity_ok=bool(item.get('author')) and bool(re.fullmatch(r'(?:4-1|\d+(?:\.\d+)?)',str(item.get('number','')))) and placement.get('name')==item['author']+'-图'+str(item['number']) and item.get('columnLabel') in ('单栏','双栏')
 label_bounds=placement.get('labelBounds');badge_bounds=placement.get('badgeBounds');label_ok=False;outside_ok=False;label_actual=''
 if identity_ok and label_bounds:
  lx0,ly0,lx1,ly1=label_bounds;label_box=(lx0-origin,top-ly0,lx1-origin,top-ly1);text_page=summary_text.pages[page_index];factor=page_sizes[page_index][0]/text_page.width;selected=[c for c in text_page.chars if label_box[0]-0.5<=(c['x0']+c['x1'])/2*factor<=label_box[2]+0.5 and label_box[1]-0.5<=(c['top']+c['bottom'])/2*factor<=label_box[3]+0.5];label_actual=''.join(c['text'] for c in selected);label_ok=compact(label_actual)==compact(item['author']+' 图'+str(item['number'])+' · '+item['columnLabel']);lb=badge_bounds or label_bounds;outside_ok=lb[3]>=y0-0.1 or lb[1]<=y1+0.1 or lb[2]<=x0+0.1 or lb[0]>=x1-0.1
 original_text=pdfplumber.open(item['pdf']);source_glyphs=glyphs(original_text.pages[0],source_size);actual_glyphs=glyphs(summary_text.pages[page_index],page_sizes[page_index],(x0-origin,top-y0,x1-origin,top-y1));fonts_ok=font_inventory_matches(source_glyphs,actual_glyphs);original_text.close()
 rgb=preserved_rgb(expected_rgb,actual_rgb,source_rgb,page_images[page_index].crop((crop_box[0],crop_box[1],crop_box[0]+source_rgb.width,crop_box[1]+source_rgb.height)));policy=item.get('colorPolicy');arr=np.asarray(actual_rgb,dtype=np.uint8);delta=np.max(arr,axis=2)-np.min(arr,axis=2);colored=int(np.count_nonzero(delta>NEUTRAL_TOLERANCE));neutral={'method':'pdfium-rgb-300dpi-neutral-v1','tolerance':NEUTRAL_TOLERANCE,'coloredPixels':colored,'totalPixels':int(delta.size),'maxChannelDelta':int(delta.max()) if delta.size else 0,'ok':colored==0}
 policy_ok=policy=='source-color' or policy=='grayscale' and neutral['ok']
 if policy=='source-color':
  cx0,cy0,cx1,cy1=crop_box;allowed_color[page_index].append(crop_box)
 hash_ok=bool(item.get('pdfHash')) and sha(item['pdf'])==item['pdfHash'];single_page_ok=len(original)==1;identity_binding_ok=bool(item.get('aiHash')) and bool(item.get('outputHash')) and bool(item.get('colorAuditHash')) and sha(item['ai'])==item['aiHash'] and sha(item['output'])==item['outputHash']
 results.append({'name':placement['name'],'author':item.get('author'),'number':str(item.get('number','')),'columnLabel':item.get('columnLabel'),'page':page_index+1,'pdfHash':sha(item['pdf']),'aiHash':item.get('aiHash'),'outputHash':item.get('outputHash'),'colorAuditHash':item.get('colorAuditHash'),'inkRecall':recall,'boundsOk':bounds_ok,'sourcePhysicalSizePt':list(source_size),'summaryContentSizePt':[x1-x0,y0-y1],'fullNumberOk':identity_ok and label_ok,'labelText':label_actual,'badgeOutsideContent':outside_ok,'sourceGlyphCount':len(source_glyphs),'summaryGlyphCount':len(actual_glyphs),'fontSizesPreserved':fonts_ok,'sourceMinGlyphPt':min((c[2] for c in source_glyphs),default=None),'summaryMinGlyphPt':min((c[2] for c in actual_glyphs),default=None),'rgbPreservation':rgb,'colorPolicy':policy,'neutralAudit':neutral,'sourceHashOk':hash_ok,'singlePageSource':single_page_ok,'ok':recall>=0.96 and bounds_ok and identity_ok and label_ok and outside_ok and fonts_ok and rgb['ok'] and policy_ok and hash_ok and single_page_ok and identity_binding_ok})
 source_page.close();original.close();del page_images[page_index],source_rgb,expected_rgb,actual_rgb,expected,actual,expected_ink,actual_ink,covered,arr,delta

page_colors=[]
for index in page_sizes:
 page=summary[index];img=page.render(scale=scale).to_pil().convert('RGB');page.close();allowed=np.zeros((img.height,img.width),dtype=bool)
 for cx0,cy0,cx1,cy1 in allowed_color[index]:allowed[max(0,cy0):min(cy1,allowed.shape[0]),max(0,cx0):min(cx1,allowed.shape[1])]=True
 arr=np.asarray(img,dtype=np.uint8);delta=np.max(arr,axis=2)-np.min(arr,axis=2);unapproved=(delta>NEUTRAL_TOLERANCE)&~allowed;bad=int(np.count_nonzero(unapproved));page_colors.append({'page':index+1,'method':'pdfium-rgb-300dpi-neutral-v1','tolerance':NEUTRAL_TOLERANCE,'unapprovedColoredPixels':bad,'ok':bad==0});del img,arr,delta,unapproved,allowed
page_count_ok=len(page_sizes)==len(items) and sorted(item['placement']['page'] for item in items)==list(range(1,len(items)+1))
identity_keys=[(item.get('author'),str(item.get('number'))) for item in items];set_ok=len(set(identity_keys))==len(identity_keys);versions_ok=request.get('ruleVersion')==DELIVERY_RULE_VERSION and request.get('colorRuleVersion')==COLOR_RULE_VERSION and request.get('layout')=='figure-pages';summary_hash=sha(request['pdf']);summary_hash_ok=request.get('pdfHash')==summary_hash;summary_ai_hash=sha(request['ai']);summary_hash_ok=summary_hash_ok and request.get('aiHash')==summary_ai_hash
result={'ruleVersion':DELIVERY_RULE_VERSION,'colorRuleVersion':COLOR_RULE_VERSION,'pdfHash':summary_hash,'aiHash':summary_ai_hash,'ok':versions_ok and summary_hash_ok and page_count_ok and set_ok and all(x['ok'] for x in results) and all(x['ok'] for x in page_colors),'versionsOk':versions_ok,'summaryHashOk':summary_hash_ok,'pageCountOk':page_count_ok,'exportItemSetOk':set_ok,'pages':len(page_sizes),'figures':results,'pageColorAudit':page_colors}
summary_text.close();summary.close();(directory/'summary-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False));sys.exit(0 if result['ok'] else 2)
