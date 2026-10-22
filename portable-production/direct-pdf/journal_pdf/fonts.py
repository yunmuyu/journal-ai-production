"""Explicit font profiles, persistent face cache and per-batch font loading.

Never walks the system font directory. A warm run stats ONLY configured files.
Cache misses inspect name/OS2/cmap; unchanged files do not get rehashed.
Font bytes stay in the local private cache, never in generated source packages.
"""
from __future__ import annotations
from pathlib import Path
import hashlib, io, json, os, sqlite3, time, unicodedata, math
from dataclasses import dataclass
import pymupdf as fitz
from fontTools.ttLib import TTFont
from fontTools.ttLib.sfnt import SFNTWriter
from fontTools.pens.boundsPen import BoundsPen
from fontTools import subset
from .common import FigureError, read_json, atomic_json, digest_json, digest_file
from .editorial import display_content

CJK_PUNCT = "、。，；：？！“”‘’（）【】《》〈〉〔〕［］｛｝…—·"

def cache_home() -> Path:
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', str(Path.home() / 'AppData' / 'Local')))
    else: base = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache')))
    return base/'JournalDirectPDF'


def names(tt):
    return sorted({n.toUnicode() for n in tt['name'].names if n.nameID in (1,2,4,6,16,17)})


def _stat(path):
    s=path.stat(); return {'size':s.st_size,'mtime_ns':s.st_mtime_ns}


