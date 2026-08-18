from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable

from .contradiction import identity_key
from .candidate_detection import structured_assertion_side


class FilterDecision(str, Enum):
    KEEP = "keep"
    MERGE = "merge"
    DROP = "drop"
    QUARANTINE = "quarantine"
    CONTRADICTION = "contradiction"
    REFERENCE_ONLY = "reference-only"


def stable_fingerprint(value: Any) -> str:
    """Return a deterministic content fingerprint for exact de-duplication.

    This deliberately performs no semantic normalization. It is safe to use as merge
    authority because equal fingerprints mean equal deterministic JSON representations.
    """
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass
class FilterStats:
    input_items: int = 0
    kept_items: int = 0
    merged_items: int = 0
    dropped_items: int = 0
    quarantined_items: int = 0
    reference_only_items: int = 0
    contradiction_items: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def record(self, decision: FilterDecision, reason: str, count: int = 1) -> None:
        n = max(0, int(count))
        self.input_items += n
        if decision == FilterDecision.KEEP:
            self.kept_items += n
        elif decision == FilterDecision.MERGE:
            self.merged_items += n
        elif decision == FilterDecision.DROP:
            self.dropped_items += n
        elif decision == FilterDecision.QUARANTINE:
            self.quarantined_items += n
        elif decision == FilterDecision.REFERENCE_ONLY:
            self.reference_only_items += n
        elif decision == FilterDecision.CONTRADICTION:
            self.contradiction_items += n
        self.reasons[reason] = self.reasons.get(reason, 0) + n

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept": self.kept_items,
            "merged": self.merged_items,
            "dropped": self.dropped_items,
            "quarantined": self.quarantined_items,
            "reference_only": self.reference_only_items,
            "contradictions": self.contradiction_items,
            "reason_counts": dict(sorted(self.reasons.items())),
        }


def _deduplicate_list(items: list[Any]) -> tuple[list[Any], int]:
    out: list[Any] = []
    seen: set[str] = set()
    removed = 0
    for item in items:
        key = stable_fingerprint(item)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        out.append(item)
    return out, removed


def deduplicate_exact_list(value: Any) -> tuple[Any, int]:
    """Deduplicate one list level by exact JSON equality; nested sequences are untouched."""
    if not isinstance(value, list):
        return value, 0
    return _deduplicate_list(value)


def deduplicate_recursive(value: Any) -> tuple[Any, dict[str, int]]:
    """Recursively remove exact duplicate list entries while preserving order.

    Dict keys are never deduplicated across one another because equal values in distinct
    fields can have distinct semantics. This is intentionally exact-only and therefore
    safe for handoff compaction.
    """
    stats = {"lists_seen": 0, "items_removed": 0}

    def visit(item: Any) -> Any:
        if isinstance(item, dict):
            return {str(k): visit(v) for k, v in item.items()}
        if isinstance(item, list):
            stats["lists_seen"] += 1
            nested = [visit(v) for v in item]
            unique, removed = _deduplicate_list(nested)
            stats["items_removed"] += removed
            return unique
        return item

    return visit(value), stats


