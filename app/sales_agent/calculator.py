"""General deterministic calculator tool for figures the rep needs mid-call."""

from __future__ import annotations

import ast
import operator
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from .calc_tools import parse_sales_date

_MAX_EXPRESSION_LENGTH = 300
_MAX_NODES = 80
_MAX_MAGNITUDE = Decimal("1e12")
_MAX_ADD_DAYS = 3660
_CENT = Decimal("0.01")
_DISPLAY_PLACES = Decimal("1e-10")
_TRANSLATIONS = str.maketrans({"×": "*", "÷": "/", "−": "-", "–": "-", "$": None})
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_SUPPORTED = (
    "Supported: + - * / and parentheses, round(x, places), min(...), max(...), abs(x), "
    'days_between("YYYY-MM-DD", "YYYY-MM-DD"), add_days("YYYY-MM-DD", n).'
)


class _CalculationError(ValueError):
    """Raised for input the calculator deliberately does not evaluate."""


def calculate(expression: str) -> str:
    """Evaluate arithmetic exactly; use it for any figure the rep needs.

    Supports + - * / and parentheses, round(x, places), min(...), max(...),
    abs(x), days_between("YYYY-MM-DD", "YYYY-MM-DD") (end minus start, in days),
    and add_days("YYYY-MM-DD", n). Dates may also be MM/DD/YYYY. Write
    percentages explicitly, for example 1299 * 15 / 100, and leave out thousands
    separators. Non-whole results are also shown rounded to the cent.
    """
    text = str(expression).translate(_TRANSLATIONS).strip().strip("=").strip()
    if not text:
        return _failure("the expression is empty")
    if len(text) > _MAX_EXPRESSION_LENGTH:
        return _failure(f"the expression is longer than {_MAX_EXPRESSION_LENGTH} characters")
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return _failure("the expression is not valid arithmetic")
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        return _failure("the expression is too long; split it into smaller steps")

    try:
        with localcontext() as context:
            context.prec = 28
            result = _evaluate(tree.body)
    except _CalculationError as exc:
        return _failure(str(exc))
    except (ZeroDivisionError, InvalidOperation):
        return _failure("division by zero or an undefined result")
    return _format_result(text, result)


def _evaluate(node: ast.AST) -> Decimal | date:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise _CalculationError(
                "text is only allowed as a quoted date inside days_between() or add_days()"
            )
        return _checked(Decimal(str(value)))
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Mod):
            raise _CalculationError("write percentages explicitly, for example 1299 * 15 / 100")
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise _CalculationError("only +, -, *, and / are supported")
        return _checked(operation(_number(node.left), _number(node.right)))
    if isinstance(node, ast.UnaryOp):
        operation = _UNARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise _CalculationError("only + and - signs are supported")
        return _checked(operation(_number(node.operand)))
    if isinstance(node, ast.Call):
        return _call(node)
    if isinstance(node, ast.Tuple):
        raise _CalculationError("leave out thousands separators, for example 1299.00")
    if isinstance(node, ast.Name):
        raise _CalculationError(f"unknown name {node.id!r}")
    raise _CalculationError("unsupported syntax")


def _call(node: ast.Call) -> Decimal | date:
    if not isinstance(node.func, ast.Name) or node.keywords:
        raise _CalculationError("call functions by name with positional arguments only")
    name, args = node.func.id, node.args

    if name == "days_between":
        _require_arguments(name, args, 2)
        start, end = (_date_argument(argument) for argument in args)
        return Decimal((end - start).days)
    if name == "add_days":
        _require_arguments(name, args, 2)
        start = _date_argument(args[0])
        days = _number(args[1])
        if days != days.to_integral_value() or abs(days) > _MAX_ADD_DAYS:
            raise _CalculationError("add_days needs a whole number of days, at most ten years")
        return start + timedelta(days=int(days))
    if name == "round":
        if len(args) not in {1, 2}:
            raise _CalculationError("round() takes a value and optional decimal places")
        value = _number(args[0])
        places = _number(args[1]) if len(args) == 2 else Decimal(0)
        if places != places.to_integral_value() or not 0 <= places <= 10:
            raise _CalculationError("round() places must be a whole number from 0 to 10")
        return value.quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_UP)
    if name == "abs":
        _require_arguments(name, args, 1)
        return abs(_number(args[0]))
    if name in {"min", "max"}:
        if not args:
            raise _CalculationError(f"{name}() needs at least one value")
        values = [_number(argument) for argument in args]
        return min(values) if name == "min" else max(values)
    raise _CalculationError(f"unknown function {name!r}")


def _require_arguments(name: str, args: list[ast.expr], count: int) -> None:
    if len(args) != count:
        raise _CalculationError(f"{name}() takes {count} argument(s)")


def _number(node: ast.AST) -> Decimal:
    value = _evaluate(node)
    if isinstance(value, date):
        raise _CalculationError("use dates only inside days_between() or add_days()")
    return value


def _date_argument(node: ast.AST) -> date:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return parse_sales_date(node.value)
        except ValueError as exc:
            raise _CalculationError(str(exc)) from exc
    value = _evaluate(node)
    if not isinstance(value, date):
        raise _CalculationError('dates must be quoted, for example "2026-09-15"')
    return value


def _checked(value: Decimal) -> Decimal:
    if not value.is_finite() or abs(value) > _MAX_MAGNITUDE:
        raise _CalculationError("values above 1,000,000,000,000 are not supported")
    return value


def _format_result(expression: str, result: Decimal | date) -> str:
    lines = ["CALCULATION", f"Expression: {expression}"]
    if isinstance(result, date):
        lines.append(f"Result: {result.isoformat()} ({result:%a %d %b %Y})")
        return "\n".join(lines)
    lines.append(f"Result: {_plain(result)}")
    if result != result.to_integral_value():
        lines.append(f"Rounded to cents: {result.quantize(_CENT, rounding=ROUND_HALF_UP):f}")
    return "\n".join(lines)


def _plain(value: Decimal) -> str:
    if value == 0:
        return "0"
    if value == value.to_integral_value():
        return f"{value.to_integral_value():f}"
    rounded = f"{value.quantize(_DISPLAY_PLACES, rounding=ROUND_HALF_UP):f}"
    return rounded.rstrip("0").rstrip(".")


def _failure(reason: str) -> str:
    return "\n".join(["CALCULATION NOT PERFORMED", f"Reason: {reason}", _SUPPORTED])
