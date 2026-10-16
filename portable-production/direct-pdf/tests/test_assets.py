from pathlib import Path
from PIL import Image,ImageDraw
import pytest,pymupdf as fitz
from journal_pdf.assets import Assets,svg_root,element,geometry_signature
from journal_pdf.common import FigureError

@pytest.fixture
def raster(tmp_path):
    p=tmp_path/'data.png';im=Image.new('L',(100,80),255);d=ImageDraw.Draw(im)
    d.line([(4,70),(50,30),(90,15)],fill=20,width=2);d.text((60,55),'old',fill=0);im.save(p);return p


def test_masks_require_reviewed_safe_region(raster):
    a=Assets()
    with pytest.raises(FigureError) as e:a.raster(raster,[0,0,100,80],masks=[[60,50,85,70]])
    assert e.value.code=='unapproved_raster_mask'
    a.close()


def test_mask_preserves_all_other_pixels(raster):
    a=Assets();asset=a.raster(raster,[0,0,100,80],masks=[[60,50,85,70]],approved_empty_regions=[[55,48,88,73]])
    assert asset.audit['protected_pixels_unchanged_before_color_conversion']
    assert not asset.audit['resampled_before_embedding'];a.close()


def test_empty_swatch_is_blocked(raster):
    a=Assets()
    with pytest.raises(FigureError) as e:a.raster(raster,[0,0,20,10],swatch=True)
    assert e.value.code=='empty_legend_swatch';a.close()


def test_aspect_ratio_cannot_stretch(raster):
    a=Assets();asset=a.raster(raster,[0,0,100,80]);doc=fitz.open();p=doc.new_page()
    with pytest.raises(FigureError):a.place(p,asset,[0,0,100,100])
    doc.close();a.close()


def test_subpixel_crop_rejected(raster):
    a=Assets()
    with pytest.raises(FigureError):a.raster(raster,[.2,0,100,80])
    a.close()


@pytest.mark.parametrize('body',[
    '<script>alert(1)</script>',
    '<image href="https://example.invalid/x.png"/>',
    '<style>@import "https://example.invalid/style.css";</style>',
    '<path onload="alert(1)" d="M0 0L1 1"/>'])
def test_unsafe_svg_rejected(tmp_path,body):
    p=tmp_path/'unsafe.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg">'+body+'</svg>')
    with pytest.raises(FigureError):svg_root(p)


@pytest.fixture
def svg(tmp_path):
    p=tmp_path/'plot.svg';p.write_text('''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100pt" height="80pt" viewBox="0 0 100 80">
    <defs><path id="mark" d="M-2 -2L2 -2L2 2L-2 2Z"/></defs>
    <g id="axes_1"><g id="curve"><path d="M10 60L50 30L90 20" style="fill:none;stroke:#333333;stroke-width:1;stroke-dasharray:3,2"/><use xlink:href="#mark" x="50" y="30"/></g>
    <g id="text_1"><text x="10" y="75">old</text></g><g id="legend"><g id="swatch"><path d="M60 10L80 10" style="stroke:#333333;stroke-width:1;stroke-dasharray:3,2"/></g></g></g></svg>''');return p


def test_referenced_marker_geometry_protected(svg):
    r=svg_root(svg);one=geometry_signature(r,['curve']);element(r,'mark').set('d','M0 0L99 99')
    assert geometry_signature(r,['curve'])!=one


def test_svg_remains_vector_and_dash_styles_survive(svg):
    a=Assets();asset=a.svg_chart(svg,'axes_1',[0,0,100,80],['curve'],'legend')
    assert asset.audit['geometry_unchanged']
    assert asset.doc[0].get_text().strip()==''
    assert not asset.doc[0].get_images()
    assert any(p.get('dashes') not in (None,'[] 0') for p in asset.doc[0].get_drawings())
    assert len(asset.doc[0].get_drawings())>=2 # path + referenced marker
    a.close()
