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

EMF extraction supports a limited subset of records and reports unsupported types. The JSON and command output explicitly say `complete=false` / partial. Coordinate transforms, viewport mapping, clipping, text metrics, raster records, and full GDI semantics are not reliable enough to reconstruct or certify a source figure. The former PDF conversion command was removed because it silently omitted text and unsupported records. Reject malformed inputs and inspect the original with a suitable viewer; never substitute the extraction for the source.

Do not upload author PDFs, EMF files, reports, local baselines, paths or font data to public version control. Test figures used in this repository are synthetic.