class FontRegistry:
    def __init__(self, profile_path: str|Path, cache_dir: str|Path|None=None, *, refresh=False):
        self.profile_path=Path(profile_path).resolve(); self.profile=read_json(self.profile_path)
        if self.profile.get('version')!=1: raise FigureError('font_profile_version','字体方案版本应为1')
        self.cache=Path(cache_dir or cache_home()); self.cache.mkdir(parents=True,exist_ok=True)
        self.stats={'directory_scans':0,'configured_file_stats':0,'hash_reads':0,
                    'face_inspections':0,'persistent_face_hits':0,'fonts_loaded':0,
                    'measure_calls':0,'measure_memory_hits':0,'measure_disk_hits':0,'measure_misses':0}
        self.face_info={}; self.faces={}; self.postscript_names={}; self._paths={}; self._glyphs={}; self._measure_memory={}; self._font_models={}; self._doc_buffers={}
        profkey=digest_json(self.profile)
        index_path=self.cache/('profile-'+profkey+'.json')
        old=read_json(index_path) if index_path.exists() and not refresh else {'faces':{}}
        grouped={}; statuses={}
        for role, spec in self.profile.get('faces',{}).items():
            path=Path(os.path.expandvars(os.path.expanduser(spec['path'])))
            if not path.is_absolute(): path=self.profile_path.parent/path
            path=path.resolve()
            if not path.is_file(): raise FigureError('font_missing',f'配置的字体不存在：{role}', path=str(path), role=role)
            key=(str(path),int(spec.get('index',0)))
            grouped.setdefault(key,[]).append(role); self._paths[role]=path
            if str(path) not in statuses:
                statuses[str(path)]=_stat(path); self.stats['configured_file_stats']+=1
        for required in ('cn','punct','latin'):
            if required not in self._paths: raise FigureError('font_role_missing','缺少字体角色',role=required)
        new={'version':1,'profile_hash':profkey,'faces':{}}
        for (pathstr, index), roles in grouped.items():
            stat=statuses[pathstr]; signature={**stat,'path':pathstr,'index':index,'normalizer':2}
            oldinfo=old.get('faces',{}).get(roles[0])
            if oldinfo and oldinfo.get('signature')==signature and (self.cache/oldinfo['cache_file']).is_file():
                info=oldinfo; data=(self.cache/info['cache_file']).read_bytes()
                self.stats['persistent_face_hits']+=1
            else:
                self.stats['hash_reads']+=1; source_hash=digest_file(pathstr)
                tt=TTFont(pathstr,fontNumber=index,lazy=True,recalcTimestamp=False)
                self.stats['face_inspections']+=1
                try:
                    family_names=names(tt); fs_type=int(tt['OS/2'].fsType) if 'OS/2' in tt else 0
                    if fs_type&2 or fs_type&0x200:
                        raise FigureError('font_embedding_restricted','字体嵌入标志限制当前输出',role=roles[0],fsType=fs_type)
                    cmap=tt.getBestCmap() or {}
                    if Path(pathstr).suffix.lower() not in ('.ttc','.otc'):
                        data=Path(pathstr).read_bytes()
                    else:
                        buff=io.BytesIO(); writer=SFNTWriter(buff,len(tt.reader.keys()),sfntVersion=tt.sfntVersion)
                        for tag in tt.reader.keys(): writer[tag]=tt.reader[tag]
                        writer.close(); data=buff.getvalue()
                finally: tt.close()
                keyhash=hashlib.sha256(data).hexdigest()
                cache_file='face-'+keyhash+'.bin'
                dest=self.cache/cache_file
                if not dest.exists():
                    tmp=dest.with_suffix('.tmp-'+str(os.getpid())); tmp.write_bytes(data); os.replace(tmp,dest)
                info={'signature':signature,'sha256':source_hash,'face_sha256':keyhash,
                      'names':family_names,'fsType':fs_type,'glyph_count':len(cmap),'cache_file':cache_file}
            for role in roles:
                spec=self.profile['faces'][role]
                expected=spec.get('expected_names',[])
                if expected and not any(x.casefold() in {n.casefold() for n in info['names']} for x in expected):
                    raise FigureError('font_family_mismatch','实际字体与显式配置的身份不符',role=role,expected=expected,actual=info['names'])
                self.face_info[role]=info; new['faces'][role]=info
            f=fitz.Font(fontbuffer=data)
            model=TTFont(io.BytesIO(data),lazy=True,recalcTimestamp=False)
            cmap=model.getBestCmap() or {}; glyphset=model.getGlyphSet();upm=model['head'].unitsPerEm
            postscript_names=[n.toUnicode() for n in model['name'].names if n.nameID==6]
            if not postscript_names:raise FigureError('font_postscript_name_missing','字体缺少PostScript名称',role=roles[0])
            for role in roles:
                self.faces[role]=(f,data)
                self.postscript_names[role]=postscript_names[0]
                self._font_models[role]=(model,cmap,glyphset,upm)
            self.stats['fonts_loaded']+=1
        if new!=old: atomic_json(index_path,new)
        self.fingerprint=digest_json({'measurement_engine':'fonttools-outline-v3-line-center','profile':self.profile,'faces':{r:v['face_sha256'] for r,v in self.face_info.items()}})
        self.db=sqlite3.connect(self.cache/'text-measurements.sqlite',timeout=20)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS measurements (k TEXT PRIMARY KEY, v TEXT NOT NULL)')
        self.no_subset=any(i['fsType']&0x100 for i in self.face_info.values())
        self.is_preview=self.profile.get('purpose')!='production'

    def close(self):
        self.db.commit();self.db.close()
        for model in {id(v[0]):v[0] for v in self._font_models.values()}.values():model.close()

    def verify_unchanged(self):
        for role,p in self._paths.items():
            sig=self.face_info[role]['signature']
            if not p.is_file() or _stat(p)!={k:sig[k] for k in ('size','mtime_ns')}:
                raise FigureError('font_changed_during_batch','批次期间字体文件变化，请重启本批次',role=role)

    def choose(self,ch,style=None):
        overrides=self.profile.get('character_overrides',{})
        if ch in overrides: role=overrides[ch]
        elif ch in self.profile.get('cjk_punctuation',CJK_PUNCT): role='punct'
        elif ('\u3400'<=ch<='\u9fff') or ('\uf900'<=ch<='\ufaff') or ord(ch)>=0x20000: role='cn'
        else: role='latin'
        if style in ('italic','bold','bolditalic'):
            candidate=role+'_'+style
            if candidate not in self.faces:
                raise FigureError('font_style_missing','明确指定的字体样式尚未配置，拒绝模拟或回退',role=candidate)
            role=candidate
        if role not in self.faces: raise FigureError('font_role_missing','字符例外引用了未知字体',role=role)
        return role

    def glyph(self,ch,role):
        k=(ch,role)
        if k not in self._glyphs:
            if role not in self.faces:raise FigureError('font_role_missing','未知显式字体角色',role=role)
            f,_=self.faces[role]
            if not f.has_glyph(ord(ch),fallback=False):
                raise FigureError('missing_glyph',f'字体缺字 U+{ord(ch):04X} {ch}',role=role)
            model,cmap,glyphset,upm=self._font_models[role]
            name=cmap.get(ord(ch))
            if not name:raise FigureError('missing_glyph','字体CMAP中缺少字符',role=role,char=ch)
            pen=BoundsPen(glyphset);glyphset[name].draw(pen)
            b=pen.bounds or (0,0,0,0)
            adv=model['hmtx'][name][0]/upm
            self._glyphs[k]=(adv,[b[0]/upm,-b[3]/upm,b[2]/upm,-b[1]/upm])
        return self._glyphs[k]

    def measure(self, content, size=8., leading=None, *, role='label'):
        content=display_content(content,role)
        self.stats['measure_calls']+=1
        if not isinstance(size,(int,float)) or isinstance(size,bool) or not math.isfinite(size) or size<6-1e-6 or size>8+1e-6:
            raise FigureError('font_size_out_of_policy','当前候选统一字号范围为6—8pt',size=size)
        leading=float(size*1.2 if leading is None else leading)
        if not math.isfinite(leading) or leading<=0:raise FigureError('line_height_invalid','行距必须是有限正数')
        key=digest_json([self.fingerprint,content,size,leading])
        if key in self._measure_memory:
            self.stats['measure_memory_hits']+=1;return self._measure_memory[key]
        row=self.db.execute('SELECT v FROM measurements WHERE k=?',(key,)).fetchone()
        if row:
            self.stats['measure_disk_hits']+=1;result=json.loads(row[0]);self._measure_memory[key]=result;return result
        self.stats['measure_misses']+=1
        parts=[{'text':content}] if isinstance(content,str) else content
        if not isinstance(parts,list): raise FigureError('text_runs_invalid','文本应为字符串或显式样式片段数组')
        x=y=0.; line_no=0; glyphs=[]; all_text=''; boxes=[]
        for part in parts:
            text=part['text'].replace('\r\n','\n').replace('\r','\n');all_text+=text
            factor=float(part.get('scale',1)); shift=float(part.get('baseline_shift_pt',0))
            if not math.isfinite(factor) or not math.isfinite(shift) or factor<=0 or factor>2: raise FigureError('text_scale_invalid','局部字号比例无效')
            s=size*factor
            for ch in text:
                if ch=='\n':x=0.;y+=leading;line_no+=1;continue
                role=part.get('face') or self.choose(ch,part.get('style'))
                adv,b=self.glyph(ch,role)
                box=[x+b[0]*s,y+shift+b[1]*s,x+b[2]*s,y+shift+b[3]*s]
                if not ch.isspace(): boxes.append(box)
                glyphs.append({'ch':ch,'face':role,'size':s,'x':x,'y':y+shift,'advance':adv*s,'ink':box,'line':line_no})
                x+=adv*s
        if not boxes: raise FigureError('empty_text','不绘制空文本')
        # Center every explicit line by its ink, not merely the entire multiline block.
        line_bounds={}
        for g in glyphs:
            if not g['ch'].isspace():
                b=g['ink'];old=line_bounds.get(g['line'],[b[0],b[2]])
                line_bounds[g['line']]=[min(old[0],b[0]),max(old[1],b[2])]
        maxwidth=max(b[1]-b[0] for b in line_bounds.values())
        for g in glyphs:
            b=line_bounds.get(g['line'],[0,0]);shift=(maxwidth-(b[1]-b[0]))/2-b[0]
            g['x']+=shift;g['ink'][0]+=shift;g['ink'][2]+=shift
        boxes=[g['ink'] for g in glyphs if not g['ch'].isspace()]
        bbox=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
        result={'text':all_text,'glyphs':glyphs,'ink':bbox,'width':bbox[2]-bbox[0],'height':bbox[3]-bbox[1],'size':size}
        self._measure_memory[key]=result
        self.db.execute('INSERT OR REPLACE INTO measurements VALUES (?,?)',(key,json.dumps(result,ensure_ascii=False)))
        return result


    def measure_vertical(self,content,size=8.):
        from .vertical_text import measure_vertical
        return measure_vertical(self,content,size)

    def prepare_document_fonts(self,texts):
        groups={}
        for item in texts:
            for g in item['measurement']['glyphs']:groups.setdefault(g['face'],set()).add(ord(g['ch']))
        result={}
        for role,chars in groups.items():
            # Retain a real capital-H metric witness only when OS/2 lacks one.
            # Visible text and positioning still use only the requested glyphs.
            model,cmap,_,_=self._font_models[role]
            cap=getattr(model['OS/2'],'sCapHeight',0) if 'OS/2' in model else 0
            if cap<=0 and ord('H') in cmap:
                chars=chars|{ord('H')}
            key=digest_json(['subset-v4-cap-witness-ps-identity',self.face_info[role]['face_sha256'],sorted(chars)])
            if key in self._doc_buffers:result[role]=self._doc_buffers[key];continue
            file=self.cache/('subset-'+key+'.bin')
            if file.is_file():data=file.read_bytes()
            elif self.face_info[role]['fsType']&0x100:data=self.faces[role][1]
            else:
                tt=TTFont(io.BytesIO(self.faces[role][1]),recalcTimestamp=False)
                opts=subset.Options();opts.layout_features=[];opts.notdef_glyph=True;opts.notdef_outline=True
                opts.recommended_glyphs=True;opts.name_IDs=[1,2,4,6];opts.name_legacy=True
                opts.name_languages=sorted({n.langID for n in tt['name'].names
                    if n.nameID==6 and n.toUnicode()==self.postscript_names[role]})
                sub=subset.Subsetter(options=opts);sub.populate(unicodes=chars);sub.subset(tt)
                b=io.BytesIO();tt.save(b);tt.close();data=b.getvalue()
                tmp=file.with_suffix('.tmp-'+str(os.getpid()));tmp.write_bytes(data);os.replace(tmp,file)
            self._doc_buffers[key]=data;result[role]=data
        self.document_fonts=result
        return result

    def summary(self):
        return {'profile_id':self.profile.get('id'),'purpose':self.profile.get('purpose'),
                'fingerprint':self.fingerprint,'faces':{r:{k:i[k] for k in ('names','sha256','face_sha256','fsType')}
                                                        for r,i in self.face_info.items()},'stats':dict(self.stats)}