def _reducer_meta(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("reducer")
    return value if isinstance(value, dict) else {}


def _best_finding(items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(items)
    if not rows:
        return {}
    return min(
        rows,
        key=lambda item: (
            -float(item.get("confidence", 0.5)),
            str(item.get("claim", "")),
            str(item.get("source", "")),
        ),
    )


def _unique_json_objects(values: Iterable[Any]) -> list[Any]:
    seen: set[str] = set()
    out: list[Any] = []
    for value in values:
        if value is None:
            continue
        key = stable_fingerprint(value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def apply_verified_candidate_merges(
    findings: list[dict[str, Any]],
    candidate_analysis: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Apply deterministic-verifier-authorized merges with component safety checks.

    Pair-wise verification is necessary but not sufficient: transitive union can otherwise
    let an identity-less bridge join two incompatible facts. Every union therefore also
    proves that the *whole resulting component* has at most one deterministic identity and
    one structured assertion side. Contradiction candidates always remain separate.
    """
    n = len(findings)
    if n <= 1 or not isinstance(candidate_analysis, dict):
        return list(findings), {
            "authorized_candidate_pairs": 0,
            "verified_merges_applied": 0,
            "components_merged": 0,
            "component_conflict_pairs_blocked": 0,
            "ambiguous_bridge_pairs_blocked": 0,
            "blocked_pair_reasons": {},
            "output_findings": n,
        }

    parent = list(range(n))
    members: dict[int, set[int]] = {i: {i} for i in range(n)}
    identities: dict[int, set[str]] = {
        i: ({identity_key(findings[i])} if identity_key(findings[i]) else set()) for i in range(n)
    }
    assertion_sides: dict[int, set[tuple[Any, ...]]] = {
        i: ({structured_assertion_side(findings[i])} if structured_assertion_side(findings[i]) is not None else set())
        for i in range(n)
    }

    # Validate and collect pair-wise authorized edges first. The complete graph is needed
    # to detect identity-less bridges that are ambiguous *before* pair-order can assign
    # them to one side arbitrarily.
    authorized_edges: list[tuple[int, int]] = []
    for row in candidate_analysis.get("pairs") or []:
        if not isinstance(row, dict):
            continue
        verification = row.get("verification") if isinstance(row.get("verification"), dict) else {}
        if verification.get("merge_authorized") is not True:
            continue
        left, right = row.get("left_index"), row.get("right_index")
        if not isinstance(left, int) or not isinstance(right, int):
            continue
        if left < 0 or right < 0 or left >= n or right >= n or left == right:
            continue
        authorized_edges.append((left, right))

    raw_parent = list(range(n))
    def raw_find(x: int) -> int:
        while raw_parent[x] != x:
            raw_parent[x] = raw_parent[raw_parent[x]]
            x = raw_parent[x]
        return x
    def raw_union(a: int, b: int) -> None:
        ra, rb = raw_find(a), raw_find(b)
        if ra != rb:
            if rb < ra:
                ra, rb = rb, ra
            raw_parent[rb] = ra
    for left, right in authorized_edges:
        raw_union(left, right)
    raw_ids: dict[int, set[str]] = {}
    raw_sides: dict[int, set[tuple[Any, ...]]] = {}
    for i in range(n):
        root = raw_find(i)
        if identity_key(findings[i]):
            raw_ids.setdefault(root, set()).add(identity_key(findings[i]))
        side = structured_assertion_side(findings[i])
        if side is not None:
            raw_sides.setdefault(root, set()).add(side)

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def compatible_components(ra: int, rb: int, left: int, right: int) -> tuple[bool, str | None]:
        left_ids, right_ids = identities.get(ra, set()), identities.get(rb, set())
        left_sides, right_sides = assertion_sides.get(ra, set()), assertion_sides.get(rb, set())
        if len(left_ids | right_ids) > 1:
            return False, "component-conflicting-identity"
        if len(left_sides | right_sides) > 1:
            return False, "component-conflicting-assertion"

        raw_root = raw_find(left)
        # If the pair-wise-authorized connected candidate graph reaches multiple explicit
        # identities/sides, an unstructured component is ambiguous. Do not let it attach
        # to whichever side happens to be processed first.
        if len(raw_ids.get(raw_root, set())) > 1 and (not left_ids or not right_ids) and (left_ids or right_ids):
            return False, "ambiguous-identity-bridge"
        if len(raw_sides.get(raw_root, set())) > 1 and (not left_sides or not right_sides) and (left_sides or right_sides):
            return False, "ambiguous-assertion-bridge"
        return True, None

    def union(a: int, b: int) -> tuple[bool, str | None]:
        ra, rb = find(a), find(b)
        if ra == rb:
            return True, None
        compatible, reason = compatible_components(ra, rb, a, b)
        if not compatible:
            return False, reason
        if rb < ra:
            ra, rb = rb, ra
        parent[rb] = ra
        members[ra] = members.get(ra, {ra}) | members.pop(rb, {rb})
        identities[ra] = identities.get(ra, set()) | identities.pop(rb, set())
        assertion_sides[ra] = assertion_sides.get(ra, set()) | assertion_sides.pop(rb, set())
        return True, None

    authorized_pairs = len(authorized_edges)
    blocked_component_conflicts = 0
    blocked_ambiguous_bridges = 0
    blocked_reasons: dict[str, int] = {}
    for left, right in authorized_edges:
        merged, reason = union(left, right)
        if merged:
            continue
        blocked_component_conflicts += 1
        if reason and reason.startswith("ambiguous-"):
            blocked_ambiguous_bridges += 1
        if reason:
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1

    components: dict[int, list[int]] = {}
    for i in range(n):
        components.setdefault(find(i), []).append(i)

    out: list[dict[str, Any]] = []
    merges_applied = 0
    components_merged = 0
    for indices in sorted(components.values(), key=lambda xs: min(xs)):
        if len(indices) == 1:
            out.append(dict(findings[indices[0]]))
            continue
        components_merged += 1
        merges_applied += len(indices) - 1
        component_members = [findings[i] for i in indices]
        best = dict(_best_finding(component_members))
        workers: set[str] = set()
        sources: set[str] = set()
        group_keys: set[str] = set()
        assertion_keys: list[Any] = []
        occurrence_count = 0
        provenance_values: list[Any] = []
        evidence_refs: list[Any] = []
        ambiguous_unstructured = False
        claim_variants: list[Any] = []
        for item in component_members:
            meta = _reducer_meta(item)
            occurrence_count += int(meta.get("occurrence_count", meta.get("agreement_count", 1)) or 1)
            workers.update(str(x) for x in (meta.get("supporting_workers") or []) if str(x))
            sources.update(str(x) for x in (meta.get("supporting_sources") or []) if str(x))
            if meta.get("group_key"):
                group_keys.add(str(meta["group_key"]))
            if meta.get("assertion_key") is not None:
                assertion_keys.append(meta.get("assertion_key"))
            provenance_values.extend(meta.get("supporting_provenance") or [])
            evidence_refs.extend(meta.get("supporting_evidence_refs") or [])
            if meta.get("ambiguous_unstructured_canonical"):
                ambiguous_unstructured = True
                claim_variants.extend(meta.get("claim_variants") or [])
            if item.get("provenance") is not None:
                provenance_values.append(item.get("provenance"))
        # Preserve unambiguous machine identity/assertion fields even when the highest-
        # confidence representative came from an identity-less duplicate. This prevents
        # deduplication itself from destroying future contradiction/dedup authority.
        promoted_fields: list[str] = []
        identity_member = next((item for item in component_members if identity_key(item)), None)
        if identity_member is not None:
            canonical = identity_member.get("canonicalKey") or identity_member.get("canonical_key")
            if canonical and not (best.get("canonicalKey") or best.get("canonical_key")):
                best["canonicalKey"] = canonical
                promoted_fields.append("canonicalKey")
            elif not canonical:
                for field in ("subject", "predicate", "period", "unit"):
                    if best.get(field) in (None, "") and identity_member.get(field) not in (None, ""):
                        best[field] = identity_member.get(field)
                        promoted_fields.append(field)
        side_member = next((item for item in component_members if structured_assertion_side(item) is not None), None)
        if side_member is not None:
            for field in ("polarity", "value", "unit"):
                if best.get(field) in (None, "") and side_member.get(field) not in (None, ""):
                    best[field] = side_member.get(field)
                    if field not in promoted_fields:
                        promoted_fields.append(field)

        best_meta = dict(_reducer_meta(best))
        best_meta.update({
            "occurrence_count": occurrence_count,
            "agreement_count": len(workers) if workers else 1,
            "independent_source_count": len(sources),
            "supporting_workers": sorted(workers),
            "supporting_sources": sorted(sources),
            "merged_group_keys": sorted(group_keys),
            "candidate_verified_merge": True,
            "candidate_component_size": len(indices),
        })
        if promoted_fields:
            best_meta["identity_assertion_fields_promoted"] = promoted_fields
        if ambiguous_unstructured:
            best_meta["ambiguous_unstructured_canonical"] = True
            best_meta["claim_variants"] = _unique_json_objects(claim_variants)
            best_meta["ambiguity_note"] = "canonicalKey grouped differently worded unstructured claims; add value/polarity for assertion-safe contradiction handling"
        if assertion_keys:
            best_meta["merged_assertion_keys"] = _unique_json_objects(assertion_keys)
        refs = _unique_json_objects(evidence_refs)
        if refs:
            best_meta["supporting_evidence_refs"] = refs
            best_meta["independent_evidence_count"] = len(refs)
        prov = _unique_json_objects(provenance_values)
        if prov:
            best_meta["supporting_provenance"] = prov
        best["reducer"] = best_meta
        out.append(best)

    out.sort(key=lambda item: (
        -float(item.get("confidence", 0.5)),
        -int(_reducer_meta(item).get("agreement_count", 1)),
        str(item.get("claim", "")),
    ))
    return out, {
        "authorized_candidate_pairs": authorized_pairs,
        "verified_merges_applied": merges_applied,
        "components_merged": components_merged,
        "component_conflict_pairs_blocked": blocked_component_conflicts,
        "ambiguous_bridge_pairs_blocked": blocked_ambiguous_bridges,
        "blocked_pair_reasons": dict(sorted(blocked_reasons.items())),
        "output_findings": len(out),
    }

