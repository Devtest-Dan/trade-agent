"""Tests for agent.playbook_eval — safe expression evaluator."""

import math
import pytest
from agent.playbook_eval import (
    ExpressionContext,
    evaluate_expr,
    evaluate_condition,
    evaluate_condition_detailed,
)


@pytest.fixture
def ctx():
    """Standard context with indicators, variables, price, trade, and risk."""
    return ExpressionContext(
        indicators={
            "h4_rsi": {"value": 45.0},
            "h4_atr": {"value": 2.5},
            "m15_ema": {"value": 2050.0, "slope": 0.3},
        },
        prev_indicators={
            "h4_rsi": {"value": 42.0},
            "m15_ema": {"value": 2048.0},
        },
        variables={"threshold": 30.0, "multiplier": 1.5},
        price=2055.0,
        trade={"open_price": 2040.0, "sl": 2030.0, "tp": 2060.0, "pnl": 15.0, "lot": 0.1},
        risk={"max_lot": 1.0, "max_risk_pct": 2.0},
    )


# ── Numeric literals ───────────────────────────────────────────────

class TestLiterals:
    def test_integer(self, ctx):
        assert evaluate_expr("42", ctx) == 42.0

    def test_float(self, ctx):
        assert evaluate_expr("3.14", ctx) == 3.14

    def test_negative(self, ctx):
        assert evaluate_expr("-5", ctx) == -5.0

    def test_positive(self, ctx):
        assert evaluate_expr("+5", ctx) == 5.0


# ── Variable resolution ───────────────────────────────────────────

class TestResolution:
    def test_price(self, ctx):
        assert evaluate_expr("_price", ctx) == 2055.0

    def test_indicator(self, ctx):
        assert evaluate_expr("ind.h4_rsi.value", ctx) == 45.0

    def test_indicator_second_field(self, ctx):
        assert evaluate_expr("ind.m15_ema.slope", ctx) == 0.3

    def test_prev_indicator(self, ctx):
        assert evaluate_expr("prev.h4_rsi.value", ctx) == 42.0

    def test_variable(self, ctx):
        assert evaluate_expr("var.threshold", ctx) == 30.0

    def test_trade_field(self, ctx):
        assert evaluate_expr("trade.open_price", ctx) == 2040.0

    def test_risk_field(self, ctx):
        assert evaluate_expr("risk.max_lot", ctx) == 1.0

    def test_missing_indicator(self, ctx):
        with pytest.raises(ValueError, match="Invalid expression"):
            evaluate_expr("ind.nonexistent.value", ctx)

    def test_missing_variable(self, ctx):
        with pytest.raises(ValueError, match="Invalid expression"):
            evaluate_expr("var.nonexistent", ctx)

    def test_missing_trade_field(self, ctx):
        with pytest.raises(ValueError, match="Invalid expression"):
            evaluate_expr("trade.nonexistent", ctx)

    def test_unknown_root(self, ctx):
        with pytest.raises(ValueError, match="Invalid expression"):
            evaluate_expr("foo.bar", ctx)


# ── Arithmetic ─────────────────────────────────────────────────────

class TestArithmetic:
    def test_addition(self, ctx):
        assert evaluate_expr("10 + 20", ctx) == 30.0

    def test_subtraction(self, ctx):
        assert evaluate_expr("_price - trade.open_price", ctx) == 15.0

    def test_multiplication(self, ctx):
        assert evaluate_expr("ind.h4_atr.value * 1.5", ctx) == 3.75

    def test_division(self, ctx):
        assert evaluate_expr("100 / 4", ctx) == 25.0

    def test_modulo(self, ctx):
        assert evaluate_expr("10 % 3", ctx) == 1.0

    def test_power(self, ctx):
        assert evaluate_expr("2 ** 3", ctx) == 8.0

    def test_division_by_zero(self, ctx):
        with pytest.raises(ValueError, match="Invalid expression"):
            evaluate_expr("10 / 0", ctx)

    def test_parentheses(self, ctx):
        assert evaluate_expr("(2 + 3) * 4", ctx) == 20.0

    def test_complex_expression(self, ctx):
        # _price - ind.h4_atr.value * 2 = 2055 - 2.5*2 = 2050.0
        assert evaluate_expr("_price - ind.h4_atr.value * 2", ctx) == 2050.0


# ── Built-in functions ─────────────────────────────────────────────

class TestFunctions:
    def test_abs_positive(self, ctx):
        assert evaluate_expr("abs(10)", ctx) == 10.0

    def test_abs_negative(self, ctx):
        assert evaluate_expr("abs(-10)", ctx) == 10.0

    def test_min(self, ctx):
        assert evaluate_expr("min(10, 20)", ctx) == 10.0

    def test_max(self, ctx):
        assert evaluate_expr("max(10, 20)", ctx) == 20.0

    def test_round_two_args(self, ctx):
        assert evaluate_expr("round(3.14159, 2)", ctx) == 3.14

    def test_round_one_arg(self, ctx):
        assert evaluate_expr("round(3.7)", ctx) == 4.0

    def test_sqrt(self, ctx):
        assert evaluate_expr("sqrt(16)", ctx) == 4.0

    def test_log(self, ctx):
        assert evaluate_expr("log(1)", ctx) == 0.0

    def test_clamp(self, ctx):
        assert evaluate_expr("clamp(50, 10, 30)", ctx) == 30.0
        assert evaluate_expr("clamp(5, 10, 30)", ctx) == 10.0
        assert evaluate_expr("clamp(20, 10, 30)", ctx) == 20.0

    def test_unknown_function(self, ctx):
        with pytest.raises(ValueError, match="Invalid expression"):
            evaluate_expr("sin(1)", ctx)


