"""Synthetic contracts only: no author gold labels or production assets."""
import copy
import hashlib
import json

import pytest

from journal_preflight.editorial_route import (
    COMMON_CHECKS, ROUTE_CHECKS, SCHEMA_VERSION, ContractError, main, validate_manifest,
)


def contract(tmp_path, route="structural_redraw"):
    source = tmp_path / "source.txt"
    source.write_bytes(b"synthetic source content")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    checks = {name: {"status": "recorded_satisfied", "evidence_ids": ["review-1"]}
              for name in COMMON_CHECKS + ROUTE_CHECKS[route]}
    figure = {
        "id": "figure-example", "sources": [{"id": "source", "sha256": digest}],
        "decision": {"proposed": {"route": route, "column": "single"}, "route": route,
                     "column": "single", "reason": "Synthetic test decision, not a classified real figure.", "overrides": []},
        "evidence": [{"id": "review-1", "source_id": "source", "source_sha256": digest,
                      "method": "synthetic fixture", "location": "whole source",
                      "observation": "A test-only recorded observation."}],
        "checks": checks, "author_issues": [],
    }
    return {"schema_version": SCHEMA_VERSION, "figures": [figure]}, {
        "files": [{"id": "source", "path": str(source)}]}


def provenance(manifest):
    return {"actor": "user", "reference": "message:test-only", "quote": "Keep the original text.",
            "recorded_at": "2026-10-22T09:00:00Z",
            "source_snapshot": {s["id"]: s["sha256"] for s in manifest["figures"][0]["sources"]}}


def author_issue(manifest, disposition="pending"):
    source = manifest["figures"][0]["sources"][0]
    issue = {"id": "text-question", "kind": "author_text", "source_id": source["id"],
             "source_sha256": source["sha256"], "location": "source label",
             "original_text": "x  =  02", "output_text": "x  =  02", "proposed_text": "x = 2",
             "status": "unresolved", "disposition": disposition,
             "reason": "Author text requires review, not silent normalization."}
    if disposition != "pending":
        issue["provenance"] = provenance(manifest)
    manifest["figures"][0]["author_issues"].append(issue)
    return issue


def gates(report):
    return {g["id"]: g["status"] for g in report["figures"][0]["gates"]}


@pytest.mark.parametrize("route", ["structural_redraw", "plot_reletter", "raster_grayscale_single_column"])
def test_supported_decision_contract_not_publication_or_semantic_certification(tmp_path, route):
    manifest, live = contract(tmp_path, route)
    before = copy.deepcopy(manifest)
    report = validate_manifest(manifest, live)
    assert report["ready_for_processing"]
    assert report["validation_scope"] == "decision_contract_only"
    assert not report["ready_for_publication"]
    assert not report["publication_performed"]
    assert not report["semantics_independently_verified"]
    assert not report["user_provenance_authenticated"]
    assert manifest == before
    report["figures"][0]["record"]["decision"]["reason"] = "changed copy"
    assert manifest == before


def test_source_files_not_modified(tmp_path):
    manifest, live = contract(tmp_path)
    before = (tmp_path / "source.txt").read_bytes()
    validate_manifest(manifest, live)
    assert (tmp_path / "source.txt").read_bytes() == before


@pytest.mark.parametrize("live_state", ["missing", "changed"])
def test_live_sources_required_not_matching_saved_jsons(tmp_path, live_state):
    manifest, live = contract(tmp_path)
    if live_state == "missing":
        live = None
    else:
        (tmp_path / "source.txt").write_bytes(b"a different current source")
    report = validate_manifest(manifest, live)
    assert not report["ready_for_processing"]
    assert gates(report)["source_current"] == "blocked"


def test_unresolved_route_is_valid_but_never_ready(tmp_path):
    manifest, live = contract(tmp_path, "unresolved")
    report = validate_manifest(manifest, live)
    assert not report["ready_for_processing"]
    assert gates(report)["route_resolved"] == "blocked"


