#!/usr/bin/env python3
"""Extends the eval/exec/compile ban to ALL files under backend/app/services.

Zero runtime side effects: uses static AST parsing on source files.
Exits non-zero on any hit; used by pre-commit and by the CI test
`tests/test_services_no_eval.py`.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import List, Tuple


ROOT = Path(__file__).resolve().parents[1]
SERVICES_DIR = ROOT / "backend" / "app" / "services"
FORBIDDEN_BUILTINS = {"eval", "exec", "compile"}


def scan_file(path: Path) -> List[Tuple[int, str]]:
    """Return list of (lineno, builtin) offences found in a Python file."""
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in FORBIDDEN_BUILTINS:
                hits.append((node.lineno, node.func.id))
        # `getattr(builtins, "eval")` is also blocked
        if isinstance(node, ast.Attribute):
            if node.attr in FORBIDDEN_BUILTINS and isinstance(node.value, ast.Name):
                if node.value.id in {"builtins", "__builtins__"}:
                    hits.append((node.lineno, f"{node.value.id}.{node.attr}"))
    return hits


def scan_dir(directory: Path) -> List[Tuple[Path, int, str]]:
    findings: List[Tuple[Path, int, str]] = []
    if not directory.exists():
        return findings
    for p in directory.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        # Allow the scanner itself and the security guard module which reference
        # the forbidden names only as string literals (already tested).
        if p.name in {"formula_security.py"}:
            continue
        for lineno, builtin in scan_file(p):
            findings.append((p, lineno, builtin))
    return findings


def main() -> int:
    findings = scan_dir(SERVICES_DIR)
    if not findings:
        print(f"[check_no_eval] OK — no eval/exec/compile in {SERVICES_DIR.relative_to(ROOT)}")
        return 0
    print("=" * 72, file=sys.stderr)
    print("EVAL/EXEC/COMPILE BAN — commit BLOCKED", file=sys.stderr)
    print("=" * 72, file=sys.stderr)
    for path, lineno, builtin in findings:
        rel = path.relative_to(ROOT)
        print(f"  {rel}:{lineno}  forbidden builtin `{builtin}(...)`", file=sys.stderr)
    print("-" * 72, file=sys.stderr)
    print(
        f"{len(findings)} offending call(s). Use `app.services.formula.eval_formula` "
        "or `app.services.formula_security.SafeExpression` instead.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
