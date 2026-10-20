from pathlib import Path
import pymupdf as fitz
import pytest
from lxml import etree as ET
from journal_pdf.assets import Assets, grayscale_svg, geometry_signature
from journal_pdf.source_icons import audit_icon_paths
from journal_pdf.common import FigureError


def test_full_source_body_removes_registered_font_and_preserves_overlapping_wire(tmp_path):
    # Given a genuine source text span whose bbox intersects an original wire.
    source = tmp_path / 'original.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=100, height=80)
        page.draw_line((10, 22), (90, 22), width=.73)
        page.insert_text((20, 25), 'R1', fontsize=8)
        span = page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(source)
    assets = Assets()
    try:
        # When the explicit source-body route replaces that exact span.
        body = assets.source_vector_body(source, 0, [0, 0, 100, 80], text_replacements=[{'source_text':'R1','source_bbox':list(span['bbox']),'target_text_id':'r1'}])
        # Then the body has no old text/font, and wire ownership remains exact.
        assert body.audit['mode'] == 'source-vector-body'
        assert body.doc[0].get_fonts() == []
        assert body.doc[0].get_texttrace() == []
        with fitz.open() as output:
            page = output.new_page(width=100, height=80)
            assets.place(page, body, [0, 0, 100, 80])
            rows = [{'asset':body,'rect':[0,0,100,80],'id':'body'}]
            assert audit_icon_paths(page, rows)['matched_path_count'] == 1
            page.draw_line((12,22), (30,22), width=.75)
            assert len(audit_icon_paths(page, rows)['stroke_violations']) == 1
    finally:
        assets.close()


def test_svg_hex_gray_is_neutral_and_does_not_change_geometry():
    # Given colored short and long hex values.
    root = ET.fromstring(b'<svg xmlns="http://www.w3.org/2000/svg"><path id="wire" d="M0 0L10 10" style="stroke:#00ffff;fill:#ff0;stroke-width:0.5"/></svg>')
    before = geometry_signature(root, ['wire'])
    # When preparing the grayscale SVG.
    changed = grayscale_svg(root)
    # Then both paints are neutral and geometry remains identical.
    assert changed == 2
    style = root[0].get('style')
    assert '#00ffff' not in style and '#ff0' not in style
    assert geometry_signature(root, ['wire']) == before

def test_svg_central_css_and_gradient_stop_color_are_neutral():
    # Given the paint locations used by the real Visio source.
    root = ET.fromstring(b'<svg xmlns="http://www.w3.org/2000/svg"><style>.wire{stroke:#00ffff;fill:#ffff00}</style><defs><linearGradient><stop stop-color="#ff0"/></linearGradient></defs></svg>')
    # When preparing grayscale.
    changed = grayscale_svg(root)
    # Then centralized styles and gradient paints are included.
    assert changed == 3
    assert '#00ffff' not in root[0].text
    assert root[1][0][0].get('stop-color') == '#ededed'

def test_body_rejects_unregistered_source_word(tmp_path):
    # Given a source word without an explicit replacement.
    path=tmp_path/'unregistered.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_line((1,1),(20,1),width=.7)
        page.insert_text((20,30),'old')
        doc.save(path)
    assets=Assets()
    try:
        # When no source glyph is registered.
        with pytest.raises(FigureError) as error:
            assets.source_vector_body(path,0,[0,0,100,80])
        # Then the body cannot silently erase it.
        assert error.value.code=='source_icon_contains_text'
    finally:
        assets.close()


def test_body_explicit_normalized_target_requires_reason(tmp_path):
    # Given a registered source label and explicit normalized target.
    path=tmp_path/'normalized.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_line((1,1),(20,1),width=.7)
        page.insert_text((20,30),'4.7K')
        span=page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(path)
    assets=Assets()
    try:
        # When a documented semantic normalization is requested.
        body=assets.source_vector_body(path,0,[0,0,100,80],text_replacements=[{'source_text':'4.7K','source_bbox':list(span['bbox']),'target_text_id':'r','target_text':'4.7 kΩ','change_reason':'resistance unit normalization; value unchanged'}])
        # Then the receipt retains the exact target and justification.
        assert body.audit['text_replacements'][0]['target_text']=='4.7 kΩ'
    finally:
        assets.close()

