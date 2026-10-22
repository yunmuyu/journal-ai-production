"""Full-canvas grayscale raster candidates, without Adobe or font substitution.

Default output is a quality-95 grayscale JPEG plus a lossless PNG and receipt.
Use ``write_jpeg=False, write_pdf=True`` for transparent sources. PDF is an
optional proof, never a publication approval. No crop, resampling, background
removal, sharpening, contrast change, EXIF rotation, or color-profile transform
is performed. Unsupported modes/frames fail instead of silently losing data.

CLI: python -m journal_pdf.raster_preprocess SOURCE --source-root INPUT_DIR
     --output OUTPUT_DIR --id FIGURE_ID [--width-mm 80] [--pdf] [--no-jpeg]
Input and output directories must be separate; existing candidates are protected.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import sys
from fractions import Fraction
from pathlib import Path

from PIL import Image, TiffImagePlugin, UnidentifiedImageError, __version__ as pillow_version
import pymupdf as fitz

from .common import (FigureError, PT_PER_MM, atomic_json, digest_file, finite,
                     resolve_source, safe_name, validate_output_isolation)

DEFAULT_WIDTH_MM = 80.0
JPEG_QUALITY = 95
_SUPPORTED_MODES = {"1", "L", "LA", "P", "RGB", "RGBA"}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=False)
    return buffer.getvalue()


def _load_gray(data: bytes):
    try:
        with Image.open(io.BytesIO(data)) as original:
            if getattr(original, "n_frames", 1) != 1:
                raise FigureError("raster_multiple_frames", "多帧/多页位图需要先明确交付范围，不自动只取首帧")
            if original.mode not in _SUPPORTED_MODES:
                raise FigureError("raster_unsupported_mode", "此无损画布路线不支持该像素模式，不自动降位深或转换色彩空间", mode=original.mode)
            orientation = original.getexif().get(274, 1)
            if orientation != 1:
                raise FigureError("raster_orientation", "来源含旋转/镜像方向标记，需先明确方向；不自动旋转画布", orientation=orientation)
            original.load()
            has_alpha = "A" in original.getbands() or "transparency" in original.info
            # RGBA expansion also respects PNG palette and color-key transparency.
            alpha = original.convert("RGBA").getchannel("A") if has_alpha else None
            gray = original.convert("RGB").convert("L") if original.mode == "P" else original.convert("L")
            facts = {
                "source_format": original.format,
                "source_mode": original.mode,
                "source_dimensions": list(original.size),
                "source_alpha_present": has_alpha,
                "source_icc_present": bool(original.info.get("icc_profile")),
            }
            # Never attach a source RGB ICC profile or EXIF orientation to L/LA.
            # Metadata removal is not a color transform and changes no pixels.
            gray.info.clear()
            if alpha is not None:
                alpha.info.clear()
                gray.putalpha(alpha)
            return gray, facts
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise FigureError("raster_source_invalid", "无法安全读取来源位图", detail=str(error)) from error


def _jpeg(gray: Image.Image, ppi: float):
    if gray.mode == "LA" and gray.getchannel("A").getextrema() != (255, 255):
        raise FigureError("raster_jpeg_alpha", "JPEG不能保留非不透明像素；请明确选择无损PNG及可选PDF，不自动铺底")
    # EXIF rational resolution records the physical width more accurately than
    # JPEG's integer JFIF density. Do not copy private source EXIF metadata.
    resolution = Fraction(ppi).limit_denominator(1_000_000)
    if resolution.numerator > 0xFFFFFFFF or resolution.denominator > 0xFFFFFFFF:
        raise FigureError("raster_resolution", "所选栏宽不能安全写入JPEG分辨率元数据")
    exif = Image.Exif()
    exif[282] = exif[283] = TiffImagePlugin.IFDRational(resolution)
    exif[296] = 2  # inches
    integer_dpi = round(ppi)
    options = {"dpi": (integer_dpi, integer_dpi)} if 1 <= integer_dpi <= 65535 else {}
    buffer = io.BytesIO()
    gray.getchannel("L").save(buffer, format="JPEG", quality=JPEG_QUALITY,
                              subsampling=0, optimize=False, progressive=False,
                              exif=exif, **options)
    data = buffer.getvalue()
    with Image.open(io.BytesIO(data)) as reopened:
        reopened.load()
        actual_ppi = float(reopened.getexif()[282])
        if reopened.mode != "L" or reopened.size != gray.size or not math.isclose(actual_ppi, ppi, rel_tol=1e-8):
            raise FigureError("raster_jpeg_verification", "JPEG尺寸、灰度模式或分辨率元数据核验失败")
    return data, {"quality": JPEG_QUALITY, "subsampling": 0, "lossy": True,
                  "exact_grayscale_pixels_preserved": False,
                  "dimensions_preserved": True, "mode": "L",
                  "exif_resolution_ppi": actual_ppi,
                  "jfif_resolution_ppi": integer_dpi if options else None,
                  "opaque_alpha_omitted": gray.mode == "LA"}


def _verify_pdf(data: bytes, gray: Image.Image, width_pt: float, height_pt: float):
    with fitz.open(stream=data, filetype="pdf") as document:
        if len(document) != 1:
            raise FigureError("raster_pdf_verification", "候选PDF必须恰好一页")
        page = document[0]
        images = page.get_images(full=True)
        if len(images) != 1 or page.get_fonts() or page.get_text().strip():
            raise FigureError("raster_pdf_verification", "候选PDF必须只含完整原图，不添加或替换文字")
        image = images[0]
        pixmap = fitz.Pixmap(document, image[0])
        if (pixmap.width, pixmap.height) != gray.size or pixmap.n != 1 or pixmap.samples != gray.getchannel("L").tobytes():
            raise FigureError("raster_pdf_pixels", "PDF内嵌灰度像素不等于完整灰度原图")
        if gray.mode == "LA":
            if not image[1]:
                raise FigureError("raster_pdf_alpha", "PDF未保留透明度软蒙版")
            mask = fitz.Pixmap(document, image[1])
            if (mask.width, mask.height) != gray.size or mask.n != 1 or mask.samples != gray.getchannel("A").tobytes():
                raise FigureError("raster_pdf_alpha", "PDF透明度像素与原图不同")
        elif image[1]:
            raise FigureError("raster_pdf_alpha", "不透明来源被意外添加透明度")
        placements = page.get_image_rects(image[0], transform=True)
        expected = (0., 0., width_pt, height_pt)
        # PDF page/placement coordinates are float32; verify physical geometry
        # within that precision, rather than claiming exact decimal millimeters.
        def same(actual, wanted):
            return all(math.isclose(a, b, rel_tol=2e-6, abs_tol=2e-5) for a, b in zip(actual, wanted))
        if not same(page.rect, expected) or len(placements) != 1 or not same(placements[0][0], expected):
            raise FigureError("raster_pdf_geometry", "PDF尺寸或完整画布位置核验失败")
        matrix = placements[0][1]
        if not same(matrix, (width_pt, 0., 0., height_pt, 0., 0.)):
            raise FigureError("raster_pdf_geometry", "PDF发生旋转、镜像或非预期变换")
        return {"exact_grayscale_pixels_preserved": True,
                "alpha_pixels_preserved": True if gray.mode == "LA" else None,
                "embedded_dimensions": [pixmap.width, pixmap.height],
                "full_canvas_preserved": True, "aspect_ratio_preserved": True,
                "page_size_pt": [page.rect.width, page.rect.height],
                "fonts_added_or_substituted": False}


def _pdf(gray: Image.Image, width_mm: float):
    width_pt = width_mm * PT_PER_MM
    height_pt = width_pt * gray.height / gray.width
    if not finite([width_pt, height_pt], positive=True):
        raise FigureError("raster_pdf_geometry", "栏宽不能表示为有限PDF尺寸")
    with fitz.open() as document:
        page = document.new_page(width=width_pt, height=height_pt)
        # Do NOT pass LA/RGBA directly to insert_image: MuPDF may premultiply
        # then unpremultiply, changing gray samples at low or zero alpha.
        options = {"mask": _png(gray.getchannel("A"))} if gray.mode == "LA" else {}
        page.insert_image(page.rect, stream=_png(gray.getchannel("L")),
                          keep_proportion=True, **options)
        document.set_metadata({
            "title": "Full-canvas grayscale candidate",
            "subject": "Candidate only; full canvas; no crop, background removal, resampling, sharpening or contrast adjustment. Awaiting review.",
            "creator": "journal_pdf.raster_preprocess",
        })
        data = document.tobytes(garbage=4, deflate=True, no_new_id=True)
    return data, _verify_pdf(data, gray, width_pt, height_pt)


def preprocess_raster(source: str | Path, output_root: str | Path, *,
                      source_root: str | Path, figure_id: str,
                      width_mm: float | None = None,
                      write_jpeg: bool = True, write_pdf: bool = False) -> dict:
    """Create a new isolated candidate folder and return its auditable receipt.

    SOURCE is absolute or relative to source_root. Existing files/folders are
    never overwritten, including symlinks. Width controls physical placement or
    resolution metadata, not pixel count. The caller remains responsible for
    source identity, content, visual review, and user acceptance.
    """
    default_width = width_mm is None
    width_mm = DEFAULT_WIDTH_MM if default_width else width_mm
    if not finite([width_mm], positive=True):
        raise FigureError("raster_width", "栏宽必须为有限正数毫米，不能是布尔值")
    if not isinstance(write_jpeg, bool) or not isinstance(write_pdf, bool):
        raise FigureError("raster_output_option", "JPEG和PDF输出开关必须为布尔值")
    figure_id = safe_name(figure_id)
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    if not source_root.is_dir():
        raise FigureError("source_root_missing", "素材根目录不存在")
    validate_output_isolation(source_root, output_root)
    source = resolve_source(source_root, str(source))
    folder = output_root / figure_id
    # lexists behavior includes dangling symlinks; casefold protects Windows.
    if output_root.exists() and (not output_root.is_dir() or any(p.name.casefold() == figure_id.casefold() for p in output_root.iterdir())):
        raise FigureError("raster_output_exists", "候选位置已存在，请使用新的输出目录或图件ID")
    data = source.read_bytes()
    source_hash = _sha(data)
    gray, facts = _load_gray(data)
    ppi = gray.width * 25.4 / width_mm
    if not finite([ppi, width_mm * gray.height / gray.width], positive=True):
        raise FigureError("raster_width", "栏宽产生了不可表示的尺寸或分辨率")
    # All conversion and verification precede writes, so rejected transparency
    # or unsupported inputs cannot leave a misleading partial candidate.
    png = _png(gray)
    with Image.open(io.BytesIO(png)) as reopened:
        reopened.load()
        if reopened.mode != gray.mode or reopened.size != gray.size or reopened.tobytes() != gray.tobytes():
            raise FigureError("raster_png_verification", "无损PNG像素核验失败")
    files = {"grayscale.png": png}
    outputs = {"png": {"path": f"{figure_id}/grayscale.png", "sha256": _sha(png),
                        "mode": gray.mode, "lossy": False,
                        "exact_grayscale_pixels_preserved": True,
                        "alpha_pixels_preserved": True if gray.mode == "LA" else None}}
    if write_jpeg:
        jpeg, audit = _jpeg(gray, ppi)
        files["grayscale.jpg"] = jpeg
        outputs["jpeg"] = {"path": f"{figure_id}/grayscale.jpg", "sha256": _sha(jpeg), **audit}
    if write_pdf:
        pdf, audit = _pdf(gray, width_mm)
        files["candidate.pdf"] = pdf
        outputs["pdf"] = {"path": f"{figure_id}/candidate.pdf", "sha256": _sha(pdf), **audit}
    if digest_file(source) != source_hash:
        raise FigureError("raster_source_changed", "转换期间来源发生变更，不输出候选")
    report = {
        "version": 1, "id": figure_id, "mode": "full-canvas-grayscale",
        "status": "candidate-rendered", "mechanical_checks_passed": True,
        "mechanical_check_scope": "Full-canvas pixels, alpha, dimensions, output hashes and physical-size metadata only",
        "ready_for_publication": False, "publication_accepted": False,
        "source_identity_review": "not-performed", "content_review": "not-performed",
        "visual_review": "not-performed", "print_acceptance": "not-performed",
        "source_path": str(source.relative_to(source_root)), "source_sha256": source_hash,
        "source_unchanged": True, **facts,
        "grayscale_method": "Pillow fixed ITU-R 601-2 RGB-to-L luminance; alpha retained separately",
        "pillow_version": pillow_version, "pymupdf_version": fitz.VersionBind,
        "source_icc_applied": False, "source_metadata_copied": False,
        "full_canvas_preserved": True, "aspect_ratio_preserved": True,
        "crop": False, "background_removal": False, "resampled": False,
        "sharpening": False, "contrast_adjustment": False, "alpha_composited": False,
        "exif_orientation_applied": False, "font_substitution": False,
        "width_mm": float(width_mm), "height_mm": width_mm * gray.height / gray.width,
        "effective_ppi": ppi,
        "width_basis": "repository-default-single-column" if default_width else "caller-supplied",
        "width_user_confirmed": None,
        "outputs": outputs, "receipt": f"{figure_id}/audit.json",
    }
    output_root.mkdir(parents=True, exist_ok=True)
    folder.mkdir()  # Exclusive reservation: do not reuse an existing candidate.
    created = []
    try:
        for name, content in files.items():
            path = folder / name
            with path.open("xb") as file:
                file.write(content)
            created.append(path)
        # Re-read saved artifacts instead of reporting only in-memory hashes.
        for artifact in outputs.values():
            if digest_file(output_root / artifact["path"]) != artifact["sha256"]:
                raise FigureError("raster_output_hash", "写入后的输出哈希不匹配")
        atomic_json(folder / "audit.json", report)
    except Exception:
        for path in created:
            path.unlink(missing_ok=True)
        if not any(folder.iterdir()):
            folder.rmdir()
        raise
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--id", required=True, dest="figure_id")
    parser.add_argument("--width-mm", type=float)
    parser.add_argument("--pdf", action="store_true", help="另输出无损像素PDF候选")
    parser.add_argument("--no-jpeg", action="store_true", help="只保留无损PNG及可选PDF；支持透明度")
    args = parser.parse_args(argv)
    try:
        report = preprocess_raster(args.source, args.output, source_root=args.source_root,
                                   figure_id=args.figure_id, width_mm=args.width_mm,
                                   write_jpeg=not args.no_jpeg, write_pdf=args.pdf)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except FigureError as error:
        print(json.dumps({"status": "blocked", "error": error.as_dict()}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, RuntimeError) as error:
        print(json.dumps({"status": "error", "type": type(error).__name__, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
