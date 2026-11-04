import base64
import io
import pytest
from PIL import Image
from journal_pdf.assets import svg_root
from journal_pdf.svg_embedded import embedded_image, gray_data_uri
from journal_pdf.common import FigureError

def uri():
    image=Image.new('RGBA',(3,2),(255,0,0,120));out=io.BytesIO();image.save(out,format='PNG')
    return 'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()

def source(tmp_path,href,tag='image'):
    p=tmp_path/'source.svg'
    p.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 3 2"><{tag} href="{href}" width="3" height="2"/></svg>')
    return p

def test_legacy_default_still_rejects_data(tmp_path):
    with pytest.raises(FigureError):svg_root(source(tmp_path,uri()))

def test_opt_in_decodes_only_raster_image(tmp_path):
    svg_root(source(tmp_path,uri()),allow_embedded_images=True)
    with pytest.raises(FigureError):svg_root(source(tmp_path,uri(),'use'),allow_embedded_images=True)

@pytest.mark.parametrize('href',['https://example.invalid/img.png','file:///C:/private.png','data:image/svg+xml;base64,PHN2Zy8+','data:image/png;base64,ZmFrZQ==','data:image/png;base64,!!!!'])
def test_external_or_invalid_payload_rejected(tmp_path,href):
    with pytest.raises(FigureError):svg_root(source(tmp_path,href),allow_embedded_images=True)

def test_gray_keeps_pixels_dimensions_alpha():
    image=Image.open(io.BytesIO(embedded_image(gray_data_uri(uri()))))
    assert image.size==(3,2)
    for r,g,b,a in image.getdata():assert r==g==b and a==120

def test_declared_mime_must_match_bytes():
    with pytest.raises(FigureError):embedded_image(uri().replace('image/png','image/jpeg'))