@pytest.mark.parametrize("route", ROUTE_CHECKS)
def test_route_label_without_review_is_not_enough(tmp_path, route):
    manifest, live = contract(tmp_path, route)
    manifest["figures"][0]["checks"] = {}
    report = validate_manifest(manifest, live)
    assert not report["ready_for_processing"]
    assert gates(report)["source_identity"] == "blocked"


@pytest.mark.parametrize("route,missing", [(r, c) for r, checks in ROUTE_CHECKS.items() for c in checks])
def test_missing_route_specific_review_blocks_processing(tmp_path, route, missing):
    manifest, live = contract(tmp_path, route)
    del manifest["figures"][0]["checks"][missing]
    assert gates(validate_manifest(manifest, live))[missing] == "blocked"


def test_unresolved_author_text_blocks_unless_explicit_preserve_original(tmp_path):
    manifest, live = contract(tmp_path)
    issue = author_issue(manifest)
    assert not validate_manifest(manifest, live)["ready_for_processing"]
    issue.update(disposition="preserve_original", provenance=provenance(manifest))
    report = validate_manifest(manifest, live)
    assert report["ready_for_processing"]
    assert report["figures"][0]["record"]["author_issues"][0]["status"] == "unresolved"
    assert report["figures"][0]["record"]["author_issues"][0]["original_text"] == "x  =  02"
    assert not report["semantics_independently_verified"]


def test_preserve_original_does_not_waive_source_conflict(tmp_path):
    manifest, live = contract(tmp_path)
    author_issue(manifest, "preserve_original")["kind"] = "source_conflict"
    assert not validate_manifest(manifest, live)["ready_for_processing"]


def test_reviewer_may_explicitly_preserve_original_without_resolving_text(tmp_path):
    manifest, live = contract(tmp_path)
    issue = author_issue(manifest, "preserve_original")
    issue["provenance"].update(actor="reviewer", reference="review:test-only",
                                quote="Preserve unchanged author text and retain the question for review.")
    report = validate_manifest(manifest, live)
    assert report["ready_for_processing"]
    assert not report["provenance_authenticated"]
    assert report["figures"][0]["record"]["author_issues"][0]["status"] == "unresolved"


def test_reviewer_cannot_authorize_text_correction(tmp_path):
    manifest, live = contract(tmp_path)
    issue = author_issue(manifest, "approved_correction")
    issue.update(status="resolved", output_text=issue["proposed_text"])
    issue["provenance"]["actor"] = "reviewer"
    with pytest.raises(ContractError, match="actor"):
        validate_manifest(manifest, live)


def test_reviewer_cannot_impersonate_user_override(tmp_path):
    manifest, live = contract(tmp_path)
    decision = manifest["figures"][0]["decision"]
    decision["column"] = "double"
    decision["overrides"] = [{"id": "override-1", "field": "column", "previous_value": "single",
                               "value": "double", "provenance": provenance(manifest)}]
    decision["overrides"][0]["provenance"]["actor"] = "reviewer"
    with pytest.raises(ContractError, match="actor"):
        validate_manifest(manifest, live)


def test_explicit_correction_keeps_original_and_records_exact_output(tmp_path):
    manifest, live = contract(tmp_path)
    issue = author_issue(manifest, "approved_correction")
    issue.update(status="resolved", output_text=issue["proposed_text"])
    issue["provenance"]["quote"] = "Change x  =  02 to x = 2."
    report = validate_manifest(manifest, live)
    assert report["ready_for_processing"]
    assert report["figures"][0]["record"]["author_issues"][0]["original_text"] == "x  =  02"
    issue["output_text"] = "x = 3"
    with pytest.raises(ContractError, match="approved correction"):
        validate_manifest(manifest, live)


@pytest.mark.parametrize("disposition", ["pending", "preserve_original"])
def test_silent_normalization_rejected(tmp_path, disposition):
    manifest, live = contract(tmp_path)
    issue = author_issue(manifest, disposition)
    issue["output_text"] = "x = 02"
    with pytest.raises(ContractError, match="silent text correction"):
        validate_manifest(manifest, live)


