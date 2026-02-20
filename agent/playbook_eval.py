"""Safe expression evaluator for playbook dynamic expressions.

Supports:
  ind.<id>.<field>     — current indicator value
  prev.<id>.<field>    — previous bar's indicator value
  var.<name>           — playbook variable
  _price               — current mid price
  trade.<field>        — open trade field (open_price, sl, tp, lot, pnl)
  risk.<field>         — risk config field
  Arithmetic           — +, -, *, / with parentheses

Uses Python's ast module for safe parsing — no eval().
"""

import ast
import operator
from typing import Any

from loguru import logger


# Allowed binary operations
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
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
        tree = ast.parse(expr_str.strip(), mode="eval")
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
        # Reconstruct the dotted name
        name = _reconstruct_dotted(node)
        return ctx.resolve(name)

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
