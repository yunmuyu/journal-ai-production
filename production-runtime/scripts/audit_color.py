import argparse,hashlib,io,json,sys
from pathlib import Path
from PIL import Image,ImageChops,ImageCms
import pypdfium2 as pdfium
import pypdf
RULE='jfw-color-2026-10-11-v1'
TOLERANCE=2
def hash_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pixels(im):
 im=im.convert('RGB');r,g,b=im.split();d=ImageChops.lighter(ImageChops.lighter(ImageChops.difference(r,g),ImageChops.difference(r,b)),ImageChops.difference(g,b));h=d.histogram();bad=sum(h[TOLERANCE+1:]);return {'coloredPixels':bad,'totalPixels':im.width*im.height,'maxChannelDelta':max(i for i,n in enumerate(h) if n),'size':list(im.size),'ok':bad==0}
def image_samples(x,resources,mask_kind=None):
 if not isinstance(x,pypdf.generic.StreamObject) or x.get('/Subtype')!='/Image':raise ValueError('Final PDF mask must be an image stream')
 if any(k in x for k in ['/F','/Matte','/SMaskInData']):raise ValueError('Final PDF linked/custom image transparency unsupported')
 if mask_kind and any(k in x for k in ['/Mask','/SMask']):raise ValueError('Final PDF nested image mask unsupported')
 if '/ImageMask' in x and not isinstance(x['/ImageMask'],pypdf.generic.BooleanObject):raise ValueError('Final PDF ImageMask must be boolean')
 stencil=bool(getattr(x.get('/ImageMask',False),'value',False))
 if mask_kind=='Mask' and not stencil or mask_kind=='SMask' and stencil:raise ValueError('Final PDF mask image type mismatch')
 if any(not isinstance(x.get(k),pypdf.generic.NumberObject) or x[k]<=0 for k in ['/Width','/Height']):raise ValueError('Final PDF image dimensions must be positive integers')
 width,height=int(x['/Width']),int(x['/Height']);bits=x.get('/BitsPerComponent',pypdf.generic.NumberObject(1)if stencil else None)
 if not isinstance(bits,pypdf.generic.NumberObject) or bits not in [1,2,4,8,16] or stencil and bits!=1:raise ValueError('Final PDF image bit depth unsupported')
 cs=x.get('/ColorSpace');cs=cs.get_object()if cs is not None else None
 def space(value,depth=0):
  if depth>8:raise ValueError('Final PDF recursive image color space')
  value=value.get_object()if value is not None else None
  if isinstance(value,pypdf.generic.NameObject)and str(value)not in ['/DeviceGray','/DeviceRGB']:
   return space(resources.get('/ColorSpace',{}).get(value),depth+1)
  if str(value)in ['/DeviceGray','/DeviceRGB']:return (1 if str(value)=='/DeviceGray'else 3,None)
  if isinstance(value,list)and len(value)==2 and str(value[0])=='/ICCBased':
   profile=value[1].get_object();count=profile.get('/N')
   if count not in [1,3]or profile.get('/Alternate',pypdf.generic.NameObject('/DeviceGray'if count==1 else'/DeviceRGB'))!=('/DeviceGray'if count==1 else'/DeviceRGB'):raise ValueError('Final PDF ICC image components/alternate unsupported')
   return int(count),ImageCms.ImageCmsProfile(io.BytesIO(profile.get_data()))
  raise ValueError('Final PDF image color encoding unsupported')
 palette=None;profile=None;indexed=False
 if stencil:
  if cs is not None:raise ValueError('Final PDF stencil mask must not have ColorSpace')
  components=1;label='stencil'
 else:
  if isinstance(cs,pypdf.generic.NameObject)and str(cs)not in ['/DeviceGray','/DeviceRGB']:cs=resources.get('/ColorSpace',{}).get(cs);cs=cs.get_object()if cs is not None else None
  if isinstance(cs,list)and len(cs)==4 and str(cs[0])=='/Indexed':
   if mask_kind or bits not in [1,2,4,8]:raise ValueError('Final PDF Indexed image/mask bit depth unsupported')
   indexed=True;components=1;count,profile=space(cs[1]);limit=cs[2]
   if not isinstance(limit,pypdf.generic.NumberObject)or not 0<=int(limit)<=255:raise ValueError('Final PDF Indexed palette bounds invalid')
   table=cs[3].get_object()
   if isinstance(table,pypdf.generic.StreamObject):table=table.get_data()
   elif hasattr(table,'original_bytes'):table=table.original_bytes
   if not isinstance(table,bytes)or len(table)!=(int(limit)+1)*count:raise ValueError('Final PDF Indexed palette length mismatch')
   palette=Image.frombytes('RGB'if count==3 else'L',(int(limit)+1,1),table)
   if profile is not None:palette=ImageCms.profileToProfile(palette,profile,ImageCms.createProfile('sRGB'),outputMode='RGB')
   palette=palette.convert('RGB');palette=[palette.getpixel((i,0))for i in range(palette.width)];profile=None;label='/Indexed'
  else:
   components,profile=space(cs);label='/ICCBased'if profile is not None else str(cs)
   if mask_kind=='SMask'and str(cs)!='/DeviceGray':raise ValueError('Final PDF image color encoding unsupported')
  if components==3 and bits!=8:raise ValueError('Final PDF RGB image bit depth unsupported')
 default=[0,(2**int(bits)-1)if indexed else 1]*components
 decode=x.get('/Decode',pypdf.generic.ArrayObject([pypdf.generic.NumberObject(v)for v in default]))
 maximum=2**int(bits)-1 if indexed else 1
 if not isinstance(decode,pypdf.generic.ArrayObject)or len(decode)!=2*components or any(not isinstance(v,(pypdf.generic.NumberObject,pypdf.generic.FloatObject))or not 0<=float(v)<=maximum for v in decode)or stencil and list(decode)not in [[0,1],[1,0]]:raise ValueError('Final PDF image/mask Decode unsupported')
 filters=x.get('/Filter',pypdf.generic.ArrayObject());filters=filters.get_object();filters=filters if isinstance(filters,list)else[filters]
 if any(str(f)not in ['/FlateDecode','/DCTDecode']for f in filters)or (stencil or mask_kind)and any(str(f)=='/DCTDecode'for f in filters):raise ValueError('Final PDF image/mask filter unsupported')
 data=x.get_data()
 if any(str(f)=='/DCTDecode'for f in filters):
  im=Image.open(io.BytesIO(data));im.load()
  if im.size!=(width,height)or im.mode!=('RGB'if components==3 else'L'):raise ValueError('Final PDF JPEG image dictionary mismatch')
  data=im.tobytes()
 if len(data)!=((width*components*int(bits)+7)//8)*height:raise ValueError('Final PDF image/mask decoded pixel length mismatch')
 colored=0
 if indexed:
  row_bytes=(width*int(bits)+7)//8;indices=[];mask=(1<<int(bits))-1
  for row in range(height):
   for column in range(width):
    offset=column*int(bits);sample=(data[row*row_bytes+offset//8]>>(8-int(bits)-offset%8))&mask
    index=round(float(decode[0])+sample*(float(decode[1])-float(decode[0]))/mask);index=max(0,min(len(palette)-1,index));values=palette[index]
    colored+=max(values)-min(values)>TOLERANCE
 elif components==3 or profile is not None:
  if bits!=8:raise ValueError('Final PDF ICC image bit depth unsupported')
  image=Image.frombytes('RGB'if components==3 else'L',(width,height),data);channels=[]
  for component,channel in enumerate(image.split()):
   low,high=map(float,decode[2*component:2*component+2]);channels.append(channel.point([max(0,min(255,round(low*255+v*(high-low))))for v in range(256)]))
  image=Image.merge('RGB'if components==3 else'L',channels)
  if profile is not None:image=ImageCms.profileToProfile(image,profile,ImageCms.createProfile('sRGB'),outputMode='RGB')
  colored=pixels(image)['coloredPixels']
 return {'width':width,'height':height,'bitsPerComponent':int(bits),'colorSpace':label,'decode':list(decode),'decodedHash':hashlib.sha256(data).hexdigest(),'decodedBytes':len(data),'coloredPixels':colored,'pixelsCheckedBeforeMask':True}

def objects(pdf,gray):
 r=pypdf.PdfReader(pdf);seen=set();masks_seen=set();counts={'images':0,'forms':0,'deviceColorOperators':0,'nonNeutralColorOperators':0,'normalVectorAlphaStates':0,'pureVectorAlphaForms':0,'imageMasks':0,'nonNeutralImagePixels':0,'imageAudits':[]}
 def pure_vector_form(form,resources,active=None):
  active=set() if active is None else active
  if id(form) in active:raise ValueError('Final PDF recursive alpha Form unsupported')
  active=active|{id(form)}
  if '/SMask' in form or '/Mask' in form:raise ValueError('Final PDF alpha Form mask unsupported')
  if '/Group' in form:
   group=form['/Group'].get_object()
   if str(group.get('/S'))!='/Transparency' or bool(getattr(group.get('/I',False),'value',group.get('/I',False))) or bool(getattr(group.get('/K',False),'value',group.get('/K',False))) or set(group)-{'/S','/I','/K','/Type'}:raise ValueError('Final PDF alpha Form isolated/knockout/custom group unsupported')
  local=form.get('/Resources',resources).get_object()
  content=pypdf.generic.ContentStream(form,r)
  for operands,operator in content.operations:
   if operator in [b'INLINE IMAGE',b'BI',b'sh',b'Tj',b'TJ',b"'",b'"']:raise ValueError('Final PDF alpha Form must contain pure vector paths')
   if operator==b'Do':
    child=local.get('/XObject',{}).get(operands[0]);child=child.get_object() if child is not None else {}
    if child.get('/Subtype')!='/Form':raise ValueError('Final PDF alpha Form contains image or unsupported XObject')
    pure_vector_form(child,local,active)
 def walk(resources,stream):
  resources=resources.get_object()
  if any(resources[key].get_object() for key in ['/Shading','/Pattern'] if key in resources):raise ValueError('Final PDF gradient/pattern unsupported')
  for c in resources.get('/ColorSpace',{}).values():
   c=c.get_object()
   if isinstance(c,list) and str(c[0]) in ['/Separation','/DeviceN']:raise ValueError('Final PDF spot/DeviceN unsupported')
  for name,x in resources.get('/XObject',{}).items():
   x=x.get_object();identity=id(x)
   if identity in seen:continue
   seen.add(identity)
   if x.get('/Subtype')=='/Image':
    counts['images']+=1
    if '/Mask'in x and '/SMask'in x:raise ValueError('Final PDF simultaneous Mask/SMask unsupported')
    audit=image_samples(x,resources);counts['nonNeutralImagePixels']+=audit['coloredPixels']
    for key in ['/Mask','/SMask']:
     if key in x:
      mask=x[key].get_object();audit['mask']=image_samples(mask,resources,key[1:]);audit['mask']['kind']=key[1:]
      if id(mask)not in masks_seen:counts['imageMasks']+=1;masks_seen.add(id(mask))
    counts['imageAudits'].append(audit)
   elif x.get('/Subtype')=='/Form':counts['forms']+=1;walk(x.get('/Resources',resources),x)
  if stream is None:return
  content=pypdf.generic.ContentStream(stream,r)
  alpha=(1,1);stack=[]
  for a,op in content.operations:
   if op==b'q':stack.append(alpha)
   elif op==b'Q':alpha=stack.pop() if stack else (1,1)
   if op==b'gs':
    g=resources.get('/ExtGState',{}).get(a[0]);g=g.get_object() if g else {}
    if str(g.get('/BM','/Normal')) not in ['/Normal','/Compatible'] or str(g.get('/SMask','/None'))!='/None' or not 0<=float(g.get('/ca',alpha[0]))<=1 or not 0<=float(g.get('/CA',alpha[1]))<=1:raise ValueError('Final PDF transparency combination unsupported')
   if op==b'gs':
    alpha=(float(g.get('/ca',alpha[0])),float(g.get('/CA',alpha[1])))
    if alpha!=(1,1):counts['normalVectorAlphaStates']+=1
   if op==b'Do' and alpha!=(1,1):
    x=resources.get('/XObject',{}).get(a[0]);x=x.get_object() if x else {}
    if x.get('/Subtype')=='/Image':raise ValueError('Alpha applied to image unsupported')
    if x.get('/Subtype')=='/Form':pure_vector_form(x,resources);counts['pureVectorAlphaForms']+=1
   if op in [b'rg',b'RG',b'k',b'K',b'g',b'G']:
    counts['deviceColorOperators']+=1
    if op in [b'rg',b'RG']:values=[float(z)*255 for z in a]
    elif op in [b'k',b'K']:
     c,m,y,k=map(float,a);values=[255*(1-c)*(1-k),255*(1-m)*(1-k),255*(1-y)*(1-k)]
    else:values=[float(a[0])*255]*3
    if max(values)-min(values)>TOLERANCE:counts['nonNeutralColorOperators']+=1
   if op in [b'sc',b'scn',b'SC',b'SCN'] and gray:
    values=[float(z)*255 for z in a if isinstance(z,(int,float))]
    if len(values)>1 and max(values)-min(values)>TOLERANCE:counts['nonNeutralColorOperators']+=1
 for p in r.pages:walk(p['/Resources'],p.get_contents())
 counts['ok']=not gray or counts['nonNeutralColorOperators']==0 and counts['nonNeutralImagePixels']==0;counts['unsupportedRejected']=True;return counts
def editable_text_ink(pdf):
 r=pypdf.PdfReader(pdf)
 counts={'textShows':0,'nonBlackTextShows':0,'unknownTextShows':0}
 def color(space,values):
  if space=='/DeviceGray':return len(values)==1 and abs(values[0])<=0.005
  if space=='/DeviceRGB':return len(values)==3 and all(abs(v)<=0.005 for v in values)
  if space=='/DeviceCMYK':return len(values)==4 and all(abs(v)<=0.005 for v in values[:3]) and abs(values[3]-1)<=0.005
  return None
 def walk(stream,resources,initial,active):
  identity=id(stream)
  if identity in active:raise ValueError('Recursive PDF Form in text audit')
  active=active|{identity};resources=resources.get_object()
  state=initial.copy();stack=[]
  for args,op in pypdf.generic.ContentStream(stream,r).operations:
   if op==b'q':stack.append(state.copy())
   elif op==b'Q':state=stack.pop() if stack else initial.copy()
   elif op in (b'g',b'rg',b'k'):
    state['fillSpace']={b'g':'/DeviceGray',b'rg':'/DeviceRGB',b'k':'/DeviceCMYK'}[op]
    state['fill']=tuple(float(v) for v in args)
   elif op in (b'G',b'RG',b'K'):
    state['strokeSpace']={b'G':'/DeviceGray',b'RG':'/DeviceRGB',b'K':'/DeviceCMYK'}[op]
    state['stroke']=tuple(float(v) for v in args)
   elif op in (b'cs',b'CS'):
    name=str(args[0]);value=resources.get('/ColorSpace',{}).get(args[0],name)
    resolved=value.get_object() if hasattr(value,'get_object') else value
    space=str(resolved[0]) if isinstance(resolved,list) else str(resolved)
    state['fillSpace' if op==b'cs' else 'strokeSpace']=space
    state['fill' if op==b'cs' else 'stroke']=None
   elif op in (b'sc',b'scn',b'SC',b'SCN'):
    key='fill' if op in (b'sc',b'scn') else 'stroke'
    state[key]=tuple(float(v) for v in args) if all(isinstance(v,(int,float)) for v in args) else None
   elif op==b'gs':
    entry=resources.get('/ExtGState',{}).get(args[0])
    gs=entry.get_object() if entry is not None else {}
    state['fillAlpha']=float(gs.get('/ca',state['fillAlpha']))
    state['strokeAlpha']=float(gs.get('/CA',state['strokeAlpha']))
   elif op==b'Tr':state['renderMode']=int(args[0])
   elif op in (b'Tj',b'TJ',b"'",b'"'):
    mode=state['renderMode']
    if mode in (3,7):continue
    counts['textShows']+=1
    checks=[]
    if mode in (0,2,4,6):checks.append(None if state['fill'] is None else color(state['fillSpace'],state['fill']) and state['fillAlpha']==1)
    if mode in (1,2,5,6):checks.append(None if state['stroke'] is None else color(state['strokeSpace'],state['stroke']) and state['strokeAlpha']==1)
    if any(value is None for value in checks):counts['unknownTextShows']+=1
    elif not all(checks):counts['nonBlackTextShows']+=1
   elif op==b'Do':
    entry=resources.get('/XObject',{}).get(args[0])
    obj=entry.get_object() if entry is not None else {}
    if obj.get('/Subtype')=='/Form':walk(obj,obj.get('/Resources',resources),state,active)
 for page in r.pages:
  initial={'fillSpace':'/DeviceGray','fill':(0,), 'strokeSpace':'/DeviceGray','stroke':(0,), 'fillAlpha':1,'strokeAlpha':1,'renderMode':0}
  walk(page.get_contents(),page['/Resources'],initial,set())
 counts['ok']=counts['nonBlackTextShows']==0 and counts['unknownTextShows']==0
 return counts
def main():
 parser=argparse.ArgumentParser();parser.add_argument('request');q=parser.parse_args();req=json.loads(Path(q.request).read_text('utf-8-sig'));policy=req['policy'];gray=policy=='grayscale';route=req.get('route')
 if req['ruleVersion']!=RULE or policy not in ['grayscale','source-color']:raise ValueError('Invalid color rule/policy')
 if route not in ['raster-reletter','vector-reletter','rebuild','image','compose','chart-redraw']:raise ValueError('Invalid color audit route')
 for k in ['source','planFile','pdf','output','ai','preview']:
  h='planFileHash' if k=='planFile' else k+'Hash'
  if hash_file(req[k])!=req['bindings'][h]:raise ValueError('Color audit hash mismatch: '+k)
 doc=pdfium.PdfDocument(req['pdf']);page_results=[]
 for i in range(len(doc)):
  im=doc[i].render(scale=300/72,fill_color=(255,255,255,255)).to_pil();page_results.append({'page':i+1,**pixels(im)})
 file_results=[]
 for k in ['preview','output']:
  p=Path(req[k])
  if p.suffix.lower()=='.pdf':continue
  file_results.append({'kind':k,'path':str(p),'sha256':hash_file(p),**pixels(Image.open(p))})
 all_results=page_results+file_results;pixel={'method':'pdfium-rgb-300dpi-neutral-v1','tolerance':TOLERANCE,'toleranceReason':'At most2/255 channel spread for independent 8bit encoding/rendering rounding; no pixels beyond this threshold are allowed. RGB channels compared before any luminance conversion.','ok':all(x['ok'] for x in all_results),'coloredPixels':sum(x['coloredPixels'] for x in all_results),'totalPixels':sum(x['totalPixels'] for x in all_results),'maxChannelDelta':max(x['maxChannelDelta'] for x in all_results),'pages':len(doc),'pageAudits':page_results,'fileAudits':file_results}
 obj=objects(req['pdf'],gray);ink=editable_text_ink(req['pdf']) if route!='image' else {'ok':True,'skipped':'image route','textShows':0,'nonBlackTextShows':0,'unknownTextShows':0};out={'ok':obj['ok'] and ink['ok'] and (pixel['ok'] or not gray),'ruleVersion':RULE,'policy':policy,'route':route,'bindings':req['bindings'],'pixelAudit':pixel,'objectAudit':obj,'textInkAudit':ink,'approval':req.get('approval')};Path(req['report']).write_text(json.dumps(out,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(out,ensure_ascii=False));sys.exit(0 if out['ok'] else 1)
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False));sys.exit(1)
