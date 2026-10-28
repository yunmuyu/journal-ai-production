# Measured stage-grid candidate

`kind: "stage-grid"` is a direct-spec candidate for bounded stage-column diagrams. Columns contain measured stages, nodes, labels, groups or notes. Edges declare endpoints and ports; the layout derives positions and audits the resulting scene. It does not implement arbitrary nested-graph reflow or infer connections from an image. Use verified source bindings and review the generated PDF against the source.

The implementation supports bounded nesting, explicit alignment, forward and vertical relations, shared merge/split routes and optional cropped raster or PDF icons. Icon paths are resolved within the declared source root; normal `render_one` source-hash binding applies. Reject unsupported or infeasible layouts instead of fabricating a result.

The stage-grid tests cover layout constraints and a synthetic PDF through `render_one`. They do not establish that every real figure or scale is feasible. In particular, dense layouts and final arrow terminal lengths must be checked in the produced report and visually inspected. This branch is a source candidate; it does not update the sealed release manifest, installed runtime, publication status or Adobe/InDesign validation.

Polygon fill, stroke gray and opacity are available in direct scene paths. They are independently audited; decorative geometry is not a general exemption from text-collision checks.

The separate local PDF guard, spacing heuristics, corpus rules, EMF parser, private baselines and per-author scripts are not part of this candidate. Their current evidence does not justify treating empirical thresholds as mandatory editorial standards or exposing machine-specific data in a public repository. A guard PASS cannot establish source fidelity or visual acceptability.
