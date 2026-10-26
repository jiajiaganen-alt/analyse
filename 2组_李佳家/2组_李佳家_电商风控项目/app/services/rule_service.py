"""规则管理服务：列表统计、新增、编辑、启停用、删除与条件校验。"""

from __future__ import annotations

import json
import re
from sqlite3 import Connection
from typing import Any

from app import db
from app.errors import AppError
from app.rule_engine import validate_condition
from app.utils import format_dt, json_dumps, now_dt

RULE_CODE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,19}$")
RULE_STATUSES = {"enabled", "disabled"}


def _serialize_rule(row: dict[str, Any]) -> dict[str, Any]:
    """将数据库规则转换为 API 结构，同时返回 JSON 字符串与对象。"""
    condition = {}
    try:
        condition = json.loads(row["condition_json"])
    except (json.JSONDecodeError, TypeError):
        condition = {}
    return {
        "id": row["id"],
        "rule_code": row["rule_code"],
        "rule_name": row["rule_name"],
        "rule_status": row["rule_status"],
        "rule_status_label": "启用" if row["rule_status"] == "enabled" else "停用",
        "priority": row["priority"],
        "score": row["score"],
        "condition_json": json.dumps(condition, ensure_ascii=False, indent=2),
        "condition": condition,
        "description": row["description"],
        "updated_at": row["updated_at"],
        "hit_count": int(row.get("hit_count", 0) or 0),
        "total_hit_score": round(float(row.get("total_hit_score", 0) or 0), 1),
    }


def list_rules(conn: Connection, keyword: str | None = None, status: str | None = None) -> dict[str, Any]:
    """查询规则列表，附带命中次数与汇总统计。"""
    sql = """
        SELECT r.*,
               COUNT(h.id) AS hit_count,
               COALESCE(SUM(h.hit_score), 0) AS total_hit_score
        FROM risk_rules r
        LEFT JOIN rule_hits h ON h.rule_id = r.id
        WHERE 1 = 1
    """
    params: list[Any] = []
    if keyword:
        sql += " AND (r.rule_code LIKE ? OR r.rule_name LIKE ?)"
        like = f"%{keyword.strip()}%"
        params.extend([like, like])
    if status in RULE_STATUSES:
        sql += " AND r.rule_status = ?"
        params.append(status)
    sql += " GROUP BY r.id ORDER BY r.priority DESC, r.score DESC, r.id ASC"
    items = [_serialize_rule(row) for row in db.query_all(conn, sql, params)]

    total = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_rules")["c"])
    enabled = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_rules WHERE rule_status = 'enabled'")["c"])
    total_hits = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM rule_hits")["c"])
    avg_score = db.query_one(conn, "SELECT COALESCE(AVG(score), 0) AS avg_score FROM risk_rules")["avg_score"]
    return {
        "items": items,
        "total": total,
        "filtered_total": len(items),
        "enabled_count": enabled,
        "disabled_count": total - enabled,
        "total_hits": total_hits,
        "avg_score": round(float(avg_score or 0), 1),
    }


def _normalize_condition(raw: Any) -> dict[str, Any]:
    """将前端提交的 JSON 字符串或对象统一为 AST 对象。"""
    if isinstance(raw, str):
        try:
            condition = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise AppError(f"条件 JSON 解析失败：{exc.msg}") from exc
    elif isinstance(raw, dict):
        condition = raw
    else:
        raise AppError("condition_json 必须为 JSON 对象或 JSON 字符串")
    validate_condition(condition)
    return condition


def _validate_common(data: dict[str, Any]) -> dict[str, Any]:
    """校验并规范化规则字段。"""
    rule_name = str(data.get("rule_name") or "").strip()
    if not rule_name:
        raise AppError("规则名称不能为空")
    if len(rule_name) > 50:
        raise AppError("规则名称不能超过 50 个字符")
    description = str(data.get("description") or "").strip()
    if len(description) > 500:
        raise AppError("规则描述不能超过 500 个字符")
    try:
        priority = int(data.get("priority", 5))
        score = int(data.get("score", 10))
    except (TypeError, ValueError) as exc:
        raise AppError("优先级与分值必须为整数") from exc
    if not 1 <= priority <= 10:
        raise AppError("优先级必须在 1-10 之间")
    if not 0 <= score <= 100:
        raise AppError("规则分值必须在 0-100 之间")
    status = str(data.get("rule_status") or "enabled")
    if status not in RULE_STATUSES:
        raise AppError("规则状态只能为 enabled 或 disabled")
    if "condition_json" not in data and "condition" not in data:
        raise AppError("规则条件不能为空")
    condition = _normalize_condition(data.get("condition_json", data.get("condition")))
    return {
        "rule_name": rule_name,
        "description": description,
        "priority": priority,
        "score": score,
        "rule_status": status,
        "condition": condition,
    }


