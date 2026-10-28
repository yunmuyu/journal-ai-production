# Figure audit and partial EMF inspection

These optional, independent inspection utilities produce evidence for human review. They do not approve figures or replace source, visual, semantic, or publication review. They are not connected to automatic publication or the production runtime.

With `portable-production/direct-pdf` on `PYTHONPATH`:

```text
python -m figure_audit.guard --out <candidate.pdf> --src <source.pdf> --column 80 --mode trace --json <report.json>
python -m figure_audit.spacing <candidate.pdf> --out <spacing.json>
python -m figure_audit.emf dump <source.emf>
python -m figure_audit.emf json <source.emf> <inspection.json>
python -m figure_audit.emf json <source.emf> <inspection.json> --dpi-x 96 --dpi-y 96 --clip-geometry --clip-bounds 0 0 1920 1080
python -m figure_audit.selftest
```

The guard accepts single-page PDFs only. Its checks include dimensions, extracted text, numerical tokens, fonts, paths and optional topology/spacing observations. An issue flagged by a heuristic must be checked against the source; an `INCOMPLETE` result is never approval. Exit codes: 1 for flagged issues, 3 when no issue was flagged but review remains incomplete, and 2 for invalid CLI arguments. No source, no extractable text, bitmap text, and unrecognized structures leave parts unexamined. One-way path shape matching does not prove that source objects are all present, positions are correct, or data is unchanged. An apparently matching topology does not establish that all elements were detected.

Spacing measurements are experimental. Historical quantiles were reported from two issues; the private corpus and raw per-file results are not included in the public repository and have not been independently revalidated here. Numeric targets and ranges are observations, not required editorial thresholds. Detection may confuse legends, axes or subplots. Reports are tied to the exact PDF SHA-256; inputs are never valid report destinations.

EMF extraction supports a limited subset of records and reports unsupported types. World transforms, predefined physical-unit mapping modes, MM_TEXT, MM_ANISOTROPIC and extent scaling use reference-device dimensions in the EMF header. MM_ISOTROPIC additionally requires verified playback DPI supplied with `--dpi-x` and `--dpi-y`; never assume the example's 96 DPI applies to another file or device. Missing or invalid DPI is rejected. Coordinates are continuous estimates, not exact GDI device pixel rounding.

Intersect and exclude rectangles are recorded as `clip_regions_mm` and `clip_exclusions_mm`. Optional `--clip-geometry` adds `visible_geometry_mm` for line/polygon centerlines and filled polygons, and models rectangle-region COPY/AND/OR/XOR/DIFF, clip offsets, meta clipping and SaveDC/RestoreDC. The user must supply verified playback surface bounds in device coordinates via `--clip-bounds`; an EMF ink bounding box is not a safe substitute for the playback surface. Install the optional dependency from `requirements-clip.txt` in a separate validated environment; normal inspection does not require it. This uses [Shapely](https://pypi.org/project/shapely/) (BSD-3-Clause; its GEOS dependency is LGPL-2.1).

The optional clipped stroke is a **centerline**, not a complete clipped stroked outline. Ellipses, text glyph outlines, clip paths, bitmap content, GDI device-region rounding and full rendering remain unsupported. Invalid or unrecognized clipping and unknown coordinate mappings remain unknown, and unsupported ellipses are explicitly labeled. The legacy clip constraint fields remain partial for complex operations; use the optional visible geometry only when its status is `clipped`. JSON and command output always remain `complete=false`; inspect the original with a suitable viewer and never substitute extraction for source or final production validation.

The state model follows [Microsoft EMF region definitions](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/939400bc-0ecd-4a28-aa8c-60c7e4cc9877), [world transform modes](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/e6bb2996-195f-473f-80c6-9dc1afe474f9), [intersect clip records](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/13cd0c98-d4e9-4ca7-a79d-58055bf45c79) and [offset clip records](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/8bf2b60d-3b19-4bd1-b2d7-c89b027ad808).

Do not upload author PDFs, EMF files, reports, local baselines, paths or font data to public version control. Test figures used in this repository are synthetic.

# 单页 PDF 预检

在 `portable-production/direct-pdf` 下运行 `python -m figure_audit.prescan 图.pdf --json 新报告.json`。报告记录整页尺寸、源文件 SHA-256、可提取文字的字号分布，以及整页等比缩到 80 mm 和 160 mm 时的主字号估算（不放大）。报告文件必须不存在，避免覆盖原稿或已有报告。

预检只提供证据，始终返回 `INCOMPLETE` 和退出码 3；输入或输出失败返回 2。它不判断能否排成单栏、不判定合格，也不考虑裁边、重排、换字或位图文字，仍需逐图核对。
