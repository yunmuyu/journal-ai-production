import argparse,base64,hashlib,io,json,re,sys,xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image,ImageColor
NORMALIZATION_RULE_VERSION='jfw-color-normalize-2026-10-18-v6-binary-mask'
LUMA='Pillow L (ITU-R 601 encoded RGB coefficients .299/.587/.114)'
def sha(data):return hashlib.sha256(data).hexdigest()
def image_rgb(data,gray,embedded=False):
 im=Image.open(io.BytesIO(data));source_mode=im.mode
 if im.mode not in ['RGB','RGBA','L','LA','P','1']:raise ValueError('Unsupported image mode: '+im.mode)
 icc_conversion=None
 if im.info.get('icc_profile'):
  from PIL import ImageCms
  profile=ImageCms.ImageCmsProfile(io.BytesIO(im.info['icc_profile']))
  name=ImageCms.getProfileName(profile).strip()
  alpha=im.convert('RGBA').getchannel('A')
  im=ImageCms.profileToProfile(im.convert('RGB'),profile,ImageCms.createProfile('sRGB'),outputMode='RGB')
  im.putalpha(alpha)
  icc_conversion={'sourceProfile':name,'targetProfile':'sRGB','engine':'LittleCMS'}
 rgba=im.convert('RGBA');alpha=rgba.getchannel('A')
 if embedded and alpha.getextrema()!=(255,255):raise ValueError('Embedded image transparency needs explicit composition support')
 out=Image.new('RGBA',rgba.size,'white');out.alpha_composite(rgba);out=out.convert('RGB')
 if gray:out=out.convert('L').convert('RGB')
 buf=io.BytesIO();out.save(buf,'PNG');return buf.getvalue(),{'width':out.width,'height':out.height,'sourceMode':source_mode,'outputMode':'RGB','opaque':True,'alphaFlattenedWhite':alpha.getextrema()!=(255,255),'iccConversion':icc_conversion}
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
 r=pypdf.PdfReader(source);wr=pypdf.PdfWriter();seen={};active=set();form_states={};images=0;paths=0;color_count=0;geometry_before=[];geometry_after=[];image_conversions=[]
 def device_space(name,resources):
  space=name
  if str(space) not in ['/DeviceRGB','/DeviceGray']:
   space=resources.get('/ColorSpace',{}).get(name)
   space=space.get_object() if space is not None else None
  if str(space) not in ['/DeviceRGB','/DeviceGray']:raise ValueError('Non-device PDF color space unsupported for normalization: '+str(space))
  return str(space)
 def validate_binary_mask(obj):
  if not isinstance(obj,pypdf.generic.StreamObject) or obj.get('/Subtype')!='/Image' or not isinstance(obj.get('/ImageMask'),pypdf.generic.BooleanObject) or not obj['/ImageMask'].value:raise ValueError('PDF explicit mask must be an ImageMask image stream')
  if any(k in obj for k in ['/ColorSpace','/Mask','/SMask','/F','/Matte']):raise ValueError('PDF binary mask color space/nested transparency/linked data unsupported')
  for key in ['/Width','/Height']:
   if not isinstance(obj.get(key),pypdf.generic.NumberObject) or obj[key]<=0:raise ValueError('PDF binary mask dimensions must be positive integers')
  if '/BitsPerComponent' in obj and (not isinstance(obj['/BitsPerComponent'],pypdf.generic.NumberObject) or obj['/BitsPerComponent']!=1):raise ValueError('PDF binary mask requires 1 bit per component')
  decode=obj.get('/Decode',pypdf.generic.ArrayObject([pypdf.generic.NumberObject(0),pypdf.generic.NumberObject(1)]))
  if not isinstance(decode,pypdf.generic.ArrayObject) or len(decode)!=2 or any(not isinstance(x,(pypdf.generic.NumberObject,pypdf.generic.FloatObject)) for x in decode) or list(decode) not in [[0,1],[1,0]]:raise ValueError('PDF binary mask Decode must be [0 1] or [1 0]')
  if '/Interpolate' in obj and not isinstance(obj['/Interpolate'],pypdf.generic.BooleanObject):raise ValueError('PDF binary mask Interpolate must be boolean')
  filters=obj.get('/Filter',pypdf.generic.ArrayObject());filters=filters.get_object()
  if not isinstance(filters,list):filters=[filters]
  if any(str(f)!='/FlateDecode' for f in filters):raise ValueError('PDF binary mask filter unsupported')
  data=obj.get_data()
  if len(data)!=((int(obj['/Width'])+7)//8)*int(obj['/Height']):raise ValueError('PDF binary mask decoded pixel length mismatch')
  return {'width':int(obj['/Width']),'height':int(obj['/Height']),'decode':list(decode),'decodedHash':sha(data),'preserved':True}
 def normalize_image(obj,resources):
  if '/ImageMask' in obj and not isinstance(obj['/ImageMask'],pypdf.generic.BooleanObject):raise ValueError('PDF image ImageMask must be boolean')
  if bool(getattr(obj.get('/ImageMask',False),'value',obj.get('/ImageMask',False))):
   validate_binary_mask(obj);return obj
  if any(k in obj for k in ['/SMask','/F']):raise ValueError('PDF image mask/transparency/linked image unsupported')
  mask_info=None;mask_ref=None
  if '/Mask' in obj:
   mask=obj['/Mask'].get_object();mask_info=validate_binary_mask(mask)
   if id(mask) not in seen:seen[id(mask)]=wr._add_object(mask)
   mask_ref=seen[id(mask)]
  if '/Decode' in obj:raise ValueError('PDF image explicit Decode unsupported')
  if not isinstance(obj.get('/BitsPerComponent'),pypdf.generic.NumberObject) or obj['/BitsPerComponent']!=8:raise ValueError('PDF image requires 8 bits per component')
  if any(not isinstance(obj.get(k),pypdf.generic.NumberObject) for k in ['/Width','/Height']):raise ValueError('PDF image dimensions must be positive integers')
  width,height=int(obj['/Width']),int(obj['/Height'])
  if width<=0 or height<=0:raise ValueError('PDF image dimensions must be positive')
  cs=obj.get('/ColorSpace');cs=cs.get_object() if cs is not None else None
  if isinstance(cs,pypdf.generic.NameObject) and str(cs) not in ['/DeviceRGB','/DeviceGray']:
   cs=resources.get('/ColorSpace',{}).get(cs);cs=cs.get_object() if cs is not None else None
  profile=None;icc_conversion=None
  if isinstance(cs,list) and str(cs[0])=='/ICCBased':
   profile=cs[1].get_object()
   if int(profile.get('/N',0))!=3:raise ValueError('PDF image ICCBased profile must have 3 RGB components')
   mode='RGB';source_space='ICCBased RGB'
  elif str(cs) in ['/DeviceRGB','/DeviceGray']:mode='RGB' if str(cs)=='/DeviceRGB' else 'L';source_space=str(cs)
  else:raise ValueError('PDF image color space unsupported: '+str(cs))
  filters=obj.get('/Filter',pypdf.generic.ArrayObject());filters=filters.get_object()
  if not isinstance(filters,list):filters=[filters]
  if any(str(f) not in ['/FlateDecode','/DCTDecode'] for f in filters):raise ValueError('PDF image filter unsupported: '+str(filters))
  raw=obj.get_data()
  if any(str(f)=='/DCTDecode' for f in filters):
   im=Image.open(io.BytesIO(raw));im.load()
   if im.mode!=mode or im.size!=(width,height):raise ValueError('PDF JPEG mode/dimensions differ from image dictionary')
  else:
   expected=width*height*(3 if mode=='RGB' else 1)
   if len(raw)!=expected:raise ValueError('PDF image decoded pixel length mismatch')
   im=Image.frombytes(mode,(width,height),raw)
  if profile is not None:
   from PIL import ImageCms
   icc=ImageCms.ImageCmsProfile(io.BytesIO(profile.get_data()))
   if icc.profile.xcolor_space.strip()!='RGB':raise ValueError('PDF image ICC profile is not RGB')
   im=ImageCms.profileToProfile(im,icc,ImageCms.createProfile('sRGB'),outputMode='RGB')
   icc_conversion={'sourceProfile':ImageCms.getProfileName(icc).strip(),'targetProfile':'sRGB','engine':'LittleCMS'}
  im=im.convert('L' if gray else mode);pixels=im.tobytes()
  out=pypdf.generic.DecodedStreamObject();out.set_data(pixels)
  for key,value in obj.items():
   if key not in ['/Length','/Filter','/DecodeParms','/ColorSpace']:out[key]=value
  if mask_ref is not None:out[pypdf.generic.NameObject('/Mask')]=mask_ref
  out[pypdf.generic.NameObject('/ColorSpace')]=pypdf.generic.NameObject('/DeviceGray' if im.mode=='L' else '/DeviceRGB')
  image_conversions.append({'width':width,'height':height,'sourceColorSpace':source_space,'outputColorSpace':str(out['/ColorSpace']),'sourceDecodedHash':sha(raw),'normalizedPixelHash':sha(pixels),'iccConversion':icc_conversion,'positionAndClipPreserved':True,'explicitBinaryMask':mask_info})
  return out
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
   if o.get('/Subtype')=='/Form':
    validate_resources(o.get('/Resources',resources))
 def normalize(resources,stream,initial_spaces=('/DeviceGray','/DeviceGray')):
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
   if o.get('/Subtype')=='/Form':continue
   if identity in active:raise ValueError('Cyclic PDF Form unsupported')
   if identity in seen:
    resources['/XObject'][n]=seen[identity];continue
   active.add(identity)
   if o.get('/Subtype')=='/Image':
    normalized=normalize_image(o,resources);reference=wr._add_object(normalized);images+=1;resources['/XObject'][n]=reference;seen[identity]=reference;seen[id(normalized)]=reference;active.remove(identity)
  cs=pypdf.generic.ContentStream(stream,r);operations=[];spaces=list(initial_spaces);space_stack=[]
  for a,op in cs.operations:
   if op==b'INLINE IMAGE':raise ValueError('PDF inline image unsupported; use image XObject')
   if op==b'q':space_stack.append(spaces[:])
   elif op==b'Q':spaces=space_stack.pop()
   if op==b'Do':
    o=resources['/XObject'][a[0]].get_object();identity=id(o)
    if o.get('/Subtype')=='/Form':
     if identity in active:raise ValueError('Cyclic PDF Form unsupported')
     if identity in seen:
      if form_states.get(identity)!=tuple(spaces):raise ValueError('PDF Form reused with different inherited color spaces unsupported')
      resources['/XObject'][a[0]]=seen[identity]
     else:
      active.add(identity);normalized=normalize(o.get('/Resources',resources),o,tuple(spaces))
      for k,z in o.items():
       if k not in ['/Length','/Filter','/DecodeParms']:normalized[k]=z
      resources['/XObject'][a[0]]=normalized;seen[identity]=normalized;seen[id(normalized)]=normalized;form_states[identity]=form_states[id(normalized)]=tuple(spaces);active.remove(identity)
   color_operation=op in [b'cs',b'CS',b'sc',b'SC',b'scn',b'SCN',b'rg',b'RG',b'k',b'K',b'g',b'G']
   if not color_operation:geometry_before.append([str(op),str(a)])
   if op in [b'cs',b'CS']:
    if len(a)!=1:raise ValueError('PDF color space selection requires one name')
    spaces[op==b'CS']=device_space(a[0],resources)
    if gray:a=[pypdf.generic.FloatObject(0)]*3;op=b'rg' if op==b'cs' else b'RG'
   elif op in [b'sc',b'scn',b'SC',b'SCN']:
    space=spaces[op in [b'SC',b'SCN']];count={'/DeviceRGB':3,'/DeviceGray':1}.get(space)
    if count is None or len(a)!=count or any(not isinstance(x,(pypdf.generic.NumberObject,pypdf.generic.FloatObject)) or not 0<=float(x)<=1 for x in a):raise ValueError('PDF device color component count/range unsupported')
    if gray:
     if count==1:a=a*3
     op=b'RG' if op in [b'SC',b'SCN'] else b'rg'
   elif op in [b'rg',b'RG',b'k',b'K',b'g',b'G']:
    spaces[op in [b'RG',b'K',b'G']]='/DeviceRGB' if op in [b'rg',b'RG'] else '/DeviceCMYK' if op in [b'k',b'K'] else '/DeviceGray'
   paths+=op in [b'm',b'l',b'c',b're']
   if gray and op in [b'rg',b'RG',b'k',b'K']:
    if op in [b'k',b'K']:
     c,m,y,k=map(float,a);rgb=[255*(1-c)*(1-k),255*(1-m)*(1-k),255*(1-y)*(1-k)]
    else:rgb=[float(z)*255 for z in a]
    rgb=tuple(max(0,min(255,round(z))) for z in rgb);value=Image.new('RGB',(1,1),rgb).convert('L').getpixel((0,0))/255;a=[pypdf.generic.FloatObject(value)]*3;op=b'RG' if op in [b'RG',b'K'] else b'rg';color_count+=1
   operations.append((a,op))
   if not color_operation:geometry_after.append([str(op),str(a)])
  cs.operations=operations;out=pypdf.generic.DecodedStreamObject();out.set_data(cs.get_data());return out
 for page in r.pages:
  page[pypdf.generic.NameObject('/Contents')]=normalize(page['/Resources'],page.get_contents())
  for private in ['/PieceInfo','/Metadata']:
   if private in page:del page[private]
 if geometry_before!=geometry_after:raise ValueError('PDF path/coordinate/text changed during color normalization')
 for page in r.pages:wr.add_page(page)
 wr.write(dest)
 return {'kind':'pdf-vector','geometryPreserved':True,'geometryHashBefore':sha(json.dumps(geometry_before).encode()),'geometryHashAfter':sha(json.dumps(geometry_after).encode()),'embeddedImages':images,'imageConversions':image_conversions,'pathOperators':paths,'normalizedColorOperators':color_count,'nativePrivateDataExcluded':True,'mapping':LUMA,'unsupportedRejected':True}
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


