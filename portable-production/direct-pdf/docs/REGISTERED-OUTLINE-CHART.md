# Explicit outlined SVG chart registration

This is a bounded source-preserving adapter, not generic SVG chart recognition. An anonymous SVG can produce a primitive inventory without being classified as a chart. No values are inferred from line shapes, OCR, spacing or screenshots. Original source files remain unchanged.

## Entry and evidence

`ingest_native.svg_pages` returns `outline_inventory` where supported. An explicit reply uses `kind: outlined-svg-chart` and an `outline_chart` registration. `agent_spec._outline_chart` compiles it to the ordinary `kind: chart` engine. Default 8pt policy, axis-title roles, explicit `power10`, typography, layout and actual-PDF audits remain in force.

A registration binds the original source SHA256 and the complete primitive ID→hash map, then declares:

- `frame`: an original closed, axis-aligned rectangular path.
- `x_ticks` / `y_ticks`: original inward line refs plus outlined label refs and verified text; optional integer `power10` must match the explicit source notation.
- `x_title` / `y_title`: original outlined text refs, original transcription, target text, and a specific `correction_evidence` reference for any change. No unit or meaning is inferred.
- `title`: original figure-title refs and transcription. Its center is derived from the source ink bounds, not a sample-specific offset.
- `legend`: exact rectangular decoration refs and original region ref. `width_extension` is zero unless a specific user decision is referenced by `extension_evidence`; it is a maximum source-unit rightward allowance, not default permission to widen.
- `series`: verified label, original curve/marker primitive refs, and original swatch primitive refs. A series is not assumed to equal an SVG group.
- `protected_refs`: every primitive not explicitly removed as registered text, swatch or legend decoration. Frame, inward ticks and every series primitive must be protected.

Registration requires explicit `outline_transcription_checked` and `series_identity_checked` reviews. Hashes prove byte/object identity, not the correctness of transcriptions, omissions or semantic assignments. A source change invalidates the registration. Renamed/reordered SVGs require newly generated evidence and registration, not stale indices.

## Preservation and limits

All geometry and inherited attributes of retained primitives are checked before conversion. Only registered primitives are removed. Original swatches are isolated as complete primitives. Named groups are not required; mixed-series groups are supported through individual primitive refs. SVG user units are explicitly converted 1:1 to PDF points, with original dimensions and conversion recorded.

The original legend location and height are retained. Measured 8pt capacity failure is an error, not permission to move outside the plot, increase the height or shrink the font. Protected series ink bounds conservatively reject overlap with the original/expanded legend region; this may reject a safe complex source rather than claim unverified clearance. No hidden curve is reconstructed or painted in.

The actual-PDF source-path auditor re-prepares registered assets from the hash-bound original and consumes each placed path instance. Original source strokes are preserved under that exact ownership contract; unowned strokes still require the normal 0.5pt policy. There is no viewport exemption and no global tolerance change.

Initial supported inputs are static independent path/line/rect/circle/ellipse/polygon/polyline primitives, explicit inline styles/attributes, and supported finite affine transforms. Missing viewBox is supported only with explicit finite, positive, unitless width/height. Nonzero viewBox origins, nested SVG viewports, CSS stylesheets, XML entities, live text/use/images, percentage dimensions, ambiguous bounds and unsupported resources fail closed. External resources remain forbidden. This does not claim arbitrary SVG, multi-panel, transcription or final production acceptance.

## Frame boundary safety

The adapter rejects series geometry outside the mathematical axis frame, even if a source clipPath is present; this version does not infer clipping intent. Markers crossing that boundary are therefore unsupported rather than partially clipped. Retained nonbackground grid/axis lines must also lie within the frame. A viewport padded by the retained primitives' conservative ink bounds preserves legitimate boundary strokes. Placement scale remains based on the mathematical frame width, so padding does not shrink the plot or its data relationships. The padded viewport must fit the original SVG canvas.

Larger registered background rectangles are intentionally viewport-trimmed and identified as `background_viewport_trimmed_refs` in preparation receipts. The preservation claim applies to fully retained series/axis geometry and its visible ink, not to every pixel of larger original page backgrounds. Actual rendered-pixel regression verifies that a boundary series stroke remains visible outside the mathematical frame.
