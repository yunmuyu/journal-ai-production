import pytest
from task_quality.checks import preview
from task_quality.models import GateError

XHTML = 'http://www.w3.org/1999/xhtml'
LINK = 'xmlns:xlink="http://www.w3.org/1999/xlink"'


def svg(markup, **extra):
    attributes = ' '.join('%s="%s"' % (key, value) for key, value in extra.items())
    return ('<svg xmlns="http://www.w3.org/2000/svg" ' + attributes + ' width="200" height="60">'
            + markup.replace('@X', XHTML) + '</svg>')


def test_svg_source_preview_without_viewbox(tmp_path):
    source=tmp_path/'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="100" height="40"><text x="5" y="20">source</text></svg>')
    target=tmp_path/'preview.png'
    preview(source,target)
    assert target.is_file() and target.stat().st_size>0


def test_svg_external_resource_is_not_loaded(tmp_path):
    source=tmp_path/'source.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><image href="file:///secret.png"/></svg>')
    with pytest.raises(GateError):preview(source,tmp_path/'preview.png')


def test_drawio_html_label_preview_uses_native_text_fallback(tmp_path):
    source=tmp_path/'source.svg'
    source.write_text(svg('<switch><foreignObject width="100%" height="100%"><div xmlns="@X">系统总体架构</div></foreignObject>'
                          '<text x="100" y="30" text-anchor="middle">系统总体架构</text></switch>'))
    target=tmp_path/'preview.png'
    preview(source,target)
    assert target.is_file() and target.stat().st_size>0
    assert '<foreignObject' in source.read_text()


def test_drawio_export_link_is_not_an_external_resource(tmp_path):
    source=tmp_path/'source.svg'
    source.write_text(svg('<a xlink:href="https://www.drawio.com/doc/faq/svg-export-text-problems" target="_blank" transform="translate(0,-5)">'
                          '<switch><foreignObject width="100%" height="100%"><div xmlns="@X">标签</div></foreignObject>'
                          '<text x="10" y="20">标签</text></switch></a>', **{'xmlns:xlink':'http://www.w3.org/1999/xlink'}))
    target=tmp_path/'preview.png'
    preview(source,target)
    assert target.is_file() and target.stat().st_size>0


def test_other_external_link_still_refused(tmp_path):
    source=tmp_path/'source.svg'
    source.write_text(svg('<a xlink:href="https://example.com/other">'
                          '<switch><foreignObject width="100%" height="100%"><div xmlns="@X">标签</div></foreignObject>'
                          '<text x="10" y="20">标签</text></switch></a>', **{'xmlns:xlink':'http://www.w3.org/1999/xlink'}))
    with pytest.raises(GateError) as refusal:
        preview(source,tmp_path/'preview.png')
    assert refusal.value.code=='preview_svg_external'


def test_html_label_without_text_fallback_stays_unsupported(tmp_path):
    source=tmp_path/'source.svg'
    source.write_text(svg('<switch><foreignObject width="100%" height="100%"><div xmlns="@X">仅HTML标签</div></foreignObject></switch>'))
    with pytest.raises(GateError) as refusal:
        preview(source,tmp_path/'preview.png')
    assert refusal.value.code=='preview_svg_unsupported'


def test_truncated_native_fallback_is_not_used_as_complete_source_preview(tmp_path):
    source = tmp_path/'source.svg'
    source.write_text(svg('<switch><foreignObject><div xmlns="@X">DiffLogLoader日志解析</div></foreignObject>'
                          '<text x="10" y="20">DiffLogLoader...</text></switch>'))
    with pytest.raises(GateError) as refusal:
        preview(source, tmp_path/'preview.png')
    assert refusal.value.code == 'preview_svg_fallback_mismatch'


def test_resolved_switch_preserves_its_transform_and_clip():
    from lxml import etree
    from task_quality.checks import _flatten_html_text_svg
    root = etree.fromstring(svg('<switch transform="translate(20,10)" clip-path="url(#clip)">'
                               '<foreignObject><div xmlns="@X">标签</div></foreignObject>'
                               '<text x="10" y="20">标签</text></switch>').encode())
    assert _flatten_html_text_svg(root)
    group = root[0]
    assert etree.QName(group).localname == 'g'
    assert group.get('transform') == 'translate(20,10)'
    assert group.get('clip-path') == 'url(#clip)'
    assert len(group) == 1
