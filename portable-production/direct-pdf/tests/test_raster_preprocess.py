"""Synthetic, font-free coverage for the no-crop raster candidate route."""
import hashlib
import json

from PIL import Image
import pymupdf as fitz
import pytest

from journal_pdf.common import FigureError, PT_PER_MM
from journal_pdf.raster_preprocess import main, preprocess_raster


@pytest.fixture
def locations(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    return source, tmp_path / "output"


def save(locations, image, name="source.png", **options):
    source_root, _ = locations
    source = source_root / name
    image.save(source, **options)
    return source


def run(locations, source, **options):
    source_root, output = locations
    return preprocess_raster(source, output, source_root=source_root,
                             figure_id="synthetic", **options)


def artifact(locations, report, kind):
    return locations[1] / report["outputs"][kind]["path"]


def synthetic_rgb():
    # Entire colored border and large empty interior would expose trimming,
    # background removal, thresholding, or automatic contrast adjustments.
    image = Image.new("RGB", (37, 19), (210, 210, 210))
    for y in range(image.height):
        for x in range(image.width):
            if x in (0, image.width - 1) or y in (0, image.height - 1):
                image.putpixel((x, y), ((x * 7) % 256, (y * 19) % 256, 63))
    for x, color in enumerate([(255, 0, 0), (0, 255, 0), (0, 0, 255), (0, 0, 0), (255, 255, 255)]):
        image.putpixel((x + 4, 6), color)
    return image


def test_default_jpeg_and_lossless_full_canvas_png(locations):
    original = synthetic_rgb()
    source = save(locations, original)
    before = source.read_bytes()
    report = run(locations, source)
    assert set(report["outputs"]) == {"png", "jpeg"}
    assert source.read_bytes() == before
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert report["source_unchanged"] is True
    assert report["source_dimensions"] == [37, 19]
    assert report["full_canvas_preserved"] is True
    with Image.open(artifact(locations, report, "png")) as png:
        assert png.size == original.size
        assert png.mode == "L"
        assert png.tobytes() == original.convert("L").tobytes()
        assert [png.getpixel((x + 4, 6)) for x in range(5)] == [76, 150, 29, 0, 255]
        assert png.getpixel((15, 10)) == 210
    with Image.open(artifact(locations, report, "jpeg")) as jpeg:
        assert jpeg.size == original.size
        assert jpeg.mode == "L"
        ppi = original.width * 25.4 / 80
        assert float(jpeg.getexif()[282]) == pytest.approx(ppi)
        assert float(jpeg.getexif()[283]) == pytest.approx(ppi)
        assert jpeg.getexif()[296] == 2
        assert jpeg.info["dpi"] == (round(ppi), round(ppi))
    assert report["outputs"]["jpeg"]["lossy"] is True
    assert report["outputs"]["jpeg"]["exact_grayscale_pixels_preserved"] is False
    assert report["width_mm"] == 80
    assert report["height_mm"] == pytest.approx(80 * 19 / 37)
    assert report["width_basis"] == "repository-default-single-column"
    assert report["width_user_confirmed"] is None
    for key in ("crop", "background_removal", "resampled", "contrast_adjustment", "sharpening", "alpha_composited", "font_substitution", "publication_accepted", "ready_for_publication"):
        assert report[key] is False
    for result in report["outputs"].values():
        assert result["sha256"] == hashlib.sha256((locations[1] / result["path"]).read_bytes()).hexdigest()
    assert json.loads((locations[1] / report["receipt"]).read_text()) == report


@pytest.mark.parametrize("size,width", [((37, 19), 80), ((19, 37), 60.5), ((3, 3), 40)])
def test_pdf_full_canvas_aspect_ratio_and_exact_pixels(locations, size, width):
    original = Image.new("RGB", size, (177, 95, 49))
    original.putpixel((0, 0), (255, 0, 0))
    original.putpixel((size[0] - 1, size[1] - 1), (0, 255, 0))
    source = save(locations, original)
    report = run(locations, source, write_pdf=True, width_mm=width)
    with fitz.open(artifact(locations, report, "pdf")) as document:
        page = document[0]
        assert page.rect.width == pytest.approx(width * PT_PER_MM)
        assert page.rect.height == pytest.approx(width * PT_PER_MM * size[1] / size[0])
        assert page.rect.width / page.rect.height == pytest.approx(size[0] / size[1])
        images = page.get_images(full=True)
        assert len(images) == 1
        pixmap = fitz.Pixmap(document, images[0][0])
        assert (pixmap.width, pixmap.height) == size
        assert pixmap.n == 1
        assert pixmap.samples == original.convert("L").tobytes()
        rect = page.get_image_rects(images[0][0])[0]
        assert tuple(rect) == pytest.approx(tuple(page.rect))
        assert page.get_fonts() == []
        assert "Candidate only" in document.metadata["subject"]
    assert report["width_basis"] == "caller-supplied"
    assert report["outputs"]["pdf"]["exact_grayscale_pixels_preserved"] is True
    assert report["source_identity_review"] == "not-performed"
    assert report["content_review"] == "not-performed"
    assert report["visual_review"] == "not-performed"


@pytest.mark.parametrize("mode", ["RGBA", "LA"])
def test_alpha_exact_in_png_and_pdf_including_invisible_pixels(locations, mode):
    original = Image.new(mode, (6, 3))
    alphas = [0, 1, 2, 127, 254, 255]
    for y in range(3):
        for x, alpha in enumerate(alphas):
            original.putpixel((x, y), (49 + x * 30, alpha) if mode == "LA" else (49 + x * 30, 91, 171, alpha))
    source = save(locations, original)
    before = source.read_bytes()
    report = run(locations, source, write_jpeg=False, write_pdf=True)
    assert set(report["outputs"]) == {"png", "pdf"}
    with Image.open(artifact(locations, report, "png")) as png:
        assert png.mode == "LA"
        assert png.size == original.size
        assert png.getchannel("L").tobytes() == original.convert("L").tobytes()
        assert png.getchannel("A").tobytes() == original.getchannel("A").tobytes()
    with fitz.open(artifact(locations, report, "pdf")) as document:
        image = document[0].get_images(full=True)[0]
        assert fitz.Pixmap(document, image[0]).samples == original.convert("L").tobytes()
        assert fitz.Pixmap(document, image[1]).samples == original.getchannel("A").tobytes()
    assert report["outputs"]["pdf"]["alpha_pixels_preserved"] is True
    assert source.read_bytes() == before


@pytest.mark.parametrize("mode", ["RGB", "L", "P"])
def test_palette_and_color_key_transparency_preserved(locations, mode):
    image = Image.new(mode, (5, 3))
    if mode == "P":
        image.putpalette([255, 0, 0, 0, 255, 0, 0, 0, 255] + [0] * (768 - 9))
        image.putpixel((1, 0), 1)
        image.putpixel((2, 0), 2)
        transparency = bytes([0, 128, 255])
    else:
        transparency = (0, 0, 0) if mode == "RGB" else 0
        image.putpixel((1, 0), (128, 90, 20) if mode == "RGB" else 128)
    source = save(locations, image, transparency=transparency)
    with Image.open(source) as original:
        expected_alpha = original.convert("RGBA").getchannel("A").tobytes()
        expected_gray = original.convert("RGB").convert("L").tobytes()
    report = run(locations, source, write_jpeg=False, write_pdf=True)
    with Image.open(artifact(locations, report, "png")) as png:
        assert png.getchannel("A").tobytes() == expected_alpha
        assert png.getchannel("L").tobytes() == expected_gray


def test_nonopaque_alpha_rejects_jpeg_before_any_write(locations):
    source = save(locations, Image.new("RGBA", (8, 6), (100, 50, 25, 254)))
    with pytest.raises(FigureError) as exc:
        run(locations, source, write_pdf=True)
    assert exc.value.code == "raster_jpeg_alpha"
    assert not locations[1].exists()


def test_opaque_alpha_can_be_omitted_only_from_lossy_jpeg(locations):
    source = save(locations, Image.new("RGBA", (8, 6), (100, 50, 25, 255)))
    report = run(locations, source, write_pdf=True)
    assert report["outputs"]["jpeg"]["opaque_alpha_omitted"] is True
    assert report["outputs"]["png"]["alpha_pixels_preserved"] is True
    assert report["outputs"]["pdf"]["alpha_pixels_preserved"] is True


@pytest.mark.parametrize("mode", ["1", "L", "P", "RGB"])
def test_supported_opaque_modes_are_deterministic(locations, mode):
    image = Image.new(mode, (13, 7))
    if mode == "P":
        image.putpalette([85, 170, 255] * 256)
    source = save(locations, image)
    report = run(locations, source, write_pdf=True)
    second = preprocess_raster(source, locations[1], source_root=locations[0], figure_id="second", write_pdf=True)
    for kind in report["outputs"]:
        assert artifact(locations, report, kind).read_bytes() == artifact(locations, second, kind).read_bytes()


def test_source_rgb_icc_is_not_copied_to_grayscale(locations):
    source = save(locations, synthetic_rgb(), icc_profile=b"synthetic-not-an-actual-profile")
    report = run(locations, source)
    assert report["source_icc_present"] is True
    assert report["source_icc_applied"] is False
    for kind in ("png", "jpeg"):
        with Image.open(artifact(locations, report, kind)) as output:
            assert not output.info.get("icc_profile")


@pytest.mark.parametrize("width", [0, -1, True, False, float("nan"), float("inf"), float("-inf"), "80", 1e-320, 1e308])
def test_invalid_width_does_not_write(locations, width):
    source = save(locations, synthetic_rgb())
    with pytest.raises(FigureError):
        run(locations, source, width_mm=width)
    assert not locations[1].exists()


@pytest.mark.parametrize("figure_id", ["../outside", "/absolute", "a/b", "a\\b", "CON", "", ".."])
def test_unsafe_id_does_not_write(locations, figure_id):
    source = save(locations, synthetic_rgb())
    with pytest.raises(FigureError):
        preprocess_raster(source, locations[1], source_root=locations[0], figure_id=figure_id)
    assert not locations[1].exists()


@pytest.mark.parametrize("where", ["same", "child", "parent", "symlink"])
def test_source_output_overlap_blocked_before_write(locations, where):
    source = save(locations, synthetic_rgb())
    original = source.read_bytes()
    source_root, output = locations
    if where == "same":
        output = source_root
    elif where == "child":
        output = source_root / "candidate"
    elif where == "parent":
        output = source_root.parent
    else:
        output.symlink_to(source_root, target_is_directory=True)
    with pytest.raises(FigureError) as exc:
        preprocess_raster(source, output, source_root=source_root, figure_id="synthetic")
    assert exc.value.code == "output_source_overlap"
    assert source.read_bytes() == original
    assert not (output / "synthetic").exists()


def test_source_outside_root_and_symlink_escape_blocked(locations, tmp_path):
    other = tmp_path / "outside.png"
    Image.new("L", (8, 8)).save(other)
    for source in (other, locations[0] / "link.png"):
        if source != other:
            source.symlink_to(other)
        with pytest.raises(FigureError) as exc:
            run(locations, source)
        assert exc.value.code == "source_outside_root"
    assert not locations[1].exists()


def test_existing_candidate_and_casefold_collision_protected(locations):
    source = save(locations, synthetic_rgb())
    report = run(locations, source)
    before = artifact(locations, report, "jpeg").read_bytes()
    for figure_id in ("synthetic", "SYNTHETIC"):
        with pytest.raises(FigureError) as exc:
            preprocess_raster(source, locations[1], source_root=locations[0], figure_id=figure_id)
        assert exc.value.code == "raster_output_exists"
    assert artifact(locations, report, "jpeg").read_bytes() == before


def test_dangling_output_symlink_protected(locations, tmp_path):
    source = save(locations, synthetic_rgb())
    locations[1].mkdir()
    link = locations[1] / "synthetic"
    target = tmp_path / "not-created"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(FigureError) as exc:
        run(locations, source)
    assert exc.value.code == "raster_output_exists"
    assert not target.exists()
    assert link.is_symlink()


@pytest.mark.parametrize("problem", ["invalid", "missing", "multiframe", "orientation", "16bit"])
def test_unsupported_source_rejected_without_output(locations, problem):
    source = locations[0] / "source.png"
    expected = "raster_source_invalid"
    if problem == "invalid":
        source.write_text("not an image")
    elif problem == "missing":
        expected = "source_missing"
    elif problem == "multiframe":
        Image.new("L", (5, 5)).save(source, save_all=True, append_images=[Image.new("L", (5, 5), 30)])
        expected = "raster_multiple_frames"
    elif problem == "orientation":
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (5, 7)).save(source, exif=exif)
        expected = "raster_orientation"
    else:
        Image.new("I;16", (5, 5), 1000).save(source)
        expected = "raster_unsupported_mode"
    with pytest.raises(FigureError) as exc:
        run(locations, source)
    assert exc.value.code == expected
    assert not locations[1].exists()


def test_cli_success_and_alpha_block(locations, capsys):
    source = save(locations, synthetic_rgb())
    args = [str(source), "--source-root", str(locations[0]), "--output", str(locations[1]), "--id", "synthetic", "--pdf"]
    assert main(args) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report["outputs"]) == {"png", "jpeg", "pdf"}
    transparent = save(locations, Image.new("RGBA", (3, 4), (100, 200, 50, 0)), name="transparent.png")
    args[0] = str(transparent)
    args[-2] = "transparent"
    assert main(args) == 2
    assert json.loads(capsys.readouterr().err)["error"]["code"] == "raster_jpeg_alpha"
    assert main(args + ["--no-jpeg"]) == 0
    assert set(json.loads(capsys.readouterr().out)["outputs"]) == {"png", "pdf"}
