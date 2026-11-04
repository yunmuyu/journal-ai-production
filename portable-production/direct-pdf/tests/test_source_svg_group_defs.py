import pymupdf as fitz
from journal_pdf.assets import svg_pdf_bytes,svg_root
from journal_pdf.source_svg_groups import isolate_svg_group
from journal_pdf.source_icons import path_record,consume_paths


def test_isolation_preserves_marker_paths_defined_inside_selected_group(tmp_path):
    # Given a Matplotlib-style series containing its own reused marker definition.
    source=tmp_path/'markers.svg'
    source.write_text('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="100pt" height="80pt" viewBox="0 0 100 80"><g id="series"><path d="M 20 20 L 80 60" style="fill:none;stroke:#003366"/><defs><path id="dot" d="M -2 -2 L 2 -2 L 2 2 L -2 2 Z"/></defs><use xlink:href="#dot" x="20" y="20" style="fill:#003366"/><use xlink:href="#dot" x="80" y="60" style="fill:#003366"/></g></svg>')
    original=svg_pdf_bytes(svg_root(source))
    # When the shared isolator hoists definitions before retaining this group.
    isolated,proof=isolate_svg_group(source,'series',gray=False)
    # Then actual native PDF paint remains identical, including both markers.
    with fitz.open(stream=original,filetype='pdf') as before,fitz.open(stream=svg_pdf_bytes(isolated),filetype='pdf') as after:
        expected=[path_record(p) for p in before[0].get_drawings()];actual=[path_record(p) for p in after[0].get_drawings()]
        assert len(expected)==len(actual)==3
        consume_paths(expected,actual)
    assert proof['geometry_unchanged']
