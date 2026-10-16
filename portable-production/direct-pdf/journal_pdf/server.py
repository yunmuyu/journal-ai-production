"""Small localhost-only review surface. No production state or arbitrary-file API."""
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
from urllib.parse import unquote,urlparse
import json,secrets,time,copy,mimetypes,math
from .editorial import engine_signature
from .common import read_json,atomic_json,FigureError,resolve_source,PT_PER_MM,digest_json,validate_output_isolation
from .batch import load_batch,run_batch
from .fonts import FontRegistry
from .assets import Assets
from .render import render_one
from .gallery import gallery_html


def apply_changes(spec,changes):
    allowed={'column','font_size','plot_width_mm','legend_placement'}
    if not isinstance(changes,dict) or set(changes)-allowed:raise FigureError('unknown_override','拒绝未知修改字段')
    new=copy.deepcopy(spec);policy=new.setdefault('policy',{})
    if 'column' in changes:
        if changes['column'] not in ('single','double','auto'):raise FigureError('invalid_column','栏宽无效')
        policy['column']=changes['column']
    if 'font_size' in changes:
        v=str(changes['font_size'])
        try:size=8. if v=='auto' else float(v)
        except ValueError:raise FigureError('invalid_font_choice','字号选项无效')
        if not math.isfinite(size) or not 6<=size<=8:raise FigureError('invalid_font_choice','字号需为6—8pt，可使用小数')
        policy['font_sizes']=[size];policy['design_font_size_pt']=size
    if 'plot_width_mm' in changes:
        v=changes['plot_width_mm']
        if new['kind']!='chart' or not isinstance(v,(int,float)) or not 15<=v<=130:
            raise FigureError('invalid_plot_width','绘图区宽度无效')
        new['plot_width_pt']=v*PT_PER_MM
    if 'legend_placement' in changes:
        if new['kind']!='chart' or changes['legend_placement'] not in ('upper-right','lower-right','source-region'):
            raise FigureError('invalid_legend_override','图例位置无效')
        new['legend_placement']=changes['legend_placement']
    return new



def validate_review_identity(report,batch_path,manifest,specs,profile):
    """Never show old PDFs as current after a manifest, spec or profile change."""
    if report.get('engine_signature') != engine_signature():
        raise FigureError('review_rules_changed','引擎或规范版本已变；旧候选与旧通过记录不能复用，请使用新输出目录')
    if report.get('source_batch') != str(batch_path.resolve()):
        raise FigureError('review_batch_mismatch','输出目录属于另一批次，请更换候选输出目录')
    expected = digest_json({'manifest':manifest,'specs':specs})
    if report.get('batch_signature') != expected:
        raise FigureError('review_inputs_changed','批次或制作说明已变化，请使用新的输出目录重新生成')
    if report.get('font_profile_signature') != digest_json(read_json(profile)):
        raise FigureError('review_font_profile_changed','字体方案已变化，请使用新的输出目录重新生成')


