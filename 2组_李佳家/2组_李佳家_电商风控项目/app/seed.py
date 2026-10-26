"""演示数据初始化。

从 ``data/rules.json`` 与 ``data/demo_data.json`` 读取规则、用户、订单、地址、
设备、登录日志、售后记录、黑名单与历史检查计划，首次启动时写入数据库。

历史检查会真实调用风险 Agent 完成 40 次评估，因此命中规则、特征快照、案件、
审核日志、黑名单命中留痕与看板趋势均来自真实计算，而不是手工伪造。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from app import db
from app.rule_engine import validate_condition
from app.risk_agent import run_risk_check
from app.utils import format_dt, json_dumps, now_dt, parse_dt

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

REVIEWER_BY_STATUS = {
    "approved": "RV001",
    "resolved": "RV003",
    "rejected": "RV002",
    "reviewing": "RV002",
}
REVIEW_REMARK = {
    "approved": "已电话核实为本人操作，风险信号解除，同意放行。",
    "resolved": "已联系用户完成退款并加固账号，风险处置闭环。",
    "rejected": "确认存在盗刷与套利行为，拒绝售后并冻结相关权益。",
    "reviewing": "案件风险较高，已领取并联系用户补充材料。",
}
HANDLE_HOURS = [2.5, 3.0, 4.5, 6.0, 8.0, 10.5, 14.0, 20.0]


def _load_json(name: str) -> Any:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def _at(now: datetime, days_ago: int, hour: int = 10, minute: int = 0) -> datetime:
    """生成相对当前时间的历史时间点。"""
    return (now - timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0, microsecond=0)


def _insert_users(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT INTO biz_users
                (user_id, user_name, phone, phone_city, register_at, register_province, register_city, is_enterprise, credit_score, vip_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["user_id"],
                item["user_name"],
                item["phone"],
                item["phone_city"],
                format_dt(_at(now, item["register_days_ago"], 10, 0)),
                item["register_province"],
                item["register_city"],
                item["is_enterprise"],
                item["credit_score"],
                item["vip_level"],
            ),
        )


def _insert_addresses(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT INTO biz_addresses
                (address_id, user_id, receiver_name, phone, province, city, detail, is_default, change_cnt, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["address_id"],
                item["user_id"],
                item["receiver_name"],
                item["phone"],
                item["province"],
                item["city"],
                item["detail"],
                item["is_default"],
                item["change_cnt"],
                format_dt(_at(now, item["created_days_ago"], 9, 0)),
            ),
        )


def _insert_devices(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT INTO biz_devices (device_id, user_id, device_name, os, first_seen, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item["device_id"],
                item["user_id"],
                item["device_name"],
                item["os"],
                format_dt(_at(now, item["first_seen_days_ago"], 12, 0)),
                format_dt(_at(now, item["last_login_days_ago"], 20, 0)),
            ),
        )


def _insert_login_logs(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        conn.execute(
            "INSERT INTO biz_login_logs (user_id, city, ip, device_id, login_at) VALUES (?, ?, ?, ?, ?)",
            (
                item["user_id"],
                item["city"],
                item["ip"],
                item["device_id"],
                format_dt(_at(now, item["login_days_ago"], item["login_hour"], 5)),
            ),
        )


def _insert_orders(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        created = _at(now, item["created_days_ago"], item["created_hour"], item["created_minute"])
        paid = created + timedelta(seconds=item["pay_interval_sec"])
        conn.execute(
            """
            INSERT INTO biz_orders
                (order_id, user_id, amount, discount_rate, freight, pay_method, created_at, paid_at,
                 pay_interval_sec, category, category_risk_score, item_count, address_id, device_id, ip,
                 receive_province, receive_city, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["order_id"],
                item["user_id"],
                item["amount"],
                item["discount_rate"],
                item["freight"],
                item["pay_method"],
                format_dt(created),
                format_dt(paid),
                item["pay_interval_sec"],
                item["category"],
                item["category_risk_score"],
                item["item_count"],
                item["address_id"],
                item["device_id"],
                item["ip"],
                item["receive_province"],
                item["receive_city"],
                item["status"],
            ),
        )


