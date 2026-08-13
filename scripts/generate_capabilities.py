#!/usr/bin/env python3
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repo_context import __version__
from repo_context.capabilities import native_capability_manifest


def main() -> int:
    out = ROOT / "capabilities.json"
    out.write_text(
        json.dumps(native_capability_manifest(__version__), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
