import argparse,base64,hashlib,io,json,re,sys,xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image,ImageColor
NORMALIZATION_RULE_VERSION='jfw-color-normalize-2026-10-12-v3-vector-alpha'
LUMA='Pillow L (ITU-R 601 encoded RGB coefficients .299/.587/.114)'
def sha(data):return hashlib.sha256(data).hexdigest()
def image_rgb(data,gray,embedded=False):
 im=Image.open(io.BytesIO(data))
 if im.info.get('icc_profile'):
  from PIL import ImageCms
  name=ImageCms.getProfileName(ImageCms.ImageCmsProfile(io.BytesIO(im.info['icc_profile'])))
  if 'srgb' not in name.lower():raise ValueError('Unsupported image ICC profile: '+name.strip())
 if im.mode not in ['RGB','RGBA','L','LA','P','1']:raise ValueError('Unsupported image mode: '+im.mode)
 rgba=im.convert('RGBA');alpha=rgba.getchannel('A')
 if embedded and alpha.getextrema()!=(255,255):raise ValueError('Embedded image transparency needs explicit composition support')
 out=Image.new('RGBA',rgba.size,'white');out.alpha_composite(rgba);out=out.convert('RGB')
 if gray:out=out.convert('L').convert('RGB')
 buf=io.BytesIO();out.save(buf,'PNG');return buf.getvalue(),{'width':out.width,'height':out.height,'sourceMode':im.mode,'outputMode':'RGB','opaque':True,'alphaFlattenedWhite':alpha.getextrema()!=(255,255)}
def color(s,gray):
 s=s.strip()
 if s in ['none','inherit','currentColor']:return s
 if s.startswith('url('):
  if not re.fullmatch(r'url\(#[\w.-]+\)',s):raise ValueError('External paint reference unsupported')
  return s
 try:
  if s.startswith('rgb('):
   parts=s[4:-1].replace(',',' ').split();rgb=tuple(round(float(x[:-1])*2.55) if x.endswith('%') else round(float(x)) for x in parts)
   if len(rgb)!=3 or min(rgb)<0 or max(rgb)>255:raise ValueError()
  else:rgb=ImageColor.getrgb(s)
 except Exception:raise ValueError('Unsupported SVG color: '+s)
 if len(rgb)==4:
  if rgb[3]!=255:raise ValueError('Alpha color unsupported')
  rgb=rgb[:3]
 if gray:
  y=Image.new('RGB',(1,1),rgb).convert('L').getpixel((0,0));rgb=(y,y,y)
 return '#'+''.join('%02x'%x for x in rgb)
def css_rules(text,gray=None):
 rules=[];residue=re.sub(r'/\*.*?\*/','',text,flags=re.S)
 for match in re.finditer(r'([^{}]+)\{([^{}]*)\}',residue):
  selector=match.group(1).strip()
  if '@' in selector:raise ValueError('SVG external/conditional CSS unsupported')
  props=[]
  for pair in match.group(2).split(';'):
   if not pair.strip():continue
   if ':' not in pair:raise ValueError('Malformed SVG CSS')
   a,z=pair.split(':',1);a=a.strip();z=z.strip()
   if a in ['opacity','fill-opacity','stroke-opacity'] and float(z)!=1:raise ValueError('SVG CSS transparency unsupported')
   if a in ['mix-blend-mode','filter','mask','color-profile'] and z not in ['none','normal']:raise ValueError('Unsupported SVG CSS compositing/profile')
   if a in ['fill','stroke','color','stop-color','background-color','flood-color','lighting-color','solid-color','text-decoration-color']:
    if 'url(' in z:raise ValueError('SVG CSS paint servers unsupported')
    if gray is None:continue
    z=color(z,gray)
   props.append((a,z))
  rules.append((selector,props))
 if re.sub(r'([^{}]+)\{([^{}]*)\}','',residue).strip():raise ValueError('Unsupported SVG CSS syntax')
 return rules
