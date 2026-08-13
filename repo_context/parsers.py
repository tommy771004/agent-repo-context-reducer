from __future__ import annotations

import ast
import pathlib
import re
from typing import Any

from .util import compact_signature, uniq

JS_EXTS = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte"}
C_EXTS = {".c", ".h", ".cc", ".cpp", ".hpp"}
SHELL_EXTS = {".sh", ".bash", ".zsh"}

# Control-flow keywords that look like C call sites but are not definitions.
C_NON_FUNCTIONS = {"if", "for", "while", "switch", "catch", "return", "sizeof", "do", "else"}

C_INCLUDE_RE = re.compile(r'^#include\s+(?:"([^"]+)"|<([^>]+)>)')
C_FUNCTION_RE = re.compile(r"^(?:[A-Za-z_][\w:<>,\s\*&]*?[\s\*&])([A-Za-z_]\w*)\s*\((.*?)\)\s*(?:const\s*)?\{")
SHELL_SOURCE_RE = re.compile(r"^(?:source|\.)\s+([^\s;|&]+)")
SHELL_FUNCTION_RE = re.compile(r"^(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\s*\)\s*\{")
SHELL_FUNCTION_KW_RE = re.compile(r"^function\s+([A-Za-z_][\w-]*)\s*\{")
PS_IMPORT_RE = re.compile(r"^Import-Module\s+([^\s;]+)", re.I)
PS_DOTSOURCE_RE = re.compile(r"^\.\s+([.\\/][^\s;]+)")
PS_FUNCTION_RE = re.compile(r"^function\s+([A-Za-z_][\w-]*)", re.I)
SQL_OBJECT_RE = re.compile(
    r"^CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)\s+|GLOBAL\s+|UNIQUE\s+|MATERIALIZED\s+)?"
    r"(TABLE|VIEW|TYPE|SCHEMA|INDEX|TRIGGER|PROCEDURE|FUNCTION)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)",
    re.I,
)


def _empty(lines: int) -> dict[str, Any]:
    return {
        "imports": [], "classes": [], "types": [], "functions": [],
        "exports": [], "routes": [], "symbols": [], "lines": lines,
        "parser": "heuristic",
    }


