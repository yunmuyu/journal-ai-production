# Editorial route / author issue contract v1

This is an **additive, local decision validator**, not an automatic classifier,
renderer, production-state adapter, or publication approval. It has no built-in
author IDs, figure labels, gold answers, OCR, external service, or font dependency.
Existing preflight-v2 routing and production state are unchanged.
At this commit, existing localflow/delivery does not call this validator:
runtime delivery is not yet gated by it. A downstream integration must explicitly
invoke it and handle blocked/error results before dispatch or release.

## Use

From the preflight package directory, with the existing Python environment:

```sh
python -m journal_preflight.editorial_route <decisions.json> \
  --manifest <current-inputs.json> --previous <previous-decisions.json> \
  --out <new-report.json>
```

`--previous` is optional for the first record. On later revisions, supply the
previous decision manifest to detect rewritten proposals, deleted figures/issues,
rewritten overrides, and changed original issue text/source/location. Keep both
input records and reports outside the repository. Reports use exclusive creation
and do not overwrite existing evidence. No source file is changed.

The local input manifest is `{"files":[{"id":"source-a","path":"<local-source-path>"}]}`.
Its IDs must exactly match the union of sources in the decision manifest. Paths
are caller-supplied, never inferred or fetched from URLs. Every file is hashed at
validation time, using streaming SHA-256. Missing/unreadable files are errors;
changed hashes or omission of `--manifest` block readiness. Consumers must recheck
the source hash at the point of processing, since a report is a point-in-time
snapshot, not a lock on future file contents.

Python API:

```python
from journal_preflight.editorial_route import ContractError, validate_manifest

report = validate_manifest(decisions, current_inputs, previous=prior_decisions)
if not report["ready_for_processing"]:
    # Stop dispatch; report the blocked per-figure gates.
    ...
```

Malformed or contradictory input raises `ContractError`. A valid incomplete
record produces a report with blocked gates. CLI exit code is 0 only when all
figures are ready for candidate processing; otherwise 2. The CLI creates a report
for valid-but-blocked decisions, but not for malformed contracts.

## What readiness means

`ready_for_processing` means **the supplied decision contract is complete and its
live source hashes match**. The validator checks evidence references and required
review records, not the truth of their observations. It does not authenticate a
quoted instruction, user/reviewer identity, or independently inspect semantic correctness. Callers must
obtain legitimate review evidence and verified user authorization themselves.
Never manufacture a successful review record just to satisfy a gate.

The report always records:

- `validation_scope: decision_contract_only`
- `semantics_independently_verified: false`
- `user_provenance_authenticated: false`
- `provenance_authenticated: false` (applies to reviewers as well as users)
- `ready_for_publication: false` and `publication_performed: false`

Its figure set is the explicit caller scope, not proof that all figures in a
manuscript have been discovered. Output geometry, preserved data, source identity,
visual/font audits, and final user acceptance remain separate downstream work.
No existing localflow dispatch or publication gate is bypassed or replaced.

## Decisions and evidence

Exactly four routes are accepted:

| Route | Intended candidate operation | Additional recorded checks |
| --- | --- | --- |
| `structural_redraw` | Redraw a reviewed structure while preserving nodes, connections, directions, and meanings | `topology_preservation` |
| `plot_reletter` | Preserve original plot geometry/data relationships and replace only reviewed text | `original_geometry`, `text_replacement_plan` |
| `raster_grayscale_single_column` | Preserve the full raster canvas, convert suitable content to grayscale, and fit one column | `full_canvas`, `grayscale_suitability`, `single_column_legibility` |
| `unresolved` | Keep a decision pending | Always blocking |

All resolved routes also require `source_identity`, `delivery_scope`,
`protected_content`, and `column_capacity` checks. Record real measured capacity,
not a default column label. A grayscale raster decision must specify `single`;
other routes may use `single` or `double`. An `unresolved` column blocks readiness.

Each check has a `status` of `recorded_satisfied` or `unresolved`, plus
`evidence_ids`. A satisfied check needs at least one known evidence record. Every
record includes its method, location, observation, source ID, and source SHA-256.
The source-identity check must cover every source declared for that figure, such
as both the current Word and selected artwork. Missing checks block; unknown
fields, fabricated reference IDs, stale hashes, and duplicate IDs are errors.

