"""黑名单服务：查询、新增、删除、批量导入与统计。"""

from __future__ import annotations

import re
from sqlite3 import Connection
from typing import Any

from app import db
from app.constants import BLACKLIST_BONUS, BLACKLIST_TYPES
from app.errors import AppError
from app.utils import format_dt, now_dt

BLACKLIST_STATUSES = {"active", "inactive"}


def _serialize_blacklist(row: dict[str, Any]) -> dict[str, Any]:
    """转换为 API 结构。"""
    return {
        "id": row["id"],
        "blacklist_type": row["blacklist_type"],
        "blacklist_type_label": BLACKLIST_TYPES.get(row["blacklist_type"], row["blacklist_type"]),
        "blacklist_value": row["blacklist_value"],
        "remark": row["remark"],
        "status": row["status"],
        "status_label": "生效中" if row["status"] == "active" else "已停用",
        "bonus_score": float(BLACKLIST_BONUS.get(row["blacklist_type"], 0)),
        "hit_count": int(row.get("hit_count", 0) or 0),
        "last_hit_at": row.get("last_hit_at"),
        "created_at": row["created_at"],
    }


def list_blacklists(conn: Connection,
    blacklist_type: str | None = None,
    keyword: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """查询黑名单列表及类型统计。"""
    sql = """
        SELECT b.*,
               (SELECT COUNT(*) FROM blacklist_hit_records h WHERE h.blacklist_id = b.id) AS hit_count,
               (SELECT MAX(h.created_at) FROM blacklist_hit_records h WHERE h.blacklist_id = b.id) AS last_hit_at
        FROM blacklists b
        WHERE 1 = 1
    """
    params: list[Any] = []
    if blacklist_type:
        if blacklist_type not in BLACKLIST_TYPES:
            raise AppError(f"不支持的黑名单类型：{blacklist_type}")
        sql += " AND b.blacklist_type = ?"
        params.append(blacklist_type)
    if keyword:
        sql += " AND (b.blacklist_value LIKE ? OR b.remark LIKE ?)"
        like = f"%{keyword.strip()}%"
        params.extend([like, like])
    if status in BLACKLIST_STATUSES:
        sql += " AND b.status = ?"
        params.append(status)
    sql += " ORDER BY CASE b.status WHEN 'active' THEN 0 ELSE 1 END, b.id DESC"
    items = [_serialize_blacklist(row) for row in db.query_all(conn, sql, params)]

    type_stats = {key: 0 for key in BLACKLIST_TYPES}
    for row in db.query_all(conn, "SELECT blacklist_type, COUNT(*) AS c FROM blacklists GROUP BY blacklist_type"):
        type_stats[row["blacklist_type"]] = int(row["c"])
    total = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklists")["c"])
    active = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklists WHERE status = 'active'")["c"])
    hit_total = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklist_hit_records")["c"])
    return {
        "items": items,
        "total": total,
        "filtered_total": len(items),
        "active_count": active,
        "hit_total": hit_total,
        "type_stats": type_stats,
        "type_labels": BLACKLIST_TYPES,
    }


def _validate_item(item: dict[str, Any]) -> dict[str, Any]:
    """校验单条黑名单数据。"""
    blacklist_type = str(item.get("blacklist_type") or "").strip()
    if blacklist_type not in BLACKLIST_TYPES:
        raise AppError(f"黑名单类型必须为：{', '.join(BLACKLIST_TYPES)}")
    value = str(item.get("blacklist_value") or "").strip()
    if not value:
        raise AppError("黑名单取值不能为空")
    if len(value) > 120:
        raise AppError("黑名单取值不能超过 120 个字符")
    if blacklist_type == "phone":
        digits = re.sub(r"\D", "", value)
        if len(digits) < 6:
            raise AppError("手机号黑名单至少需要 6 位数字")
    if blacklist_type == "ip":
        if not re.match(r"^[0-9a-fA-F.:]{3,45}$", value):
            raise AppError("IP 黑名单格式不正确")
    remark = str(item.get("remark") or "").strip()
    if len(remark) > 200:
        raise AppError("备注不能超过 200 个字符")
    status = str(item.get("status") or "active")
    if status not in BLACKLIST_STATUSES:
        raise AppError("黑名单状态只能为 active 或 inactive")
    return {
        "blacklist_type": blacklist_type,
        "blacklist_value": value,
        "remark": remark,
        "status": status,
    }


def create_blacklist(conn: Connection, item: dict[str, Any]) -> dict[str, Any]:
    """新增黑名单，重复条目返回冲突错误。"""
    values = _validate_item(item)
    duplicate = db.query_one(
        conn,
        "SELECT id FROM blacklists WHERE blacklist_type = ? AND LOWER(blacklist_value) = LOWER(?)",
        (values["blacklist_type"], values["blacklist_value"]),
    )
    if duplicate:
        raise AppError("该黑名单条目已存在", status_code=409)
    cursor = conn.execute(
        "INSERT INTO blacklists (blacklist_type, blacklist_value, remark, status, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            values["blacklist_type"],
            values["blacklist_value"],
            values["remark"],
            values["status"],
            format_dt(now_dt()),
        ),
    )
    row = db.query_one(conn, "SELECT * FROM blacklists WHERE id = ?", (int(cursor.lastrowid),))
    return _serialize_blacklist(row)


def delete_blacklists(conn: Connection, ids: list[int]) -> dict[str, Any]:
    """按 ID 批量删除黑名单，历史命中记录保留用于审计。"""
    cleaned: list[int] = []
    for value in ids:
        try:
            cleaned.append(int(value))
        except (TypeError, ValueError) as exc:
            raise AppError("黑名单 ID 必须为整数") from exc
    if not cleaned:
        raise AppError("请选择要删除的黑名单")
    placeholders = ",".join("?" for _ in cleaned)
    rows = db.query_all(conn, f"SELECT id, blacklist_type, blacklist_value FROM blacklists WHERE id IN ({placeholders})", cleaned)
    if not rows:
        raise AppError("黑名单条目不存在", status_code=404)
    conn.execute(f"DELETE FROM blacklists WHERE id IN ({placeholders})", cleaned)
    return {"deleted_count": len(rows), "deleted": rows}


def import_blacklists(conn: Connection, items: list[dict[str, Any]]) -> dict[str, Any]:
    """批量导入黑名单，逐条校验并返回失败明细。"""
    if not items:
        raise AppError("导入内容不能为空")
    if len(items) > 500:
        raise AppError("单次最多导入 500 条黑名单")
    success = 0
    failed: list[dict[str, Any]] = []
    now = format_dt(now_dt())
    for index, item in enumerate(items, start=1):
        try:
            values = _validate_item(item)
            duplicate = db.query_one(
                conn,
                "SELECT id FROM blacklists WHERE blacklist_type = ? AND LOWER(blacklist_value) = LOWER(?)",
                (values["blacklist_type"], values["blacklist_value"]),
            )
            if duplicate:
                raise AppError("该条目已存在")
            conn.execute(
                "INSERT INTO blacklists (blacklist_type, blacklist_value, remark, status, created_at) VALUES (?, ?, ?, ?, ?)",
                (values["blacklist_type"], values["blacklist_value"], values["remark"], values["status"], now),
            )
            success += 1
        except AppError as exc:
            failed.append({"index": index, "message": exc.message, "item": item})
    return {"success_count": success, "failed_count": len(failed), "failed": failed}
