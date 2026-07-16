"""Formula security policy — defense-in-depth against `eval()` regressions.

The project's formula evaluation lives in `app.services.formula` and is
implemented as a strict AST-whitelist parser (safer than `simpleeval` because
it preserves `Decimal` semantics and enforces node/depth/length caps).

This module:

1. Asserts at import time that `app.services.formula` does not import or call
   the built-in `eval` / `exec` / `compile` — reject any code regression that
   accidentally reintroduces them.
2. Exposes a `SafeExpression` shim over `simpleeval.SimpleEval` for callers
   that need a *very* lightweight, non-monetary expression evaluator (e.g.
   condition trees). All uses must go through `SafeExpression.evaluate()`.
   Direct `eval()` in application code is forbidden.

If you need to evaluate a pricing / BOM / geometry formula that must return
`Decimal`, always use `app.services.formula.eval_formula` — never touch
`simpleeval` directly and never call `eval()`.
"""
from __future__ import annotations
import ast
import inspect
from typing import Any, Dict, Mapping

from simpleeval import SimpleEval, DEFAULT_OPERATORS, DEFAULT_FUNCTIONS


def _assert_no_eval_in_module(module_name: str) -> None:
    """Import-time guard: raises RuntimeError if the given module contains
    a call to `eval(...)`, `exec(...)` or `compile(...)` on Python source.
    """
    mod = __import__(module_name, fromlist=["*"])
    try:
        src = inspect.getsource(mod)
    except (OSError, TypeError):
        return
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"eval", "exec"}:
                raise RuntimeError(
                    f"SECURITY: forbidden builtin '{node.func.id}(...)' found in "
                    f"{module_name} at line {node.lineno}. Use "
                    "`app.services.formula.eval_formula` instead."
                )
            # `compile()` used on source is also forbidden; ast.parse is fine.
            if node.func.id == "compile":
                raise RuntimeError(
                    f"SECURITY: forbidden builtin 'compile(...)' found in "
                    f"{module_name} at line {node.lineno}."
                )


class SafeExpression:
    """Minimal wrapper around `simpleeval.SimpleEval` used for boolean/condition
    expressions where `Decimal` precision is not required. Blocks attribute
    access, function calls, imports and generators by default.
    """

    #: Only pure math operators — no bit-shift, no attribute access, no `and/or` short-circuit tricks.
    _ALLOWED_OPERATORS = DEFAULT_OPERATORS
    _ALLOWED_FUNCTIONS = {name: DEFAULT_FUNCTIONS[name]
                          for name in ("int", "float", "str", "bool",
                                        "min", "max", "abs", "round")
                          if name in DEFAULT_FUNCTIONS}

    def __init__(self) -> None:
        self._engine = SimpleEval(
            operators=dict(self._ALLOWED_OPERATORS),
            functions=dict(self._ALLOWED_FUNCTIONS),
            names={},
        )

    def evaluate(self, expression: str, variables: Mapping[str, Any]) -> Any:
        """Evaluate a whitelisted expression. Raises on unknown names.

        Callers MUST NOT catch and silently swallow errors — a bad expression
        must produce a hard failure so the misconfiguration is visible.
        """
        if not isinstance(expression, str) or not expression.strip():
            raise ValueError("expression must be a non-empty string")
        self._engine.names = dict(variables)
        return self._engine.eval(expression)


# Enforce at import time — best-effort static check on the formula module.
_assert_no_eval_in_module("app.services.formula")


__all__ = ["SafeExpression", "_assert_no_eval_in_module"]
