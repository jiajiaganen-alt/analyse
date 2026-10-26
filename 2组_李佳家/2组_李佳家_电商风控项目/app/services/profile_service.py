"""用户画像服务：聚合历史订单、售后、投诉、地址、设备、风险事件与关联案件。"""

from __future__ import annotations

from sqlite3 import Connection
from typing import Any

from app import db
from app.constants import CASE_STATUSES, DECISIONS, EVENT_TYPES, RISK_LEVELS
from app.errors import AppError
from app.services.case_service import mask_phone, reviewer_name
from app.utils import days_between, format_case_no, parse_dt, round_value, safe_div


def get_user_profile(conn: Connection, user_id: str) -> dict[str, Any]:
    """查询用户画像。"""
    user = db.query_one(conn, "SELECT * FROM biz_users WHERE user_id = ?", (user_id,))
    if user is None:
        raise AppError(f"用户不存在：{user_id}", status_code=404)

    order_stats = db.query_one(
        conn,
        """
        SELECT COUNT(*) AS order_count, COALESCE(SUM(amount), 0) AS total_amount,
               COALESCE(AVG(amount), 0) AS avg_amount, MAX(created_at) AS last_order_at
        FROM biz_orders WHERE user_id = ?
        """,
        (user_id,),
    )
    refund_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_after_sales WHERE user_id = ? AND apply_type = 'refund'",
            (user_id,),
        )["c"]
    )
    complaint_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_after_sales WHERE user_id = ? AND apply_type = 'complaint'",
            (user_id,),
        )["c"]
    )
    address_cnt = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM biz_addresses WHERE user_id = ?", (user_id,))["c"])
    device_cnt = int(db.query_one(conn, "SELECT COUNT(DISTINCT device_id) AS c FROM biz_devices WHERE user_id = ?", (user_id,))["c"])
    login_city_cnt = int(
        db.query_one(conn, "SELECT COUNT(DISTINCT city) AS c FROM biz_login_logs WHERE user_id = ?", (user_id,))["c"]
    )
    high_risk_cnt = int(
        db.query_one(
            conn,
            """
            SELECT COUNT(*) AS c FROM risk_assessments a
            JOIN risk_events e ON e.id = a.event_id
            WHERE e.user_id = ? AND a.risk_level = 'high'
            """,
            (user_id,),
        )["c"]
    )
    blacklist_items = db.query_all(
        conn,
        """
        SELECT id, blacklist_type, blacklist_value, remark FROM blacklists
        WHERE status = 'active' AND (
            (blacklist_type = 'user' AND blacklist_value = ?) OR
            (blacklist_type = 'phone' AND blacklist_value = ?)
        )
        ORDER BY id
        """,
        (user_id, user["phone"]),
    )
    night_orders = 0
    orders = db.query_all(conn, "SELECT created_at FROM biz_orders WHERE user_id = ?", (user_id,))
    for item in orders:
        created = parse_dt(item["created_at"])
        if created and (created.hour < 6 or created.hour >= 22):
            night_orders += 1

    event_rows = db.query_all(
        conn,
        """
        SELECT e.id AS event_id, e.event_type, e.source_id, e.order_id, e.created_at,
               a.id AS assessment_id, a.risk_score, a.risk_level, a.decision,
               c.id AS case_id, c.case_status
        FROM risk_events e
        JOIN risk_assessments a ON a.event_id = e.id
        LEFT JOIN risk_cases c ON c.assessment_id = a.id
        WHERE e.user_id = ?
        ORDER BY e.created_at DESC, e.id DESC
        LIMIT 10
        """,
        (user_id,),
    )
    recent_events = [
        {
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "event_type_label": EVENT_TYPES.get(row["event_type"], row["event_type"]),
            "source_id": row["source_id"],
            "order_id": row["order_id"],
            "assessment_id": row["assessment_id"],
            "risk_score": round(float(row["risk_score"]), 1),
            "risk_level": row["risk_level"],
            "risk_level_label": RISK_LEVELS.get(row["risk_level"], row["risk_level"]),
            "decision": row["decision"],
            "decision_label": DECISIONS.get(row["decision"], row["decision"]),
            "case_id": row["case_id"],
            "case_no": format_case_no(row["case_id"]),
            "case_status": row["case_status"],
            "case_status_label": CASE_STATUSES.get(row["case_status"]) if row["case_status"] else None,
            "created_at": row["created_at"],
        }
        for row in event_rows
    ]

    case_rows = db.query_all(
        conn,
        """
        SELECT c.*, a.risk_score, a.risk_level, a.decision, e.event_type
        FROM risk_cases c
        JOIN risk_assessments a ON a.id = c.assessment_id
        JOIN risk_events e ON e.id = a.event_id
        WHERE c.user_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT 10
        """,
        (user_id,),
    )
    cases = [
        {
            "case_id": row["id"],
            "case_no": format_case_no(row["id"]),
            "order_id": row["order_id"],
            "event_type": row["event_type"],
            "event_type_label": EVENT_TYPES.get(row["event_type"], row["event_type"]),
            "risk_score": round(float(row["risk_score"]), 1),
            "risk_level": row["risk_level"],
            "risk_level_label": RISK_LEVELS.get(row["risk_level"], row["risk_level"]),
            "decision": row["decision"],
            "decision_label": DECISIONS.get(row["decision"], row["decision"]),
            "case_status": row["case_status"],
            "case_status_label": CASE_STATUSES.get(row["case_status"], row["case_status"]),
            "reviewer_id": row["reviewer_id"],
            "reviewer_name": reviewer_name(row["reviewer_id"]),
            "created_at": row["created_at"],
        }
        for row in case_rows
    ]

    trend_rows = db.query_all(
        conn,
        """
        SELECT a.risk_score, a.risk_level, a.decision, a.created_at, e.event_type
        FROM risk_assessments a
        JOIN risk_events e ON e.id = a.event_id
        WHERE e.user_id = ?
        ORDER BY a.created_at DESC, a.id DESC
        LIMIT 10
        """,
        (user_id,),
    )
    trend = [
        {
            "date": row["created_at"][:10],
            "created_at": row["created_at"],
            "risk_score": round(float(row["risk_score"]), 1),
            "risk_level": row["risk_level"],
            "event_type": row["event_type"],
            "event_type_label": EVENT_TYPES.get(row["event_type"], row["event_type"]),
        }
        for row in reversed(trend_rows)
    ]

    addresses = db.query_all(
        conn,
        "SELECT address_id, province, city, detail, is_default, change_cnt, created_at FROM biz_addresses WHERE user_id = ? ORDER BY is_default DESC, created_at ASC",
        (user_id,),
    )
    for item in addresses:
        item["full_address"] = f"{item['province']}{item['city']}{item['detail']}"

    blacklist_hits = db.query_all(
        conn,
        """
        SELECT h.blacklist_type, h.blacklist_value, h.added_score, h.created_at
        FROM blacklist_hit_records h
        JOIN risk_assessments a ON a.id = h.assessment_id
        JOIN risk_events e ON e.id = a.event_id
        WHERE e.user_id = ?
        ORDER BY h.id DESC LIMIT 5
        """,
        (user_id,),
    )

    register_at = parse_dt(user["register_at"])
    return {
        "user": {
            "user_id": user["user_id"],
            "user_name": user["user_name"],
            "phone": mask_phone(user["phone"]),
            "phone_city": user["phone_city"],
            "register_at": user["register_at"],
            "register_days": days_between(register_at),
            "register_province": user["register_province"],
            "register_city": user["register_city"],
            "is_enterprise": int(user["is_enterprise"]),
            "credit_score": int(user["credit_score"]),
            "vip_level": user["vip_level"],
            "blacklisted": bool(blacklist_items),
            "blacklist_items": blacklist_items,
        },
        "stats": {
            "order_count": int(order_stats["order_count"]),
            "refund_count": refund_cnt,
            "complaint_count": complaint_cnt,
            "address_count": address_cnt,
            "device_count": device_cnt,
            "login_city_count": login_city_cnt,
            "high_risk_count": high_risk_cnt,
            "total_amount": round_value(float(order_stats["total_amount"]), 2),
            "avg_amount": round_value(float(order_stats["avg_amount"]), 2),
            "night_order_ratio": safe_div(night_orders, int(order_stats["order_count"]), 4),
            "last_order_at": order_stats["last_order_at"],
            "refund_rate": safe_div(refund_cnt, int(order_stats["order_count"]), 4),
        },
        "recent_events": recent_events,
        "cases": cases,
        "risk_trend": trend,
        "addresses": addresses,
        "blacklist_hits": blacklist_hits,
    }
