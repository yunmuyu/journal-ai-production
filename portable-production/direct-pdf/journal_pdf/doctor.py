"""Dependency probe, explicit invocation only; no downloads or system mutations."""
import importlib,platform,sys

def diagnose():
    rows=[]
    for name in ('pymupdf','fontTools','PIL','lxml','pptx','cairosvg','numpy','cv2'):
        try:
            m=importlib.import_module(name)
            rows.append({'module':name,'available':True,'version':str(getattr(m,'__version__',getattr(m,'VersionBind','unknown')))})
        except Exception as e:
            rows.append({'module':name,'available':False,'error':str(e),
                         'affected_route':'SVG only' if name=='cairosvg' else 'raster evidence only' if name in ('numpy','cv2') else 'core'})
    return {'platform':platform.platform(),'python':sys.version,'modules':rows,
            'font_directory_scans':0,'system_mutations':False,
            'all_dependencies_available':all(r['available'] for r in rows),
            'note':'Windows SVG路线需要Cairo运行库；pip安装成功不等于Cairo DLL可加载。缺失则明确阻断SVG，不改变虚线、不自动转位图。'}