These route names are not evidence of semantic fitness. A plot must not become a
structural redraw merely because an agent labels it one. This v1 contract does
not authorize reconstructing quantitative data from screenshots or infer that
grayscale is safe for a color-encoded scientific image. Such judgments require
actual protected-content and route-specific review. Unsupported cases remain
`unresolved`, rather than being forced into the nearest label.

`decision.proposed` retains the original route and column. The selected route and
column must equal the proposal after applying `overrides` in order. Each override
has a stable ID, field, previous value, new value, and explicit user provenance:

```json
{
  "id": "override-1",
  "field": "column",
  "previous_value": "single",
  "value": "double",
  "provenance": {
    "actor": "user",
    "reference": "<verified-message-reference>",
    "quote": "<exact-user-instruction>",
    "recorded_at": "2026-01-01T12:00:00Z",
    "source_snapshot": {"source-a": "<current-64-character-lowercase-sha256>"}
  }
}
```

The provenance snapshot must exactly match the figure's sources. Overrides cannot
waive missing evidence, source staleness, an unresolved route, or the single-column
restriction. A source change requires a fresh reviewed snapshot, not editing old
evidence to pretend a previous review covered new bytes. Archive old manifests;
v1 does not provide automatic rebasing of issue/override history across changed
source versions.

## Author issues: preserve, do not silently fix

Every issue includes `id`, `kind`, `source_id`, `source_sha256`, `location`,
`original_text`, `output_text`, `status`, `disposition`, and `reason`. Exact text is
preserved, including spaces; the validator never normalizes it. `proposed_text`
may record a suggested correction without applying it. Allowed kinds are
`author_text`, `source_conflict`, and `other`.

- `pending`: must remain `unresolved`, retain `output_text == original_text`, and
  blocks processing. A proposal alone is not approval.
- `preserve_original`: requires the explicit provenance format above, with
  `actor: user` or `actor: reviewer`, and
  `output_text == original_text`. An unresolved `author_text` issue may then be
  nonblocking while remaining visibly unresolved in the output ledger. It is
  not a correctness pass. Unresolved source conflicts or other issues still block.
  A source-bound reviewer record may retain author text unchanged without asking
  for a fresh user approval for every suspected typo; keep the issue for later
  consolidated review. Its reference and quote record the explicit preservation
  decision, not an invented user instruction.
- `approved_correction`: requires explicit user provenance, `status: resolved`,
  and `output_text == proposed_text != original_text`. The original remains in
  the ledger. This records approval; it does not apply edits to source files.

There is no caller-set `blocks_readiness: false` escape hatch. Resolved status
alone cannot authorize changed text. With `previous` supplied, original issue
content and provenance location cannot be silently rewritten or removed.

## Minimal pending example

All hashes and observations below are placeholders. This intentionally incomplete
record is valid but **not ready**; it illustrates the contract without inventing a
successful review. Replace placeholders with actual evidence outside the repo.

```json
{
  "schema_version": "editorial-route/1",
  "figures": [{
    "id": "figure-a",
    "sources": [{"id": "source-a", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}],
    "decision": {
      "proposed": {"route": "unresolved", "column": "unresolved"},
      "route": "unresolved",
      "column": "unresolved",
      "reason": "Current source identity and intended treatment await review.",
      "overrides": []
    },
    "evidence": [],
    "checks": {},
    "author_issues": []
  }]
}
```

After reviewing a source, the reusable shape of an evidence/check pair is:

```json
{
  "evidence": [{
    "id": "source-review-1",
    "source_id": "source-a",
    "source_sha256": "<current-64-character-lowercase-sha256>",
    "method": "<how-the-source-was-actually-inspected>",
    "location": "<page-panel-or-region>",
    "observation": "<specific-observed-facts-and-their-relevance>"
  }],
  "checks": {
    "source_identity": {"status": "recorded_satisfied", "evidence_ids": ["source-review-1"]}
  }
}
```

Supply all required route checks independently and retain unresolved author
questions. The tests exercise all routes with synthetic files, not an author-
specific six-figure answer key.