def position_text(measured, x, y, align='center', rotation=0):
    if rotation not in (0,90,180,270): raise FigureError('unsupported_text_rotation','只支持0/90/180/270度文字')
    def rot(px,py):
        return {0:(px,py),90:(py,-px),180:(-px,-py),270:(-py,px)}[rotation]
    b=measured['ink']; corners=[rot(px,py) for px in (b[0],b[2]) for py in (b[1],b[3])]
    bb=[min(p[0] for p in corners),min(p[1] for p in corners),max(p[0] for p in corners),max(p[1] for p in corners)]
    if align=='center':dx=x-(bb[0]+bb[2])/2
    elif align=='left':dx=x-bb[0]
    elif align=='right':dx=x-bb[2]
    else: raise FigureError('text_alignment','未知文字对齐')
    dy=y-(bb[1]+bb[3])/2
    return {'bbox':[bb[0]+dx,bb[1]+dy,bb[2]+dx,bb[3]+dy],
            'offset':[dx,dy],'rotation':rotation}


def draw_text(page, registry, item):
    m=item['measurement'];p=item['position'];dx,dy=p['offset'];rot=p['rotation']
    # Contiguous glyphs of the same face/size and baseline are written as one run.
    runs=[]
    for g in m['glyphs']:
        turn=g.get('rotation',0)
        ax,ay={0:(g['advance'],0),90:(0,-g['advance']),180:(-g['advance'],0),270:(0,g['advance'])}[turn]
        if runs and runs[-1]['face']==g['face'] and runs[-1]['size']==g['size'] and runs[-1]['rotation']==turn and abs(runs[-1]['end_x']-g['x'])<1e-6 and abs(runs[-1]['end_y']-g['y'])<1e-6:
            runs[-1]['text']+=g['ch'];runs[-1]['end_x']=g['x']+ax;runs[-1]['end_y']=g['y']+ay
        else:runs.append({'face':g['face'],'size':g['size'],'x':g['x'],'y':g['y'],'text':g['ch'],
                          'rotation':turn,'end_x':g['x']+ax,'end_y':g['y']+ay})
    for r in runs:
        name='JFW_'+r['face']; page.insert_font(fontname=name,fontbuffer=registry.document_fonts[r['face']])
        px,py=r['x'],r['y'];rx,ry={0:(px,py),90:(py,-px),180:(-px,-py),270:(-py,px)}[rot]
        page.insert_text((dx+rx,dy+ry),r['text'],fontname=name,fontsize=r['size'],rotate=(rot+r['rotation'])%360,color=(0,),overlay=True)
