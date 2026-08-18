from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .fan_in import reduce_worker_outputs, reduce_worker_stream
from .streaming import iter_worker_input
from .synthesis_packet import build_synthesis_packet
from .filter_audit import audit_filter_reduction


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-context-fan-in",
        description="Deterministically reduce JSON/NDJSON worker handoffs before final synthesis.",
    )
    parser.add_argument("input", nargs="?", default="-", help="JSON/NDJSON file or '-' for stdin (stdin auto=NDJSON)")
    parser.add_argument("-o", "--out", help="write JSON output to file")
    parser.add_argument("--format", choices=["auto", "json", "ndjson"], default="auto")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--max-estimated-tokens", type=int, default=6000)
    parser.add_argument("--no-conflicts", action="store_true")
    parser.add_argument("--tokenizer", default="native")
    parser.add_argument("--tokenizer-model")
    parser.add_argument("--candidate-provider", default="lexical")
    parser.add_argument("--no-candidate-dedup", action="store_true")
    parser.add_argument("--candidate-threshold", type=float, default=0.72)
    parser.add_argument("--max-candidate-pairs", type=int, default=500)
    parser.add_argument("--malformed-detail-limit", type=int, default=1000)
    parser.add_argument("--filtered-detail-limit", type=int, default=1000)
    parser.add_argument("--trust-policy", choices=["keep", "quarantine-high", "drop-high"], default="keep")
    parser.add_argument("--unstructured-canonical-policy", choices=["exact-claim", "legacy-merge"], default="exact-claim")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 0.0 <= args.min_confidence <= 1.0:
        parser.error("--min-confidence must be between 0 and 1")
    if args.max_estimated_tokens <= 0:
        parser.error("--max-estimated-tokens must be positive")

    try:
        records, input_meta = iter_worker_input(args.input, input_format=args.format)
        common = dict(
            min_confidence=args.min_confidence,
            detect_conflicts=not args.no_conflicts,
            tokenizer=args.tokenizer,
            tokenizer_model=args.tokenizer_model,
            candidate_provider=None if args.no_candidate_dedup else args.candidate_provider,
            candidate_threshold=args.candidate_threshold,
            max_candidate_pairs=args.max_candidate_pairs,
            trust_policy=args.trust_policy,
            unstructured_canonical_policy=args.unstructured_canonical_policy,
        )
        if input_meta.get("streaming"):
            reduction = reduce_worker_stream(
                records,
                malformed_detail_limit=args.malformed_detail_limit,
                filtered_detail_limit=args.filtered_detail_limit,
                **common,
            )
        else:
            reduction = reduce_worker_outputs(
                list(records),
                malformed_detail_limit=args.malformed_detail_limit,
                filtered_detail_limit=args.filtered_detail_limit,
                **common,
            )
        packet = build_synthesis_packet(
            reduction,
            max_estimated_tokens=args.max_estimated_tokens,
            tokenizer=args.tokenizer,
            tokenizer_model=args.tokenizer_model,
        )
        filter_audit = audit_filter_reduction(reduction)
        result = {"input": input_meta, "reduction": reduction, "filter_audit": filter_audit, "synthesis_packet": packet}
        text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None) + "\n"
        if args.out:
            pathlib.Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        if not filter_audit.get("passed"):
            return 3
        if not reduction["findings"] and not reduction["contradictions"]:
            return 2
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"repo-context-fan-in: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
