#!/usr/bin/env python3
"""Dependency-free repository context reducer for AI coding agents."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from collections import Counter, defaultdict
from typing import Any

VERSION = "0.1.0"

IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", ".next", ".nuxt", ".turbo",
    ".cache", ".pytest_cache", ".mypy_cache", ".ruff_cache", "__pycache__",
    "node_modules", "vendor", "dist", "build", "target", "bin", "obj",
    "coverage", ".coverage", ".venv", "venv", "env", ".tox", ".gradle",
}

SOURCE_EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".jsx": "JavaScript",
    ".cs": "C#",
    ".rs": "Rust",
    ".go": "Go",
    ".java": "Java", ".kt": "Kotlin", ".kts": "Kotlin",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".c": "C", ".h": "C/C++", ".cc": "C/C++", ".cpp": "C/C++", ".hpp": "C/C++",
    ".vue": "Vue", ".svelte": "Svelte",
    ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell",
}

MANIFESTS = {
    "package.json", "pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock",
    "Cargo.toml", "go.mod", "pom.xml", "build.gradle", "build.gradle.kts",
    "Gemfile", "composer.json", "Package.swift", "*.csproj", "*.sln",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
}

ENTRY_NAMES = {
    "main.py", "app.py", "manage.py", "__main__.py",
    "index.js", "index.ts", "index.tsx", "main.js", "main.ts", "main.tsx",
    "server.js", "server.ts", "Program.cs", "Main.java", "main.rs", "lib.rs",
    "main.go", "App.tsx", "App.jsx",
}

TEXT_CONFIG_EXTS = {".json", ".toml", ".yaml", ".yml", ".xml", ".ini", ".cfg", ".md"}


def estimate_tokens_from_bytes(size: int) -> int:
    return max(1, (size + 3) // 4) if size else 0


def safe_read_text(path: pathlib.Path, max_bytes: int) -> tuple[str | None, int]:
    try:
        size = path.stat().st_size
        if size > max_bytes:
            return None, size
        data = path.read_bytes()
        if b"\x00" in data[:4096]:
            return None, size
        return data.decode("utf-8", errors="replace"), size
    except (OSError, PermissionError):
        return None, 0


def is_manifest(path: pathlib.Path) -> bool:
    name = path.name
    if name in MANIFESTS:
        return True
    return path.suffix in {".csproj", ".sln"}


def relpath(path: pathlib.Path, root: pathlib.Path) -> str:
    return path.relative_to(root).as_posix()


def should_skip_dir(name: str, include_hidden: bool) -> bool:
    if name in IGNORE_DIRS:
        return True
    if not include_hidden and name.startswith("."):
        return True
    return False


def compact_signature(line: str, limit: int = 180) -> str:
    s = re.sub(r"\s+", " ", line.strip())
    return s[:limit] + ("…" if len(s) > limit else "")


def summarize_source(path: str, text: str) -> dict[str, Any]:
    ext = pathlib.Path(path).suffix.lower()
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    types: list[str] = []
    routes: list[str] = []
    exports: list[str] = []

    lines = text.splitlines()

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith(("//", "#", "/*", "*")):
            continue

        # Imports / dependencies
        if ext == ".py":
            m = re.match(r"(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", line)
            if m:
                imports.append(m.group(1) or m.group(2))
        elif ext in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}:
            m = re.search(r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]", line)
            if m:
                imports.append(m.group(1))
        elif ext == ".rs":
            m = re.match(r"(?:use|mod)\s+([^;{]+)", line)
            if m:
                imports.append(compact_signature(m.group(1)))
        elif ext == ".go":
            if line.startswith("import "):
                imports.append(compact_signature(line[7:].strip('()\"')))
        elif ext in {".cs", ".java", ".kt", ".kts"}:
            m = re.match(r"(?:using|import)\s+([^;]+)", line)
            if m:
                imports.append(m.group(1))

        # Classes / structural types
        class_patterns = [
            r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_][\w]*)",
            r"^(?:public\s+|private\s+|internal\s+|protected\s+)?(?:abstract\s+|sealed\s+|static\s+)?class\s+([A-Za-z_][\w]*)",
            r"^class\s+([A-Za-z_][\w]*)",
            r"^(?:pub\s+)?struct\s+([A-Za-z_][\w]*)",
        ]
        for pat in class_patterns:
            m = re.match(pat, line)
            if m:
                classes.append(m.group(1)); break

        type_patterns = [
            r"^(?:export\s+)?interface\s+([A-Za-z_][\w]*)",
            r"^(?:export\s+)?type\s+([A-Za-z_][\w]*)",
            r"^(?:pub\s+)?(?:enum|trait)\s+([A-Za-z_][\w]*)",
            r"^(?:public\s+)?interface\s+([A-Za-z_][\w]*)",
            r"^(?:public\s+)?enum\s+([A-Za-z_][\w]*)",
        ]
        for pat in type_patterns:
            m = re.match(pat, line)
            if m:
                types.append(m.group(1)); break

        # Function / method signatures
        fn_match = None
        if ext == ".py":
            fn_match = re.match(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", line)
        elif ext in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}:
            fn_match = re.match(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", line)
            if not fn_match:
                fn_match = re.match(r"^(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*(?:get\s+|set\s+)?([A-Za-z_]\w*)\s*\(([^)]*)\)\s*[:{]", line)
        elif ext == ".rs":
            fn_match = re.match(r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\(([^)]*)\)", line)
        elif ext == ".go":
            fn_match = re.match(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(([^)]*)\)", line)
        elif ext in {".cs", ".java", ".kt", ".kts", ".swift", ".php"}:
            if "(" in line and ")" in line and not re.match(r"^(if|for|while|switch|catch|foreach)\b", line):
                m = re.search(r"([A-Za-z_]\w*)\s*\(([^)]*)\)", line)
                if m:
                    name = m.group(1)
                    if name not in {"if", "for", "while", "switch", "catch", "new", "return"}:
                        fn_match = m
        if fn_match:
            functions.append(compact_signature(f"{fn_match.group(1)}({fn_match.group(2)})"))

        # JS/TS exports
        if re.match(r"^export\s+", line):
            m = re.search(r"(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_]\w*)", line)
            if m:
                exports.append(m.group(1))

        # Common HTTP route patterns
        for pat in [
            r"\b(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)",
            r"\[(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete)(?:\(\s*['\"]([^'\"]*)['\"]\s*\))?\]",
        ]:
            m = re.search(pat, line, re.I)
            if m:
                method = m.group(1).replace("Http", "").upper()
                route = (m.group(2) or "").strip()
                routes.append(f"{method} {route}".strip())

    def uniq(values: list[str], cap: int = 40) -> list[str]:
        seen = set(); out = []
        for v in values:
            if v and v not in seen:
                seen.add(v); out.append(v)
            if len(out) >= cap:
                break
        return out

    return {
        "imports": uniq(imports, 30),
        "classes": uniq(classes, 30),
        "types": uniq(types, 30),
        "functions": uniq(functions, 50),
        "exports": uniq(exports, 30),
        "routes": uniq(routes, 30),
        "lines": len(lines),
    }


def detect_framework_hints(manifest_texts: dict[str, str]) -> list[str]:
    corpus = "\n".join(manifest_texts.values()).lower()
    patterns = {
        "React": ["\"react\"", "react-dom"],
        "Next.js": ["\"next\""],
        "Vue": ["\"vue\""],
        "Svelte": ["\"svelte\""],
        "Express": ["\"express\""],
        "NestJS": ["@nestjs/"],
        "Tauri": ["@tauri-apps", "tauri ="],
        "Django": ["django"],
        "FastAPI": ["fastapi"],
        "Flask": ["flask"],
        ".NET": ["microsoft.net.sdk", "<targetframework>"],
        "ASP.NET Core": ["microsoft.net.sdk.web", "aspnetcore"],
        "Spring": ["spring-boot", "org.springframework"],
        "Rails": ["rails"],
        "Laravel": ["laravel/framework"],
    }
    found = []
    for name, needles in patterns.items():
        if any(n in corpus for n in needles):
            found.append(name)
    return found


def importance_score(path: str, summary: dict[str, Any], is_manifest_file: bool, is_entry: bool) -> int:
    score = 0
    lower = path.lower()
    if is_entry: score += 30
    if is_manifest_file: score += 20
    if any(x in lower for x in ("router", "route", "controller", "service", "main", "index", "app", "server")): score += 8
    if any(x in lower for x in ("auth", "security", "payment", "database", "db", "config")): score += 5
    score += min(len(summary.get("imports", [])), 10)
    score += min(len(summary.get("classes", [])) * 2, 10)
    score += min(len(summary.get("functions", [])) // 3, 8)
    score += min(len(summary.get("routes", [])) * 2, 10)
    return score


def scan_repository(root: pathlib.Path | str, max_files: int = 5000, max_file_bytes: int = 512_000,
                    include_hidden: bool = False) -> dict[str, Any]:
    root = pathlib.Path(root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Not a directory: {root}")

    files: list[dict[str, Any]] = []
    manifests: list[str] = []
    entry_points: list[str] = []
    manifest_texts: dict[str, str] = {}
    language_counts: Counter[str] = Counter()
    directory_counts: Counter[str] = Counter()
    raw_bytes = 0
    skipped_large = 0
    skipped_unreadable = 0
    scanned = 0

    for current, dirs, names in os.walk(root):
        current_path = pathlib.Path(current)
        dirs[:] = [d for d in sorted(dirs) if not should_skip_dir(d, include_hidden)]
        for name in sorted(names):
            if scanned >= max_files:
                break
            if not include_hidden and name.startswith("."):
                continue
            path = current_path / name
            rel = relpath(path, root)
            ext = path.suffix.lower()
            manifest = is_manifest(path)
            source = ext in SOURCE_EXTENSIONS
            config = ext in TEXT_CONFIG_EXTS
            if not (source or manifest or config or name in ENTRY_NAMES):
                continue

            text, size = safe_read_text(path, max_file_bytes)
            raw_bytes += size
            if text is None:
                if size > max_file_bytes: skipped_large += 1
                else: skipped_unreadable += 1
                continue

            scanned += 1
            directory_counts[path.parent.relative_to(root).as_posix() or "."] += 1
            language = SOURCE_EXTENSIONS.get(ext)
            if language:
                language_counts[language] += 1

            is_entry = name in ENTRY_NAMES or rel in {"src/main.rs", "src/lib.rs", "cmd/main.go"}
            if is_entry:
                entry_points.append(rel)
            if manifest:
                manifests.append(rel)
                manifest_texts[rel] = text[:100_000]

            summary = summarize_source(rel, text) if source else {
                "imports": [], "classes": [], "types": [], "functions": [], "exports": [], "routes": [],
                "lines": len(text.splitlines()),
            }
            item = {
                "path": rel,
                "language": language,
                "bytes": size,
                "lines": summary["lines"],
                "imports": summary["imports"],
                "classes": summary["classes"],
                "types": summary["types"],
                "functions": summary["functions"],
                "exports": summary["exports"],
                "routes": summary["routes"],
                "manifest": manifest,
                "entry_point": is_entry,
            }
            item["importance"] = importance_score(rel, item, manifest, is_entry)
            files.append(item)
        if scanned >= max_files:
            break

    files.sort(key=lambda x: (-x["importance"], x["path"]))
    important = [f["path"] for f in files if f["importance"] > 0][:25]

    reduced_core = {
        "project": {
            "root_name": root.name,
            "files_scanned": scanned,
            "languages": dict(language_counts.most_common()),
            "framework_hints": detect_framework_hints(manifest_texts),
            "manifests": sorted(set(manifests)),
        },
        "entry_points": sorted(set(entry_points)),
        "directories": [{"path": p, "files": c} for p, c in directory_counts.most_common(30)],
        "important_files": important,
        "files": files,
    }
    reduced_bytes = len(json.dumps(reduced_core, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    result = dict(reduced_core)
    result["stats"] = {
        "source_bytes_considered": raw_bytes,
        "estimated_raw_tokens": estimate_tokens_from_bytes(raw_bytes),
        "reduced_json_bytes": reduced_bytes,
        "estimated_reduced_tokens": estimate_tokens_from_bytes(reduced_bytes),
        "estimated_reduction_ratio": round(max(0.0, 1 - (reduced_bytes / raw_bytes)), 4) if raw_bytes else 0.0,
        "skipped_large_files": skipped_large,
        "skipped_unreadable_files": skipped_unreadable,
        "max_files": max_files,
        "max_file_bytes": max_file_bytes,
        "token_estimate_note": "Approximation uses UTF-8 bytes / 4; it is not a model tokenizer or billing estimate.",
    }
    return result


def inspect_file(path: pathlib.Path | str, max_file_bytes: int = 1_000_000) -> dict[str, Any]:
    path = pathlib.Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"Not a file: {path}")
    text, size = safe_read_text(path, max_file_bytes)
    if text is None:
        raise ValueError(f"File is unreadable, binary, or larger than {max_file_bytes} bytes: {path}")
    summary = summarize_source(path.name, text)
    return {
        "path": str(path),
        "language": SOURCE_EXTENSIONS.get(path.suffix.lower()),
        "bytes": size,
        **summary,
        "estimated_raw_tokens": estimate_tokens_from_bytes(size),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repo-context", description="Build compact repository context for AI agents.")
    parser.add_argument("--version", action="version", version=f"repo-context {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="Scan a repository and emit compact JSON context")
    scan.add_argument("path", nargs="?", default=".")
    scan.add_argument("--max-files", type=int, default=5000)
    scan.add_argument("--max-file-bytes", type=int, default=512_000)
    scan.add_argument("--include-hidden", action="store_true")
    scan.add_argument("--pretty", action="store_true")

    inspect = sub.add_parser("inspect", help="Extract structural metadata from one source file")
    inspect.add_argument("path")
    inspect.add_argument("--max-file-bytes", type=int, default=1_000_000)
    inspect.add_argument("--pretty", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            result = scan_repository(args.path, args.max_files, args.max_file_bytes, args.include_hidden)
        else:
            result = inspect_file(args.path, args.max_file_bytes)
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, separators=None if args.pretty else (",", ":")))
        return 0
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