def geometry(root):
 out=[]
 for x in root.iter():
  attrs={}
  for k,v in x.attrib.items():
   local=k.split('}')[-1]
   if local in ['fill','stroke','color','stop-color','background-color','flood-color','lighting-color','solid-color','text-decoration-color']:continue
   if local=='href' and x.tag.split('}')[-1]=='image':continue
   if local=='style':
    parts=[]
    for pair in v.split(';'):
     if ':' in pair:
      key,value=pair.split(':',1)
      if key.strip() not in ['fill','stroke','color','stop-color','background-color','flood-color','lighting-color','solid-color','text-decoration-color']:parts.append((key.strip(),value.strip()))
    attrs[k]=sorted(parts)
   else:attrs[k]=v
  out.append([x.tag,sorted(attrs.items()),css_rules(x.text or '') if x.tag.split('}')[-1]=='style' else x.text or '',x.tail or ''])
 return sha(json.dumps(out,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode())
def normalize_svg(source,dest,gray):
 text=source.read_text('utf-8-sig')
 if '<!DOCTYPE' in text or '<!ENTITY' in text:raise ValueError('SVG external document/entity unsupported')
 root=ET.fromstring(text);before=geometry(root);images=[];colors=0;href_canonicalized=0
 for x in root.iter():
  if x.tag.split('}')[-1]=='use' and any(x.get(k,'1')!='1' for k in ['fill-opacity','stroke-opacity']):
   ref=x.get('{http://www.w3.org/1999/xlink}href',x.get('href',''));targets=[y for y in root.iter() if y.get('id')==ref.lstrip('#')]
   if not ref.startswith('#') or not targets or any(y.tag.split('}')[-1] not in ['path','line','polyline','polygon','circle','ellipse','rect'] or len(y) for y in targets) or any(y.attrib!=targets[0].attrib for y in targets):raise ValueError('Alpha use must reference identical pure vector shapes')
 forbidden={'linearGradient','radialGradient','pattern','filter','mask','foreignObject','script','animate','animateTransform','set'}
 for x in root.iter():
  tag=x.tag.split('}')[-1]
  if tag in forbidden:raise ValueError('Unsupported SVG element: '+tag)
  if tag=='image':
   refs=[(k,v) for k,v in x.attrib.items() if k.split('}')[-1]=='href']
   if not refs:raise ValueError('SVG image href missing')
   if len(set(v for k,v in refs))!=1:raise ValueError('Conflicting SVG href/xlink:href')
   if any(k not in ['href','{http://www.w3.org/1999/xlink}href'] for k,v in refs):raise ValueError('Unsupported SVG image href namespace')
   href_canonicalized+=any(k=='href' for k,v in refs)
   for k,v in refs:del x.attrib[k]
   x.set('{http://www.w3.org/1999/xlink}href',refs[0][1])
  if tag=='style':x.text=''.join(selector+'{'+(';'.join(a+':'+z for a,z in props))+'}' for selector,props in css_rules(x.text or '',gray))
  for k,v in list(x.attrib.items()):
   local=k.split('}')[-1]
   if local in ['opacity','fill-opacity','stroke-opacity'] and float(v)!=1:
    if local=='opacity' or tag not in ['path','line','polyline','polygon','circle','ellipse','rect','use'] or not 0<=float(v)<=1:raise ValueError('SVG transparency combination unsupported')
   if local in ['mix-blend-mode','filter','mask','color-profile'] and v not in ['none','normal']:raise ValueError('Unsupported SVG compositing/profile')
   if local in ['fill','stroke','color','stop-color','background-color','flood-color','lighting-color','solid-color','text-decoration-color']:
    if 'url(' in v:raise ValueError('SVG paint servers unsupported')
    x.set(k,color(v,gray));colors+=1
   elif local=='style':
    parts=[]
    for pair in v.split(';'):
     if not pair.strip():continue
     if ':' not in pair:raise ValueError('Malformed SVG style')
     a,z=pair.split(':',1);a=a.strip();z=z.strip()
     if a in ['opacity','fill-opacity','stroke-opacity'] and float(z)!=1:raise ValueError('SVG style transparency unsupported')
     if a in ['mix-blend-mode','filter','mask','color-profile'] and z not in ['none','normal']:raise ValueError('Unsupported SVG style compositing/profile')
     if a in ['fill','stroke','color','stop-color','background-color','flood-color','lighting-color','solid-color','text-decoration-color']:
      if 'url(' in z:raise ValueError('SVG paint servers unsupported')
      z=color(z,gray);colors+=1
     parts.append(a+':'+z)
    x.set(k,';'.join(parts))
   elif local=='href':
    if tag=='image':
     m=re.fullmatch(r'data:image/(png|jpeg|jpg|webp);base64,([A-Za-z0-9+/=\s]+)',v)
     if not m:raise ValueError('Linked/non-base64 SVG image unsupported')
     raw=base64.b64decode(m.group(2),validate=False);new,info=image_rgb(raw,gray,embedded=True);info.update({'sourceImageHash':sha(raw),'normalizedImageHash':sha(new),'geometryAttributes':{z:x.get(z) for z in ['x','y','width','height','transform']}});images.append(info);x.set(k,'data:image/png;base64,'+base64.b64encode(new).decode())
    elif not v.startswith('#'):raise ValueError('Linked SVG object unsupported')
 after=geometry(root)
 if before!=after:raise ValueError('Non-color SVG geometry/text changed')
 ET.register_namespace('','http://www.w3.org/2000/svg');ET.register_namespace('xlink','http://www.w3.org/1999/xlink');ET.ElementTree(root).write(dest,encoding='utf-8',xml_declaration=True)
 return {'kind':'svg','geometryHashBefore':before,'geometryHashAfter':after,'geometryPreserved':True,'embeddedImages':images,'imageHrefCanonicalized':href_canonicalized,'imageHrefPolicy':'SVG2 href to Illustrator-compatible xlink:href; conflicting aliases rejected','colorAttributes':colors,'mapping':LUMA,'unsupportedRejected':True}
def inspect_pdf(source,dest,gray):
 import pypdf
 r=pypdf.PdfReader(source);seen={};active=set();images=0;paths=0;color_count=0;geometry_before=[];geometry_after=[]
 checked_resources=set()
 def validate_resources(resources):
  resources=resources.get_object()
  if id(resources) in checked_resources:return
  checked_resources.add(id(resources))
  if any(resources[key].get_object() for key in ['/Shading','/Pattern'] if key in resources):raise ValueError('PDF gradient/pattern unsupported')
  for c in resources.get('/ColorSpace',{}).values():
   c=c.get_object()
   if isinstance(c,list) and str(c[0]) in ['/Separation','/DeviceN']:raise ValueError('PDF spot/DeviceN unsupported')
  for g in resources.get('/ExtGState',{}).values():
   g=g.get_object()
   if str(g.get('/BM','/Normal')) not in ['/Normal','/Compatible'] or str(g.get('/SMask','/None'))!='/None' or not 0<=float(g.get('/ca',1))<=1 or not 0<=float(g.get('/CA',1))<=1:raise ValueError('PDF transparency combination unsupported')
  for v in resources.get('/XObject',{}).values():
   o=v.get_object()
   if o.get('/Subtype')=='/Image':raise ValueError('Non-SVG vector source has embedded image; normalize a source SVG or explicit raster route')
   if o.get('/Subtype')=='/Form':
    for operands,operator in pypdf.generic.ContentStream(o,r).operations:
     if operator in [b'sc',b'scn',b'SC',b'SCN'] or operator in [b'cs',b'CS'] and (len(operands)!=1 or str(operands[0])!='/DeviceRGB'):raise ValueError('Non-device PDF color space unsupported for normalization')
    validate_resources(o.get('/Resources',resources))
 def normalize(resources,stream):
  nonlocal images,paths,color_count
  resources=resources.get_object()
  if any(resources[key].get_object() for key in ['/Shading','/Pattern'] if key in resources):raise ValueError('PDF gradient/pattern unsupported')
  for c in resources.get('/ColorSpace',{}).values():
   c=c.get_object()
   if isinstance(c,list) and str(c[0]) in ['/Separation','/DeviceN']:raise ValueError('PDF spot/DeviceN unsupported')
  for g in resources.get('/ExtGState',{}).values():
   g=g.get_object()
   if str(g.get('/BM','/Normal')) not in ['/Normal','/Compatible'] or str(g.get('/SMask','/None'))!='/None' or not 0<=float(g.get('/ca',1))<=1 or not 0<=float(g.get('/CA',1))<=1:raise ValueError('PDF transparency combination unsupported')
  validate_resources(resources)
  cs=pypdf.generic.ContentStream(stream,r)
  invoked={a[0] for a,op in cs.operations if op==b'Do'}
  for n,v in list(resources.get('/XObject',{}).items()):
   if n not in invoked:continue
   o=v.get_object();identity=id(o)
   if identity in active:raise ValueError('Cyclic PDF Form unsupported')
   if identity in seen:
    resources['/XObject'][n]=seen[identity];continue
   active.add(identity)
   if o.get('/Subtype')=='/Image':images+=1;raise ValueError('Non-SVG vector source has embedded image; normalize a source SVG or explicit raster route')
   if o.get('/Subtype')=='/Form':
    normalized=normalize(o.get('/Resources',resources),o)
    for k,z in o.items():
     if k not in ['/Length','/Filter','/DecodeParms']:normalized[k]=z
    resources['/XObject'][n]=normalized;seen[identity]=normalized;active.remove(identity)
  cs=pypdf.generic.ContentStream(stream,r);operations=[]
  for a,op in cs.operations:
   if op in [b'cs',b'CS']:
    if len(a)!=1 or str(a[0])!='/DeviceRGB':raise ValueError('Non-device PDF color space unsupported for normalization')
    if gray:a=[pypdf.generic.FloatObject(0)]*3;op=b'rg' if op==b'cs' else b'RG'
   if op in [b'sc',b'scn',b'SC',b'SCN']:raise ValueError('Non-device PDF color space unsupported for normalization')
   if op in [b'm',b'l',b'c',b're',b'h',b'cm',b'Tm',b'Td',b'TD',b'Tj',b'TJ']:geometry_before.append([str(op),str(a)])
   paths+=op in [b'm',b'l',b'c',b're']
   if gray and op in [b'rg',b'RG',b'k',b'K']:
    if op in [b'k',b'K']:
     c,m,y,k=map(float,a);rgb=[255*(1-c)*(1-k),255*(1-m)*(1-k),255*(1-y)*(1-k)]
    else:rgb=[float(z)*255 for z in a]
    rgb=tuple(max(0,min(255,round(z))) for z in rgb);value=Image.new('RGB',(1,1),rgb).convert('L').getpixel((0,0))/255;a=[pypdf.generic.FloatObject(value)]*3;op=b'RG' if op in [b'RG',b'K'] else b'rg';color_count+=1
   operations.append((a,op))
   if op in [b'm',b'l',b'c',b're',b'h',b'cm',b'Tm',b'Td',b'TD',b'Tj',b'TJ']:geometry_after.append([str(op),str(a)])
  cs.operations=operations;out=pypdf.generic.DecodedStreamObject();out.set_data(cs.get_data());return out
 for page in r.pages:
  page[pypdf.generic.NameObject('/Contents')]=normalize(page['/Resources'],page.get_contents())
  for private in ['/PieceInfo','/Metadata']:
   if private in page:del page[private]
 if geometry_before!=geometry_after:raise ValueError('PDF path/coordinate/text changed during color normalization')
 wr=pypdf.PdfWriter()
 for page in r.pages:wr.add_page(page)
 wr.write(dest)
 return {'kind':'pdf-vector','geometryPreserved':True,'geometryHashBefore':sha(json.dumps(geometry_before).encode()),'geometryHashAfter':sha(json.dumps(geometry_after).encode()),'embeddedImages':images,'pathOperators':paths,'normalizedColorOperators':color_count,'nativePrivateDataExcluded':True,'mapping':LUMA,'unsupportedRejected':True}
def main():
 a=argparse.ArgumentParser();a.add_argument('input');a.add_argument('output');a.add_argument('--policy',choices=['grayscale','source-color'],default='grayscale');a.add_argument('--kind',choices=['svg','image','pdf'],required=True);q=a.parse_args();s=Path(q.input);o=Path(q.output);o.parent.mkdir(parents=True,exist_ok=True);before=sha(s.read_bytes());gray=q.policy=='grayscale'
 if q.kind=='svg':e=normalize_svg(s,o,gray)
 elif q.kind=='image':new,info=image_rgb(s.read_bytes(),gray);o.write_bytes(new);e={'kind':'image','geometryPreserved':True,'pixelPositionsPreserved':True,'mapping':LUMA,**info}
 else:e=inspect_pdf(s,o,gray)
 if sha(s.read_bytes())!=before:raise ValueError('Original source changed')
 e.update({'ok':True,'normalizationRuleVersion':NORMALIZATION_RULE_VERSION,'sourceHash':before,'normalizedHash':sha(o.read_bytes()),'policy':q.policy,'output':str(o)});print(json.dumps(e,ensure_ascii=False))
if __name__=='__main__':
 try:main()
 except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False));sys.exit(1)


