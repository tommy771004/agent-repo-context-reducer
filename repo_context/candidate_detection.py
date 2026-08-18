from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Any, Callable

from .contradiction import identity_key, normalize_identity_text


@dataclass(frozen=True)
class CandidateProvider:
    name: str
    callback: Callable[[list[dict[str, Any]], float, int], list[tuple[int, int, float]]]
    semantic: bool = False
    description: str = "Candidate detector"


_PROVIDERS: dict[str, CandidateProvider] = {}


def _terms(value: Any) -> set[str]:
    text = normalize_identity_text(value)
    return {
        token
        for token in re.findall(r"[a-z0-9_.:/-]{2,}|[\u4e00-\u9fff]{1,6}", text)
        if token not in {"the", "and", "for", "with", "from", "this", "that", "into", "is", "are", "was", "were"}
    }


def _lexical_pairs(findings: list[dict[str, Any]], threshold: float, max_pairs: int) -> list[tuple[int, int, float]]:
    term_sets = [_terms(item.get("claim")) for item in findings]
    inverted: dict[str, list[int]] = {}
    for i, terms in enumerate(term_sets):
        for term in sorted(terms):
            inverted.setdefault(term, []).append(i)

    pair_cap = max(1, int(max_pairs)) * 8
    pair_candidates: set[tuple[int, int]] = set()

    # Structured/canonical identity gets first access to the bounded candidate set. This
    # preserves the highest-value deterministic verification opportunities without letting
    # one huge identity bucket allocate O(n^2) pairs.
    identities: dict[str, list[int]] = {}
    for i, item in enumerate(findings):
        key = identity_key(item)
        if key:
            identities.setdefault(key, []).append(i)
    cap_reached = False
    for indices in identities.values():
        for pos, left in enumerate(indices):
            for right in indices[pos + 1:]:
                pair_candidates.add((left, right))
                if len(pair_candidates) >= pair_cap:
                    cap_reached = True
                    break
            if cap_reached:
                break
        if cap_reached:
            break

    # Shared lexical terms are only a blocking mechanism; they never authorize a merge.
    if not cap_reached:
        for indices in inverted.values():
            # Extremely common terms provide little signal and can cause quadratic work.
            if len(indices) > 200:
                continue
            for pos, left in enumerate(indices):
                for right in indices[pos + 1:]:
                    pair_candidates.add((left, right))
                    if len(pair_candidates) >= pair_cap:
                        cap_reached = True
                        break
                if cap_reached:
                    break
            if cap_reached:
                break

    scored: list[tuple[int, int, float]] = []
    for left, right in pair_candidates:
        a, b = term_sets[left], term_sets[right]
        union = a | b
        jaccard = 0.0 if not union else len(a & b) / len(union)
        left_text = normalize_identity_text(findings[left].get("claim"))
        right_text = normalize_identity_text(findings[right].get("claim"))
        sequence = difflib.SequenceMatcher(None, left_text, right_text, autojunk=False).ratio() if left_text and right_text else 0.0
        score = max(jaccard, sequence)
        left_identity = identity_key(findings[left])
        right_identity = identity_key(findings[right])
        same_identity = left_identity is not None and left_identity == right_identity
        if score >= threshold or same_identity:
            scored.append((left, right, round(score, 6)))
    scored.sort(key=lambda x: (-x[2], x[0], x[1]))
    return scored[:max_pairs]


def register_candidate_provider(name: str,
                                callback: Callable[[list[dict[str, Any]], float, int], list[tuple[int, int, float]]],
                                *, semantic: bool = True, description: str = "Host-registered candidate detector") -> None:
    key = str(name).strip().lower()
    if not key or key == "lexical":
        raise ValueError("custom candidate provider name must be non-empty and may not replace 'lexical'")
    _PROVIDERS[key] = CandidateProvider(key, callback, semantic=bool(semantic), description=description)


def candidate_provider_status() -> list[dict[str, Any]]:
    items = [{
        "name": "lexical",
        "available": True,
        "semantic": False,
        "description": "Dependency-free lexical blocking/Jaccard fallback; candidate detection only.",
    }]
    items.extend({
        "name": item.name,
        "available": True,
        "semantic": item.semantic,
        "description": item.description,
    } for item in sorted(_PROVIDERS.values(), key=lambda x: x.name))
    return items


