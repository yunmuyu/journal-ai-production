from __future__ import annotations
import time, os, tempfile, shutil, html
from pathlib import Path
from collections import Counter
import pymupdf as fitz
from .common import read_json,atomic_json,FigureError,digest_file,resolve_source,safe_name,digest_json,validate_output_isolation
from .fonts import FontRegistry
from .assets import Assets
from .render import render_one
from .editorial import engine_signature,RULESET


def load_batch(path:Path):
    path=path.resolve();b=read_json(path)
    if b.get('version')!=1:raise FigureError('batch_version','批次版本必须为1')
    specs=[]
    for name in b.get('specs',[]):
        p=resolve_source(path.parent,name);s=read_json(p);safe_name(s['id']);safe_name(s.get('author','未归属'));specs.append(s)
    ids=[s['id'] for s in specs];expected=b.get('expected_export_ids',[])
    if len(ids)!=len(set(ids)) or len(expected)!=len(set(expected)):raise FigureError('duplicate_figure_id','批次中有重复图件ID')
    # Reject collisions on Windows as well as on this test platform.
    if len({v.casefold() for v in ids}) != len(ids):
        raise FigureError('casefold_figure_collision','图件ID在Windows上会发生大小写文件名冲突')
    if not expected or Counter(ids)!=Counter(expected):raise FigureError('incomplete_export_set','制作说明与预期交付集合不一致',actual=ids,expected=expected)
    source=(path.parent/b['source_root']).resolve()
    if not source.is_dir():raise FigureError('source_root_missing','素材根目录不存在')
    return b,specs,source


def make_summary(results,output_root,reg):
    """Physical figure size is unchanged; 7pt identity band is outside the figure."""
    from .fonts import draw_text, position_text
    doc=fitz.open();evidence=[]
    for r in results:
        p=resolve_source(output_root,r['output_pdf'])
        if digest_file(p)!=r['pdf_sha256']:raise FigureError('summary_hash_mismatch','汇总前单图已变更')
        d=fitz.open(p);src=d[0];w,h=src.rect.width,src.rect.height
        label=r.get('author','未归属')+'  '+r['id']+'  '+('双栏' if r['layout']['layout_evidence']['column_mm']==160 else '单栏')+'  候选'
        m=reg.measure(label,7)
        pw=max(w,m['width']+.5);band=m['height']+6.5
        pg=doc.new_page(width=pw,height=h+band)
        target=fitz.Rect((pw-w)/2,0,(pw+w)/2,h)
        pg.show_pdf_page(target,d,0,keep_proportion=True)
        # Independent footer document: prevents reuse of an imported subset's CID map.
        footer=fitz.open();fp=footer.new_page(width=pw,height=band)
        item={'measurement':m,'position':position_text(m,pw/2,3+m['height']/2)}
        reg.prepare_document_fonts([item]);draw_text(fp,reg,item)
        if label not in fp.get_text():raise FigureError('summary_label_text','图外标注文字写入失败')
        pg.show_pdf_page(fitz.Rect(0,h,pw,h+band),footer,0,keep_proportion=True)
        footer.close()
        evidence.append({'id':r['id'],'source_sha256':r['pdf_sha256'],'source_size_pt':[w,h],
                         'target_rect_pt':list(target),'figure_scale':1,'label_font_size_pt':7,
                         'identity_text':label,'summary_page_size_pt':[pw,h+band]})
        d.close()
    if len(doc):
        target=output_root/'候选样张汇总.pdf';tmp=output_root/'.summary.tmp.pdf'
        doc.set_toc([[1,r['id'],i+1] for i,r in enumerate(results)])
        doc.set_metadata({'title':'直接PDF规则修订候选汇总','subject':'非排版定稿；单图不缩放；7pt图外身份标注'})
        doc.save(tmp,garbage=4,deflate=True);doc.close()
        with fitz.open(tmp) as audit_doc:
            for page,ev in zip(audit_doc,evidence):
                if ev['identity_text'] not in page.get_text():
                    raise FigureError('summary_label_text','实际汇总PDF的图外标注丢字',id=ev['id'])
        os.replace(tmp,target)
        atomic_json(output_root/'summary-audit.json',{'pages':evidence,'summary_sha256':digest_file(target),
                    'status':'candidate','requires_visual_review':True})
        return target.name
    doc.close();return None


def run_batch(batch_path:Path,profile:Path,output:Path,cache=None,overwrite=False):
    t=time.perf_counter();b,specs,source=load_batch(batch_path);output=output.resolve()
    validate_output_isolation(source,output)
    output.mkdir(parents=True,exist_ok=True)
    if (output/'batch-report.json').exists() and not overwrite:raise FigureError('batch_output_exists','批次输出已存在，请用新目录或显式覆盖')
    reg=FontRegistry(profile,cache);font_init=time.perf_counter()-t;assets=Assets();results=[];failures=[]
    try:
        # Work is grouped by type; the final manifest/summary returns to per-paper order.
        for s in sorted(specs,key=lambda x:(x['kind'],x.get('author','未归属'),x['id'])):
            try:
                result=render_one(s,reg,assets,source,output,overwrite=overwrite)
                ref=next((v for v in s.get('sources',[]) if v.get('role')=='reference' and v['path'].endswith('.pdf')),None)
                if ref:
                    d=fitz.open(resolve_source(source,ref['path']));q=output/result['output_pdf'];dest=q.parent/'reference.png'
                    d[0].get_pixmap(dpi=220).save(dest);d.close();result['reference_preview']=str(dest.relative_to(output))
                results.append(result)
            except Exception as e:
                f={'id':s['id'],'author':s['author'],'status':'blocked','error':e.as_dict() if isinstance(e,FigureError) else {'code':'unexpected_error','message':str(e)}}
                failures.append(f);atomic_json(output/'failures'/(s['id']+'.json'),f)
        order={s['id']:i for i,s in enumerate(specs)};results.sort(key=lambda r:order[r['id']])
        summary=make_summary(results,output,reg) if results else None
        report={'version':1,'engine_signature':engine_signature(),'editorial_ruleset':RULESET,'editorial_coverage':'partial-see-RULE-COVERAGE.md','status':'candidate-complete' if not failures else 'candidate-partial','ready_for_publication':False,
                'expected_ids':b['expected_export_ids'],'rendered_ids':[r['id'] for r in results],
                'results':results,'failures':failures,'font_cache':reg.summary(),'asset_cache':assets.stats,
                'unassigned_sources':b.get('unassigned_sources',[]),'summary_pdf':summary,
                'wall_clock_ms':round((time.perf_counter()-t)*1000,3),'font_init_ms':round(font_init*1000,3),
                'timing_scope':'includes manifest/source checks, font init, layout, PDF generation, actual PDF audits, previews, reference previews and summary; excludes author/AI specification preparation, human review, final gallery/report serialization and cache commit',
                'ai_required':False,'source_batch':str(batch_path.resolve()),
                'batch_signature':digest_json({'manifest':b,'specs':specs}),
                'font_profile_signature':digest_json(read_json(profile))}
        atomic_json(output/'batch-report.json',report)
        from .gallery import make_gallery
        make_gallery(report,output)
        return report
    finally:reg.close();assets.close()
