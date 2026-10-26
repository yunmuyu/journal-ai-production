# Source-body text coverage gate

`source-vector-body` and `source-mixed-body` preserve arbitrary source paths or image pixels. Replacing every extractable native PDF span does not establish that all visible labels were replaced: retained paths/pixels can contain lettering. The engine does not claim to recognize such lettering automatically.

These routes therefore save a diagnostic PDF, preview and report, then raise `source_text_coverage`. Existing mechanical checks remain `true` when they passed; `overall_checks_passed` is `false`, `typography_coverage.status` is `unverified`, and the status is `candidate-unverified-source-text`. A batch or agent caller receives a failure, not an accepted candidate. Localflow also rejects legacy source-body reports even when they claim mechanical success.

This is a conservative route-level limitation, not proof that a particular source has outlined text or incorrect typography. Explicitly registered SVG/chart and isolated vector-glyph routes retain their existing contracts. A future full-coverage route must carry independently verified evidence before allowing arbitrary preserved source bodies into acceptance; a caller-supplied success flag is not sufficient.

Synthetic regression includes a native label plus a tiny H built from filled paths, with a raster image in the mixed-body variant. It verifies retained diagnostic artifacts, native-text mechanical success and explicit overall rejection. No private manuscript or font is included.

## Complete native PDF / companion SVG registration

A separate `source_registered_pdf_text: true` scene asset accepts `text_registration` with `pdf_sha256`, `svg_path` (relative to source root), `svg_sha256`, and `groups`. Each group has `svg_group_id` and `entries`; each entry declares `svg_text_index` (within the group's SVG `text` elements) and `pdf_span_indices` (whole-page nonblank native spans in extraction order). All SVG text_N groups/text elements and all PDF spans must be consumed exactly once, with exact concatenated text. Both sources must appear in the scene's hash-bound `sources`.

The whole page is registered before applying `clip`; clips cutting a native label are rejected. `text_replacements` retains the existing bbox/text/target-ID contract for the selected clip. `texts[].gray` defaults to black (`0`); `1` is accepted only for an explicitly registered original white label. Actual PDF character/color counts are checked separately from the truthful `editable_text_pure_black` field.

Nontext content operations are preserved while native text operators/resources are removed. This matters for Type3 fonts: native glyph programs also appear as drawing paths and must not be misclassified as retained plot geometry. Nontext paths and image pixel/alpha/placement records are checked before normalization and again through source-bound asset regeneration against the actual output. Text clipping modes and unsupported nested residual text are rejected.

`grayscale: true` explicitly applies the shared RGB luminance mapping to vector paint and decoded image pixels. The receipt records original/derived image hashes and the mapping; it does not claim original RGB pixels were unchanged. Dimensions, image placement and alpha are retained. `false` preserves source colors and remains subject to the existing neutral-output audit.

Companion SVG is parsed for text only, with networking and entity expansion disabled; embedded images are not executed. An explicit `nontext_svg_groups: [{id, role: "label-background"}]` declaration may identify a source label background containing path/rect paint. Unregistered paint inside text groups is rejected. This bounded contract does not detect arbitrary outlined or raster text outside registered SVG text groups. Semantic source pairing and actual-size visual inspection remain required; a mechanical pass is not publication approval.

Type3 white-label evidence uses both the companion SVG's inherited `fill` and independent PDF text decoding with the native graphics-state fill. MuPDF span/trace color is not authoritative for Type3 glyphs: it can report black while the glyph is painted white. A mismatch between the two white-text inventories is rejected. The report keeps the extractor's original color for diagnosis and the corroborated black/white target separately.

## Native text rotation

Scene `rotation` accepts finite angles in degrees; positive angles follow the existing quarter-turn convention. Oblique bounds are measured from original font curves after rotation, using the same font and point size. PDF text uses an affine rotation, never a substituted italic face. Editable text content and per-character PDF direction are independently audited (0.01 degree angular tolerance). Non-quarter-turn text collision checks use rotated per-glyph ink quadrilaterals for neighboring text, strokes and arrowheads; existing quarter-turn checks remain in place. The final font minimum remains 6pt, and rotation itself does not reduce font size.
# Reflowed text provenance without a painted viewport

Scene specs may declare `source_text_bindings`: each entry supplies an `id`,
source `path`, zero-based `page`, `clip`, complete `text_registration`, and exact
`text_replacements`. The same whole-page PDF/SVG registration validates source
hashes and text identity, and every declared target must exist with matching
editable text and black/white contrast. Line breaks may reflow without changing
the remaining characters. These records appear under
`layout.layout_evidence.source_text_bindings` and paint no source asset.

Use this for annotation text whose placement is independent of a retained data
viewport. Do not use a tiny or hidden PDF asset as a provenance carrier: it can
introduce visible paint and affect final cropping. A text-only binding neither
removes source graphics nor proves the completeness of selected data viewports.
Any omitted nondata background or decomposed figure still requires separate,
source-bound evidence; this interface is not permission to erase data.


## Actual PDF font faces and quantity separators

The PDF gate matches editable scene characters by baseline position, point size
and direction, then checks each configured PostScript face. A correct italic
font elsewhere in the document cannot mask a regular glyph at an italic target.
This checks declared styles, not whether a source symbol is semantically a
variable; that decision still requires source review.

Confirmed storage quantity spacing is normalized for plain and rich text while
preserving values and unit case. Literal/code/path content is protected. An
independent PDF check retains spaces, unlike a whitespace-insensitive character
multiset. Unknown units and physical character-gap measurement remain outside
that rule's scope.
