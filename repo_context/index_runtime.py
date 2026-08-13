from __future__ import annotations

import argparse
from typing import Any

from .indexer import ensure_index


def index_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "max_files": args.max_files,
        "max_file_bytes": args.max_file_bytes,
        "include_hidden": args.include_hidden,
        "use_cache": not args.no_cache,
        "include_generated": args.include_generated,
    }


def persistent_index(args: argparse.Namespace) -> dict[str, Any]:
    return ensure_index(args.path, sync=not args.no_sync, **index_kwargs(args))["index"]
