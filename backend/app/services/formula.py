"""Secure formula engine for pricelist rules.

Uses Python's built-in `ast` module with a strict whitelist of node types.
No eval/exec/compile of arbitrary strings. No attribute access, no calls except
whitelisted functions, no imports, no name lookups outside whitelist.

Supported:
  - Numeric literals (int, float)
  - Binary ops: + - * /
  - Unary ops: + -
  - Parentheses
  - Comparisons: == != < <= > >= (numeric only)
  - Boolean ops: `and`, `or`, `not`
  - Conditional: `a if cond else b`
  - Whitelisted functions: min, max, round, ceil, floor, abs

Variables must come from a `context: dict` provided at eval time.
Missing variables → 0.0 (safe default).

Safety limits:
  - Max formula length: 500 chars
  - Max AST depth: 20
  - Max node count: 200
  - Division by zero returns 0.0 (never raises)

Return type: Decimal — monetary math uses Decimal, never binary float.
"""
from __future__ import annotations
import ast
import math
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, Set

getcontext().prec = 28

MAX_LEN = 500
MAX_DEPTH = 20
MAX_NODES = 200

# Modalità strict per formule parametriche BOM/produzione.
# In modalità strict, div/0 diventa un errore bloccante.
# Le regole legacy pricing_v2 non usano strict (mantengono div/0 → 0 per retro-compatibilità).
from contextvars import ContextVar
_STRICT: ContextVar[bool] = ContextVar("_STRICT_FORMULA", default=False)


class strict_mode:
    """Context manager per abilitare la modalità strict.
    Uso:
        with strict_mode():
            eval_formula("L / nr_ante", ctx)  # div/0 solleva FormulaError DIV_ZERO
    """
    def __enter__(self):
        self._token = _STRICT.set(True)
        return self

    def __exit__(self, *a):
        _STRICT.reset(self._token)

ALLOWED_FUNCTIONS = {
    "min": min,
    "max": max,
    "round": round,
    "ceil": math.ceil,
    "floor": math.floor,
    "abs": abs,
}

ALLOWED_VARIABLES = {
    # legacy pricing rules
    "width", "height", "area", "billable_area", "perimeter",
    "linear_meters", "quantity", "leaves", "weight",
    "base_price", "base_cost",
    "sqm", "min_billable_sqm",
    # parametric engine — dimensioni foro/luce
    "L", "H", "width_mm", "height_mm",
    # parametric engine — contatori
    "nr_ante", "nr_traversi", "nr_montanti", "nr_fissi", "nr_vetri",
    # parametric engine — taglio
    "kerf", "bar_length",
    # parametric engine — profilo/sistema (tech params)
    "frame_width", "frame_depth", "sash_width", "sash_depth",
    "frame_clearance", "sash_clearance", "glass_clearance",
    "glazing_bead_clearance", "weld_allowance",
    "overlap", "rebate", "threshold_height",
    "mullion_offset", "transom_offset", "coupling_gap",
    "installation_gap", "profile_length_adjustment", "central_node",
    "glass_deduction",
    # derived
    "glass_width", "glass_height", "glass_area", "glass_weight",
    "profile_weight", "total_weight",
    # per componente
    "component_index",
}


class FormulaError(Exception):
    """Errore bloccante di valutazione formula.
    Attributi:
      code: DIV_ZERO | SYNTAX | LIMIT | UNKNOWN_VAR | UNSAFE_NODE | UNSAFE_FN | NON_NUMERIC | INFINITE
      formula: espressione originale
      severity: blocking | warning
    """
    def __init__(self, message: str, *, code: str = "GENERIC", formula: str = "",
                 severity: str = "blocking", meta: dict | None = None):
        super().__init__(message)
        self.code = code
        self.formula = formula
        self.severity = severity
        self.meta = meta or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code, "message": str(self),
            "formula": self.formula, "severity": self.severity, "meta": self.meta,
        }


def _depth(node: ast.AST, current: int = 0) -> int:
    if current > MAX_DEPTH:
        raise FormulaError(f"Formula troppo profonda (>{MAX_DEPTH})")
    max_c = current
    for child in ast.iter_child_nodes(node):
        d = _depth(child, current + 1)
        if d > max_c:
            max_c = d
    return max_c


def _count_nodes(tree: ast.AST) -> int:
    return sum(1 for _ in ast.walk(tree))