def structured_assertion_side(item: dict[str, Any]) -> tuple[Any, ...] | None:
    polarity = normalize_identity_text(item.get("polarity"))
    raw = item.get("value")
    value: tuple[str, Any] | None = None
    if isinstance(raw, bool):
        value = ("bool", raw)
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        number = float(raw)
        if number == number and number not in {float("inf"), float("-inf")}:
            value = ("number", int(number) if number.is_integer() else number)
    elif isinstance(raw, str) and raw.strip():
        value = ("string", normalize_identity_text(raw))
    unit = normalize_identity_text(item.get("unit"))
    if polarity or value is not None:
        return (polarity or None, value, unit or None)
    return None


def verify_candidate(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Verify a candidate using deterministic identity/assertion fields only.

    Similar wording or embedding similarity is never merge authority. Structured assertion
    disagreement is checked *before* exact-claim equivalence so identical wording can never
    hide conflicting ``value``/``polarity`` fields.
    """
    left_claim = normalize_identity_text(left.get("claim"))
    right_claim = normalize_identity_text(right.get("claim"))
    left_identity = identity_key(left)
    right_identity = identity_key(right)
    left_side = structured_assertion_side(left)
    right_side = structured_assertion_side(right)

    if left_identity and right_identity and left_identity != right_identity:
        return {
            "verdict": "conflicting-identity",
            "merge_authorized": False,
            "reason": "candidate wording does not override conflicting deterministic identities",
        }

    # Assertion metadata outranks wording. Even an identical claim must stay separate when
    # structured sides disagree. We only call this a contradiction candidate when a shared
    # deterministic fact identity exists; otherwise it is simply unsafe to merge.
    if left_side is not None and right_side is not None and left_side != right_side:
        same_identity = bool(left_identity and left_identity == right_identity)
        return {
            "verdict": "same-identity-different-assertion" if same_identity else "conflicting-structured-assertion",
            "merge_authorized": False,
            "contradiction_candidate": same_identity,
            "reason": "structured assertion side differs; exact wording cannot authorize a merge",
            **({"identity": left_identity} if same_identity else {}),
        }

    if left_claim and left_claim == right_claim:
        return {
            "verdict": "safe-duplicate",
            "merge_authorized": True,
            "reason": "exact-normalized-claim",
            "identity": left_identity or right_identity,
        }

    if not left_identity or left_identity != right_identity:
        return {
            "verdict": "insufficient-identity",
            "merge_authorized": False,
            "reason": "candidate similarity does not establish deterministic fact identity",
        }

    if left_side is not None and right_side is not None:
        # The disagreement case was handled above.
        return {
            "verdict": "safe-duplicate",
            "merge_authorized": True,
            "reason": "exact-identity-and-structured-assertion",
            "identity": left_identity,
        }

    return {
        "verdict": "same-identity-unverified-assertion",
        "merge_authorized": False,
        "reason": "identity matches but assertion side is not structured enough to prove equivalence",
        "identity": left_identity,
    }


def analyze_candidates(findings: list[dict[str, Any]], *, provider: str = "lexical",
                       threshold: float = 0.72, max_pairs: int = 500) -> dict[str, Any]:
    if not 0.0 <= float(threshold) <= 1.0:
        raise ValueError("candidate threshold must be between 0 and 1")
    if max_pairs <= 0:
        raise ValueError("max_pairs must be positive")

    key = str(provider or "lexical").strip().lower()
    if key == "lexical":
        pairs = _lexical_pairs(findings, float(threshold), int(max_pairs))
        semantic = False
        description = "dependency-free lexical candidate detector"
    else:
        registered = _PROVIDERS.get(key)
        if registered is None:
            raise ValueError(f"Unknown candidate provider: {provider}")
        pairs = registered.callback(findings, float(threshold), int(max_pairs))
        semantic = registered.semantic
        description = registered.description

    rows = []
    verified_duplicates = 0
    contradiction_candidates = 0
    for left, right, score in pairs[:max_pairs]:
        if left < 0 or right < 0 or left >= len(findings) or right >= len(findings) or left == right:
            continue
        verification = verify_candidate(findings[left], findings[right])
        if verification.get("merge_authorized"):
            verified_duplicates += 1
        if verification.get("contradiction_candidate"):
            contradiction_candidates += 1
        rows.append({
            "left_index": left,
            "right_index": right,
            "left_claim": findings[left].get("claim"),
            "right_claim": findings[right].get("claim"),
            "score": float(score),
            "provider": key,
            "verification": verification,
        })

    return {
        "classification": "candidate-detection-with-deterministic-verification",
        "provider": key,
        "provider_description": description,
        "semantic_similarity_used": semantic,
        "candidate_count": len(rows),
        "verified_duplicate_candidates": verified_duplicates,
        "contradiction_candidates": contradiction_candidates,
        "pairs": rows,
        "policy": "Candidate similarity may propose pairs but never authorizes a merge; only deterministic verification may do so.",
    }
