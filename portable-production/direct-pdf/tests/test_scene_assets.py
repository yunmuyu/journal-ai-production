import json

import pymupdf as fitz
from PIL import Image

from journal_pdf.assets import Assets
from journal_pdf.common import digest_file
from journal_pdf.fonts import draw_text
from journal_pdf.pdf_fonts import normalize_type0_font_names
from journal_pdf.render import render_one
from journal_pdf.scene import Scene


def test_transparent_raster_is_composited_on_white_before_embedding(tmp_path):
    source = tmp_path / "transparent-icon.png"
    image = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    for x in range(4, 8):
        for y in range(3, 9):
            image.putpixel((x, y), (0, 0, 0, 255))
    image.save(source)
    assets = Assets()
    try:
        asset = assets.raster(source, [0, 0, 12, 12], gray=False)
        embedded = Image.open(__import__("io").BytesIO(asset.data)).convert("RGB")
        assert embedded.getpixel((0, 0)) == (255, 255, 255)
        assert embedded.getpixel((5, 5)) == (0, 0, 0)
        assert asset.audit["source_alpha_present"]
        assert asset.audit["transparent_pixels_composited_to_white"]
        doc = fitz.open();page = doc.new_page(width=12, height=12)
        assets.place(page, asset, [0, 0, 12, 12])
        placed = doc.extract_image(page.get_images()[0][0])
        placed_image = Image.open(__import__("io").BytesIO(placed["image"])).convert("RGB")
        assert placed_image.getpixel((0, 0)) == (255, 255, 255)
        doc.close()
    finally:
        assets.close()


def test_scene_pdf_asset_preserves_vector_and_imported_text_audit(reg, tmp_path):
    source_root = tmp_path / "source";source_root.mkdir()
    output_root = tmp_path / "output";source_pdf = source_root / "source-vector.pdf"
    source_scene = Scene(reg, 8).finish(40, 40)
    source_scene.text("source-text", "SRC", 20, 12)
    reg.prepare_document_fonts(source_scene.texts)
    doc = fitz.open();page = doc.new_page(width=40, height=40)
    shape = page.new_shape();shape.draw_line((5, 30), (35, 30));shape.finish(width=.5, color=(0,));shape.commit()
    draw_text(page, reg, source_scene.texts[0]);normalize_type0_font_names(doc, reg.postscript_names)
    doc.save(source_pdf, garbage=4, deflate=True);doc.close()
    spec = {
        "id": "synthetic-source-vector", "author": "Synthetic", "kind": "scene",
        "width_pt": 44, "height_pt": 44, "policy": {"column": "single"},
        "sources": [{"path": source_pdf.name, "sha256": digest_file(source_pdf)}],
        "assets": [{"id": "source-fragment", "path": source_pdf.name, "source_kind": "pdf",
                    "page": 0, "clip": [0, 0, 40, 40], "target": [2, 2, 42, 42], "role": "source-vector"}],
    }
    assets = Assets()
    try:
        result = render_one(spec, reg, assets, source_root, output_root)
    finally:
        assets.close()
    assert result["assets"][0]["mode"] == "pdf-preserved-viewport"
    assert result["assets"][0]["source_text_character_count"] >= 3
    assert result["pdf_audit"]["text_multiset_exact"]
    assert result["pdf_audit"]["expected_imported_text_characters"] == 3
    output_pdf = output_root / result["output_pdf"]
    final = fitz.open(output_pdf)
    try:
        assert not final[0].get_images()
        assert final[0].get_drawings()
        assert "SRC" in final[0].get_text()
    finally:
        final.close()
