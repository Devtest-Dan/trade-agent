"""Safe expression evaluator for playbook dynamic expressions.

Supports:
  ind.<id>.<field>     — current indicator value
  prev.<id>.<field>    — previous bar's indicator value
  var.<name>           — playbook variable
  _price               — current mid price
  trade.<field>        — open trade field (open_price, sl, tp, lot, pnl)
  risk.<field>         — risk config field
  Arithmetic           — +, -, *, / with parentheses
  Functions            — abs(), min(), max(), round(), sqrt(), log(), clamp()
  Ternary              — if(condition, true_val, false_val)

Uses Python's ast module for safe parsing — no eval().
"""

import ast
import math
import operator
from typing import Any

from loguru import logger


# Allowed binary operations
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

# Built-in math functions (name -> (callable, arg_count))
_FUNCTIONS: dict[str, tuple[Any, int]] = {
    "abs": (abs, 1),
    "min": (min, 2),
    "max": (max, 2),
    "round": (lambda x, n=0: round(x, int(n)), 2),
    "sqrt": (math.sqrt, 1),
    "log": (math.log, 1),
    "clamp": (lambda val, lo, hi: max(lo, min(val, hi)), 3),
}

# Allowed comparison operations
_CMPS = {
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}


class ExpressionContext:
    """Provides named values for expression evaluation.

    Build this from the current market state before evaluating expressions.
    """

    def __init__(
        self,
        indicators: dict[str, dict[str, float]] | None = None,
        prev_indicators: dict[str, dict[str, float]] | None = None,
        variables: dict[str, Any] | None = None,
        price: float = 0.0,
        trade: dict[str, float] | None = None,
        risk: dict[str, float] | None = None,
    ):
        self.indicators = indicators or {}  # {"h4_rsi": {"value": 45.2}, ...}
        self.prev_indicators = prev_indicators or {}
        self.variables = variables or {}
        self.price = price
        self.trade = trade or {}
        self.risk = risk or {}

    def resolve(self, name: str) -> float:
        """Resolve a dotted name to a float value.

        Examples:
            ind.h4_rsi.value  → self.indicators["h4_rsi"]["value"]
            prev.m15_rsi.value → self.prev_indicators["m15_rsi"]["value"]
            var.initial_sl    → self.variables["initial_sl"]
            _price            → self.price
            trade.open_price  → self.trade["open_price"]
            risk.max_lot      → self.risk["max_lot"]
        """
        if name == "_price":
            return float(self.price)

        parts = name.split(".")

        if parts[0] == "ind" and len(parts) == 3:
            ind_id, field = parts[1], parts[2]
            ind_data = self.indicators.get(ind_id, {})
            val = ind_data.get(field)
            if val is None:
                raise ValueError(f"Indicator '{ind_id}' field '{field}' not found")
            return float(val)

        if parts[0] == "prev" and len(parts) == 3:
            ind_id, field = parts[1], parts[2]
            ind_data = self.prev_indicators.get(ind_id, {})
            val = ind_data.get(field)
            if val is None:
                raise ValueError(f"Previous indicator '{ind_id}' field '{field}' not found")
            return float(val)

        if parts[0] == "var" and len(parts) == 2:
            var_name = parts[1]
            val = self.variables.get(var_name)
            if val is None:
                raise ValueError(f"Variable '{var_name}' not found")
            return float(val)

        if parts[0] == "trade" and len(parts) == 2:
            field = parts[1]
            val = self.trade.get(field)
            if val is None:
                raise ValueError(f"Trade field '{field}' not found")
            return float(val)

        if parts[0] == "risk" and len(parts) == 2:
            field = parts[1]
            val = self.risk.get(field)
            if val is None:
                raise ValueError(f"Risk field '{field}' not found")
            return float(val)

        raise ValueError(f"Cannot resolve name: {name}")


def evaluate_expr(expr_str: str, ctx: ExpressionContext) -> float:
    """Evaluate a dynamic expression string safely using AST parsing.

    Examples:
        "ind.h4_atr.value * 1.5"
        "_price - ind.h4_atr.value * 2"
        "var.initial_sl + 10"
        "risk.max_lot"
    """
    try:
        # Pre-process: rewrite iff(...) calls since 'if' is a Python keyword.
        # We use 'iff' as the user-facing name and '_iff_' internally.
        cleaned = expr_str.strip().replace("iff(", "_iff_(")
        tree = ast.parse(cleaned, mode="eval")
        return _eval_node(tree.body, ctx)
    except Exception as e:
        logger.error(f"Expression evaluation failed: '{expr_str}' — {e}")
        raise ValueError(f"Invalid expression: {expr_str}") from e