def _eval(node: ast.AST, ctx: Dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval(node.body, ctx)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return Decimal(str(node.value))
        if isinstance(node.value, bool):
            return node.value
        raise FormulaError("Costante non supportata")
    if isinstance(node, ast.Num):  # legacy py<3.8
        return Decimal(str(node.n))
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_VARIABLES:
            raise FormulaError(f"Variabile non autorizzata: {node.id}")
        val = ctx.get(node.id, 0)
        return Decimal(str(val or 0))
    if isinstance(node, ast.BinOp):
        left = _eval(node.left, ctx)
        right = _eval(node.right, ctx)
        if isinstance(node.op, ast.Add): return left + right
        if isinstance(node.op, ast.Sub): return left - right
        if isinstance(node.op, ast.Mult): return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                if _STRICT.get():
                    raise FormulaError(
                        "Divisione per zero", code="DIV_ZERO",
                        meta={"left": str(left), "right": str(right)},
                    )
                return Decimal("0")
            return left / right
        raise FormulaError("Operatore non supportato")
    if isinstance(node, ast.UnaryOp):
        val = _eval(node.operand, ctx)
        if isinstance(node.op, ast.UAdd): return +val
        if isinstance(node.op, ast.USub): return -val
        if isinstance(node.op, ast.Not): return not _to_bool(val)
        raise FormulaError("Operatore unario non supportato")
    if isinstance(node, ast.Compare):
        left = _eval(node.left, ctx)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval(comparator, ctx)
            if isinstance(op, ast.Eq):
                if not (left == right): return False
            elif isinstance(op, ast.NotEq):
                if not (left != right): return False
            elif isinstance(op, ast.Lt):
                if not (left < right): return False
            elif isinstance(op, ast.LtE):
                if not (left <= right): return False
            elif isinstance(op, ast.Gt):
                if not (left > right): return False
            elif isinstance(op, ast.GtE):
                if not (left >= right): return False
            else:
                raise FormulaError("Confronto non supportato")
            left = right
        return True
    if isinstance(node, ast.BoolOp):
        vals = [_to_bool(_eval(v, ctx)) for v in node.values]
        if isinstance(node.op, ast.And): return all(vals)
        if isinstance(node.op, ast.Or): return any(vals)
        raise FormulaError("Operatore booleano non supportato")
    if isinstance(node, ast.IfExp):
        return _eval(node.body, ctx) if _to_bool(_eval(node.test, ctx)) else _eval(node.orelse, ctx)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("Chiamata di funzione non autorizzata")
        fname = node.func.id
        if fname not in ALLOWED_FUNCTIONS:
            raise FormulaError(f"Funzione non autorizzata: {fname}")
        args = [_eval(a, ctx) for a in node.args]
        # coerce to Decimal or float for math
        if fname in ("min", "max"):
            return min(args) if fname == "min" else max(args)
        if fname == "abs":
            return abs(args[0])
        if fname == "round":
            digits = int(args[1]) if len(args) > 1 else 2
            q = Decimal("1").scaleb(-digits)
            return (Decimal(args[0]).quantize(q, rounding=ROUND_HALF_UP))
        if fname == "ceil":
            return Decimal(math.ceil(Decimal(args[0])))
        if fname == "floor":
            return Decimal(math.floor(Decimal(args[0])))
    raise FormulaError(f"Nodo non supportato: {type(node).__name__}")


def _to_bool(v: Any) -> bool:
    if isinstance(v, Decimal):
        return v != 0
    return bool(v)


def validate_formula(expr: str) -> tuple[bool, str]:
    """Validate without evaluating. Returns (ok, error_message)."""
    if not expr or not expr.strip():
        return False, "Formula vuota"
    if len(expr) > MAX_LEN:
        return False, f"Formula troppo lunga (>{MAX_LEN} caratteri)"
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return False, f"Sintassi non valida: {e.msg}"
    try:
        _depth(tree)
        if _count_nodes(tree) > MAX_NODES:
            return False, f"Formula troppo complessa (>{MAX_NODES} nodi)"
        # Dry-run with all-zero ctx to catch unknown vars/funcs
        _eval(tree, {v: Decimal("1") for v in ALLOWED_VARIABLES})
    except FormulaError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Errore di validazione: {e}"
    return True, ""


def eval_formula(expr: str, context: Dict[str, Any], *, strict: bool | None = None) -> Decimal:
    """Evaluate a formula against provided context. Raises FormulaError on invalid input.
    Returns Decimal.

    strict:
      - None (default): usa ContextVar attivo (default False)
      - True: DIV_ZERO/INFINITE diventano FormulaError bloccanti
      - False: DIV_ZERO → 0 (comportamento legacy pricing_v2)
    """
    if not expr or not expr.strip():
        raise FormulaError("Formula vuota", code="SYNTAX", formula=expr)
    if len(expr) > MAX_LEN:
        raise FormulaError(f"Formula troppo lunga (>{MAX_LEN} caratteri)", code="LIMIT", formula=expr)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormulaError(f"Sintassi non valida: {e.msg}", code="SYNTAX", formula=expr)
    _depth(tree)
    if _count_nodes(tree) > MAX_NODES:
        raise FormulaError(f"Formula troppo complessa (>{MAX_NODES} nodi)", code="LIMIT", formula=expr)
    _tok = None
    if strict is not None:
        _tok = _STRICT.set(strict)
    try:
        result = _eval(tree, context)
    finally:
        if _tok is not None:
            _STRICT.reset(_tok)
    if isinstance(result, bool):
        return Decimal("1") if result else Decimal("0")
    if not isinstance(result, Decimal):
        result = Decimal(str(result))
    if (strict is True) or (strict is None and _STRICT.get()):
        if result.is_nan() or result.is_infinite():
            raise FormulaError("Risultato non finito", code="INFINITE",
                                formula=expr, meta={"result": str(result)})
    return result


def money(value: Any, digits: int = 2) -> Decimal:
    """Quantize to money (default 2 decimals, HALF_UP)."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    q = Decimal("1").scaleb(-digits)
    return value.quantize(q, rounding=ROUND_HALF_UP)