# ── Ternary (iff) ─────────────────────────────────────────────────

class TestIff:
    def test_true_branch(self, ctx):
        assert evaluate_expr("iff(10 > 5, 100, 200)", ctx) == 100.0

    def test_false_branch(self, ctx):
        assert evaluate_expr("iff(3 > 5, 100, 200)", ctx) == 200.0

    def test_with_indicators(self, ctx):
        # h4_rsi.value = 45 > threshold = 30 → true
        result = evaluate_expr("iff(ind.h4_rsi.value > var.threshold, 1, 0)", ctx)
        assert result == 1.0

    def test_equal_comparison(self, ctx):
        assert evaluate_expr("iff(10 == 10, 1, 0)", ctx) == 1.0

    def test_not_equal(self, ctx):
        assert evaluate_expr("iff(10 != 5, 1, 0)", ctx) == 1.0


# ── evaluate_condition ─────────────────────────────────────────────

class TestEvaluateCondition:
    def test_and_all_true(self, ctx):
        cond = {
            "type": "AND",
            "rules": [
                {"left": "ind.h4_rsi.value", "operator": ">", "right": "30"},
                {"left": "_price", "operator": ">", "right": "2000"},
            ],
        }
        assert evaluate_condition(cond, ctx) is True

    def test_and_one_false(self, ctx):
        cond = {
            "type": "AND",
            "rules": [
                {"left": "ind.h4_rsi.value", "operator": ">", "right": "30"},
                {"left": "_price", "operator": "<", "right": "2000"},
            ],
        }
        assert evaluate_condition(cond, ctx) is False

    def test_or_one_true(self, ctx):
        cond = {
            "type": "OR",
            "rules": [
                {"left": "ind.h4_rsi.value", "operator": ">", "right": "90"},  # false
                {"left": "_price", "operator": ">", "right": "2000"},           # true
            ],
        }
        assert evaluate_condition(cond, ctx) is True

    def test_or_all_false(self, ctx):
        cond = {
            "type": "OR",
            "rules": [
                {"left": "ind.h4_rsi.value", "operator": ">", "right": "90"},
                {"left": "_price", "operator": "<", "right": "1000"},
            ],
        }
        assert evaluate_condition(cond, ctx) is False

    def test_empty_rules(self, ctx):
        assert evaluate_condition({"type": "AND", "rules": []}, ctx) is False

    def test_all_operators(self, ctx):
        for op, expected in [("<", False), (">", True), ("<=", False), (">=", True), ("==", False), ("!=", True)]:
            cond = {"type": "AND", "rules": [{"left": "45", "operator": op, "right": "30"}]}
            assert evaluate_condition(cond, ctx) is expected, f"Failed for operator {op}"

    def test_unknown_operator(self, ctx):
        cond = {"type": "AND", "rules": [{"left": "1", "operator": "~", "right": "1"}]}
        with pytest.raises(ValueError, match="Unknown operator"):
            evaluate_condition(cond, ctx)


# ── evaluate_condition_detailed ────────────────────────────────────

class TestEvaluateConditionDetailed:
    def test_returns_per_rule_results(self, ctx):
        cond = {
            "type": "AND",
            "rules": [
                {"left": "ind.h4_rsi.value", "operator": ">", "right": "30", "description": "RSI above 30"},
                {"left": "_price", "operator": "<", "right": "2000", "description": "Price below 2000"},
            ],
        }
        overall, details = evaluate_condition_detailed(cond, ctx)
        assert overall is False  # second rule fails
        assert len(details) == 2
        assert details[0]["passed"] is True
        assert details[0]["description"] == "RSI above 30"
        assert details[0]["left_val"] == 45.0
        assert details[1]["passed"] is False

    def test_or_condition_detailed(self, ctx):
        cond = {
            "type": "OR",
            "rules": [
                {"left": "1", "operator": "<", "right": "0"},   # false
                {"left": "10", "operator": ">", "right": "5"},  # true
            ],
        }
        overall, details = evaluate_condition_detailed(cond, ctx)
        assert overall is True
        assert details[0]["passed"] is False
        assert details[1]["passed"] is True

    def test_empty_rules(self, ctx):
        overall, details = evaluate_condition_detailed({"type": "AND", "rules": []}, ctx)
        assert overall is False
        assert details == []

    def test_values_are_rounded(self, ctx):
        cond = {
            "type": "AND",
            "rules": [{"left": "10 / 3", "operator": ">", "right": "0"}],
        }
        _, details = evaluate_condition_detailed(cond, ctx)
        assert details[0]["left_val"] == 3.3333  # rounded to 4 decimal places