def create_rule(conn: Connection, data: dict[str, Any]) -> dict[str, Any]:
    """新增规则。"""
    raw_code = str(data.get("rule_code") or "").strip().upper()
    if not RULE_CODE_PATTERN.match(raw_code):
        raise AppError("规则编码需以字母开头，由 2-20 位字母、数字或下划线组成")
    exists = db.query_one(conn, "SELECT id FROM risk_rules WHERE UPPER(rule_code) = ?", (raw_code,))
    if exists:
        raise AppError(f"规则编码已存在：{raw_code}", status_code=409)
    values = _validate_common(data)
    now = format_dt(now_dt())
    cursor = conn.execute(
        """
        INSERT INTO risk_rules (rule_code, rule_name, rule_status, priority, score, condition_json, description, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_code,
            values["rule_name"],
            values["rule_status"],
            values["priority"],
            values["score"],
            json_dumps(values["condition"]),
            values["description"],
            now,
        ),
    )
    row = db.query_one(conn, "SELECT * FROM risk_rules WHERE id = ?", (int(cursor.lastrowid),))
    return _serialize_rule(row)


def update_rule(conn: Connection, rule_id: int, data: dict[str, Any]) -> dict[str, Any]:
    """更新规则（支持部分字段）。"""
    existing = db.query_one(conn, "SELECT * FROM risk_rules WHERE id = ?", (rule_id,))
    if existing is None:
        raise AppError(f"规则不存在：{rule_id}", status_code=404)
    merged = {
        "rule_name": data.get("rule_name", existing["rule_name"]),
        "description": data.get("description", existing["description"]),
        "priority": data.get("priority", existing["priority"]),
        "score": data.get("score", existing["score"]),
        "rule_status": data.get("rule_status", existing["rule_status"]),
        "condition_json": data.get("condition_json", data.get("condition", existing["condition_json"])),
    }
    values = _validate_common(merged)
    new_code = existing["rule_code"]
    if data.get("rule_code"):
        candidate = str(data["rule_code"]).strip().upper()
        if not RULE_CODE_PATTERN.match(candidate):
            raise AppError("规则编码需以字母开头，由 2-20 位字母、数字或下划线组成")
        duplicate = db.query_one(conn, "SELECT id FROM risk_rules WHERE UPPER(rule_code) = ? AND id != ?", (candidate, rule_id))
        if duplicate:
            raise AppError(f"规则编码已存在：{candidate}", status_code=409)
        new_code = candidate
    conn.execute(
        """
        UPDATE risk_rules
        SET rule_code = ?, rule_name = ?, rule_status = ?, priority = ?, score = ?,
            condition_json = ?, description = ?, updated_at = ?
        WHERE id = ?
        """,
        (
            new_code,
            values["rule_name"],
            values["rule_status"],
            values["priority"],
            values["score"],
            json_dumps(values["condition"]),
            values["description"],
            format_dt(now_dt()),
            rule_id,
        ),
    )
    row = db.query_one(conn, "SELECT * FROM risk_rules WHERE id = ?", (rule_id,))
    return _serialize_rule(row)


def set_rule_status(conn: Connection, rule_id: int, rule_status: str) -> dict[str, Any]:
    """启停用规则。"""
    if rule_status not in RULE_STATUSES:
        raise AppError("规则状态只能为 enabled 或 disabled")
    existing = db.query_one(conn, "SELECT * FROM risk_rules WHERE id = ?", (rule_id,))
    if existing is None:
        raise AppError(f"规则不存在：{rule_id}", status_code=404)
    conn.execute(
        "UPDATE risk_rules SET rule_status = ?, updated_at = ? WHERE id = ?",
        (rule_status, format_dt(now_dt()), rule_id),
    )
    row = db.query_one(conn, "SELECT * FROM risk_rules WHERE id = ?", (rule_id,))
    return _serialize_rule(row)


def delete_rule(conn: Connection, rule_id: int) -> dict[str, Any]:
    """删除规则；同步清理该规则的历史命中明细以保证统计一致。"""
    existing = db.query_one(conn, "SELECT * FROM risk_rules WHERE id = ?", (rule_id,))
    if existing is None:
        raise AppError(f"规则不存在：{rule_id}", status_code=404)
    hit_count = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM rule_hits WHERE rule_id = ?", (rule_id,))["c"])
    conn.execute("DELETE FROM rule_hits WHERE rule_id = ?", (rule_id,))
    conn.execute("DELETE FROM risk_rules WHERE id = ?", (rule_id,))
    return {"deleted_id": rule_id, "rule_code": existing["rule_code"], "deleted_hit_count": hit_count}
