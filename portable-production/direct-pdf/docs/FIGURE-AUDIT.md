# Figure audit and partial EMF inspection

These optional, independent inspection utilities produce evidence for human review. They do not approve figures or replace source, visual, semantic, or publication review. They are not connected to automatic publication or the production runtime.

With `portable-production/direct-pdf` on `PYTHONPATH`:

```text
python -m figure_audit.guard --out <candidate.pdf> --src <source.pdf> --column 80 --mode trace --json <report.json>
python -m figure_audit.spacing <candidate.pdf> --out <spacing.json>
python -m figure_audit.emf dump <source.emf>
python -m figure_audit.emf json <source.emf> <inspection.json>
python -m figure_audit.selftest
```

The guard accepts single-page PDFs only. Its checks include dimensions, extracted text, numerical tokens, fonts, paths and optional topology/spacing observations. An issue flagged by a heuristic must be checked against the source; an `INCOMPLETE` result is never approval. Exit codes: 1 for flagged issues, 3 when no issue was flagged but review remains incomplete, and 2 for invalid CLI arguments. No source, no extractable text, bitmap text, and unrecognized structures leave parts unexamined. One-way path shape matching does not prove that source objects are all present, positions are correct, or data is unchanged. An apparently matching topology does not establish that all elements were detected.

Spacing measurements are experimental. Historical quantiles were reported from two issues; the private corpus and raw per-file results are not included in the public repository and have not been independently revalidated here. Numeric targets and ranges are observations, not required editorial thresholds. Detection may confuse legends, axes or subplots. Reports are tied to the exact PDF SHA-256; inputs are never valid report destinations.

EMF extraction supports a limited subset of records and reports unsupported types. World transforms, MM_TEXT and MM_ANISOTROPIC window/viewport mappings are applied to supported geometry. Intersect-clip rectangles are stored as transformed polygon constraints in `clip_regions_mm`, including saved/restored state. OffsetClipRgn moves those constraints by the mapped logical offset vector; unknown coordinate state keeps clipping unknown. These constraints are not applied to trim emitted geometry and do not model device-region rounding exactly. `clip_status=unknown` indicates an unsupported clipping operation, and `coordinate_status=unknown` indicates an unsupported mapping change. JSON and command output remain `complete=false` / partial. Other map modes, scale-extent records, paths, bitmap content and full GDI semantics remain unsupported; text bounds are estimates. The former PDF conversion command was removed because it silently omitted text and unsupported records. Inspect the original with a suitable viewer; never substitute extraction for the source.

The state model follows [Microsoft EMF region definitions](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/939400bc-0ecd-4a28-aa8c-60c7e4cc9877), [world transform modes](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/e6bb2996-195f-473f-80c6-9dc1afe474f9), [intersect clip records](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/13cd0c98-d4e9-4ca7-a79d-58055bf45c79) and [offset clip records](https://learn.microsoft.com/en-us/openspecs/windows_protocols/ms-emf/8bf2b60d-3b19-4bd1-b2d7-c89b027ad808).

Do not upload author PDFs, EMF files, reports, local baselines, paths or font data to public version control. Test figures used in this repository are synthetic.
