"""风险评估查询服务：评估详情、最近评估列表、命中与快照回查。"""

from __future__ import annotations

import math
from sqlite3 import Connection
from typing import Any

from app import db
from app.constants import CASE_STATUSES, DECISIONS, EVENT_TYPES, RISK_LEVELS
from app.errors import AppError
from app.features import FEATURE_MAP
from app.risk_agent import load_trace
from app.utils import format_assessment_no, format_case_no, json_loads


def _serialize_hit(row: dict[str, Any]) -> dict[str, Any]:
    """命中规则结构。"""
    rule_score = float(row.get("rule_score") or 0)
    hit_score = float(row["hit_score"])
    return {
        "id": row["id"],
        "rule_id": row["rule_id"],
        "rule_code": row["rule_code"],
        "rule_name": row["rule_name"],
        "priority": int(row.get("priority") or 0),
        "rule_score": rule_score,
        "hit_score": hit_score,
        "weight": round(hit_score / rule_score, 4) if rule_score else 1.0,
        "hit_message": row["hit_message"],
        "description": row.get("description") or "",
        "created_at": row["created_at"],
    }


def get_rule_hits(conn: Connection, assessment_id: int) -> list[dict[str, Any]]:
    """查询某次评估的规则命中明细。"""
    rows = db.query_all(
        conn,
        """
        SELECT h.*, r.rule_code, r.rule_name, r.priority, r.score AS rule_score, r.description
        FROM rule_hits h
        JOIN risk_rules r ON r.id = h.rule_id
        WHERE h.assessment_id = ?
        ORDER BY r.priority DESC, h.hit_score DESC, h.id ASC
        """,
        (assessment_id,),
    )
    return [_serialize_hit(row) for row in rows]