def test_override_requires_provenance_preserves_proposal(tmp_path):
    manifest, live = contract(tmp_path)
    decision = manifest["figures"][0]["decision"]
    decision["column"] = "double"
    with pytest.raises(ContractError, match="override provenance"):
        validate_manifest(manifest, live)
    decision["overrides"] = [{"id": "override-1", "field": "column", "previous_value": "single",
                               "value": "double", "provenance": provenance(manifest)}]
    decision["overrides"][0]["provenance"]["quote"] = "Use double column for this figure."
    result = validate_manifest(manifest, live)
    assert result["ready_for_processing"]
    assert result["figures"][0]["record"]["decision"]["proposed"]["column"] == "single"
    decision["overrides"][0]["previous_value"] = "double"
    with pytest.raises(ContractError, match="history"):
        validate_manifest(manifest, live)


@pytest.mark.parametrize("change", ["missing", "not_user", "no_reference", "stale", "no_timezone"])
def test_preserve_original_provenance_is_explicit_and_source_bound(tmp_path, change):
    manifest, live = contract(tmp_path)
    issue = author_issue(manifest, "preserve_original")
    if change == "missing":
        del issue["provenance"]
    elif change == "not_user":
        issue["provenance"]["actor"] = "agent"
    elif change == "no_reference":
        issue["provenance"]["reference"] = " "
    elif change == "stale":
        issue["provenance"]["source_snapshot"]["source"] = "0" * 64
    else:
        issue["provenance"]["recorded_at"] = "2026-10-22T09:00:00"
    with pytest.raises(ContractError):
        validate_manifest(manifest, live)


@pytest.mark.parametrize("change", ["unknown_route", "unknown_field", "fake_ready", "empty_evidence",
                                  "unknown_evidence", "stale_evidence", "duplicate_id", "bad_hash",
                                  "string_status", "bad_issues", "empty_figures", "raster_double"])
def test_invalid_records_cannot_claim_readiness(tmp_path, change):
    manifest, live = contract(tmp_path)
    figure = manifest["figures"][0]
    if change == "unknown_route":
        figure["decision"]["route"] = "automatic_best_guess"
    elif change == "unknown_field":
        figure["author_issues"] = [{"id": "bad", "blocks_readiness": False}]
    elif change == "fake_ready":
        figure["ready_for_processing"] = True
    elif change == "empty_evidence":
        figure["checks"]["source_identity"]["evidence_ids"] = []
    elif change == "unknown_evidence":
        figure["checks"]["source_identity"]["evidence_ids"] = ["made-up"]
    elif change == "stale_evidence":
        figure["evidence"][0]["source_sha256"] = "0" * 64
    elif change == "duplicate_id":
        manifest["figures"].append(copy.deepcopy(figure))
    elif change == "bad_hash":
        figure["sources"][0]["sha256"] = "source-hash"
    elif change == "string_status":
        figure["checks"]["source_identity"]["status"] = True
    elif change == "bad_issues":
        figure["author_issues"] = None
    elif change == "empty_figures":
        manifest["figures"] = []
    else:
        figure["decision"].update(route="raster_grayscale_single_column", column="double",
                                  proposed={"route": "raster_grayscale_single_column", "column": "double"})
    with pytest.raises(ContractError):
        validate_manifest(manifest, live)


def test_source_identity_requires_all_declared_sources(tmp_path):
    manifest, live = contract(tmp_path)
    figure = manifest["figures"][0]
    figure["sources"].append({"id": "word", "sha256": "b" * 64})
    with pytest.raises(ContractError, match="every source"):
        validate_manifest(manifest, live)


