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
