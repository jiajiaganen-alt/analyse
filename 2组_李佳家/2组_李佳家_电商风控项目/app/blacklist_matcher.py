"""黑名单匹配器：在风险检查时生效，命中后直接加权并记录留痕。"""

from __future__ import annotations

import re
from datetime import datetime
from sqlite3 import Connection
from typing import Any

from app import db
from app.constants import BLACKLIST_BONUS
from app.utils import format_dt


def _normalize(value: str | None, digits_only: bool = False) -> str:
    """统一黑名单取值格式。"""
    text = (value or "").strip()
    if digits_only:
        return re.sub(r"\D", "", text)
    return text.lower()


def match_blacklists(conn: Connection,
    *,
    user_id: str,
    phone: str,
    order: dict[str, Any] | None,
    address: dict[str, Any] | None,
    occurred_at: datetime,
) -> list[dict[str, Any]]:
    """匹配当前事件关联的用户/手机号/地址/设备/IP 黑名单。

    仅使用在 ``occurred_at`` 之前生效的黑名单，保证历史评估可追溯。
    """
    rows = db.query_all(
        conn,
        "SELECT * FROM blacklists WHERE status = 'active' AND created_at <= ? ORDER BY id",
        (format_dt(occurred_at),),
    )
    hits: list[dict[str, Any]] = []
    address_text = ""
    if address:
        address_text = f"{address['province']}{address['city']}{address['detail']}"
    for row in rows:
        blacklist_type = row["blacklist_type"]
        target = _normalize(row["blacklist_value"])
        matched = False
        if blacklist_type == "user":
            matched = _normalize(user_id) == target
        elif blacklist_type == "phone":
            matched = bool(target) and _normalize(phone, digits_only=True) == _normalize(row["blacklist_value"], digits_only=True)
        elif blacklist_type == "address":
            if address:
                matched = _normalize(address["address_id"]) == target or target in _normalize(address_text)
        elif blacklist_type == "device":
            if order:
                matched = bool(target) and _normalize(order["device_id"]) == target
        elif blacklist_type == "ip":
            if order:
                matched = bool(target) and _normalize(order["ip"]) == target
        if matched:
            hits.append(
                {
                    "blacklist_id": row["id"],
                    "blacklist_type": blacklist_type,
                    "blacklist_value": row["blacklist_value"],
                    "remark": row["remark"],
                    "added_score": float(BLACKLIST_BONUS.get(blacklist_type, 10.0)),
                }
            )
    return hits


def is_blacklisted(conn: Connection, blacklist_type: str, value: str, occurred_at: datetime | None = None) -> bool:
    """判断某个取值是否命中指定类型黑名单（用于用户画像等场景）。"""
    if not value:
        return False
    if occurred_at is None:
        row = db.query_one(
            conn,
            "SELECT id FROM blacklists WHERE blacklist_type = ? AND blacklist_value = ? AND status = 'active'",
            (blacklist_type, value),
        )
        return row is not None
    row = db.query_one(
        conn,
        "SELECT id FROM blacklists WHERE blacklist_type = ? AND blacklist_value = ? AND status = 'active' AND created_at <= ?",
        (blacklist_type, value, format_dt(occurred_at)),
    )
    return row is not None
