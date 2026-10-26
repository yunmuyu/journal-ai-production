"""Source-bound editorial decisions, not an automatic figure classifier.

This additive contract validates recorded reviews before candidate processing. It
does not authenticate quoted user instructions, independently check the evidence,
render figures, change author text, or grant publication/acceptance status.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

SCHEMA_VERSION = "editorial-route/1"
ROUTES = frozenset({"structural_redraw", "plot_reletter",
                    "raster_grayscale_single_column", "unresolved"})
COLUMNS = frozenset({"single", "double", "unresolved"})
COMMON_CHECKS = ("source_identity", "delivery_scope", "protected_content", "column_capacity")
ROUTE_CHECKS = {
    "structural_redraw": ("topology_preservation",),
    "plot_reletter": ("original_geometry", "text_replacement_plan"),
    "raster_grayscale_single_column": ("full_canvas", "grayscale_suitability",
                                        "single_column_legibility"),
    "unresolved": (),
}
CHECKS = frozenset(COMMON_CHECKS).union(*ROUTE_CHECKS.values())


class ContractError(ValueError):
    """A malformed, contradictory, or stale decision contract."""


def _require(ok, message):
    if not ok:
        raise ContractError(message)


def _object(value, required, optional=(), where="object"):
    _require(isinstance(value, dict), f"{where}: expected object")
    _require(set(required) <= value.keys(), f"{where}: missing required fields")
    _require(value.keys() <= set(required) | set(optional), f"{where}: unknown fields")


def _text(value, where, allow_empty=False):
    _require(isinstance(value, str) and (allow_empty or bool(value.strip())),
             f"{where}: expected {'possibly empty ' if allow_empty else ''}text")


def _choice(value, choices, where):
    _require(isinstance(value, str) and value in choices, f"{where}: unsupported value")


def _rows(value, where, nonempty=False):
    _require(isinstance(value, list) and (not nonempty or bool(value)),
             f"{where}: expected {'nonempty ' if nonempty else ''}array")
    return value


def _sha(value, where):
    _require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
             f"{where}: expected lowercase SHA-256")


def _unique(rows, where):
    result = {}
    for row in rows:
        _require(isinstance(row, dict), f"{where}: expected object entry")
        _text(row.get("id"), f"{where}.id")
        _require(row["id"] not in result, f"{where}: duplicate id {row['id']}")
        result[row["id"]] = row
    return result


def _provenance(value, snapshot, where, actors=("user",)):
    _object(value, ("actor", "reference", "quote", "recorded_at", "source_snapshot"), where=where)
    _choice(value["actor"], actors, f"{where}.actor")
    for name in ("reference", "quote", "recorded_at"):
        _text(value[name], f"{where}.{name}")
    try:
        timestamp = datetime.fromisoformat(value["recorded_at"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"{where}: invalid recorded_at") from exc
    _require(timestamp.utcoffset() is not None, f"{where}: recorded_at needs timezone")
    _require(value["source_snapshot"] == snapshot, f"{where}: stale source snapshot")


def _source_ref(value, snapshot, where):
    _text(value.get("source_id"), f"{where}.source_id")
    _sha(value.get("source_sha256"), f"{where}.source_sha256")
    _require(snapshot.get(value["source_id"]) == value["source_sha256"],
             f"{where}: unknown or stale source reference")


def _decision(value, snapshot):
    _object(value, ("proposed", "route", "column", "reason", "overrides"), where="decision")
    _object(value["proposed"], ("route", "column"), where="decision.proposed")
    current = dict(value["proposed"])
    for record in (current, value):
        _choice(record["route"], ROUTES, "decision.route")
        _choice(record["column"], COLUMNS, "decision.column")
    _text(value["reason"], "decision.reason")
    overrides = _rows(value["overrides"], "decision.overrides")
    _unique(overrides, "decision.overrides")
    for override in overrides:
        _object(override, ("id", "field", "previous_value", "value", "provenance"), where="override")
        _choice(override["field"], ("route", "column"), "override.field")
        field = override["field"]
        _choice(override["value"], ROUTES if field == "route" else COLUMNS, "override.value")
        _require(override["previous_value"] == current[field], "override: broken decision history")
        _require(override["value"] != current[field], "override: no-op decision change")
        _provenance(override["provenance"], snapshot, "override.provenance")
        current[field] = override["value"]
    _require(current == {k: value[k] for k in current},
             "decision: changed proposal without explicit override provenance")
    _require(value["route"] != "raster_grayscale_single_column" or value["column"] == "single",
             "decision: grayscale raster route requires single column")


def _issues(rows, snapshot):
    indexed = _unique(_rows(rows, "author_issues"), "author_issues")
    blocking = []
    for issue in indexed.values():
        _object(issue, ("id", "kind", "source_id", "source_sha256", "location", "original_text",
                        "output_text", "status", "disposition", "reason"),
                ("proposed_text", "provenance"), "author_issue")
        _choice(issue["kind"], ("author_text", "source_conflict", "other"), "author_issue.kind")
        _source_ref(issue, snapshot, "author_issue")
        for key in ("location", "reason"):
            _text(issue[key], f"author_issue.{key}")
        for key in ("original_text", "output_text"):
            _text(issue[key], f"author_issue.{key}", allow_empty=True)
        if "proposed_text" in issue:
            _text(issue["proposed_text"], "author_issue.proposed_text", allow_empty=True)
        _choice(issue["status"], ("unresolved", "resolved"), "author_issue.status")
        _choice(issue["disposition"], ("pending", "preserve_original", "approved_correction"),
                "author_issue.disposition")
        disposition = issue["disposition"]
        if disposition == "pending":
            _require(issue["status"] == "unresolved", "author_issue: pending cannot be resolved")
        else:
            actors = ("user", "reviewer") if disposition == "preserve_original" else ("user",)
            _provenance(issue.get("provenance"), snapshot, "author_issue.provenance", actors)
        if disposition == "approved_correction":
            _require(issue["status"] == "resolved", "author_issue: correction approval must be resolved")
            _require("proposed_text" in issue and issue["output_text"] == issue["proposed_text"],
                     "author_issue: output differs from approved correction")
            _require(issue["output_text"] != issue["original_text"], "author_issue: no-op correction")
        else:
            _require(issue["output_text"] == issue["original_text"], "author_issue: silent text correction")
        if issue["status"] == "unresolved" and not (
                issue["kind"] == "author_text" and disposition == "preserve_original"):
            blocking.append(issue["id"])
    return blocking


def _text_review(value, evidence, snapshot, route):
    """Validate recorded text needs, not the image or truth of a review."""
    if value is None:
        return False
    _object(value, ("requirement", "categories", "reason", "evidence_ids"), where="text_review")
    _choice(value["requirement"], ("none", "preserve_native", "replace", "unknown"),
            "text_review.requirement")
    categories = _rows(value["categories"], "text_review.categories")
    for category in categories:
        _choice(category, ("axis_title", "tick_label", "legend", "data_annotation", "ui_text", "other"),
                "text_review.category")
    _require(len(set(categories)) == len(categories), "text_review: duplicate category")
    requirement = value["requirement"]
    _require(requirement != "none" or not categories, "text_review: none contradicts text categories")
    _require(requirement not in ("replace", "preserve_native") or bool(categories),
             "text_review: text treatment requires categories")
    _text(value["reason"], "text_review.reason")
    refs = _rows(value["evidence_ids"], "text_review.evidence_ids", nonempty=True)
    for ref in refs:
        _text(ref, "text_review evidence reference")
        _require(ref in evidence, "text_review: unknown evidence reference")
    _require(len(set(refs)) == len(refs), "text_review: duplicate evidence reference")
    _require({evidence[ref]["source_id"] for ref in refs} == set(snapshot),
             "text_review: review must cover every source")
    return requirement != "unknown" and not (
        requirement == "replace" and route == "raster_grayscale_single_column")


def _figure(figure):
    _object(figure, ("id", "sources", "decision", "evidence", "checks", "author_issues"),
            ("text_review", "source_review"), where="figure")
    sources = _unique(_rows(figure["sources"], "sources", nonempty=True), "sources")
    for source in sources.values():
        _object(source, ("id", "sha256"), where="source")
        _sha(source["sha256"], "source.sha256")
    snapshot = {key: row["sha256"] for key, row in sources.items()}
    _decision(figure["decision"], snapshot)
    evidence = _unique(_rows(figure["evidence"], "evidence"), "evidence")
    for item in evidence.values():
        _object(item, ("id", "source_id", "source_sha256", "method", "location", "observation"), where="evidence")
        _source_ref(item, snapshot, "evidence")
        for name in ("method", "location", "observation"):
            _text(item[name], f"evidence.{name}")
    _object(figure["checks"], (), CHECKS, "checks")
    for name, check in figure["checks"].items():
        _object(check, ("status", "evidence_ids"), where=f"check.{name}")
        _choice(check["status"], ("recorded_satisfied", "unresolved"), f"check.{name}.status")
        refs = _rows(check["evidence_ids"], f"check.{name}.evidence_ids")
        for ref in refs:
            _text(ref, "evidence reference")
            _require(ref in evidence, "check: unknown evidence reference")
        _require(len(set(refs)) == len(refs), "check: duplicate evidence reference")
        if check["status"] == "recorded_satisfied":
            _require(bool(refs), "check: satisfied claim without evidence")
            if name == "source_identity":
                _require({evidence[ref]["source_id"] for ref in refs} == set(snapshot),
                         "check: source identity must cover every source")
    text_ready = _text_review(figure.get("text_review"), evidence, snapshot, figure["decision"]["route"])
    structure_ready = False
    if figure.get("source_review") is not None:
        from .route_suggestion import suggest_route
        review = figure['source_review']
        proposal = suggest_route(review, [])
        _require(review['source_snapshot'] == snapshot, 'source_review: figure snapshot mismatch')
        _require(review['text_requirement'] == (figure.get('text_review') or {}).get('requirement'),
                 'source_review: text requirement contradicts text_review')
        # Only test recorded fact/route compatibility here. A suggestion is not
        # approval and its absent case comparison is not a satisfied review.
        structure_ready = proposal['proposed_route'] != 'unresolved' and (
            proposal['proposed_route'] == figure['decision']['route'])
    return snapshot, _issues(figure["author_issues"], snapshot), text_ready, structure_ready


def _check_history(manifest, previous):
    """Previous records are optional; when supplied, no silent history loss."""
    validate_manifest(previous)
    current = {f["id"]: f for f in manifest["figures"]}
    for old in previous["figures"]:
        _require(old["id"] in current, "history: figure removed")
        new = current[old["id"]]
        _require(new["decision"]["proposed"] == old["decision"]["proposed"], "history: proposal rewritten")
        count = len(old["decision"]["overrides"])
        _require(new["decision"]["overrides"][:count] == old["decision"]["overrides"], "history: overrides rewritten")
        issues = {issue["id"]: issue for issue in new["author_issues"]}
        for issue in old["author_issues"]:
            _require(issue["id"] in issues, "history: author issue removed")
            for key in ("kind", "source_id", "source_sha256", "location", "original_text"):
                _require(issues[issue["id"]][key] == issue[key], "history: original author issue rewritten")


def _live_hashes(manifest, expected):
    if manifest is None:
        return None
    _object(manifest, ("files",), where="input manifest")
    files = _unique(_rows(manifest["files"], "input files", nonempty=True), "input files")
    _require(set(files) == set(expected), "input manifest: source IDs must match decision scope exactly")
    actual = {}
    for key, item in files.items():
        _object(item, ("id", "path"), where="input file")
        _text(item["path"], "input file.path")
        try:
            digest = hashlib.sha256()
            with Path(item["path"]).open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual[key] = digest.hexdigest()
        except OSError as exc:
            raise ContractError(f"input file {key}: cannot read source ({type(exc).__name__})") from exc
    return actual


def validate_manifest(manifest, input_manifest=None, *, previous=None):
    """Return a fresh, JSON-serializable report; never modify any supplied record.

    Invalid records raise ContractError. Valid but incomplete/stale records return
    blocking gates. With no live input manifest, processing is never ready.
    `previous` enables append-only proposal/override and original-issue checks.
    """
    _object(manifest, ("schema_version", "figures"), where="manifest")
    _require(manifest["schema_version"] == SCHEMA_VERSION, "manifest: unsupported schema version")
    figures = _unique(_rows(manifest["figures"], "figures", nonempty=True), "figures")
    snapshots, issues, expected, text_ready, structure_ready = {}, {}, {}, {}, {}
    for key, figure in figures.items():
        snapshots[key], issues[key], text_ready[key], structure_ready[key] = _figure(figure)
        for source_id, digest in snapshots[key].items():
            _require(source_id not in expected or expected[source_id] == digest,
                     "manifest: conflicting hashes for shared source ID")
            expected[source_id] = digest
    if previous is not None:
        _check_history(manifest, previous)
    actual = _live_hashes(input_manifest, expected)
    report = []
    for key, figure in figures.items():
        decision = figure["decision"]
        gates = []

        def gate(name, passed, reason):
            gates.append({"id": name, "status": "pass" if passed else "blocked", "reason": reason})

        gate("source_current", actual is not None and all(actual[k] == v for k, v in snapshots[key].items()),
             "Live source hashes must match every source bound to this figure.")
        gate("route_resolved", decision["route"] != "unresolved", "An explicit supported route is required.")
        gate("column_resolved", decision["column"] != "unresolved", "An explicit column decision is required.")
        gate("text_treatment", text_ready[key],
             "Requires source-bound text-needs review; missing/unknown needs or replacement on a grayscale-only route block processing. Recorded findings are not independently verified.")
        gate("structure_treatment", structure_ready[key],
             "Requires source-bound joint structure/text/data/topology facts compatible with the chosen route; source file format is not figure structure.")
        for name in COMMON_CHECKS + ROUTE_CHECKS[decision["route"]]:
            gate(name, figure["checks"].get(name, {}).get("status") == "recorded_satisfied",
                 "Requires a source-bound recorded review; this validator does not independently verify its finding.")
        gate("author_issues", not issues[key], "Blocking issues: " + ", ".join(issues[key]) if issues[key]
             else "No blocking recorded issue; preserved unresolved author text is not a scientific correctness pass.")
        report.append({"id": key, "record": copy.deepcopy(figure), "gates": gates,
                       "ready_for_processing": all(g["status"] == "pass" for g in gates),
                       "ready_for_publication": False})
    return {"schema_version": SCHEMA_VERSION, "validation_scope": "decision_contract_only",
            "source_snapshot": expected, "observed_source_snapshot": actual,
            "provenance_authenticated": False, "user_provenance_authenticated": False,
            "semantics_independently_verified": False,
            "ready_for_processing": all(f["ready_for_processing"] for f in report),
            "ready_for_publication": False, "publication_performed": False, "figures": report}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("decisions")
    parser.add_argument("--manifest", help="Current local input files for source hash verification")
    parser.add_argument("--previous", help="Previous decision manifest for append-only history checks")
    parser.add_argument("--out", required=True, help="New report file; existing files are never overwritten")
    args = parser.parse_args(argv)
    try:
        def unique_keys(pairs):
            result = {}
            for key, value in pairs:
                _require(key not in result, f"JSON: duplicate object key {key}")
                result[key] = value
            return result

        def load(path):
            return json.loads(Path(path).read_text(encoding="utf-8-sig"),
                              object_pairs_hook=unique_keys) if path else None

        report = validate_manifest(load(args.decisions), load(args.manifest), previous=load(args.previous))
        with Path(args.out).open("x", encoding="utf-8") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (ContractError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0 if report["ready_for_processing"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
