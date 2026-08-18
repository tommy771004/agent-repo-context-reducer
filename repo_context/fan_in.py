from __future__ import annotations

import hashlib
from typing import Any, Iterable

from .candidate_detection import analyze_candidates
from .contradiction import canonical_group_key, detect_contradictions, normalize_identity_text
from .filter_engine import apply_verified_candidate_merges, stable_fingerprint
from .tokenizer import count_tokens, get_tokenizer
from .trust_boundary import classify_untrusted_text


SCHEMA = "repo-context-fan-in/v1"
TRUST_POLICIES = {"keep", "quarantine-high", "drop-high"}
UNSTRUCTURED_CANONICAL_POLICIES = {"exact-claim", "legacy-merge"}


def _clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _confidence(value: Any) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return 0.5
    return n if 0.0 <= n <= 1.0 else 0.5


def _worker_name(payload: dict[str, Any], index: int) -> str:
    for key in ("worker_id", "worker", "producer", "agent", "from", "role"):
        value = _clean(payload.get(key))
        if value:
            return value
    if isinstance(payload.get("provenance"), dict):
        value = _clean(payload["provenance"].get("worker") or payload["provenance"].get("producer"))
        if value:
            return value
    return f"worker-{index + 1}"


def _candidate_items(payload: Any) -> list[Any]:
    if not isinstance(payload, dict):
        return [payload]

    handoff = payload.get("handoff")
    if isinstance(handoff, dict):
        for key in ("findings", "evidence", "facts"):
            if isinstance(handoff.get(key), list):
                return list(handoff[key])

    for key in ("findings", "evidence", "facts"):
        if isinstance(payload.get(key), list):
            return list(payload[key])

    if any(key in payload for key in ("claim", "evidence", "source")):
        return [payload]
    return []


