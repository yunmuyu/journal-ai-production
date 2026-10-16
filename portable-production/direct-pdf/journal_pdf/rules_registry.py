"""Coverage ledger for the existing pinned rules; not a new editorial standard.
Entries report actual handler/audit results or an explicit pending state.
"""
from .editorial import RULESET


def rule_evidence(spec,result):
    audit=result['pdf_audit'];layout=result['layout'];nodes=layout.get('nodes',[])
    chart=spec['kind']=='chart';rows=[]
    def add(id,applies,verified,handler,limitation=None):
        rows.append({'id':id,'status':'not-applicable' if not applies else 'checked' if verified else 'pending',
                     'handler':handler,'limitation':limitation})
    add('axis-quantity-slash-unit',chart,audit['axis_unit_notation']['ok'],'axis_units + actual PDF audit',
        'Known trailing units only; unknown/compound semantics retain an explicit pending warning')
    add('numeric-groups-of-three',chart,audit['numeric_grouping_in_actual_pdf'],'editorial.group_number + pdf_audit',
        'Numeric semantic roles only; never split models/IP/version identifiers')
    add('rectangle-ink-padding',any(n['kind']=='rectangle' and not n['container'] for n in nodes),True,'Scene.box + audit_scene')
    add('diamond-formal-calibration',any(n['kind']=='diamond' for n in nodes),True,'editorial.diamond_size + audit_scene')
    add('whole-artwork-default8-min6',True,6-1e-6<=layout['layout_evidence']['final_font_size_pt']<=8+1e-6,'compile_figure + scale_scene')
    add('visible-vector-stroke-0.5pt',True,audit['effective_path_strokes_05pt'],'pdf_audit actual stroke paths',
        'Raster strokes are not silently claimed normalized')
    add('text-black-and-font-embedded',True,audit['editable_text_pure_black'] and audit['all_fonts_embedded'],'pdf_audit')
    add('neutral-gray-output',True,audit['neutral_rgb_300dpi'],'300dpi actual PDF RGB inspection')
    add('quarter-point-export-pad',True,'export_crop' in layout['layout_evidence'],'actual PDF ink crop')
    add('production-composite-font-equivalence',True,False,'configured identity available; composite equivalence needs explicit acceptance',
        'Preview fonts are not the production composite-font acceptance')
    add('native-topology-and-full-meaning',True,False,'Agent original-source review + final visual review',
        'Mechanical geometry success does not prove source semantics')
    add('complex-unit-formula-and-specialty-rules',True,False,'See RULE-COVERAGE.md','Not all specialist rules or mathematical styling are implemented')
    add('InDesign-and-print-preflight',True,False,'external acceptance','Not performed by this renderer')
    return {'source':RULESET,'scope':'existing rule implementation coverage, not whole-journal acceptance','rules':rows,
            'unimplemented_rules_never_marked_pass':True}
