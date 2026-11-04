from __future__ import annotations
import argparse,json,sys,shutil,time
from pathlib import Path
from .common import read_json,atomic_json,FigureError


def main(argv=None):
    p=argparse.ArgumentParser(description='期刊图件直接PDF候选模块：不调用Adobe，不写正式生产台账')
    sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('fonts',help='只核对已指定的字体并建立/读取缓存；不扫描字体目录')
    f.add_argument('--profile',required=True,type=Path);f.add_argument('--cache',type=Path);f.add_argument('--refresh',action='store_true');f.add_argument('--report',type=Path)
    i=sub.add_parser('inspect',help='只读检查PDF/SVG/PPTX/图片对象')
    i.add_argument('files',nargs='+',type=Path);i.add_argument('--output',required=True,type=Path)
    sp=sub.add_parser('prepare-svg-pdf',help='将受支持的SVG准备为矢量PDF中间件')
    sp.add_argument('input',type=Path);sp.add_argument('--source-sha256',required=True);sp.add_argument('--output',required=True,type=Path);sp.add_argument('--report',required=True,type=Path)
    ts=sub.add_parser('prepare-text-shadows',help='发现文字阴影候选，或按具体确认准备派生源；不生成成图')
    ts.add_argument('input',type=Path);ts.add_argument('--source-sha256',required=True);ts.add_argument('--bindings',required=True,type=Path);ts.add_argument('--report',required=True,type=Path)
    ts.add_argument('--proposal',type=Path);ts.add_argument('--confirmation',type=Path);ts.add_argument('--output',type=Path);ts.add_argument('--page',type=int,default=0)
    ps=sub.add_parser('propose-chart-series',help='查找原矢量曲线与图例样符的候选对应')
    ps.add_argument('input',type=Path);ps.add_argument('--source-sha256',required=True);ps.add_argument('--frame',nargs=4,type=float,required=True);ps.add_argument('--plot',nargs=4,type=float,required=True);ps.add_argument('--swatch',nargs=2,type=int,action='append',required=True);ps.add_argument('--output',type=Path,required=True)
    for name in ('render','batch'):
        q=sub.add_parser(name);q.add_argument('input',type=Path);q.add_argument('--profile',required=True,type=Path)
        q.add_argument('--output',required=True,type=Path);q.add_argument('--cache',type=Path);q.add_argument('--overwrite',action='store_true')
        if name=='render':q.add_argument('--source-root',required=True,type=Path)
    sv=sub.add_parser('serve',help='本地审核台；只监听127.0.0.1')
    sv.add_argument('batch',type=Path);sv.add_argument('--profile',required=True,type=Path);sv.add_argument('--output',required=True,type=Path);sv.add_argument('--cache',type=Path);sv.add_argument('--port',type=int,default=8765)
    w=sub.add_parser('windows-fonts',help='仅首次配置时主动查询Windows字体注册表，不遍历字体文件夹')
    w.add_argument('--output',required=True,type=Path)
    doctor=sub.add_parser('doctor',help='检查已安装依赖；不扫描字体、不安装或更改环境')
    doctor.add_argument('--output',required=True,type=Path)
    ae=sub.add_parser('agent',help='对话/Agent入口：原图证据、语义回复、生成与复核')
    ac=ae.add_subparsers(dest='action',required=True)
    ap=ac.add_parser('prepare');ap.add_argument('files',nargs='+',type=Path);ap.add_argument('--job',required=True,type=Path);ap.add_argument('--workers',type=int,default=1)
    ar=ac.add_parser('complete');ar.add_argument('--job',required=True,type=Path);ar.add_argument('--reply',required=True,type=Path);ar.add_argument('--profile',required=True,type=Path);ar.add_argument('--cache',type=Path)
    ar.add_argument('--production-policy-exceptions',type=Path,help='制作调用方单独提供的字号例外证据；不可来自语义回复自批')
    ast=ac.add_parser('status');ast.add_argument('--job',required=True,type=Path)
    av=ac.add_parser('review');av.add_argument('--job',required=True,type=Path);av.add_argument('--record',required=True,type=Path)
    args=p.parse_args(argv)
    try:
        if args.command=='prepare-text-shadows':
            from .source_text_shadows import discover_text_shadows,remove_confirmed_text_shadows
            from .common import digest_file
            if digest_file(args.input)!=args.source_sha256.lower():raise FigureError('text_shadow_source_changed','当前图源哈希不符')
            if args.report.exists() or args.output and args.output.exists():raise FigureError('text_shadow_output_exists','禁止覆盖已有准备件或报告')
            rows=read_json(args.bindings)
            if isinstance(rows,dict):rows=rows['replacements']
            if any((args.proposal,args.confirmation,args.output)):
                if not all((args.proposal,args.confirmation,args.output)):raise FigureError('text_shadow_confirmation','执行须同时提供候选、确认和派生源路径')
                data,out=remove_confirmed_text_shadows(args.input,args.page,rows,read_json(args.proposal),read_json(args.confirmation))
                if digest_file(args.input)!=args.source_sha256.lower():raise FigureError('text_shadow_source_changed','准备期间图源已变化')
                args.output.parent.mkdir(parents=True,exist_ok=True)
                with args.output.open('xb') as dest:dest.write(data)
                out.update(output=str(args.output.resolve()),output_sha256=digest_file(args.output))
            else:out=discover_text_shadows(args.input,args.page,rows)
            atomic_json(args.report,out)
        elif args.command=='propose-chart-series':
            import pymupdf as fitz
            from .chart_vector_legend import propose_series_binding
            from .common import digest_file
            if args.output.exists():raise FigureError('chart_output_exists','候选报告已存在，禁止覆盖')
            if digest_file(args.input)!=args.source_sha256.lower():raise FigureError('chart_source_changed','PDF源哈希不一致')
            with fitz.open(args.input) as doc:
                if len(doc)!=1:raise FigureError('chart_source_pages','当前候选发现要求单页PDF')
                drawings=doc[0].get_drawings()
                candidates=[propose_series_binding(drawings,a,b,args.frame,args.plot) for a,b in args.swatch]
            if digest_file(args.input)!=args.source_sha256.lower():raise FigureError('chart_source_changed','扫描期间PDF源已改变')
            out={'status':'needs_review','source':str(args.input.resolve()),'sourceSha256':args.source_sha256.lower(),'candidates':candidates,'warning':'候选必须结合当前图的文字与图例核对；不代表成图或已通过检查'}
            atomic_json(args.output,out)
        elif args.command=='prepare-svg-pdf':
            from .assets import svg_root,svg_pdf_bytes
            from .common import digest_file
            if args.output.exists() or args.report.exists():raise FigureError('svg_output_exists','输出或报告已存在，禁止覆盖')
            if digest_file(args.input)!=args.source_sha256.lower():raise FigureError('svg_source_changed','SVG源哈希不一致')
            root=svg_root(args.input);data=svg_pdf_bytes(root)
            if digest_file(args.input)!=args.source_sha256.lower():raise FigureError('svg_source_changed','转换期间SVG源已改变')
            args.output.parent.mkdir(parents=True,exist_ok=True);args.report.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('xb') as dest:dest.write(data)
            out={'status':'intermediate','source':str(args.input.resolve()),'sourceSha256':args.source_sha256.lower(),'output':str(args.output.resolve()),'outputSha256':digest_file(args.output),'maskCount':len(root.xpath('.//s:mask',namespaces={'s':'http://www.w3.org/2000/svg'}))}
            atomic_json(args.report,out)
        elif args.command=='agent':
            from .agent_entry import prepare,complete,review
            if args.action=='prepare':out=prepare(args.files,args.job,workers=args.workers)
            elif args.action=='status':out=read_json(args.job/'job.json')
            elif args.action=='review':
                record=read_json(args.record);out=review(args.job,reviewer=record['reviewer'],items=record['items'])
            else:
                if args.reply.stat().st_size>2_000_000:raise FigureError('reply_size_limit','语义回复过大')
                policy_exceptions=read_json(args.production_policy_exceptions) if args.production_policy_exceptions else None
                result=complete(args.job,read_json(args.reply),args.profile,cache=args.cache,production_policy_exceptions=policy_exceptions)
                out={k:result[k] for k in ('status','attempt','rendered','failures','unresolved_exceptions','declared_exclusions','timings','reused_unaffected_figures')}
            print(json.dumps(out,ensure_ascii=False,indent=2));return 2 if out.get('failures') or out.get('unresolved_exceptions') or out.get('blocked_sources') else 0
        elif args.command=='doctor':
            from .doctor import diagnose
            out=diagnose();atomic_json(args.output,out)
        elif args.command=='fonts':
            from .fonts import FontRegistry
            t=time.perf_counter();r=FontRegistry(args.profile,args.cache,refresh=args.refresh)
            out=r.summary()|{'initialization_ms':round((time.perf_counter()-t)*1000,3)};r.close()
            if args.report:atomic_json(args.report,out)
        elif args.command=='windows-fonts':
            from .windows_fonts import registry_inventory
            out=registry_inventory();atomic_json(args.output,out)
        elif args.command=='inspect':
            from .inspect import inspect_file
            out={'files':[inspect_file(f) for f in args.files]};atomic_json(args.output,out)
        elif args.command=='batch':
            from .batch import run_batch
            r=run_batch(args.input,args.profile,args.output,args.cache,args.overwrite)
            out={'status':r['status'],'rendered':len(r['results']),'blocked':len(r['failures']),'wall_clock_ms':r['wall_clock_ms'],'output':str(args.output)}
            print(json.dumps(out,ensure_ascii=False));return 0 if not r['failures'] else 2
        elif args.command=='serve':
            from .server import serve
            serve(args.batch,args.profile,args.output,args.cache,args.port);return 0
        else:
            from .fonts import FontRegistry
            from .assets import Assets
            from .render import render_one
            reg=FontRegistry(args.profile,args.cache);a=Assets()
            try:r=render_one(read_json(args.input),reg,a,args.source_root,args.output,overwrite=args.overwrite)
            finally:reg.close();a.close()
            out={'status':r['status'],'pdf':r['output_pdf'],'timings_ms':r['timings_ms']}
        print(json.dumps(out,ensure_ascii=False,indent=2));return 0
    except FigureError as e:
        print(json.dumps({'status':'blocked','error':e.as_dict()},ensure_ascii=False),file=sys.stderr);return 2
    except Exception as e:
        print(json.dumps({'status':'error','type':type(e).__name__,'message':str(e)},ensure_ascii=False),file=sys.stderr);return 1

if __name__=='__main__':raise SystemExit(main())