def _eval_node(node: ast.AST, ctx: ExpressionContext) -> float:
    """Recursively evaluate an AST node."""

    # Numeric literal: 1.5, 30, etc.
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)

    # Unary minus: -1.5, -ind.h4_rsi.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_node(node.operand, ctx)

    # Unary plus
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd):
        return _eval_node(node.operand, ctx)

    # Binary operation: a + b, a * b, etc.
    if isinstance(node, ast.BinOp):
        op_func = _OPS.get(type(node.op))
        if op_func is None:
            raise ValueError(f"Unsupported operator: {type(node.op).__name__}")
        left = _eval_node(node.left, ctx)
        right = _eval_node(node.right, ctx)
        if isinstance(node.op, ast.Div) and right == 0:
            raise ValueError("Division by zero")
        return op_func(left, right)

    # Simple name: _price
    if isinstance(node, ast.Name):
        return ctx.resolve(node.id)

    # Dotted attribute: ind.h4_rsi.value
    if isinstance(node, ast.Attribute):
        name = _reconstruct_dotted(node)
        return ctx.resolve(name)

    # Function call: abs(...), min(...), max(...), if(cond, a, b), etc.
    if isinstance(node, ast.Call):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        else:
            raise ValueError(f"Only named function calls are supported")

        # Special: iff(left op right, true_val, false_val)
        # Syntax: iff(a > b, x, y) — parsed as _iff_(Compare, val, val)
        if func_name == "_iff_":
            if len(node.args) != 3:
                raise ValueError("if() requires 3 arguments: if(condition, true_val, false_val)")
            cond_node = node.args[0]
            true_val = _eval_node(node.args[1], ctx)
            false_val = _eval_node(node.args[2], ctx)
            # Evaluate condition (must be a Compare node)
            if isinstance(cond_node, ast.Compare) and len(cond_node.ops) == 1:
                left = _eval_node(cond_node.left, ctx)
                right = _eval_node(cond_node.comparators[0], ctx)
                op_type = type(cond_node.ops[0])
                cmp_map = {
                    ast.Lt: operator.lt, ast.Gt: operator.gt,
                    ast.LtE: operator.le, ast.GtE: operator.ge,
                    ast.Eq: operator.eq, ast.NotEq: operator.ne,
                }
                cmp_func = cmp_map.get(op_type)
                if cmp_func is None:
                    raise ValueError(f"Unsupported comparison in if(): {op_type.__name__}")
                return true_val if cmp_func(left, right) else false_val
            else:
                raise ValueError("if() first argument must be a comparison (e.g., a > b)")

        # Built-in math functions
        func_info = _FUNCTIONS.get(func_name)
        if func_info is None:
            raise ValueError(f"Unknown function: {func_name}(). Available: {', '.join(sorted(_FUNCTIONS))} + iff()")

        func, expected_args = func_info
        args = [_eval_node(a, ctx) for a in node.args]

        # round() allows 1 arg (defaults to 0 decimals)
        if func_name == "round" and len(args) == 1:
            return float(round(args[0]))
        if len(args) != expected_args:
            raise ValueError(f"{func_name}() takes {expected_args} argument(s), got {len(args)}")
        return float(func(*args))

    raise ValueError(f"Unsupported expression node: {type(node).__name__}")


def _reconstruct_dotted(node: ast.AST) -> str:
    """Reconstruct a dotted name from nested Attribute nodes."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _reconstruct_dotted(node.value)
        return f"{parent}.{node.attr}"
    raise ValueError(f"Cannot reconstruct name from {type(node).__name__}")


def evaluate_condition(condition: dict, ctx: ExpressionContext) -> bool:
    """Evaluate a CheckCondition dict (type: AND/OR, rules: [...]).

    Each rule has: left, operator, right — all expression strings.
    """
    cond_type = condition.get("type", "AND")
    rules = condition.get("rules", [])

    if not rules:
        return False

    results = []
    for rule in rules:
        left_val = evaluate_expr(rule["left"], ctx)
        right_val = evaluate_expr(rule["right"], ctx)
        cmp_op = _CMPS.get(rule["operator"])
        if cmp_op is None:
            raise ValueError(f"Unknown operator: {rule['operator']}")
        results.append(cmp_op(left_val, right_val))

    if cond_type == "AND":
        return all(results)
    elif cond_type == "OR":
        return any(results)
    else:
        raise ValueError(f"Unknown condition type: {cond_type}")


def evaluate_condition_detailed(
    condition: dict, ctx: ExpressionContext
) -> tuple[bool, list[dict]]:
    """Evaluate condition and return per-rule results with values.

    Returns (overall_result, [{"description": ..., "left_val": ..., "right_val": ..., "passed": bool}, ...])
    """
    cond_type = condition.get("type", "AND")
    rules = condition.get("rules", [])

    if not rules:
        return False, []

    rule_results = []
    for rule in rules:
        left_val = evaluate_expr(rule["left"], ctx)
        right_val = evaluate_expr(rule["right"], ctx)
        cmp_op = _CMPS.get(rule["operator"])
        if cmp_op is None:
            raise ValueError(f"Unknown operator: {rule['operator']}")
        passed = cmp_op(left_val, right_val)
        rule_results.append({
            "description": rule.get("description", ""),
            "left_expr": rule["left"],
            "left_val": round(left_val, 4),
            "operator": rule["operator"],
            "right_expr": rule["right"],
            "right_val": round(right_val, 4),
            "passed": passed,
        })

    if cond_type == "AND":
        overall = all(r["passed"] for r in rule_results)
    elif cond_type == "OR":
        overall = any(r["passed"] for r in rule_results)
    else:
        raise ValueError(f"Unknown condition type: {cond_type}")

    return overall, rule_results