def _normalize_finding(
    raw: Any,
    *,
    worker: str,
    worker_index: int,
    item_index: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None, {
                "worker": worker,
                "worker_index": worker_index,
                "item_index": item_index,
                "reason": "empty evidence string",
                "finding": raw,
            }
        return {
            "claim": text,
            "evidence": text,
            "source": f"worker:{worker}",
            "source_kind": "worker-handoff",
            "confidence": 0.5,
            "_worker": worker,
            "trust": classify_untrusted_text(text, source=f"worker:{worker}"),
        }, None

    if not isinstance(raw, dict):
        return None, {
            "worker": worker,
            "worker_index": worker_index,
            "item_index": item_index,
            "reason": "finding must be an object or non-empty string",
            "finding": raw,
        }

    claim = _clean(raw.get("claim") or raw.get("summary") or raw.get("fact"))
    evidence = _clean(raw.get("evidence") or raw.get("detail") or raw.get("support"))
    source = _clean(raw.get("source") or raw.get("path") or raw.get("file") or raw.get("url"))

    missing: list[str] = []
    if not claim:
        missing.append("claim")
    if not evidence:
        missing.append("evidence")
    if not source:
        missing.append("source")
    if missing:
        return None, {
            "worker": worker,
            "worker_index": worker_index,
            "item_index": item_index,
            "reason": f"missing required field(s): {', '.join(missing)}",
            "finding": raw,
        }

    finding = {
        **raw,
        "claim": claim,
        "evidence": evidence,
        "source": source,
        "confidence": _confidence(raw.get("confidence")),
        "_worker": worker,
        "trust": classify_untrusted_text(f"{claim}\n{evidence}", source=f"worker:{worker}"),
    }
    canonical = _clean(raw.get("canonicalKey") or raw.get("canonical_key"))
    if canonical:
        finding["canonicalKey"] = canonical
    return finding, None


def _scalar_assertion_value(value: Any) -> tuple[str, Any] | None:
    if isinstance(value, bool):
        return ("bool", value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if number != number or number in {float("inf"), float("-inf")}:
            return None
        return ("number", int(number) if number.is_integer() else number)
    if isinstance(value, str) and value.strip():
        return ("string", normalize_identity_text(value))
    return None


def _assertion_signature(item: dict[str, Any], *, unstructured_canonical_policy: str = "exact-claim") -> tuple[Any, ...]:
    polarity = normalize_identity_text(item.get("polarity"))
    value = _scalar_assertion_value(item.get("value"))
    unit = normalize_identity_text(item.get("unit"))
    if polarity or value is not None:
        return ("structured", polarity or None, value, unit or None)
    canonical = _clean(item.get("canonicalKey") or item.get("canonical_key"))
    if canonical and unstructured_canonical_policy == "exact-claim":
        return ("unstructured-claim", normalize_identity_text(item.get("claim")))
    # Legacy compatibility only: canonicalKey alone acts as assertion grouping authority.
    return ("unstructured",)


def _provenance_values(finding: dict[str, Any]) -> list[Any]:
    value = finding.get("provenance")
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    return [value]


def _evidence_ref(finding: dict[str, Any]) -> dict[str, Any]:
    evidence = _clean(finding.get("evidence"))
    provenance = _provenance_values(finding)
    return {
        "source": _clean(finding.get("source")) or None,
        "evidence_sha256": hashlib.sha256(evidence.encode("utf-8")).hexdigest(),
        "provenance_sha256": stable_fingerprint(provenance) if provenance else None,
    }


class FanInAccumulator:
    """Incrementally filter and reduce worker outputs.

    Memory scales with surviving deterministic groups plus bounded diagnostics. Duplicate
    content is removed, but worker/source/provenance support is aggregated. Similarity may
    propose candidate pairs; only deterministic verification may authorize a second-pass
    merge.
    """

    def __init__(
        self,
        *,
        min_confidence: float = 0.0,
        detect_conflicts: bool = True,
        tokenizer: str = "native",
        tokenizer_model: str | None = None,
        malformed_detail_limit: int | None = None,
        filtered_detail_limit: int | None = None,
        candidate_provider: str | None = "lexical",
        candidate_threshold: float = 0.72,
        max_candidate_pairs: int = 500,
        trust_policy: str = "keep",
        unstructured_canonical_policy: str = "exact-claim",
    ):
        if not 0.0 <= float(min_confidence) <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if malformed_detail_limit is not None and malformed_detail_limit < 0:
            raise ValueError("malformed_detail_limit must be non-negative or None")
        if filtered_detail_limit is not None and filtered_detail_limit < 0:
            raise ValueError("filtered_detail_limit must be non-negative or None")
        trust_policy = str(trust_policy or "keep").strip().lower()
        if trust_policy not in TRUST_POLICIES:
            raise ValueError(f"trust_policy must be one of: {', '.join(sorted(TRUST_POLICIES))}")
        unstructured_canonical_policy = str(unstructured_canonical_policy or "exact-claim").strip().lower()
        if unstructured_canonical_policy not in UNSTRUCTURED_CANONICAL_POLICIES:
            raise ValueError(f"unstructured_canonical_policy must be one of: {', '.join(sorted(UNSTRUCTURED_CANONICAL_POLICIES))}")
        self.min_confidence = float(min_confidence)
        self.detect_conflicts = bool(detect_conflicts)
        self.tokenizer = tokenizer
        self.tokenizer_model = tokenizer_model
        self.malformed_detail_limit = malformed_detail_limit
        self.filtered_detail_limit = filtered_detail_limit
        self.candidate_provider = candidate_provider
        self.candidate_threshold = float(candidate_threshold)
        self.max_candidate_pairs = int(max_candidate_pairs)
        self.trust_policy = trust_policy
        self.unstructured_canonical_policy = unstructured_canonical_policy
        self.worker_output_count = 0
        self.extracted_count = 0
        self.normalized_valid_count = 0
        self.valid_count = 0
        self.malformed_count = 0
        self.filtered_count = 0
        self.quarantined_count = 0
        self.malformed: list[dict[str, Any]] = []
        self.filtered: list[dict[str, Any]] = []
        self.quarantined: list[dict[str, Any]] = []
        self._filtered_reasons: dict[str, int] = {}
        self._groups: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = {}
        self._input_tokens = 0
        self._filtered_tokens = 0
        self._exact_duplicate_tokens = 0
        self._trust_severity = {"none": 0, "low": 0, "medium": 0, "high": 0}
        self._trust_signals: dict[str, int] = {}
        self._peak_group_count = 0

    def _remember_malformed(self, item: dict[str, Any]) -> None:
        self.malformed_count += 1
        if self.malformed_detail_limit is None or len(self.malformed) < self.malformed_detail_limit:
            self.malformed.append(item)

    def _remember_filtered(self, item: dict[str, Any], reason: str, *, quarantine: bool = False) -> None:
        self.filtered_count += 1
        self._filtered_reasons[reason] = self._filtered_reasons.get(reason, 0) + 1
        if quarantine:
            self.quarantined_count += 1
            if self.filtered_detail_limit is None or len(self.quarantined) < self.filtered_detail_limit:
                self.quarantined.append(item)
        elif self.filtered_detail_limit is None or len(self.filtered) < self.filtered_detail_limit:
            self.filtered.append(item)

    def _record_trust(self, finding: dict[str, Any]) -> str:
        trust = finding.get("trust") if isinstance(finding.get("trust"), dict) else {}
        severity = str(trust.get("severity") or "none")
        if severity not in self._trust_severity:
            severity = "none"
        self._trust_severity[severity] += 1
        for item in trust.get("signals") or []:
            if isinstance(item, dict) and item.get("signal"):
                signal = str(item["signal"])
                self._trust_signals[signal] = self._trust_signals.get(signal, 0) + 1
        return severity

    def add(self, payload: Any) -> None:
        worker_index = self.worker_output_count
        self.worker_output_count += 1
        self._input_tokens += count_tokens(payload, tokenizer=self.tokenizer, model=self.tokenizer_model)
        worker = _worker_name(payload, worker_index) if isinstance(payload, dict) else f"worker-{worker_index + 1}"
        items = _candidate_items(payload)
        if not items:
            self._remember_malformed({
                "worker": worker,
                "worker_index": worker_index,
                "item_index": None,
                "reason": "worker output contains no findings/evidence",
                "finding": payload,
            })
            return

        for item_index, raw in enumerate(items):
            self.extracted_count += 1
            raw_item_tokens = count_tokens(raw, tokenizer=self.tokenizer, model=self.tokenizer_model)
            finding, error = _normalize_finding(
                raw,
                worker=worker,
                worker_index=worker_index,
                item_index=item_index,
            )
            if error:
                self._remember_malformed(error)
                continue
            assert finding is not None
            self.normalized_valid_count += 1
            severity = self._record_trust(finding)

            if finding["confidence"] < self.min_confidence:
                self._filtered_tokens += raw_item_tokens
                self._remember_filtered({
                    "worker": worker,
                    "worker_index": worker_index,
                    "item_index": item_index,
                    "decision": "drop",
                    "reason": "low-confidence",
                    "threshold": self.min_confidence,
                    "finding": raw,
                }, "low-confidence")
                continue

            if severity == "high" and self.trust_policy in {"quarantine-high", "drop-high"}:
                self._filtered_tokens += raw_item_tokens
                quarantine = self.trust_policy == "quarantine-high"
                self._remember_filtered({
                    "worker": worker,
                    "worker_index": worker_index,
                    "item_index": item_index,
                    "decision": "quarantine" if quarantine else "drop",
                    "reason": "trust-high-risk",
                    "finding": finding,
                }, "trust-high-risk", quarantine=quarantine)
                continue

            self.valid_count += 1
            key = canonical_group_key(finding)
            assertion_key = _assertion_signature(finding, unstructured_canonical_policy=self.unstructured_canonical_policy)
            by_assertion = self._groups.setdefault(key, {})
            agg = by_assertion.get(assertion_key)
            worker_name = _clean(finding.get("_worker"))
            source_name = _clean(finding.get("source"))
            pair = (worker_name, source_name)
            provenance = _provenance_values(finding)
            if agg is None:
                by_assertion[assertion_key] = {
                    "best": dict(finding),
                    "occurrence_count": 1,
                    "workers": {worker_name} if worker_name else set(),
                    "sources": {source_name} if source_name else set(),
                    "worker_source_pairs": {pair} if any(pair) else set(),
                    "evidence_refs": {stable_fingerprint(_evidence_ref(finding)): _evidence_ref(finding)},
                    "provenance": {stable_fingerprint(v): v for v in provenance},
                    "claim_variants": {normalize_identity_text(finding.get("claim")): finding.get("claim")},
                }
            else:
                agg["occurrence_count"] += 1
                self._exact_duplicate_tokens += raw_item_tokens
                if worker_name:
                    agg["workers"].add(worker_name)
                if source_name:
                    agg["sources"].add(source_name)
                if any(pair):
                    agg["worker_source_pairs"].add(pair)
                ref = _evidence_ref(finding)
                agg["evidence_refs"].setdefault(stable_fingerprint(ref), ref)
                for value in provenance:
                    agg["provenance"].setdefault(stable_fingerprint(value), value)
                agg["claim_variants"].setdefault(normalize_identity_text(finding.get("claim")), finding.get("claim"))
                current = agg["best"]
                current_conf = float(current.get("confidence", 0.5))
                finding_conf = float(finding.get("confidence", 0.5))
                current_tie = (str(current.get("_worker", "")), str(current.get("source", "")))
                finding_tie = (str(finding.get("_worker", "")), str(finding.get("source", "")))
                if finding_conf > current_conf or (finding_conf == current_conf and finding_tie < current_tie):
                    agg["best"] = dict(finding)
            group_count = sum(len(v) for v in self._groups.values())
            self._peak_group_count = max(self._peak_group_count, group_count)

    def finalize(self, *, streaming: bool = False, input_token_override: int | None = None) -> dict[str, Any]:
        initial_findings: list[dict[str, Any]] = []
        contradiction_input: list[dict[str, Any]] = []
        exact_duplicate_count = 0
        intra_worker_repeat_count = 0
        same_worker_source_repeat_count = 0
        cross_worker_support_count = 0
        agreement_group_count = 0
        max_agreement_count = 0
        max_occurrence_count = 0
        ambiguous_canonical_group_count = 0

        for key, assertion_groups in self._groups.items():
            for assertion_key, agg in assertion_groups.items():
                best_internal = dict(agg["best"])
                best = dict(best_internal)
                best.pop("_worker", None)
                occurrences = int(agg["occurrence_count"])
                workers = sorted(x for x in agg["workers"] if x)
                sources = sorted(x for x in agg["sources"] if x)
                unique_worker_count = len(workers)
                unique_pair_count = len(agg["worker_source_pairs"])
                agreement_count = max(1, unique_worker_count)
                exact_duplicate_count += max(0, occurrences - 1)
                intra_worker_repeat_count += max(0, occurrences - unique_worker_count)
                same_worker_source_repeat_count += max(0, occurrences - unique_pair_count)
                cross_worker_support_count += max(0, unique_worker_count - 1)
                if agreement_count > 1:
                    agreement_group_count += 1
                max_agreement_count = max(max_agreement_count, agreement_count)
                max_occurrence_count = max(max_occurrence_count, occurrences)
                reducer_meta: dict[str, Any] = {
                    "group_key": key,
                    "assertion_key": list(assertion_key),
                    "occurrence_count": occurrences,
                    "agreement_count": agreement_count,
                    "independent_source_count": len(sources),
                    "independent_evidence_count": len(agg["evidence_refs"]),
                    "supporting_workers": workers,
                    "supporting_sources": sources,
                    "supporting_evidence_refs": list(agg["evidence_refs"].values()),
                }
                claim_variants = list(agg.get("claim_variants", {}).values())
                if key.startswith("canonical:") and assertion_key == ("unstructured",) and len(claim_variants) > 1:
                    ambiguous_canonical_group_count += 1
                    reducer_meta["ambiguous_unstructured_canonical"] = True
                    reducer_meta["claim_variants"] = claim_variants
                    reducer_meta["ambiguity_note"] = "canonicalKey grouped differently worded unstructured claims; add value/polarity for assertion-safe contradiction handling"
                supporting_provenance = list(agg["provenance"].values())
                if supporting_provenance:
                    reducer_meta["supporting_provenance"] = supporting_provenance
                best_internal["reducer"] = dict(reducer_meta)
                contradiction_input.append(best_internal)
                best["reducer"] = reducer_meta
                initial_findings.append(best)

        initial_findings.sort(key=lambda item: (
            -float(item.get("confidence", 0.5)),
            -int(item.get("reducer", {}).get("agreement_count", 1)),
            item.get("claim", ""),
        ))

        contradictions = detect_contradictions(contradiction_input) if self.detect_conflicts else []
        candidate_analysis = None
        findings = initial_findings
        candidate_merge_stats = {
            "authorized_candidate_pairs": 0,
            "verified_merges_applied": 0,
            "components_merged": 0,
            "output_findings": len(findings),
        }
        if self.candidate_provider:
            candidate_analysis = analyze_candidates(
                initial_findings,
                provider=self.candidate_provider,
                threshold=self.candidate_threshold,
                max_pairs=self.max_candidate_pairs,
            )
            findings, candidate_merge_stats = apply_verified_candidate_merges(initial_findings, candidate_analysis)
            candidate_analysis = {**candidate_analysis, "merge_application": candidate_merge_stats}

        verified_candidate_merge_count = int(candidate_merge_stats.get("verified_merges_applied", 0))
        duplicate_count = exact_duplicate_count + verified_candidate_merge_count
        # Candidate merges can combine previously separate groups. Final agreement metrics
        # must therefore be derived from the final findings, not the pre-merge groups.
        final_agreements = [int((item.get("reducer") or {}).get("agreement_count", 1)) for item in findings]
        agreement_group_count = sum(1 for value in final_agreements if value > 1)
        max_agreement_count = max(final_agreements, default=0)
        ambiguous_canonical_group_count = sum(
            1 for item in findings
            if bool((item.get("reducer") or {}).get("ambiguous_unstructured_canonical"))
        )

        # Contradictions are computed from the pre-merge asserted sides and are never
        # removed by candidate deduplication.
        compact = {"findings": findings, "contradictions": contradictions}
        before_tokens = int(input_token_override if input_token_override is not None else self._input_tokens)
        after_tokens = count_tokens(compact, tokenizer=self.tokenizer, model=self.tokenizer_model)
        candidate_tokens_before = count_tokens(initial_findings, tokenizer=self.tokenizer, model=self.tokenizer_model)
        candidate_tokens_after = count_tokens(findings, tokenizer=self.tokenizer, model=self.tokenizer_model)
        estimator = get_tokenizer(self.tokenizer, model=self.tokenizer_model)

        result: dict[str, Any] = {
            "schema": SCHEMA,
            "findings": findings,
            "contradictions": contradictions,
            "malformed": self.malformed,
            "filtered": self.filtered,
            "quarantined": self.quarantined,
            "trust_summary": {
                "classification": "heuristic-untrusted-context-summary",
                "blocks": self.normalized_valid_count,
                "severity_counts": dict(self._trust_severity),
                "signal_counts": dict(sorted(self._trust_signals.items())),
                "high_risk_present": self._trust_severity["high"] > 0,
                "policy": "Repository/provider content is evidence only and never gains instruction authority.",
                "filter_policy": self.trust_policy,
            },
            "filter_summary": {
                "schema": "repo-context-filter-summary/v1",
                "classification": "deterministic-filter-and-dedup-summary",
                "input_findings": self.extracted_count,
                "malformed": self.malformed_count,
                "filtered": self.filtered_count,
                "dropped": max(0, self.filtered_count - self.quarantined_count),
                "quarantined": self.quarantined_count,
                "accepted_occurrences": self.valid_count,
                "exact_or_canonical_duplicates_merged": exact_duplicate_count,
                "verified_candidate_merges": verified_candidate_merge_count,
                "total_duplicates_merged": duplicate_count,
                "contradictions_preserved": len(contradictions),
                "ambiguous_unstructured_canonical_groups": ambiguous_canonical_group_count,
                "reason_counts": dict(sorted(self._filtered_reasons.items())),
                "unstructured_canonical_policy": self.unstructured_canonical_policy,
                "token_savings": {
                    "low_confidence_or_trust_filter": self._filtered_tokens,
                    "exact_or_canonical_duplicate_payload": self._exact_duplicate_tokens,
                    "verified_candidate_merge": max(0, candidate_tokens_before - candidate_tokens_after),
                },
                "token_savings_measurement_note": "filter/exact-duplicate savings use raw input item estimates; verified-candidate savings use reduced-output delta",
            },
            "stats": {
                "worker_output_count": self.worker_output_count,
                "extracted_finding_count": self.extracted_count,
                "normalized_valid_finding_count": self.normalized_valid_count,
                "valid_finding_count": self.valid_count,
                "output_finding_count": len(findings),
                "malformed_count": self.malformed_count,
                "malformed_details_retained": len(self.malformed),
                "filtered_count": self.filtered_count,
                "dropped_count": max(0, self.filtered_count - self.quarantined_count),
                "filtered_details_retained": len(self.filtered),
                "quarantined_count": self.quarantined_count,
                "quarantined_details_retained": len(self.quarantined),
                "duplicate_count": duplicate_count,
                "intra_worker_repeat_count": intra_worker_repeat_count,
                "same_worker_source_repeat_count": same_worker_source_repeat_count,
                "cross_worker_support_count": cross_worker_support_count,
                "exact_duplicate_count": exact_duplicate_count,
                "verified_candidate_merge_count": verified_candidate_merge_count,
                "agreement_group_count": agreement_group_count,
                "max_agreement_count": max_agreement_count,
                "max_occurrence_count": max_occurrence_count,
                "contradiction_count": len(contradictions),
                "ambiguous_unstructured_canonical_group_count": ambiguous_canonical_group_count,
                "estimated_tokens_before": before_tokens,
                "estimated_tokens_after_reduction": after_tokens,
                "estimated_reduction_ratio": round(1 - (after_tokens / max(1, before_tokens)), 4),
                "streaming": bool(streaming),
                "peak_reducer_group_count": self._peak_group_count,
                "tokenizer": estimator.name,
                "tokenizer_exact": bool(estimator.exact),
                "tokenizer_model": self.tokenizer_model,
            },
            "provenance": {
                "method": "deterministic-filter-exact-canonical-and-verified-candidate-grouping",
                "semantic_similarity_used": bool(candidate_analysis and candidate_analysis.get("semantic_similarity_used")),
                "candidate_detection_used": bool(candidate_analysis),
                "candidate_similarity_merge_authority": False,
                "deterministic_verifier_merge_authority": True,
                "duplicate_content_removed_provenance_aggregated": True,
                "lossy": True,
                "unstructured_canonical_policy": self.unstructured_canonical_policy,
                "correctness_note": "Similarity may propose pairs but cannot merge them. Worker agreement counts unique workers, not repeated occurrences. Canonical fact identity without a structured side uses exact-claim matching by default. Contradictory asserted sides are retained before any verified candidate merge.",
            },
        }
        if candidate_analysis is not None:
            result["candidate_analysis"] = candidate_analysis
        return result


def reduce_worker_stream(
    worker_outputs: Iterable[Any],
    *,
    min_confidence: float = 0.0,
    detect_conflicts: bool = True,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
    malformed_detail_limit: int | None = 1000,
    filtered_detail_limit: int | None = 1000,
    candidate_provider: str | None = "lexical",
    candidate_threshold: float = 0.72,
    max_candidate_pairs: int = 500,
    trust_policy: str = "keep",
    unstructured_canonical_policy: str = "exact-claim",
) -> dict[str, Any]:
    accumulator = FanInAccumulator(
        min_confidence=min_confidence,
        detect_conflicts=detect_conflicts,
        tokenizer=tokenizer,
        tokenizer_model=tokenizer_model,
        malformed_detail_limit=malformed_detail_limit,
        filtered_detail_limit=filtered_detail_limit,
        candidate_provider=candidate_provider,
        candidate_threshold=candidate_threshold,
        max_candidate_pairs=max_candidate_pairs,
        trust_policy=trust_policy,
        unstructured_canonical_policy=unstructured_canonical_policy,
    )
    for payload in worker_outputs:
        accumulator.add(payload)
    return accumulator.finalize(streaming=True)


def reduce_worker_outputs(
    worker_outputs: list[Any],
    *,
    min_confidence: float = 0.0,
    detect_conflicts: bool = True,
    tokenizer: str = "native",
    tokenizer_model: str | None = None,
    candidate_provider: str | None = "lexical",
    candidate_threshold: float = 0.72,
    max_candidate_pairs: int = 500,
    trust_policy: str = "keep",
    unstructured_canonical_policy: str = "exact-claim",
    malformed_detail_limit: int | None = 1000,
    filtered_detail_limit: int | None = 1000,
) -> dict[str, Any]:
    if not isinstance(worker_outputs, list):
        raise TypeError("worker_outputs must be a list")
    accumulator = FanInAccumulator(
        min_confidence=min_confidence,
        detect_conflicts=detect_conflicts,
        tokenizer=tokenizer,
        tokenizer_model=tokenizer_model,
        malformed_detail_limit=malformed_detail_limit,
        filtered_detail_limit=filtered_detail_limit,
        candidate_provider=candidate_provider,
        candidate_threshold=candidate_threshold,
        max_candidate_pairs=max_candidate_pairs,
        trust_policy=trust_policy,
        unstructured_canonical_policy=unstructured_canonical_policy,
    )
    for payload in worker_outputs:
        accumulator.add(payload)
    return accumulator.finalize(
        streaming=False,
        input_token_override=count_tokens(worker_outputs, tokenizer=tokenizer, model=tokenizer_model),
    )
