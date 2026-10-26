"""规则引擎：条件 AST 校验、规则匹配、命中解释与评分决策。

条件 JSON 支持：
- 比较运算：``>`` ``<`` ``>=`` ``<=`` ``==`` ``!=``
- 文本/集合运算：``contains`` ``in``
- 逻辑运算：``and`` ``or`` ``not``

示例::

    {"and": [
        {"field": "user_register_days", "op": "<", "value": 30},
        {"field": "order_amount", "op": ">=", "value": 2000}
    ]}
"""

from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection
from typing import Any

from app import db
from app.constants import EVENT_TYPES, decision_of, level_of, priority_weight
from app.errors import AppError
from app.features import FEATURE_MAP
from app.utils import json_loads

ALLOWED_OPERATORS = {">", "<", ">=", "<=", "==", "!=", "contains", "in"}
NUMERIC_OPERATORS = {">", "<", ">=", "<="}
MAX_DEPTH = 5
MAX_NODES = 60
_OPERATOR_TEXT = {">": ">", "<": "<", ">=": ">=", "<=": "<=", "==": "==", "!=": "!=", "contains": "包含", "in": "属于"}


def _validate_leaf(node: dict[str, Any]) -> None:
    """校验叶子节点结构。"""
    extra = set(node.keys()) - {"field", "op", "value"}
    if extra:
        raise AppError(f"条件节点包含非法字段：{', '.join(sorted(extra))}")
    if "field" not in node or "op" not in node or "value" not in node:
        raise AppError("条件叶子节点必须包含 field、op、value 三个字段")
    field = node["field"]
    if not isinstance(field, str) or field not in FEATURE_MAP:
        raise AppError(f"未知特征字段：{field}")
    op = node["op"]
    if op not in ALLOWED_OPERATORS:
        raise AppError(f"不支持的运算符：{op}")
    value = node["value"]
    if op in NUMERIC_OPERATORS:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AppError(f"运算符 {op} 的阈值必须为数字")
    elif op == "contains":
        if not isinstance(value, str) or not value:
            raise AppError("contains 运算符的阈值必须为非空字符串")
    elif op == "in":
        if not isinstance(value, list) or not value:
            raise AppError("in 运算符的阈值必须为非空数组")
        if any(isinstance(item, (dict, list)) or item is None for item in value):
            raise AppError("in 运算符的数组元素必须为字符串或数字")
    else:  # == / !=
        if isinstance(value, (dict, list)) or value is None:
            raise AppError(f"运算符 {op} 的阈值必须为字符串或数字")


def validate_condition(condition: Any, depth: int = 1, counter: list[int] | None = None) -> None:
    """递归校验条件 AST，非法时抛出 AppError。"""
    counter = counter if counter is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise AppError(f"条件节点数量不能超过 {MAX_NODES} 个")
    if depth > MAX_DEPTH:
        raise AppError(f"条件嵌套层级不能超过 {MAX_DEPTH} 层")
    if not isinstance(condition, dict) or not condition:
        raise AppError("条件必须为非空 JSON 对象")

    logical_keys = [key for key in ("and", "or") if key in condition]
    if logical_keys:
        if len(condition) != 1:
            raise AppError("逻辑节点只能包含 and 或 or 一个字段")
        key = logical_keys[0]
        children = condition[key]
        if not isinstance(children, list) or len(children) < 2:
            raise AppError(f"{key} 运算至少需要 2 个子条件")
        for child in children:
            validate_condition(child, depth + 1, counter)
        return

    if "not" in condition:
        if len(condition) != 1:
            raise AppError("not 节点只能包含一个子条件")
        validate_condition(condition["not"], depth + 1, counter)
        return

    _validate_leaf(condition)


def _display_value(field: str, value: Any) -> str:
    """将特征值格式化为中文可读文本。"""
    if field == "event_type":
        return str(EVENT_TYPES.get(str(value), value))
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def _format_threshold(value: Any) -> str:
    """阈值格式化。"""
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, str):
        return f'"{value}"'
    if isinstance(value, list):
        return "[" + ", ".join(f'"{item}"' if isinstance(item, str) else str(item) for item in value) + "]"
    return str(value)


