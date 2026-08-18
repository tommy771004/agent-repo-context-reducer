from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Iterator
from typing import Any, TextIO


def _iter_ndjson(handle: TextIO) -> Iterator[Any]:
    for line_no, raw in enumerate(handle, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid NDJSON at line {line_no}: {exc}") from exc


def _unwrap_json(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and isinstance(value.get("worker_outputs"), list):
        return list(value["worker_outputs"])
    if isinstance(value, dict):
        return [value]
    raise ValueError("JSON input must be an array, an object, or {'worker_outputs': [...]} wrapper")


def iter_worker_input(source: str | pathlib.Path, *, input_format: str = "auto") -> tuple[Iterator[Any], dict[str, Any]]:
    """Return an iterator over worker records plus input-mode metadata.

    NDJSON/JSONL is line-streamed. JSON arrays remain compatibility mode and are decoded as
    one document because the standard library has no incremental array parser. Use NDJSON
    when bounded memory is required.
    """
    fmt = str(input_format or "auto").strip().lower()
    if fmt not in {"auto", "json", "ndjson"}:
        raise ValueError("input_format must be auto, json, or ndjson")

    raw_source = str(source)
    if raw_source == "-":
        if fmt == "auto":
            fmt = "ndjson"
        if fmt == "ndjson":
            return _iter_ndjson(sys.stdin), {
                "format": "ndjson", "streaming": True, "source": "stdin",
                "note": "stdin auto mode defaults to NDJSON for bounded-memory fan-in",
            }
        data = json.load(sys.stdin)
        return iter(_unwrap_json(data)), {"format": "json", "streaming": False, "source": "stdin"}

    path = pathlib.Path(raw_source).expanduser()
    if not path.is_file():
        raise ValueError(f"worker input file not found: {path}")
    if fmt == "auto":
        fmt = "ndjson" if path.suffix.lower() in {".ndjson", ".jsonl"} else "json"
    if fmt == "ndjson":
        # Keep the handle alive through generator finalization.
        def generator() -> Iterator[Any]:
            with path.open("r", encoding="utf-8") as handle:
                yield from _iter_ndjson(handle)
        return generator(), {"format": "ndjson", "streaming": True, "source": str(path)}

    data = json.loads(path.read_text(encoding="utf-8"))
    return iter(_unwrap_json(data)), {"format": "json", "streaming": False, "source": str(path)}
