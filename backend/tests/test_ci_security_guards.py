"""CI enforcement tests — must be run automatically in every pipeline.

1. `test_no_eval_in_services` — ban `eval()` / `exec()` / `compile()` in every
   module under `backend/app/services/`.
2. `test_secret_scanner_clean` — run the same pre-commit secret scanner over
   the whole repository and require zero findings.

Both tests are DELIBERATELY strict: they must fail fast if code that would
normally slip through review reintroduces dangerous patterns.

No behaviour of the application is exercised here — these are pure static
security checks. Safe to run in any environment (no HTTP, no DB).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _run_script(script: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


# --------------------------------------------------------------------
# 1. Ban eval/exec/compile across all of backend/app/services/*
# --------------------------------------------------------------------
def test_no_eval_in_services():
    script = SCRIPTS / "check_no_eval.py"
    assert script.exists(), (
        f"Guard script missing: {script}. This is a CI-mandated check — "
        "restore it before proceeding."
    )
    result = _run_script(script)
    if result.returncode != 0:
        pytest.fail(
            "Forbidden `eval` / `exec` / `compile` builtin found under "
            "backend/app/services. Use `app.services.formula.eval_formula` "
            "or `SafeExpression` instead.\n\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_services_python_files_are_parseable():
    """Sanity check — the scanner relies on `ast.parse`. Any syntax error in a
    service module would silently bypass the ban, so the tree must be valid.
    """
    import ast

    services = REPO_ROOT / "backend" / "app" / "services"
    failures: list[str] = []
    for py in services.rglob("*.py"):
        if "__pycache__" in py.parts:
            continue
        try:
            ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        except SyntaxError as e:
            failures.append(f"{py.relative_to(REPO_ROOT)}: {e}")
    assert not failures, "Unparseable service modules:\n  " + "\n  ".join(failures)


# --------------------------------------------------------------------
# 2. Secret scanner clean over the whole repo
# --------------------------------------------------------------------
def test_secret_scanner_clean():
    script = SCRIPTS / "scan_secrets.py"
    assert script.exists(), f"Guard script missing: {script}"
    result = _run_script(script, "--all")
    if result.returncode != 0:
        pytest.fail(
            "Secret scanner found suspected credentials in the repository. "
            "Move them to environment variables and use `tests._creds` for tests.\n\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def test_secret_scanner_catches_leaks(tmp_path):
    """Negative-path guard: if someone hollows out the scanner, this test must fail."""
    script = SCRIPTS / "scan_secrets.py"
    fake = tmp_path / "leaked.py"
    fake.write_text(
        'password = "Admin!2025"\n'
        'api_key = "sk-fakefakefakefakefakefake123"\n'
    )
    result = _run_script(script, str(fake))
    assert result.returncode != 0, (
        "Scanner failed to detect a planted leak — the guard is broken.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "weak-seed-password" in result.stderr or "secret-literal" in result.stderr


def test_eval_ban_catches_leaks(tmp_path, monkeypatch):
    """Negative-path guard for eval-ban."""
    # Load scanner as a module so we can point it at a temp file.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_no_eval", str(SCRIPTS / "check_no_eval.py"),
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    fake = tmp_path / "bad_service.py"
    fake.write_text("def h(x):\n    return eval('x')\n")
    hits = m.scan_file(fake)
    assert hits, "eval-ban scanner failed to detect eval() in a fake service"


# --------------------------------------------------------------------
# 3. Formula engine invariants — belt and braces
# --------------------------------------------------------------------
def test_formula_engine_still_ast_only():
    """The public `eval_formula` API must keep raising `FormulaError` on
    unauthorized function calls, unknown vars and div/0 in strict mode. This
    guarantees the refactor never sneaks a `simpleeval`-backed silent path in.
    """
    from app.services.formula import eval_formula, FormulaError

    # Unknown variable → block
    with pytest.raises(FormulaError):
        eval_formula("unknown_var + 1", {})

    # Unauthorized function → block
    with pytest.raises(FormulaError):
        eval_formula("__import__('os')", {})

    # Div by zero (strict) → block, never silent-zero
    with pytest.raises(FormulaError):
        eval_formula("L / nr_ante", {"L": 100, "nr_ante": 0}, strict=True)

    # Legacy non-strict path keeps historical behaviour (documented)
    val = eval_formula("L / nr_ante", {"L": 100, "nr_ante": 0}, strict=False)
    assert str(val) == "0"
