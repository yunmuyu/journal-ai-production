# Mixed PDF preparation fidelity

`source_mixed_body` keeps the original PDF paint stream rather than separating
all raster images from all vectors. The existing public scene/Assets path is
still the preparation entry point. Preparation and saved-PDF ownership checks
now verify the ordered nontext paints as well as the existing path and image
instance multisets.

- Image instances resolve their real `Do` XObject references, including nested
  Forms. Equal RGB bytes do not imply equal image resources: dimensions, SMask,
  clip paths, and transforms remain individually bound to every instance.
- Native SMask bytes and properties are retained. Only the documented grayscale
  conversion may change image RGB bytes and vector paint colors. Moving a paint
  across another paint or changing an image clip fails the fidelity check.
- Visible-page coordinates remain the public coordinate system for source clips
  and text registrations. Unrotated nonzero/negative MediaBox or CropBox origins
  are normalized in memory, with path, native-text, image and pixel checks, and
  an `origin_normalization` receipt. The original source and its SHA256 binding
  are retained. Rotated nonzero-origin pages and annotated/form-filled pages
  need separate handling and are rejected rather than silently transformed.
- The vector body's existing raw-text fallback uses the same origin preparation.
  Original paths, data curves and connectors are not reconstructed from pixels.

These are fidelity checks, not proof that all source text was replaced. Native
span registrations cover only extractable PDF text. Lettering retained as
outlines or inside image pixels still requires independent supported evidence.
The `source_text_coverage` gate stays strict: native relettering alone cannot
make such an asset publication-ready. The receipt continues to disclose
`source_text_scope: native_pdf_text_only` and image semantic-review requirements.
Inline images, unsupported image formats/masks and unverified clipping constructs
remain fail-closed. There is no new automatic text-coverage exemption or arbitrary
mixed-PDF-to-editable conversion route.

Synthetic regressions cover shared RGB bytes with different dimensions/SMasks,
reused image instances, Forms, transformed clips, changed clipping, saved paint
reordering, positive/negative origins, source hashes and native-text registration.
Author files and production-machine configuration are not test fixtures.
