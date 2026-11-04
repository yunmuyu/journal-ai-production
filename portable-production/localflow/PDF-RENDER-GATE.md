# PDF decoding gate

`audit_pdf_compatibility` now first calls `pdf_render.audit_pdf_render` before
checking font descriptors. A PDF can have a readable page tree and font descriptor
but a corrupt compressed content/font stream. MuPDF can report an error, substitute
a system font and return instead of raising. The former gate accepted such files.

The shared gate starts an isolated Python process using the same interpreter and
existing PyMuPDF dependency. It rasterizes every page, caps the largest raster
dimension at 1024 pixels, captures decoder diagnostics, and rejects errors,
warnings, missing/encrypted/empty files, incomplete coverage or process timeout.
It does not mutate the caller's MuPDF warning buffer. Unusual but potentially
benign font-metric warnings are also blocked and need investigation; this is not
a font substitution or repair tool.

CLI contract for external callers such as typesetting preview export:

```text
python portable-production/localflow/pdf_render.py candidate.pdf
```

JSON contains `passed`, `page_count`, `rendered_pages`, `error`. Nonzero exit means
failure. Existing localflow rendering, publishing and acceptance callers obtain
the check through `audit_pdf_compatibility`; no separate copy is maintained.

The additive `diagnostic_kind` field distinguishes the reproduced outline Last
pointer diagnostic (`pdf_structure`) from other or mixed decoder diagnostics
(`pdf_decoder`); an empty value denotes no diagnostic classification. Compatibility
errors carry the same category instead of describing every warning as an actual
page-render failure. All categories still block publication and return nonzero.
Complete raster coverage alone cannot prove harmlessness: corrupt embedded fonts
may be substituted while producing a pixmap. The gate does not repair PDF bytes.

Regression fixtures are generated locally: valid vector pages, corrupt Flate
content, corrupt embedded library-provided font and a missing file. No manuscript,
commercial font or private PDF is committed. The content-corruption test failed
against the old implementation. All 18 localflow tests and two subtests pass with
an explicitly configured font profile. A private failing issue PDF was rejected
on its first page; this confirms detection, not the origin of the corrupt export.

This source change is a candidate with its own candidate bundle manifest.
Installed runtime and historical releases remain unchanged. Decodability does not replace visual,
source-content, semantic or print review.
