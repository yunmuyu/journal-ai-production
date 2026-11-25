"""Evidence for the current measured layout, never a choice of column policy."""
from .common import PT_PER_MM
from .journal_rules import load_rules


def layout_capacity(spec, *, spec_hash, effective_column, width_pt, height_pt, font_size_pt, scale, column_mm,
                    available_width_pt, export_padding_pt, verified_sources):
    normative = load_rules()['normative']
    floor = float(normative['scale_floor_pt'])
    stroke = float(normative['stroke_pt'])
    proposed_size = font_size_pt * scale
    fits_font = proposed_size >= floor - 1e-7
    column = '单栏简图' if column_mm == float(normative['simple_chart_mm']) else '单栏' if column_mm <= float(normative['single_column_mm']) else '双栏'
    summary = (f'当前布局在{column}{column_mm:g} mm内整图缩放后正文为{proposed_size:.2f} pt'
               + (f'，不低于{floor:g} pt。' if fits_font else f'，低于{floor:g} pt，须重新布局。'))
    return {
        'version': 1, 'figure_id': spec.get('id'), 'spec_hash': spec_hash,
        'source_bindings': dict(verified_sources or {}),
        'requested_column': spec.get('policy', {}).get('column', 'single'),
        'effective_column': effective_column,
        'column_mm': column_mm, 'available_width_pt': available_width_pt,
        'layout_width_pt': width_pt, 'layout_height_pt': height_pt,
        'layout_font_size_pt': font_size_pt, 'whole_artwork_scale': scale,
        'proposed_font_size_pt': proposed_size, 'minimum_font_size_pt': floor,
        'export_padding_pt': export_padding_pt, 'stroke_allowance_pt': stroke,
        # This is only a font-rule bound for this layout. Arrows, geometry and
        # protected content can require more width, and a new layout can need less.
        'minimum_width_mm_for_font_rule': (width_pt * floor / font_size_pt
                                           + 2 * export_padding_pt + stroke) / PT_PER_MM,
        'status': 'font-rule-passed' if fits_font else 'blocked-font',
        'summary': summary,
        'scope': 'current measured layout only; not a global minimum or publication approval; '
                 'source-path and raster-internal typography are not measured',
        'decision_policy': 'preserve explicit single column; simple charts start at 60mm; auto advances after 6pt relayout',
    }


def check_capacity(spec, reg, assets, source_root):
    """Run the same bound layout and geometry checks as render, without a PDF."""
    from .render import compile_bound_figure
    from .common import FigureError, digest_file, resolve_source
    scene, bindings, _, _ = compile_bound_figure(spec, reg, assets, source_root)
    # A plan that fits only after violating a registered route is not feasible.
    # Reuse the same source contract; saved-PDF visibility still needs rendering.
    from .source_route_contract import audit_source_routes
    routes = audit_source_routes(spec, scene, source_root, bindings)
    if routes['status'] == 'checked':
        scene.layout_evidence['capacity']['source_route_audit'] = routes
    reg.verify_unchanged()
    for binding in bindings:
        if digest_file(resolve_source(source_root, binding['path'])) != binding['sha256']:
            raise FigureError('source_changed_during_capacity', '容量检查期间源文件已变化')
    return {'status': 'layout-capacity-checked', 'capacity': scene.layout_evidence['capacity'],
            'pdf_produced': False, 'ready_for_publication': False}
