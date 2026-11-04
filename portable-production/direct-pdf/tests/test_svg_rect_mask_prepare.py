from pathlib import Path
import fitz
import pytest

from journal_pdf.assets import svg_root, svg_pdf_bytes
from journal_pdf.common import FigureError


def source(tmp_path: Path, child: str) -> Path:
    path=tmp_path/'chart.svg'
    path.write_text(f'''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100"><defs><mask id="m">{child}</mask></defs><g mask="url(#m)"><path d="M10 40 L50 50 L90 40" stroke="black" fill="none" stroke-width="2"/></g></svg>''',encoding='utf8')
    return path


def test_rectangular_opaque_mask_keeps_vector_inside_clip(tmp_path):
    path=source(tmp_path,'<rect x="20" y="10" width="60" height="80" fill="white"/>')
    root=svg_root(path); before=path.read_bytes(); pdf=svg_pdf_bytes(root)
    with fitz.open(stream=pdf,filetype='pdf') as doc:
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(4/3,4/3),colorspace=fitz.csGRAY,alpha=False)
        assert pix.pixel(50,50)[0]<100
        assert pix.pixel(10,50)[0]>240
        assert doc[0].get_drawings()
    assert path.read_bytes()==before


def test_non_opaque_or_complex_masks_are_not_silently_converted(tmp_path):
    path=source(tmp_path,'<rect x="20" y="10" width="60" height="80" fill="white" opacity="0.5"/>')
    with pytest.raises(FigureError,match='mask'):
        svg_pdf_bytes(svg_root(path))


def test_prepare_cli_binds_hash_and_creates_intermediate(tmp_path):
    import hashlib
    import json
    from journal_pdf.cli import main
    path=source(tmp_path,'<rect x="20" y="10" width="60" height="80" fill="white"/>')
    output=tmp_path/'prepared.pdf';report=tmp_path/'prepared.json'
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    assert main(['prepare-svg-pdf',str(path),'--source-sha256',digest,'--output',str(output),'--report',str(report)])==0
    assert json.loads(report.read_text(encoding='utf8'))['status']=='intermediate'
    assert main(['prepare-svg-pdf',str(path),'--source-sha256',digest,'--output',str(output),'--report',str(report)])!=0