def test_selected_svg_group_keeps_ancestor_matrix_and_excludes_sibling(tmp_path):
    # Given a source group nested under a nontrivial parent matrix and a sibling.
    source=tmp_path/'groups.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100pt" height="80pt" viewBox="0 0 100 80"><style>.wire{stroke:#000;fill:none;stroke-width:0.73}</style><g id="parent" transform="translate(20 10)"><g id="selected"><path id="wire" class="wire" d="M0 0L20 0"/></g><g id="sibling"><path d="M0 5L20 5" stroke="#000"/></g></g></svg>',encoding='utf-8')
    assets=Assets()
    try:
        # When the public group preparation is selected.
        body=assets.source_svg_group(source,'selected',[0,0,100,80])
        # Then only the original transformed group path survives.
        assert body.audit['mode']=='source-svg-group'
        drawings=body.doc[0].get_drawings()
        assert len(drawings)==1
        assert list(drawings[0]['rect'])==pytest.approx([20,10,40,10])
        assert body.audit['ancestor_attributes'][0]['transform']=='translate(20 10)'
    finally:
        assets.close()

def test_body_records_removed_formatting_whitespace(tmp_path):
    # Given a real whitespace text operator and an original wire.
    source=tmp_path/'space.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_line((10,10),(40,10),width=.7)
        page.insert_text((20,30),' ')
        doc.save(source)
    assets=Assets()
    try:
        # When preparing the explicit body without semantic source labels.
        body=assets.source_vector_body(source,0,[0,0,100,80])
        # Then formatting-only glyph operations are reported and all old fonts are gone.
        assert len(body.audit['whitespace_spans_removed'])==1
        assert body.doc[0].get_fonts()==[]
    finally:assets.close()

def test_svg_group_rejects_clip_that_truncates_zero_width_source_wire(tmp_path):
    # Given a selected group with a vertical source wire extending below its other shapes.
    source=tmp_path/'vertical.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100pt" height="80pt" viewBox="0 0 100 80"><g id="selected"><path d="M20 20L30 20L30 25L20 25Z" fill="none" stroke="#000"/><path d="M25 25L25 50" stroke="#000"/></g></svg>',encoding='utf-8')
    assets=Assets()
    try:
        # When the requested clip contains the box but truncates the long zero-width line.
        with pytest.raises(FigureError) as error:
            assets.source_svg_group(source,'selected',[18,18,32,28])
        # Then complete source group extent is required independently of cropped-pixel equality.
        assert error.value.code=='source_svg_group_extent'
    finally:assets.close()

@pytest.mark.parametrize('reason',[None,''])
def test_body_rejects_changed_target_without_documented_reason(tmp_path,reason):
    # Given one source label and an altered target without a usable justification.
    source=tmp_path/'reason.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_line((10,10),(40,10),width=.7)
        page.insert_text((20,30),'4.7K')
        span=page.get_text('dict')['blocks'][0]['lines'][0]['spans'][0]
        doc.save(source)
    replacement={'source_text':'4.7K','source_bbox':list(span['bbox']),'target_text_id':'r','target_text':'4.7 kΩ'}
    if reason is not None:replacement['change_reason']=reason
    assets=Assets()
    try:
        # When the public body route validates the glyph ownership declaration.
        with pytest.raises(FigureError) as error:
            assets.source_vector_body(source,0,[0,0,100,80],text_replacements=[replacement])
        # Then unexplained semantic changes are rejected.
        assert error.value.code=='source_body_change_reason'
    finally:assets.close()