def parse_python(text: str) -> dict[str, Any]:
    result = _empty(len(text.splitlines()))
    result["parser"] = "python-ast"
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return parse_heuristic("file.py", text)

    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    types: list[str] = []
    symbols: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append("." * node.level + (node.module or ""))
        elif isinstance(node, ast.ClassDef):
            classes.append(node.name)
            symbols.append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            sig = f"{node.name}({', '.join(args)})"
            functions.append(sig)
            symbols.append(node.name)
        elif isinstance(node, (ast.AnnAssign, ast.Assign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id[:1].isupper():
                    types.append(target.id)
    result.update({
        "imports": uniq(imports, 40), "classes": uniq(classes, 40),
        "types": uniq(types, 40), "functions": uniq(functions, 80),
        "symbols": uniq(symbols, 100),
    })
    return result


def parse_heuristic(path: str, text: str) -> dict[str, Any]:
    ext = pathlib.Path(path).suffix.lower()
    result = _empty(len(text.splitlines()))
    imports: list[str] = []
    classes: list[str] = []
    functions: list[str] = []
    types: list[str] = []
    routes: list[str] = []
    exports: list[str] = []
    symbols: list[str] = []
    lines = text.splitlines()

    # Join lightweight multi-line signatures without parsing bodies.
    logical_lines: list[str] = []
    buffer = ""
    paren_balance = 0
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        if buffer:
            buffer += " " + stripped
        else:
            buffer = stripped
        paren_balance += stripped.count("(") - stripped.count(")")
        if paren_balance <= 0 or len(buffer) > 500:
            logical_lines.append(buffer)
            buffer = ""
            paren_balance = 0
    if buffer:
        logical_lines.append(buffer)

    for line in logical_lines:
        # `#` is a comment in shell/PowerShell/Ruby, but a C preprocessor include is a real import.
        if line.startswith("#") and not (ext in C_EXTS and line.startswith("#include")):
            continue
        if line.startswith(("//", "/*", "*")):
            continue

        if ext in JS_EXTS:
            for match in re.finditer(r"(?:from\s+|require\s*\(\s*)['\"]([^'\"]+)['\"]", line):
                imports.append(match.group(1))
            for match in re.finditer(r"(?:import\s*\(\s*)['\"]([^'\"]+)['\"]", line):
                imports.append(match.group(1))
        elif ext == ".rs":
            m = re.match(r"(?:use|mod)\s+([^;{]+)", line)
            if m: imports.append(compact_signature(m.group(1)))
        elif ext == ".go":
            m = re.match(r"import\s+(?:\w+\s+)?[\"`]([^\"`]+)", line)
            if m: imports.append(m.group(1))
        elif ext in {".cs", ".java", ".kt", ".kts"}:
            m = re.match(r"(?:using|import)\s+([^;]+)", line)
            if m: imports.append(m.group(1))
        elif ext in C_EXTS:
            m = C_INCLUDE_RE.match(line)
            if m:
                # Quoted includes are project-local by C convention; angle includes are system/external.
                imports.append(f"./{m.group(1)}" if m.group(1) else m.group(2))
        elif ext in SHELL_EXTS:
            m = SHELL_SOURCE_RE.match(line)
            if m and not m.group(1).startswith("$"):
                imports.append(m.group(1).strip("'\""))
        elif ext == ".ps1":
            m = PS_IMPORT_RE.match(line)
            if m:
                imports.append(m.group(1).strip("'\""))
            else:
                m = PS_DOTSOURCE_RE.match(line)
                if m: imports.append(m.group(1).replace("\\", "/"))

        if ext == ".sql":
            m = SQL_OBJECT_RE.match(line)
            if m:
                kind, name = m.group(1).upper(), m.group(2)
                if kind in {"PROCEDURE", "FUNCTION"}:
                    functions.append(f"{name}()")
                else:
                    types.append(name)
                symbols.append(name)
            continue

        for pat in [
            r"^(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+([A-Za-z_]\w*)",
            r"^(?:public\s+|private\s+|internal\s+|protected\s+)?(?:abstract\s+|sealed\s+|static\s+)?class\s+([A-Za-z_]\w*)",
            r"^(?:pub\s+)?struct\s+([A-Za-z_]\w*)",
        ]:
            m = re.match(pat, line)
            if m:
                classes.append(m.group(1)); symbols.append(m.group(1)); break

        for pat in [
            r"^(?:export\s+)?interface\s+([A-Za-z_]\w*)",
            r"^(?:export\s+)?type\s+([A-Za-z_]\w*)",
            r"^(?:pub\s+)?(?:enum|trait)\s+([A-Za-z_]\w*)",
            r"^(?:public\s+)?(?:interface|enum|record)\s+([A-Za-z_]\w*)",
        ]:
            m = re.match(pat, line)
            if m:
                types.append(m.group(1)); symbols.append(m.group(1)); break

        fn_name = None
        fn_args = ""
        if ext in JS_EXTS:
            m = re.match(r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\((.*?)\)", line)
            if not m:
                m = re.match(r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?\((.*?)\)\s*=>", line)
            if not m:
                m = re.match(r"^(?:export\s+)?(?:const|let|var)\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?([A-Za-z_]\w*)\s*=>", line)
            if m:
                fn_name, fn_args = m.group(1), m.group(2)
        elif ext == ".rs":
            m = re.match(r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?fn\s+([A-Za-z_]\w*)\s*\((.*?)\)", line)
            if m: fn_name, fn_args = m.group(1), m.group(2)
        elif ext == ".go":
            m = re.match(r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\((.*?)\)", line)
            if m: fn_name, fn_args = m.group(1), m.group(2)
        elif ext in {".cs", ".java", ".kt", ".kts", ".swift", ".php"}:
            if "(" in line and ")" in line and not re.match(r"^(if|for|while|switch|catch|foreach)\b", line):
                m = re.search(r"([A-Za-z_]\w*)\s*\((.*?)\)", line)
                if m and m.group(1) not in {"if", "for", "while", "switch", "catch", "new", "return"}:
                    fn_name, fn_args = m.group(1), m.group(2)
        elif ext in C_EXTS:
            m = C_FUNCTION_RE.match(line)
            if m and m.group(1) not in C_NON_FUNCTIONS:
                fn_name, fn_args = m.group(1), m.group(2)
        elif ext in SHELL_EXTS:
            m = SHELL_FUNCTION_RE.match(line) or SHELL_FUNCTION_KW_RE.match(line)
            if m: fn_name, fn_args = m.group(1), ""
        elif ext == ".ps1":
            m = PS_FUNCTION_RE.match(line)
            if m: fn_name, fn_args = m.group(1), ""
        if fn_name:
            functions.append(compact_signature(f"{fn_name}({fn_args})"))
            symbols.append(fn_name)

        if re.match(r"^export\s+", line):
            m = re.search(r"(?:class|function|const|let|var|interface|type|enum)\s+([A-Za-z_]\w*)", line)
            if m: exports.append(m.group(1))

        for pat in [
            r"\b(?:app|router)\.(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)",
            r"\[(HttpGet|HttpPost|HttpPut|HttpPatch|HttpDelete)(?:\(\s*['\"]([^'\"]*)['\"]\s*\))?\]",
            r"@(get|post|put|patch|delete)\s*\(\s*['\"]([^'\"]+)",
        ]:
            m = re.search(pat, line, re.I)
            if m:
                method = m.group(1).replace("Http", "").upper()
                routes.append(f"{method} {(m.group(2) or '').strip()}".strip())

    result.update({
        "imports": uniq(imports, 40), "classes": uniq(classes, 40),
        "types": uniq(types, 40), "functions": uniq(functions, 80),
        "exports": uniq(exports, 40), "routes": uniq(routes, 40),
        "symbols": uniq(symbols + classes + types + exports, 120),
    })
    return result


def summarize_source(path: str, text: str) -> dict[str, Any]:
    if pathlib.Path(path).suffix.lower() == ".py":
        return parse_python(text)
    return parse_heuristic(path, text)