@pytest.mark.parametrize("change", ["extra", "missing", "duplicate", "unreadable"])
def test_live_source_scope_is_exact_and_readable(tmp_path, change):
    manifest, live = contract(tmp_path)
    if change == "extra":
        live["files"].append({"id": "extra", "path": str(tmp_path / "source.txt")})
    elif change == "missing":
        live["files"] = []
    elif change == "duplicate":
        live["files"].append(copy.deepcopy(live["files"][0]))
    else:
        live["files"][0]["path"] = str(tmp_path / "missing.txt")
    with pytest.raises(ContractError):
        validate_manifest(manifest, live)


def test_per_figure_source_staleness_and_shared_hash_conflict(tmp_path):
    manifest, live = contract(tmp_path)
    second = copy.deepcopy(manifest["figures"][0])
    second["id"] = "second"
    manifest["figures"].append(second)
    assert len(validate_manifest(manifest, live)["figures"]) == 2
    second["sources"][0]["sha256"] = second["evidence"][0]["source_sha256"] = "0" * 64
    with pytest.raises(ContractError, match="conflicting hashes"):
        validate_manifest(manifest, live)


@pytest.mark.parametrize("change", ["original", "remove_issue", "proposal", "remove_figure"])
def test_previous_manifest_protects_originals_and_ledger(tmp_path, change):
    manifest, live = contract(tmp_path)
    author_issue(manifest, "preserve_original")
    previous = copy.deepcopy(manifest)
    figure = manifest["figures"][0]
    if change == "original":
        figure["author_issues"][0].update(original_text="changed", output_text="changed")
    elif change == "remove_issue":
        figure["author_issues"] = []
    elif change == "proposal":
        figure["decision"]["proposed"]["column"] = figure["decision"]["column"] = "double"
    else:
        figure["id"] = "different"
    with pytest.raises(ContractError, match="history"):
        validate_manifest(manifest, live, previous=previous)


def test_previous_override_history_is_append_only(tmp_path):
    manifest, live = contract(tmp_path)
    decision = manifest["figures"][0]["decision"]
    decision["column"] = "double"
    decision["overrides"] = [{"id": "override-1", "field": "column", "previous_value": "single",
                               "value": "double", "provenance": provenance(manifest)}]
    previous = copy.deepcopy(manifest)
    assert validate_manifest(manifest, live, previous=previous)["ready_for_processing"]
    decision["overrides"][0]["provenance"]["quote"] = "rewritten history"
    with pytest.raises(ContractError, match="overrides rewritten"):
        validate_manifest(manifest, live, previous=previous)


def test_cli_reports_blocked_and_does_not_overwrite(tmp_path):
    manifest, live = contract(tmp_path)
    decisions = tmp_path / "decisions.json"
    inputs = tmp_path / "inputs.json"
    output = tmp_path / "report.json"
    decisions.write_text(json.dumps(manifest))
    inputs.write_text(json.dumps(live))
    assert main([str(decisions), "--out", str(output)]) == 2
    report = json.loads(output.read_text())
    assert not report["ready_for_processing"]
    before = output.read_bytes()
    with pytest.raises(SystemExit):
        main([str(decisions), "--manifest", str(inputs), "--out", str(output)])
    assert output.read_bytes() == before
    output = tmp_path / "verified.json"
    assert main([str(decisions), "--manifest", str(inputs), "--out", str(output)]) == 0


def test_cli_rejects_duplicate_json_keys_without_report(tmp_path):
    decisions = tmp_path / "ambiguous.json"
    output = tmp_path / "report.json"
    decisions.write_text('{"schema_version":"editorial-route/1","figures":[],"figures":[]}')
    with pytest.raises(SystemExit):
        main([str(decisions), "--out", str(output)])
    assert not output.exists()


def test_unresolved_column_blocks_even_with_recorded_route_checks(tmp_path):
    manifest, live = contract(tmp_path)
    decision = manifest["figures"][0]["decision"]
    decision["column"] = decision["proposed"]["column"] = "unresolved"
    report = validate_manifest(manifest, live)
    assert not report["ready_for_processing"]
    assert gates(report)["column_resolved"] == "blocked"
