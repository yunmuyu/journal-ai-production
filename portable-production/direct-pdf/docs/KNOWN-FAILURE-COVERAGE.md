# Known failure coverage and release boundary

This is a bounded engineering ledger, not a zero-error or production-readiness
claim. Automated checks, source-semantic review, visual review and final human
acceptance are distinct. Passing more tests does not close an unsupported input
route. All development artifacts remain candidates until explicitly accepted.

## Closed known bypasses, subject to integration verification

- Missing Word/VML/OLE figures: preflight reports unbound captions and unsupported
  embedded evidence; editorial completeness gate blocks unresolved source-bound
  figure inventory. It does not convert every OLE object or infer its meaning.
  Regression: preflight DOCX tests and tests-local/test_editorial_gate.py.
- Wrong figure publication in a multi-output batch: review and publication bind
  current sealed spec identity, not merely expected_outputs membership. Wrong
  number and explicit filename negatives cover JPG and real PDF chains.
  Regression: test_native_jpg_publishing.py and
  LocalFlowTest.test_real_pdf_candidate_cannot_be_reassigned_in_multi_output_batch.
- Manual smaller-font start mislabeled as default8: semantic entry requires
  separately supplied source/reply/size-bound exception; measured reports state
  their real starting input. Preview APIs remain available, but publication
  consumes the measured font-policy evidence.
  Regression: test_production_font_policy.py and test_publication_font_gate.py.
- Copied exception from another source: agreement between copied provenance
  fields is insufficient; exception source must identify the current candidate's
  verified sources. Matching-source positive and stale-source real-PDF negatives
  are covered. This does not authenticate the exception's human approver.
- Plot disguised as generic scene labels: a recorded plot_reletter route requires
  actual chart output and both axis-title actual-PDF checks. Empty checks with
  ok=true cannot qualify. Untitled/one-title charts remain outside this route.
  Regression: test_publication_font_gate.py, including real scene negative and
  dedicated-chart publication positive.
- Same-size log exponents/hyphen: explicit power10 semantics produce reduced
  exponent glyph sizes and mathematical minus, not independently moved labels.
  Original tick spelling and bound positions must agree with the declaration.
  Regression: test_scientific_text.py, actual PDF span verification.

- Invented native edge label: a nonempty native connector label must bind an
  original text object, and an explicit duplicate string must agree exactly.
  Raster reviewed transcription remains available. Regression:
  test_grouped_chains.py native label negatives and raster positive.

- Protected series silently cropped at frame: registered outlined charts now
  reject exterior series/axis geometry and derive boundary ink padding without
  squeezing it into the old viewport. Pixel-level synthetic regression verifies
  boundary stroke visibility. Larger background rectangles are explicitly
  recorded as viewport-trimmed, not claimed fully preserved.
  Regression: test_source_outline_chart.py.

## Bounded new adapter, not universal layout

The grouped-chains model derives two opposite-direction container chains from
measured text, existing padding/arrow rules and explicit membership. No manual
origin, row gap or lower-font shortcut is accepted. Unsupported branches,
shapes, missing/extra edges and capacity failures stop explicitly. Optional
container dash declarations retain their verification status; supported native
PDF style references are checked separately. Reviewed declaration is not native
geometry proof. See GROUPED-CHAINS.md and test_grouped_chains.py.

## Unclosed acceptance boundaries

- Generic ZIP/DOCX embedded-Visio extraction to complete source-bound semantic
  input is not implemented end to end. A manually inspected native object is not
  evidence that the unattended intake path supports the same object.
- Arbitrary outlined charts, source titles and original legend capacity cannot
  be replaced by private scene scripts. Registered-outline adaptation is a
  separately tested bounded route; do not infer all-SVG support from it.
- Route evidence records reviewed classification, not independent truth. Wrong
  source transcription or misclassification can still require human detection.
- Independent reconstruction of an absent semantic reply and approver identity
  authentication are not implemented by a hash-bound exception record.
- Multiple state roots writing one delivery root are unsupported. Deployments
  must use one state root per delivery root; current locks are not global locks.
- InDesign placement, issue/page metadata and printing acceptance are outside
  this figure renderer's automated acceptance. No later proofreading is assumed
  to repair layout or publication metadata errors.

## Stop and rollback rules for this development increment

Keep inputs read-only, outputs isolated and source/output hashes available. Do
not replace accepted deliverables with development candidates. On ambiguous
source, unsupported geometry, failed audit or repeated manual intervention,
keep the original and report the blocking object rather than changing data,
shrinking around the rule or silently dropping content. A candidate that needs
more correction than a manual route is not an automation success.

Local code commits may be reviewed independently and reverted before release;
no release, deployment or production-state migration follows automatically from
a passing test run. Record engineering/test time separately from actual unseen
input-to-reviewed-output time. No held-out throughput claim is established by
these development fixtures.