def get_blacklist_hits(conn: Connection, assessment_id: int) -> list[dict[str, Any]]:
    """查询某次评估的黑名单命中记录（历史留痕，不随黑名单删除消失）。"""
    rows = db.query_all(
        conn,
        "SELECT * FROM blacklist_hit_records WHERE assessment_id = ? ORDER BY id",
        (assessment_id,),
    )
    return [
        {
            "blacklist_id": row["blacklist_id"],
            "blacklist_type": row["blacklist_type"],
            "blacklist_value": row["blacklist_value"],
            "added_score": float(row["added_score"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_assessment_detail(conn: Connection, assessment_id: int) -> dict[str, Any]:
    """评估详情：风险结果、特征快照、命中规则、黑名单、案件与 Agent 轨迹。"""
    row = db.query_one(
        conn,
        """
        SELECT a.*, e.event_type, e.source_id, e.user_id, e.order_id, e.event_payload_json,
               e.created_at AS event_created_at, u.user_name
        FROM risk_assessments a
        JOIN risk_events e ON e.id = a.event_id
        LEFT JOIN biz_users u ON u.user_id = e.user_id
        WHERE a.id = ?
        """,
        (assessment_id,),
    )
    if row is None:
        raise AppError(f"评估记录不存在：{assessment_id}", status_code=404)
    snapshot_row = db.query_one(conn, "SELECT feature_json FROM feature_snapshots WHERE assessment_id = ?", (assessment_id,))
    feature_snapshot = json_loads(snapshot_row["feature_json"], default={}) if snapshot_row else {}
    rule_hits = get_rule_hits(conn, assessment_id)
    blacklist_hits = get_blacklist_hits(conn, assessment_id)
    case = db.query_one(conn, "SELECT * FROM risk_cases WHERE assessment_id = ?", (assessment_id,))
    rule_score_total = round(sum(item["hit_score"] for item in rule_hits), 1)
    blacklist_score_total = round(sum(item["added_score"] for item in blacklist_hits), 1)
    raw_score = round(rule_score_total + blacklist_score_total, 1)
    return {
        "assessment_id": row["id"],
        "assessment_no": format_assessment_no(row["id"]),
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "event_type_label": EVENT_TYPES.get(row["event_type"], row["event_type"]),
        "source_id": row["source_id"],
        "user_id": row["user_id"],
        "user_name": row.get("user_name"),
        "order_id": row["order_id"],
        "risk_score": round(float(row["risk_score"]), 1),
        "risk_level": row["risk_level"],
        "risk_level_label": RISK_LEVELS.get(row["risk_level"], row["risk_level"]),
        "decision": row["decision"],
        "decision_label": DECISIONS.get(row["decision"], row["decision"]),
        "assessment_status": row["assessment_status"],
        "assessment_status_label": "已完成",
        "feature_snapshot": feature_snapshot,
        "rule_hits": rule_hits,
        "blacklist_hits": blacklist_hits,
        "case_id": case["id"] if case else None,
        "case_no": format_case_no(case["id"]) if case else None,
        "case_status": case["case_status"] if case else None,
        "case_status_label": CASE_STATUSES.get(case["case_status"]) if case else None,
        "score_detail": {
            "rule_score_total": rule_score_total,
            "blacklist_score_total": blacklist_score_total,
            "raw_score": raw_score,
            "score_capped": raw_score > 100.0,
        },
        "trace": load_trace(conn, assessment_id),
        "event_payload": json_loads(row["event_payload_json"], default={}),
        "created_at": row["created_at"],
    }


def list_assessments(conn: Connection,
    page: int = 1,
    page_size: int = 20,
    risk_level: str | None = None,
    keyword: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """最近评估列表，支持按等级、用户、关键字筛选。"""
    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))
    where = " WHERE 1 = 1"
    params: list[Any] = []
    if risk_level:
        where += " AND a.risk_level = ?"
        params.append(risk_level)
    if user_id:
        where += " AND e.user_id = ?"
        params.append(user_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        where += " AND (e.user_id LIKE ? OR e.order_id LIKE ? OR u.user_name LIKE ?)"
        params.extend([like, like, like])
    total = int(
        db.query_one(
            conn,
            f"SELECT COUNT(*) AS c FROM risk_assessments a JOIN risk_events e ON e.id = a.event_id LEFT JOIN biz_users u ON u.user_id = e.user_id{where}",
            params,
        )["c"]
    )
    rows = db.query_all(
        conn,
        f"""
        SELECT a.id, a.risk_score, a.risk_level, a.decision, a.created_at, a.event_id,
               e.event_type, e.source_id, e.user_id, e.order_id, u.user_name,
               (SELECT COUNT(*) FROM rule_hits h WHERE h.assessment_id = a.id) AS hit_count,
               (SELECT c.id FROM risk_cases c WHERE c.assessment_id = a.id) AS case_id,
               (SELECT c.case_status FROM risk_cases c WHERE c.assessment_id = a.id) AS case_status
        FROM risk_assessments a
        JOIN risk_events e ON e.id = a.event_id
        LEFT JOIN biz_users u ON u.user_id = e.user_id
        {where}
        ORDER BY a.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    )
    items = [
        {
            "assessment_id": row["id"],
            "assessment_no": format_assessment_no(row["id"]),
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "event_type_label": EVENT_TYPES.get(row["event_type"], row["event_type"]),
            "source_id": row["source_id"],
            "user_id": row["user_id"],
            "user_name": row.get("user_name"),
            "order_id": row["order_id"],
            "risk_score": round(float(row["risk_score"]), 1),
            "risk_level": row["risk_level"],
            "risk_level_label": RISK_LEVELS.get(row["risk_level"], row["risk_level"]),
            "decision": row["decision"],
            "decision_label": DECISIONS.get(row["decision"], row["decision"]),
            "hit_count": int(row["hit_count"] or 0),
            "case_id": row["case_id"],
            "case_no": format_case_no(row["case_id"]),
            "case_status": row["case_status"],
            "case_status_label": CASE_STATUSES.get(row["case_status"]) if row["case_status"] else None,
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)),
        "feature_total": len(FEATURE_MAP),
    }
