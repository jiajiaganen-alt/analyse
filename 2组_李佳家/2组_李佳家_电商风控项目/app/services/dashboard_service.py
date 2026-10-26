"""运营看板服务：事件、案件、规则命中、黑名单与近 7 日趋势统计。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app import db
from app.constants import CASE_STATUSES, DECISIONS, EVENT_TYPES, RISK_LEVELS
from app.utils import format_dt, hours_between, last_n_days, now_dt, parse_dt, round_value

FINAL_STATUSES = ("approved", "rejected", "resolved")


def get_dashboard(conn) -> dict[str, Any]:
    """汇总运营看板指标。"""
    now = now_dt()
    event_total = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_events")["c"])
    level_stats = {key: 0 for key in RISK_LEVELS}
    for row in db.query_all(conn, "SELECT risk_level, COUNT(*) AS c FROM risk_assessments GROUP BY risk_level"):
        level_stats[row["risk_level"]] = int(row["c"])
    high_count = level_stats.get("high", 0)
    high_ratio = round(high_count / event_total * 100, 2) if event_total else 0.0

    decision_stats = {key: 0 for key in DECISIONS}
    for row in db.query_all(conn, "SELECT decision, COUNT(*) AS c FROM risk_assessments GROUP BY decision"):
        decision_stats[row["decision"]] = int(row["c"])

    case_status_stats = {key: 0 for key in CASE_STATUSES}
    for row in db.query_all(conn, "SELECT case_status, COUNT(*) AS c FROM risk_cases GROUP BY case_status"):
        case_status_stats[row["case_status"]] = int(row["c"])
    case_total = sum(case_status_stats.values())
    pending_count = case_status_stats.get("pending", 0) + case_status_stats.get("reviewing", 0)
    finished_count = sum(case_status_stats.get(key, 0) for key in FINAL_STATUSES)

    # 平均处理时长：已审核案件从创建到最后一次审核结论的平均小时数
    reviewed_cases = db.query_all(
        conn,
        f"SELECT id, created_at, updated_at FROM risk_cases WHERE case_status IN ({','.join('?' for _ in FINAL_STATUSES)})",
        FINAL_STATUSES,
    )
    durations: list[float] = []
    for item in reviewed_cases:
        log = db.query_one(
            conn,
            f"SELECT created_at FROM review_logs WHERE case_id = ? AND action_type IN ({','.join('?' for _ in FINAL_STATUSES)}) ORDER BY id DESC LIMIT 1",
            (item["id"], *FINAL_STATUSES),
        )
        end_text = log["created_at"] if log else item["updated_at"]
        start_dt = parse_dt(item["created_at"])
        end_dt = parse_dt(end_text)
        if start_dt and end_dt:
            durations.append(hours_between(start_dt, end_dt))
    avg_handle_hours = round_value(sum(durations) / len(durations), 1) if durations else 0.0

    rule_hit_total = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM rule_hits")["c"])
    rule_hit_top = db.query_all(
        conn,
        """
        SELECT r.rule_code, r.rule_name, r.priority,
               COUNT(h.id) AS hit_count,
               ROUND(SUM(h.hit_score), 1) AS total_score,
               ROUND(AVG(h.hit_score), 1) AS avg_score
        FROM rule_hits h
        JOIN risk_rules r ON r.id = h.rule_id
        GROUP BY r.id
        ORDER BY hit_count DESC, total_score DESC
        LIMIT 8
        """,
    )

    blacklist_hit_total = int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklist_hit_records")["c"])
    blacklist_hits = db.query_all(
        conn,
        """
        SELECT h.blacklist_type, h.blacklist_value,
               COUNT(*) AS hit_count,
               ROUND(SUM(h.added_score), 1) AS total_score,
               MAX(h.created_at) AS last_hit_at
        FROM blacklist_hit_records h
        GROUP BY h.blacklist_type, h.blacklist_value
        ORDER BY hit_count DESC, last_hit_at DESC
        LIMIT 8
        """,
    )
    for item in blacklist_hits:
        item["blacklist_type_label"] = {
            "user": "用户",
            "phone": "手机号",
            "address": "地址",
            "device": "设备",
            "ip": "IP",
        }.get(item["blacklist_type"], item["blacklist_type"])

    recent_blacklist_hits = db.query_all(
        conn,
        """
        SELECT h.blacklist_type, h.blacklist_value, h.added_score, h.created_at,
               e.user_id, e.order_id
        FROM blacklist_hit_records h
        JOIN risk_assessments a ON a.id = h.assessment_id
        JOIN risk_events e ON e.id = a.event_id
        ORDER BY h.id DESC LIMIT 6
        """,
    )
    for item in recent_blacklist_hits:
        item["blacklist_type_label"] = {
            "user": "用户",
            "phone": "手机号",
            "address": "地址",
            "device": "设备",
            "ip": "IP",
        }.get(item["blacklist_type"], item["blacklist_type"])

    # 近 7 日趋势
    dates = last_n_days(7, now)
    event_trend: dict[str, dict[str, int]] = {
        day: {"event_count": 0, "high_count": 0, "case_count": 0} for day in dates
    }
    for row in db.query_all(
        conn,
        "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c FROM risk_events GROUP BY day",
    ):
        if row["day"] in event_trend:
            event_trend[row["day"]]["event_count"] = int(row["c"])
    for row in db.query_all(
        conn,
        "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c FROM risk_assessments WHERE risk_level = 'high' GROUP BY day",
    ):
        if row["day"] in event_trend:
            event_trend[row["day"]]["high_count"] = int(row["c"])
    for row in db.query_all(
        conn,
        "SELECT substr(created_at, 1, 10) AS day, COUNT(*) AS c FROM risk_cases GROUP BY day",
    ):
        if row["day"] in event_trend:
            event_trend[row["day"]]["case_count"] = int(row["c"])
    date_objects = [parse_dt(day + " 00:00:00") for day in dates]
    trend_7d = [
        {
            "date": day,
            "label": (date_objects[index].strftime("%m-%d") if date_objects[index] else day),
            **event_trend[day],
        }
        for index, day in enumerate(dates)
    ]

    recent_events = db.query_all(
        conn,
        """
        SELECT a.id AS assessment_id, a.risk_score, a.risk_level, a.decision, a.created_at,
               e.event_type, e.user_id, e.order_id, u.user_name
        FROM risk_assessments a
        JOIN risk_events e ON e.id = a.event_id
        LEFT JOIN biz_users u ON u.user_id = e.user_id
        ORDER BY a.id DESC LIMIT 6
        """,
    )
    for item in recent_events:
        item["risk_score"] = round(float(item["risk_score"]), 1)
        item["risk_level_label"] = RISK_LEVELS.get(item["risk_level"], item["risk_level"])
        item["decision_label"] = DECISIONS.get(item["decision"], item["decision"])
        item["event_type_label"] = EVENT_TYPES.get(item["event_type"], item["event_type"])

    return {
        "generated_at": format_dt(now),
        "kpi": {
            "event_total": event_total,
            "high_risk_count": high_count,
            "high_risk_ratio": high_ratio,
            "case_total": case_total,
            "pending_case_count": pending_count,
            "finished_case_count": finished_count,
            "avg_handle_hours": avg_handle_hours,
            "rule_hit_total": rule_hit_total,
            "blacklist_hit_total": blacklist_hit_total,
            "rule_total": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_rules")["c"]),
            "rule_enabled_count": int(
                db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_rules WHERE rule_status = 'enabled'")["c"]
            ),
            "blacklist_total": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklists")["c"]),
        },
        "level_distribution": level_stats,
        "decision_distribution": decision_stats,
        "case_status_distribution": case_status_stats,
        "trend_7d": trend_7d,
        "rule_hit_top": [
            {
                **row,
                "hit_count": int(row["hit_count"]),
                "total_score": round(float(row["total_score"] or 0), 1),
                "avg_score": round(float(row["avg_score"] or 0), 1),
            }
            for row in rule_hit_top
        ],
        "blacklist_hits": blacklist_hits,
        "recent_blacklist_hits": recent_blacklist_hits,
        "recent_events": recent_events,
        "avg_handle_sample": len(durations),
    }
