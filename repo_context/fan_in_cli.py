from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

from .fan_in import reduce_worker_outputs
from .synthesis_packet import build_synthesis_packet


def _load(path: str) -> list[Any]:
    text = sys.stdin.read() if path == "-" else pathlib.Path(path).read_text(encoding="utf-8")
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("worker_outputs"), list):
        return data["worker_outputs"]
    if isinstance(data, list):
        return data
    raise ValueError("input must be a JSON array or {\"worker_outputs\": [...]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repo-context-fan-in",
        description="Deterministically reduce multiple worker handoffs before final synthesis.",
    )
    parser.add_argument("input", nargs="?", default="-", help="JSON file or '-' for stdin")
    parser.add_argument("-o", "--out", help="write JSON output to file")
    parser.add_argument("--pretty", action="store_true", help="pretty-print JSON")
    parser.add_argument("--min-confidence", type=float, default=0.0)
    parser.add_argument("--max-estimated-tokens", type=int, default=6000)
    parser.add_argument("--no-conflicts", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 0.0 <= args.min_confidence <= 1.0:
        parser.error("--min-confidence must be between 0 and 1")
    if args.max_estimated_tokens <= 0:
        parser.error("--max-estimated-tokens must be positive")

    try:
        worker_outputs = _load(args.input)
        reduction = reduce_worker_outputs(
            worker_outputs,
            min_confidence=args.min_confidence,
            detect_conflicts=not args.no_conflicts,
        )
        packet = build_synthesis_packet(
            reduction,
            max_estimated_tokens=args.max_estimated_tokens,
        )
        result = {
            "reduction": reduction,
            "synthesis_packet": packet,
        }
        text = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None) + "\n"
        if args.out:
            pathlib.Path(args.out).write_text(text, encoding="utf-8")
        else:
            sys.stdout.write(text)
        if not reduction["findings"] and not reduction["contradictions"]:
            return 2
        return 0
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"repo-context-fan-in: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
