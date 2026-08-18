from __future__ import annotations

from typing import Any

from .contradiction import comparable_assertion_value, normalize_identity_text


SCHEMA = "repo-context-filter-audit/v1"


def audit_filter_reduction(reduction: dict[str, Any]) -> dict[str, Any]:
    """Check reducer invariants without using model judgment.

    This is an internal consistency gate, not an external correctness proof. It verifies
    that support counts, duplicate accounting, contradiction counts, and merge authority
    metadata are self-consistent after filtering.
    """
    violations: list[str] = []
    warnings: list[str] = []
    if not isinstance(reduction, dict):
        return {
            "schema": SCHEMA,
            "classification": "deterministic-filter-invariant-audit",
            "passed": False,
            "violations": ["reduction must be an object"],
            "warnings": [],
            "metrics": {},
        }

    findings = reduction.get("findings") if isinstance(reduction.get("findings"), list) else []
    contradictions = reduction.get("contradictions") if isinstance(reduction.get("contradictions"), list) else []
    stats = reduction.get("stats") if isinstance(reduction.get("stats"), dict) else {}
    provenance = reduction.get("provenance") if isinstance(reduction.get("provenance"), dict) else {}

    observed_agreement_groups = 0
    observed_max_agreement = 0
    ambiguous_groups = 0
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            violations.append(f"findings[{index}] must be an object")
            continue
        reducer = finding.get("reducer") if isinstance(finding.get("reducer"), dict) else {}
        workers = [str(x) for x in (reducer.get("supporting_workers") or []) if str(x)]
        sources = [str(x) for x in (reducer.get("supporting_sources") or []) if str(x)]
        agreement = int(reducer.get("agreement_count", 1) or 1)
        occurrence = int(reducer.get("occurrence_count", agreement) or agreement)
        source_count = int(reducer.get("independent_source_count", len(set(sources))) or 0)
        evidence_refs = reducer.get("supporting_evidence_refs") if isinstance(reducer.get("supporting_evidence_refs"), list) else []
        evidence_count = int(reducer.get("independent_evidence_count", len(evidence_refs)) or 0)

        if len(workers) != len(set(workers)):
            violations.append(f"findings[{index}] supporting_workers contains duplicates")
        if len(sources) != len(set(sources)):
            violations.append(f"findings[{index}] supporting_sources contains duplicates")
        expected_agreement = len(set(workers)) if workers else 1
        if agreement != expected_agreement:
            violations.append(
                f"findings[{index}] agreement_count={agreement} but unique supporting_workers={expected_agreement}"
            )
        if source_count != len(set(sources)):
            violations.append(
                f"findings[{index}] independent_source_count={source_count} but unique supporting_sources={len(set(sources))}"
            )
        if occurrence < agreement:
            violations.append(f"findings[{index}] occurrence_count cannot be lower than agreement_count")
        if occurrence < source_count:
            violations.append(f"findings[{index}] occurrence_count cannot be lower than independent_source_count")
        unique_evidence_refs = {str(item) for item in evidence_refs}
        if evidence_count != len(unique_evidence_refs):
            violations.append(f"findings[{index}] independent_evidence_count does not match unique supporting_evidence_refs")
        if occurrence < evidence_count:
            violations.append(f"findings[{index}] occurrence_count cannot be lower than independent_evidence_count")
        if reducer.get("ambiguous_unstructured_canonical"):
            ambiguous_groups += 1
            warnings.append(
                f"findings[{index}] canonicalKey grouped multiple unstructured claim variants; add value/polarity for stronger assertion identity"
            )
        if agreement > 1:
            observed_agreement_groups += 1
        observed_max_agreement = max(observed_max_agreement, agreement)

    if "output_finding_count" in stats and int(stats.get("output_finding_count", -1)) != len(findings):
        violations.append("stats.output_finding_count does not match findings length")
    if "contradiction_count" in stats and int(stats.get("contradiction_count", -1)) != len(contradictions):
        violations.append("stats.contradiction_count does not match contradictions length")
    if "agreement_group_count" in stats and int(stats.get("agreement_group_count", -1)) != observed_agreement_groups:
        violations.append("stats.agreement_group_count does not match final findings")
    if "max_agreement_count" in stats and int(stats.get("max_agreement_count", -1)) != observed_max_agreement:
        violations.append("stats.max_agreement_count does not match final findings")

    exact = stats.get("exact_duplicate_count")
    verified = stats.get("verified_candidate_merge_count")
    total = stats.get("duplicate_count")
    if all(isinstance(x, int) for x in (exact, verified, total)) and total != exact + verified:
        violations.append("stats.duplicate_count must equal exact_duplicate_count + verified_candidate_merge_count")

    malformed = reduction.get("malformed") if isinstance(reduction.get("malformed"), list) else []
    if isinstance(stats.get("malformed_count"), int) and stats["malformed_count"] < len(malformed):
        violations.append("stats.malformed_count cannot be lower than retained malformed details")

    filtered = reduction.get("filtered") if isinstance(reduction.get("filtered"), list) else []
    quarantined = reduction.get("quarantined") if isinstance(reduction.get("quarantined"), list) else []
    if isinstance(stats.get("filtered_count"), int) and stats["filtered_count"] < len(filtered) + len(quarantined):
        violations.append("stats.filtered_count cannot be lower than retained filtered+quarantined details")

    if provenance.get("candidate_similarity_merge_authority") is not False:
        violations.append("candidate similarity must never have merge authority")
    if reduction.get("candidate_analysis") and provenance.get("deterministic_verifier_merge_authority") is not True:
        violations.append("candidate merges require deterministic verifier authority")

    candidate_analysis = reduction.get("candidate_analysis") if isinstance(reduction.get("candidate_analysis"), dict) else {}
    merge_application = candidate_analysis.get("merge_application") if isinstance(candidate_analysis.get("merge_application"), dict) else {}
    if merge_application:
        applied = merge_application.get("verified_merges_applied")
        if isinstance(applied, int) and isinstance(stats.get("verified_candidate_merge_count"), int) and applied != stats["verified_candidate_merge_count"]:
            violations.append("candidate merge_application.verified_merges_applied does not match stats")
        authorized = merge_application.get("authorized_candidate_pairs")
        blocked = merge_application.get("component_conflict_pairs_blocked", 0)
        if isinstance(authorized, int) and isinstance(blocked, int) and blocked > authorized:
            violations.append("component_conflict_pairs_blocked cannot exceed authorized_candidate_pairs")
        if isinstance(blocked, int) and blocked > 0:
            warnings.append(f"{blocked} pair-wise authorized merge(s) were blocked by component-level identity/assertion safety")

    filter_summary = reduction.get("filter_summary") if isinstance(reduction.get("filter_summary"), dict) else {}
    summary_pairs = (
        ("filtered", "filtered_count"),
        ("quarantined", "quarantined_count"),
        ("total_duplicates_merged", "duplicate_count"),
        ("contradictions_preserved", "contradiction_count"),
    )
    for summary_key, stats_key in summary_pairs:
        if isinstance(filter_summary.get(summary_key), int) and isinstance(stats.get(stats_key), int) and filter_summary[summary_key] != stats[stats_key]:
            violations.append(f"filter_summary.{summary_key} does not match stats.{stats_key}")

    for index, contradiction in enumerate(contradictions):
        if not isinstance(contradiction, dict):
            violations.append(f"contradictions[{index}] must be an object")
            continue
        claims = contradiction.get("claims") if isinstance(contradiction.get("claims"), list) else []
        if len(claims) < 2:
            violations.append(f"contradictions[{index}] must retain at least two asserted sides")
        reasons = {str(x) for x in (contradiction.get("reasons") or [])}
        if "value disagreement" in reasons:
            values = {comparable_assertion_value(item.get("value")) for item in claims if isinstance(item, dict) and comparable_assertion_value(item.get("value")) is not None}
            if len(values) < 2:
                violations.append(f"contradictions[{index}] declares value disagreement without two distinct normalized values")
        if "polarity disagreement" in reasons:
            polarities = {normalize_identity_text(item.get("polarity")) for item in claims if isinstance(item, dict) and normalize_identity_text(item.get("polarity"))}
            if len(polarities) < 2:
                violations.append(f"contradictions[{index}] declares polarity disagreement without two distinct polarities")

    stat_ambiguous = stats.get("ambiguous_unstructured_canonical_group_count")
    if isinstance(stat_ambiguous, int) and stat_ambiguous != ambiguous_groups:
        violations.append("stats.ambiguous_unstructured_canonical_group_count does not match final findings")

    return {
        "schema": SCHEMA,
        "classification": "deterministic-filter-invariant-audit",
        "passed": not violations,
        "violations": violations,
        "warnings": warnings,
        "metrics": {
            "findings": len(findings),
            "contradictions": len(contradictions),
            "agreement_groups": observed_agreement_groups,
            "max_agreement": observed_max_agreement,
            "ambiguous_unstructured_canonical_groups": ambiguous_groups,
            "filtered_details": len(filtered),
            "quarantined_details": len(quarantined),
        },
        "scope_note": "Internal consistency only; this does not prove semantic truth or final-model correctness.",
    }