def serve(batch_path,profile,output,cache=None,port=8765):
    if not 1024<=port<=65535:raise FigureError('port','端口需位于1024—65535')
    output=output.resolve()
    b,specs,source=load_batch(batch_path)
    validate_output_isolation(source,output)
    output.mkdir(parents=True,exist_ok=True)
    specmap={s['id']:s for s in specs}
    reportfile=output/'batch-report.json'
    report=read_json(reportfile) if reportfile.exists() else run_batch(batch_path,profile,output,cache)
    validate_review_identity(report,batch_path,b,specs,profile)
    session=output/'session-report.json';session_specs=output/'session-specs.json'
    if session.is_file() and session_specs.is_file():
        saved=read_json(session_specs)
        if set(saved)!=set(specmap):raise FigureError('review_set_mismatch','会话图件集合不同')
        report=read_json(session);specmap=saved
        if report.get('engine_signature') != engine_signature():
            raise FigureError('review_rules_changed','会话候选基于旧规则，请重新生成')
    reg=FontRegistry(profile,cache)
    if report.get('font_cache',{}).get('fingerprint')!=reg.fingerprint:
        reg.close()
        raise FigureError('review_fonts_changed','字体字节或测量版本已变化；请换新输出目录重新生成，不复用旧PDF预览')
    assets=Assets();token=secrets.token_urlsafe(32)
    notesfile=output/'review-notes.json';notes=read_json(notesfile) if notesfile.exists() else {}
    class Handler(BaseHTTPRequestHandler):
        def host_ok(self):return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
        def send_data(self,status,data,kind='application/json; charset=utf-8'):
            if not isinstance(data,bytes):data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)))
            self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def do_GET(self):
            if not self.host_ok():return self.send_data(403,{'message':'Host rejected'})
            route=urlparse(self.path).path
            if route=='/':return self.send_data(200,gallery_html(report,token,'/outputs/').encode(),'text/html; charset=utf-8')
            if route=='/api/notes':return self.send_data(200,notes)
            if route.startswith('/outputs/'):
                try:
                    p=resolve_source(output,unquote(route[len('/outputs/'):]))
                    if p.suffix.lower() not in ('.png','.pdf','.json'):raise FigureError('file_type','该文件类型不对外提供')
                    return self.send_data(200,p.read_bytes(),mimetypes.guess_type(p.name)[0] or 'application/octet-stream')
                except FigureError:return self.send_data(404,{'message':'Not found'})
            return self.send_data(404,{'message':'Not found'})
        def do_POST(self):
            if not self.host_ok() or self.headers.get('X-JFW-Token')!=token:return self.send_data(403,{'message':'Token or Host rejected'})
            origin=self.headers.get('Origin')
            if origin and origin not in (f'http://127.0.0.1:{port}',f'http://localhost:{port}'):
                return self.send_data(403,{'message':'Origin rejected'})
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=16384:raise FigureError('request_size','请求大小无效')
                body=json.loads(self.rfile.read(size));id=body.get('id')
                if id not in specmap:raise FigureError('unknown_figure','未知图件ID')
                if self.path=='/api/note':
                    text=body.get('text','')
                    if not isinstance(text,str) or len(text)>8000:raise FigureError('note_length','备注过长')
                    notes[id]=text;atomic_json(notesfile,notes);return self.send_data(200,{'ok':True})
                if self.path!='/api/render':return self.send_data(404,{'message':'Not found'})
                new=apply_changes(specmap[id],body.get('changes',{}));run=output/'runs'/str(time.time_ns())
                r=render_one(new,reg,assets,source,run)
                r['output_pdf']=str((run/r['output_pdf']).relative_to(output));r['preview']=str((run/r['preview']).relative_to(output))
                # Earlier batch summary is deliberately not presented as current after an edit.
                report['summary_pdf']=None
                report['summary_stale_after_edit']=True
                old=next((x for x in report['results'] if x['id']==id),None)
                if old and old.get('reference_preview'):r['reference_preview']=old['reference_preview']
                specmap[id]=new
                merged={x['id']:x for x in report['results']};merged[id]=r
                report['results']=[merged[k] for k in b['expected_export_ids'] if k in merged]
                report['failures']=[f for f in report.get('failures',[]) if f['id']!=id]
                report['rendered_ids']=[x['id'] for x in report['results']]
                report['status']='candidate-partial' if report['failures'] else 'candidate-complete'
                atomic_json(session_specs,specmap);atomic_json(output/'session-report.json',report)
                return self.send_data(200,r)
            except Exception as e:
                err=e.as_dict() if isinstance(e,FigureError) else {'code':'server_error','message':str(e)}
                return self.send_data(422,{'error':err})
    http=HTTPServer(('127.0.0.1',port),Handler)
    print(f'本地候选工作台：http://127.0.0.1:{port}   Ctrl+C 停止。未连接正式生产台账。',flush=True)
    try:http.serve_forever()
    except KeyboardInterrupt:pass
    finally:http.server_close();reg.close();assets.close()