def _insert_after_sales(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        conn.execute(
            """
            INSERT INTO biz_after_sales
                (after_sale_id, order_id, user_id, apply_type, reason, amount, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["after_sale_id"],
                item["order_id"],
                item["user_id"],
                item["apply_type"],
                item["reason"],
                item["amount"],
                item["status"],
                format_dt(_at(now, item["created_days_ago"], item["created_hour"], 30)),
            ),
        )


def _insert_blacklists(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for item in rows:
        conn.execute(
            "INSERT INTO blacklists (blacklist_type, blacklist_value, remark, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                item["blacklist_type"],
                item["blacklist_value"],
                item["remark"],
                item["status"],
                format_dt(_at(now, item["created_days_ago"], 10, 0)),
            ),
        )


def _insert_rules(conn: Connection, rows: list[dict[str, Any]], now: datetime) -> None:
    for index, item in enumerate(rows):
        condition = item["condition_json"]
        validate_condition(condition)
        conn.execute(
            """
            INSERT INTO risk_rules
                (rule_code, rule_name, rule_status, priority, score, condition_json, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["rule_code"],
                item["rule_name"],
                item["rule_status"],
                item["priority"],
                item["score"],
                json_dumps(condition),
                item["description"],
                format_dt(_at(now, index % 5, 18, index % 50)),
            ),
        )


def _seed_review_flow(conn: Connection, now: datetime) -> None:
    """为 12 个自动生成案件补齐审核状态、审核人与审核日志。"""
    cases = db.query_all(conn, "SELECT * FROM risk_cases ORDER BY created_at ASC, id ASC")
    status_by_index = ["approved"] * 4 + ["resolved"] * 2 + ["rejected"] * 2 + ["reviewing"] * 2 + ["pending"] * 2
    handle_index = 0
    for index, case in enumerate(cases):
        status = status_by_index[index] if index < len(status_by_index) else "pending"
        created = parse_dt(case["created_at"])
        if created is None:
            continue
        if status == "pending":
            continue
        reviewer = REVIEWER_BY_STATUS[status]
        claim_at = created + timedelta(hours=1)
        final_at = created + timedelta(hours=HANDLE_HOURS[handle_index % len(HANDLE_HOURS)])
        handle_index += 1
        latest_allowed = now - timedelta(minutes=2)
        if claim_at > latest_allowed:
            claim_at = latest_allowed - timedelta(minutes=30)
        if final_at > latest_allowed:
            final_at = latest_allowed
        if final_at <= claim_at:
            final_at = claim_at + timedelta(minutes=20)
            if final_at > latest_allowed:
                final_at = latest_allowed
        conn.execute(
            "INSERT INTO review_logs (case_id, operator_id, action_type, action_remark, created_at) VALUES (?, ?, 'start_review', ?, ?)",
            (case["id"], reviewer, "领取案件，开始人工复核", format_dt(claim_at)),
        )
        if status == "reviewing":
            conn.execute(
                "UPDATE risk_cases SET case_status = 'reviewing', reviewer_id = ?, review_result = NULL, updated_at = ? WHERE id = ?",
                (reviewer, format_dt(claim_at), case["id"]),
            )
            continue
        conn.execute(
            "INSERT INTO review_logs (case_id, operator_id, action_type, action_remark, created_at) VALUES (?, ?, ?, ?, ?)",
            (case["id"], reviewer, status, REVIEW_REMARK[status], format_dt(final_at)),
        )
        conn.execute(
            "UPDATE risk_cases SET case_status = ?, reviewer_id = ?, review_result = ?, updated_at = ? WHERE id = ?",
            (status, reviewer, status, format_dt(final_at), case["id"]),
        )


def seed_demo_data(now: datetime | None = None) -> dict[str, Any]:
    """灌入完整演示数据，返回数据量摘要。"""
    now = (now or now_dt()).replace(microsecond=0)
    demo = _load_json("demo_data.json")
    rules = _load_json("rules.json")

    with db.get_conn() as conn:
        _insert_users(conn, demo["users"], now)
        _insert_addresses(conn, demo["addresses"], now)
        _insert_devices(conn, demo["devices"], now)
        _insert_login_logs(conn, demo["login_logs"], now)
        _insert_orders(conn, demo["orders"], now)
        _insert_after_sales(conn, demo["after_sales"], now)
        _insert_blacklists(conn, demo["blacklists"], now)
        _insert_rules(conn, rules, now)

        # 计算并校验历史检查时间，确保订单早于事件
        planned: list[tuple[datetime, dict[str, Any]]] = []
        for index, item in enumerate(demo["historical_checks"]):
            occurred = _at(now, item["days_ago"], item["hour"], item["minute"])
            if occurred > now - timedelta(minutes=3):
                occurred = now - timedelta(minutes=10 + index)
            order = db.query_one(conn, "SELECT created_at FROM biz_orders WHERE order_id = ?", (item["order_id"],))
            if order is None:
                raise RuntimeError(f"演示检查引用了不存在的订单：{item['order_id']}")
            order_at = parse_dt(order["created_at"])
            if order_at and order_at > occurred:
                raise RuntimeError(
                    f"演示数据时间顺序错误：订单 {item['order_id']} 创建于 {order['created_at']}，晚于检查时间 {format_dt(occurred)}"
                )
            planned.append((occurred, item))
        planned.sort(key=lambda pair: pair[0])

        for occurred, item in planned:
            run_risk_check(
                conn,
                {
                    "event_type": item["event_type"],
                    "source_id": item["source_id"],
                    "user_id": item["user_id"],
                    "order_id": item["order_id"],
                },
                occurred_at=occurred,
            )

        _seed_review_flow(conn, now)

        summary = {
            "users": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM biz_users")["c"]),
            "orders": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM biz_orders")["c"]),
            "rules": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_rules")["c"]),
            "events": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_events")["c"]),
            "assessments": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_assessments")["c"]),
            "cases": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_cases")["c"]),
            "blacklists": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklists")["c"]),
            "review_logs": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM review_logs")["c"]),
        }
    return summary
