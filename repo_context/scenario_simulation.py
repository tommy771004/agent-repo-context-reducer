from __future__ import annotations

from typing import Any

from .adaptive_reduction import eligible_modes, project_reduction_mode

SCHEMA = "repo-context-reduction-simulation/v1"

DEFAULT_SCENARIOS: list[dict[str, Any]] = [
    {"name": "small-single-file", "source_tokens": 3000, "baseline_output_tokens": 700, "duplicate_ratio": 0.05, "conflict_ratio": 0.00, "complexity": "focused", "risk": "low", "workers": 1},
    {"name": "medium-cross-file-repetitive", "source_tokens": 14000, "baseline_output_tokens": 1200, "duplicate_ratio": 0.38, "conflict_ratio": 0.01, "complexity": "focused", "risk": "medium", "workers": 1},
    {"name": "large-high-dup-investigation", "source_tokens": 55000, "baseline_output_tokens": 1800, "duplicate_ratio": 0.55, "conflict_ratio": 0.02, "complexity": "complex", "risk": "medium", "workers": 3, "requires_parallel_evidence": True},
    {"name": "conflicting-evidence", "source_tokens": 32000, "baseline_output_tokens": 1800, "duplicate_ratio": 0.22, "conflict_ratio": 0.14, "complexity": "complex", "risk": "high", "workers": 3, "requires_parallel_evidence": True},
    {"name": "large-low-dup-provenance", "source_tokens": 26000, "baseline_output_tokens": 1500, "duplicate_ratio": 0.06, "conflict_ratio": 0.01, "complexity": "complex", "risk": "medium", "workers": 3},
    {"name": "security-sensitive-small", "source_tokens": 4800, "baseline_output_tokens": 900, "duplicate_ratio": 0.10, "conflict_ratio": 0.00, "complexity": "focused", "risk": "high", "workers": 2},
    {"name": "orchestration-overhead-regression", "source_tokens": 4500, "baseline_output_tokens": 750, "duplicate_ratio": 0.30, "conflict_ratio": 0.00, "complexity": "focused", "risk": "low", "workers": 1},
]


def _clamp_ratio(value: Any) -> float:
    return min(1.0, max(0.0, float(value or 0.0)))


def _strategy_projection(s: dict[str, Any], mode: str) -> dict[str, Any]:
    return project_reduction_mode(
        mode,
        source_tokens=max(1, int(s.get("source_tokens", 1))),
        baseline_output_tokens=max(0, int(s.get("baseline_output_tokens", 800))),
        duplicate_ratio=_clamp_ratio(s.get("duplicate_ratio")),
        conflict_ratio=_clamp_ratio(s.get("conflict_ratio")),
        workers=max(1, int(s.get("workers", 1))),
    )


def simulate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    s = dict(scenario)
    name = str(s.get("name") or "scenario")
    complexity = str(s.get("complexity") or "focused")
    risk = str(s.get("risk") or "low")
    conflict = _clamp_ratio(s.get("conflict_ratio"))
    eligibility = eligible_modes(
        complexity_level=complexity,
        risk_level=risk,
        conflict_ratio=conflict,
        requires_parallel_evidence=bool(s.get("requires_parallel_evidence", False)),
    )
    projections = {mode: _strategy_projection(s, mode) for mode in ("direct", "light", "full")}
    candidates = [p for mode, p in projections.items() if eligibility[mode]["eligible"]]
    selected = min(candidates, key=lambda p: (p["total_model_tokens"], p["model_calls"], p["latency_proxy_units"], p["mode"]))
    # Avoid mode churn for negligible savings. If direct is eligible, a more complex mode
    # must save at least 3% and 256 projected tokens before it is preferred.
    direct = projections["direct"]
    if eligibility["direct"]["eligible"] and selected["mode"] != "direct":
        savings = direct["total_model_tokens"] - selected["total_model_tokens"]
        savings_ratio = savings / max(1, direct["total_model_tokens"])
        if savings < 256 or savings_ratio < 0.03:
            selected = direct
    return {
        "name": name,
        "inputs": s,
        "eligibility": eligibility,
        "strategies": projections,
        "selected_mode": selected["mode"],
        "selection_basis": "safety/correctness eligibility first; all modes share deterministic local filtering; then projected total model tokens with a 3%/256-token hysteresis before leaving direct mode; then model calls and latency proxy",
        "selected_projection": selected,
    }


def simulate_scenarios(scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    rows = [simulate_scenario(s) for s in (scenarios or DEFAULT_SCENARIOS)]
    static_totals = {
        mode: sum(row["strategies"][mode]["total_model_tokens"] for row in rows)
        for mode in ("direct", "light", "full")
    }
    adaptive_total = sum(row["selected_projection"]["total_model_tokens"] for row in rows)
    eligible_static = {
        mode: all(row["eligibility"][mode]["eligible"] for row in rows)
        for mode in ("direct", "light", "full")
    }
    return {
        "schema": SCHEMA,
        "classification": "deterministic-routing-economics-simulation",
        "scenarios": rows,
        "aggregate": {
            "static_mode_total_tokens": static_totals,
            "static_mode_globally_eligible": eligible_static,
            "adaptive_total_tokens": adaptive_total,
            "adaptive_savings_vs_always_full": static_totals["full"] - adaptive_total,
            "adaptive_savings_ratio_vs_always_full": round((static_totals["full"] - adaptive_total) / max(1, static_totals["full"]), 4),
        },
        "recommended_policy": "adaptive",
        "why": "No single static mode is both efficient and eligible in every scenario. Route per scenario with safety/correctness constraints before token economics.",
        "limitations": [
            "Token projections are deterministic simulation assumptions, not provider billing measurements.",
            "Latency values are relative proxies, not wall-clock predictions.",
            "No simulated quality score is treated as model-answer correctness.",
        ],
    }
