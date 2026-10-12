import argparse,hashlib,json,sys
from pathlib import Path
from PIL import Image,ImageChops
import pypdfium2 as pdfium
import pypdf
RULE='jfw-color-2026-10-11-v1'
TOLERANCE=2
def hash_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pixels(im):
 im=im.convert('RGB');r,g,b=im.split();d=ImageChops.lighter(ImageChops.lighter(ImageChops.difference(r,g),ImageChops.difference(r,b)),ImageChops.difference(g,b));h=d.histogram();bad=sum(h[TOLERANCE+1:]);return {'coloredPixels':bad,'totalPixels':im.width*im.height,'maxChannelDelta':max(i for i,n in enumerate(h) if n),'size':list(im.size),'ok':bad==0}
def objects(pdf,gray):
 r=pypdf.PdfReader(pdf);seen=set();counts={'images':0,'forms':0,'deviceColorOperators':0,'nonNeutralColorOperators':0,'normalVectorAlphaStates':0,'pureVectorAlphaForms':0}
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
    if x.get('/SMask') or x.get('/Mask') or x.get('/F') or x.get('/ImageMask'):raise ValueError('Final PDF image mask/transparency/linked image unsupported')
    cs=x.get('/ColorSpace')
    if cs:
     cs=cs.get_object()
     if isinstance(cs,list) and str(cs[0]) not in ['/ICCBased','/Indexed']:raise ValueError('Final PDF image color encoding unsupported')
     if isinstance(cs,list) and str(cs[0])=='/ICCBased' and cs[1].get_object().get('/N') not in [1,3]:raise ValueError('Final PDF image profile unsupported')
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
 counts['ok']=not gray or counts['nonNeutralColorOperators']==0;counts['unsupportedRejected']=True;return counts
def main():
 parser=argparse.ArgumentParser();parser.add_argument('request');q=parser.parse_args();req=json.loads(Path(q.request).read_text('utf-8-sig'));policy=req['policy'];gray=policy=='grayscale'
 if req['ruleVersion']!=RULE or policy not in ['grayscale','source-color']:raise ValueError('Invalid color rule/policy')
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
 obj=objects(req['pdf'],gray);out={'ok':obj['ok'] and (pixel['ok'] or not gray),'ruleVersion':RULE,'policy':policy,'bindings':req['bindings'],'pixelAudit':pixel,'objectAudit':obj,'approval':req.get('approval')};Path(req['report']).write_text(json.dumps(out,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(out,ensure_ascii=False));sys.exit(0 if out['ok'] else 1)
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False));sys.exit(1)
