# Source-bound editorial release gate

`editorial_gate.check_editorial_gate(config, candidate, report, artifact_format)` is a fail-closed guard for review/publication. It does not render or copy files and never grants final human acceptance.

New publishing candidates require these inline fields in `constraints.confirmed`:

- `editorial_route_contract`: the `editorial-route/1` decision manifest described in `../preflight/docs/EDITORIAL-ROUTE-V1.md`.
- `editorial_figure_id`: the selected figure ID.
- `editorial_targets`: complete, unique `{id, author_rel, figure_number}` entries for all figures in that contract.

The inline records are bound by the existing constraints hash. Sources use preflight manifest IDs; the selected decision's source set must equal the actual candidate report's source bindings. The gate revalidates current source bytes and the sealed preflight evidence, checks all recorded routes are resolved, and requires all DOCX caption candidates (including unsupported/unextracted figures) to have source-associated target identities. Duplicate caption numbers block pending inventory resolution. Caption candidates themselves are not proof of figure identity.

PDF delivery is supported only by structural-redraw or plot-reletter decisions; JPG by raster-grayscale-single-column decisions. Legacy candidates without the contract are not grandfathered into publication: regenerate their confirmed constraints and candidate. Rendering an isolated candidate remains distinct from approving or publishing it.

This contract validates structure, recorded evidence, source completeness and exact hashes. It does not authenticate a quoted user, independently prove topology or text correctness, infer the route, or replace actual visual review. Preserving suspected author errors is separately recorded; silent author correction is not allowed by the decision contract.

Integration: the native-JPG publishing increment calls this function from both review and publish. A separately tested function alone is not an end-to-end publication gate until those call sites are present.

PDF candidates additionally require an explicit full-scene final-visibility audit, coverage of every reported text, path and asset, and complete original-asset reference coverage. Rebuilt scenes require an independently bound original structure contract. Unresolved or unknown warnings block delivery regardless of the candidate status; an independently bound font-size exception and the informational axis-unit normalization notice remain handled separately. These checks cover recorded evidence only: they do not prove white-text contrast, image-internal typography, or relationships absent from the independent contract. JPG takes its existing raster review route; do not treat these PDF checks as JPG coverage. Preview rendering remains available; older PDF candidates lacking this evidence must be regenerated.

An individually reviewed warning may be resolved in the candidate-bound review record using `resolved_warnings`: each entry contains the exact `warning_sha256` (canonical `hash_json` of that report warning) and a specific `evidence` string of at least 20 characters. Review validates the candidate, output, source and constraint hashes first; publish revalidates the same immutable review and warning identities. This is a recorded human/agent review, not automatic proof or user acceptance. Missing evidence cannot bypass an unchecked structure, visibility or original-asset audit.