@pytest.mark.parametrize('mutation',['none','hash','source-point','parameter','endpoint','scaled'])
def test_source_bezier_port_is_recomputed_from_bound_source_and_placement(tmp_path,reg,mutation):
    # Given a real source cubic and a proportional target placement.
    from journal_pdf.scene import Scene,audit_scene
    source=tmp_path/'curve.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        shape=page.new_shape();shape.draw_bezier((20,20),(20,40),(80,40),(80,20));shape.finish(width=.7);shape.commit()
        doc.save(source)
    assets=Assets()
    try:
        body=assets.source_vector_body(source,0,[0,0,100,80])
        scene=Scene(reg,8);scene.embed('body',body,[10,10,110,90]);scene.finish(130,110)
        declaration={'source_asset':'body','source_sha256':body.source_hash,'path_index':0,'primitive_index':0,'primitive':'c','t':.5,'source_point':[50,35]}
        scene.line('link',[[60,45],[110,50]],arrow=True,endpoint_nodes=[declaration,{'asset':'body','side':'right','fraction':.5}])
        if mutation=='hash':declaration['source_sha256']='0'*64
        elif mutation=='source-point':declaration['source_point'][1]+=.1
        elif mutation=='parameter':declaration['t']=.6
        elif mutation=='endpoint':scene.paths[0]['points'][0][0]+=.1
        elif mutation=='scaled':
            from journal_pdf.editorial import scale_scene
            scale_scene(scene,.8)
        # When the public scene audit checks the source path endpoint.
        issues=audit_scene(scene)
        # Then only the exact source cubic and its true target transform are accepted.
        assert bool(issues)==(mutation not in ('none','scaled'))
    finally:assets.close()


def test_fractional_source_viewport_does_not_add_reference_scaling_roundoff(tmp_path):
    # Given a native large-page PDF shape and the real Wu4 fractional viewport.
    source=tmp_path/'large-page.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=960,height=540)
        page.draw_rect(fitz.Rect(126.34,230.79,140.50,244.95),width=1.02,fill=(.463,.443,.443))
        doc.save(source)
    assets=Assets()
    try:
        # When the exact source viewport is prepared without a compensating redraw.
        icon=assets.source_icon(source,0,[125.7,230.15,169.5,273.95])
        # Then native source path/style and pixels remain exactly bound at the original tolerance.
        assert icon.audit['source_path_multiset_preserved']
        assert all(row['exact'] for row in icon.audit['pixels'])
    finally:assets.close()


def test_explicit_native_path_selection_excludes_overlapping_source_connectors(tmp_path):
    # Given native source paths whose bounds overlap a white background and a connector.
    source=tmp_path/'selected.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=100,height=80)
        page.draw_rect(page.rect,color=None,fill=(1,1,1))
        page.draw_rect(fitz.Rect(20,20,40,40),color=(0,),fill=(.5,),width=.7)
        page.draw_line((30,10),(30,50),width=.7)
        doc.save(source)
    assets=Assets()
    try:
        # When an explicit source glyph selects only its original native paint path.
        glyph=assets.source_vector_glyph(source,0,[18,18,42,42],[1])
        # Then no bbox masking, background shell, source connector or redraw survives.
        assert glyph.audit['mode']=='source-vector-glyph'
        assert len(glyph.doc[0].get_drawings())==1
        assert glyph.audit['selected_source_path_indices']==[1]
        assert glyph.doc[0].get_drawings()[0]['width']==pytest.approx(.7)
        with fitz.open() as doc:
            page=doc.new_page(width=60,height=60)
            assets.place(page,glyph,[0,0,24,24])
            from journal_pdf.source_path_ports import matches_source_port
            endpoint={'source_asset':'glyph','source_sha256':glyph.source_hash,'path_index':1,'primitive_index':0,'primitive':'re','edge':3,'t':.5,'source_point':[20,30]}
            placements=[{'id':'glyph','asset':glyph,'rect':[0,0,24,24]}]
            assert matches_source_port(endpoint,(2,12),placements)
            assert not matches_source_port(endpoint,(0,12),placements)
            page.draw_line((5,5),(10,5),width=.75)
            assert len(audit_icon_paths(page,[{'id':'glyph','asset':glyph,'rect':[0,0,24,24]}])['stroke_violations'])==1
    finally:assets.close()
