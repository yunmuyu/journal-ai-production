"""Coverage ledger for the existing pinned rules; not a new editorial standard.
Entries report actual handler/audit results or an explicit pending state.
"""
import math
from .editorial import RULESET
from .common import FigureError,PT_PER_MM
from .agent_spec import validate_production_policy_exception


def _font_policy_evidence(spec,evidence):
    """Check measured inputs and arithmetic, never infer an 8pt start from final size."""
    keys=('initial_design_font_size_pt','initial_design_width_pt','design_font_size_pt',
          'design_width_pt','whole_artwork_scale','final_font_size_pt','column_mm')
    values=[evidence.get(k) for k in keys]
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in values):
        return False,False
    initial,initial_width,design,width,scale,final,column=values
    policy=spec.get('policy',{});legacy=policy.get('font_sizes',[8])
    declared=policy.get('design_font_size_pt',legacy[0] if legacy else None)
    attempts=evidence.get('fit_attempts',[])
    measured=(6<=initial<=8 and declared==initial and initial_width>0 and width>0
              and 6-1e-6<=final<=8+1e-6 and 6<=design<=initial and 0<scale<=1 and column in (80,160)
              and math.isclose(design*scale,final,abs_tol=1e-6)
              and math.isclose(scale,min(1.,(column*PT_PER_MM-.5)/width),abs_tol=1e-6)
              and (final>=initial-1e-6 or initial_width>column*PT_PER_MM-.5)
              and len(attempts)==1 and attempts[0].get('design_font_size_pt')==initial
              and attempts[0].get('font_size_pt')==final and attempts[0].get('whole_artwork_scale')==scale)
    if not measured:return False,False
    exception_ok=False
    provenance=spec.get('ingest_provenance',{});basis=provenance.get('production_font_policy',{})
    bound_source=provenance.get('source_file_sha256')
    source_is_current=any(isinstance(row,dict) and row.get('sha256')==bound_source
                          for row in spec.get('sources',[]))
    if initial<8 and source_is_current and isinstance(basis,dict) and basis.get('design_font_size_pt')==initial:
        try:
            validate_production_policy_exception(basis.get('exception'),provenance.get('reply_hash'),
                                                 provenance.get('source_file_sha256'),initial)
            exception_ok=True
        except FigureError:pass
    return initial==8,exception_ok


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
    default8,exception=_font_policy_evidence(spec,layout['layout_evidence'])
    add('whole-artwork-default8-min6',True,default8,'compile_figure measured initial input + scale_scene arithmetic',
        None if default8 else 'No verified 8pt starting layout; an explicit exception is reported separately, not relabelled as default8')
    add('explicit-design-size-policy-exception',spec.get('policy',{}).get('design_font_size_pt',8)<8,exception,
        'separate production caller record + exact reply/source/size binding',
        'Recorded external approval claim only; not cryptographic authentication or an 8pt-first measurement')
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