def describe_condition(condition: dict[str, Any], features: dict[str, Any]) -> str:
    """生成命中原因说明，例如：注册天数=12 < 30 且 订单金额=2680 >= 2000。"""
    if "and" in condition:
        return " 且 ".join(f"({describe_condition(child, features)})" for child in condition["and"])
    if "or" in condition:
        return " 或 ".join(f"({describe_condition(child, features)})" for child in condition["or"])
    if "not" in condition:
        return f"非({describe_condition(condition['not'], features)})"
    field = condition["field"]
    op = condition["op"]
    expected = condition["value"]
    actual = features.get(field)
    label = FEATURE_MAP[field]["name"]
    if op == "contains":
        return f'{label}={_display_value(field, actual)} {_OPERATOR_TEXT[op]} {_format_threshold(expected)}'
    if op == "in":
        return f'{label}={_display_value(field, actual)} {_OPERATOR_TEXT[op]} {_format_threshold(expected)}'
    return f"{label}={_display_value(field, actual)} {_OPERATOR_TEXT[op]} {_format_threshold(expected)}"


def evaluate_condition(condition: dict[str, Any], features: dict[str, Any]) -> bool:
    """执行条件 AST，返回是否命中。"""
    if "and" in condition:
        return all(evaluate_condition(child, features) for child in condition["and"])
    if "or" in condition:
        return any(evaluate_condition(child, features) for child in condition["or"])
    if "not" in condition:
        return not evaluate_condition(condition["not"], features)

    field = condition["field"]
    op = condition["op"]
    expected = condition["value"]
    actual = features.get(field)

    if op in NUMERIC_OPERATORS:
        if isinstance(actual, bool) or not isinstance(actual, (int, float)):
            return False
        if op == ">":
            return actual > expected
        if op == "<":
            return actual < expected
        if op == ">=":
            return actual >= expected
        return actual <= expected

    if op == "in":
        if isinstance(actual, list):
            return any(item in expected for item in actual)
        return actual in expected

    if op == "contains":
        if isinstance(actual, str):
            return str(expected) in actual
        if isinstance(actual, list):
            return expected in actual
        return False

    if op == "==":
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and not isinstance(actual, bool):
            return float(actual) == float(expected)
        return actual == expected

    if op == "!=":
        if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) and not isinstance(actual, bool):
            return float(actual) != float(expected)
        return actual != expected

    return False


def match_rules(conn: Connection, features: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    """匹配所有启用规则，返回命中列表与参与匹配的规则数。"""
    rows = db.query_all(
        conn,
        "SELECT * FROM risk_rules WHERE rule_status = 'enabled' ORDER BY priority DESC, score DESC, id ASC",
    )
    hits: list[dict[str, Any]] = []
    for rule in rows:
        condition = json_loads(rule["condition_json"], default=None)
        if not isinstance(condition, dict):
            continue
        try:
            matched = evaluate_condition(condition, features)
        except (TypeError, KeyError, ValueError):
            matched = False
        if not matched:
            continue
        weight = priority_weight(int(rule["priority"]))
        hit_score = round(float(rule["score"]) * weight, 1)
        message = f"{rule['rule_name']}：{describe_condition(condition, features)}"
        if len(message) > 500:
            message = message[:497] + "..."
        hits.append(
            {
                "rule_id": rule["id"],
                "rule_code": rule["rule_code"],
                "rule_name": rule["rule_name"],
                "rule_score": float(rule["score"]),
                "priority": int(rule["priority"]),
                "weight": weight,
                "hit_score": hit_score,
                "hit_message": message,
            }
        )
    return hits, len(rows)


def calculate_decision(rule_hits: list[dict[str, Any]], blacklist_hits: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总规则分与黑名单加权，输出最终的分数、等级与处理建议。"""
    rule_total = round(sum(float(item["hit_score"]) for item in rule_hits), 1)
    blacklist_total = round(sum(float(item["added_score"]) for item in blacklist_hits), 1)
    raw_score = round(rule_total + blacklist_total, 1)
    final_score = min(100.0, raw_score)
    return {
        "rule_score_total": rule_total,
        "blacklist_score_total": blacklist_total,
        "raw_score": raw_score,
        "risk_score": final_score,
        "risk_level": level_of(final_score),
        "decision": decision_of(final_score),
        "score_capped": raw_score > 100.0,
    }
