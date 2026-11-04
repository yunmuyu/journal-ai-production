# Bounded grouped chains (development adapter)

`kind: diagram`, `model: grouped-chains` compiles source-bound `nodes` and
`edges` using the existing native text coverage and connector direction checks.
`structure` contains exactly `groups` and `bridge`:

- `groups`: exactly two containers, upper then lower. Each has `id`, `title`
  (native `ref` or `refs`/`join`, or reviewed raster `ref`/`text`), `direction`
  (`LR` or `RL`), and an ordered nonempty `nodes` ID list. Optional `dash`
  preserves an explicitly reviewed source stroke pattern; omitted means solid.
  Optional `style_ref` verifies it against an existing rectangular PDF
  native-path candidate with zero dash phase.
- The groups must face opposite directions. All nodes retain the declared
  chain order; no topological edge is added, dropped, or reversed.
- `bridge`: null for one outside return connection, or `{node, side}` for
  exactly one outside node between the upper last and lower first node.
  `side` is `right` for upper LR, `left` for upper RL.
- Every node belongs exactly once to a group or the bridge. Only ordinary
  rectangle nodes and single-headed chain edges are supported. Other shapes,
  branches, nested groups, arbitrary ports, extra edges, or missing edges fail
  with `grouped_chains_unsupported`.
- Source-native titles, node text and edge labels share one coverage check.
  Missing, duplicate, rewritten native text and reversed native arrows remain
  errors. Existing source line breaks and explicit native fragment joins are
  preserved. No automatic text rewriting or author-specific wrapping is added.

No origin, gap, individual position, or font knob is accepted by this semantic
model. The existing production policy starts at 8pt; this adapter does not
attempt smaller fonts or claim a single-column fit. The existing whole-artwork
fit/minimum-6pt gate remains responsible for publication capacity. It may return
`layout_reflow_required`; no automatic switch to double column occurs.

## Derived geometry, not new editorial constants

The adapter reuses `PAD_X`, `PAD_Y`, `COMPACT_GAP`, `LABEL_CLEARANCE`,
`ARROW_DEPTH`, `ARROW_BOUNDARY_GAP`, `STROKE`, and `EXPORT_PAD` from editorial.py.
Node ink is measured by the configured registry. Each chain shares a measured
row height. Adjacent edge gaps reserve the measured label width plus the existing
clearances/arrow depth, never less than the existing arrow boundary gap.

Container envelopes include measured title, complete row-node and edge-label
ink, and existing padding. The vertical row-center separation is the maximum of
nonoverlapping container envelopes plus compact gap, and bridge height plus two
arrow terminal lengths. The outside corridor reserves measured external labels,
clearance, the bridge half-width, and arrow terminal length. Page bounds include
all measured text ink, including labels outside the frames. Left-bridge layouts
mirror geometry, not text glyphs or directed connectivity.

`layout_evidence` reports group envelopes, measured title dimensions, edge gaps,
the competing vertical constraints and chosen separation, outside label width,
and corridor width. This is a bounded construction, not a global optimum or a
general clustered graph solver. It uses `Scene` arrows/ports and the common
endpoint, overlap, ink-boundary and terminal-length audits. An audit failure
returns `grouped_chains_no_feasible_layout` with issues; it does not retry with
local manual adjustments or smaller text.

Validation is synthetic, varying node counts, unequal group sizes, text length,
source line breaks, bridge presence and side. No customer PDF, publication
approval, actual-print acceptance, or held-out generalization is implied.

## Container stroke provenance

Group `dash` uses the same shared validation as `Scene.shape`: a nonempty list
of finite nonnegative numbers, with at least one positive entry; booleans,
negative values, all-zero arrays and explicit null are rejected. There is no
invented dashed default. Pattern values are points and follow the existing
whole-artwork scaling and node PDF export, like other Scene dashed nodes.

Without `style_ref`, evidence says `reviewed-declaration` and
`mechanically_verified: false`. This is not mechanical proof of transcription.
Omitted style remains `solid-default`, also not source-verified.

With `style_ref`, only an existing `native-path` rectangle with parseable
`geometry.dashes` and zero phase is supported. An explicit dash must exactly
match the native pattern (or be omitted for a verified solid pattern).
Mismatches, unknown candidates, unsupported shape kinds and nonzero phases
raise an error; they do not fall back to reviewed declarations. The evidence
binds source ID/hash and native object ID, and states `dash-pattern-only`.
Container membership and source visual equivalence still require review.
Visio line-pattern enumeration and PPTX dash extraction are not converted to
invented point patterns by this adapter.
