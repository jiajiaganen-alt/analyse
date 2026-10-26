"""案件服务：列表、详情、审核流转与审核日志。"""

from __future__ import annotations

import math
import re
from sqlite3 import Connection
from typing import Any

from app import db
from app.constants import CASE_FINAL_STATUSES, CASE_STATUSES, DECISIONS, EVENT_TYPES, REVIEWERS, RISK_LEVELS
from app.errors import AppError
from app.features import FEATURE_MAP
from app.risk_agent import load_trace
from app.services.assessment_service import get_blacklist_hits, get_rule_hits
from app.utils import format_case_no, json_loads, now_dt, format_dt

ACTION_LABELS: dict[str, str] = {
    "create_case": "创建案件",
    "start_review": "开始审核",
    "approved": "审核通过",
    "rejected": "审核拒绝",
    "resolved": "标记解决",
    "comment": "审核备注",
}
REVIEW_RESULTS = {"approved", "rejected", "resolved"}


def reviewer_name(reviewer_id: str | None) -> str | None:
    """审核人展示名。"""
    if not reviewer_id:
        return None
    return REVIEWERS.get(reviewer_id, reviewer_id)


def mask_phone(phone: str | None) -> str:
    """手机号脱敏。"""
    if not phone:
        return ""
    if len(phone) >= 7:
        return phone[:3] + "****" + phone[-4:]
    return phone


def _serialize_log(row: dict[str, Any]) -> dict[str, Any]:
    """审核日志结构。"""
    return {
        "id": row["id"],
        "case_id": row["case_id"],
        "operator_id": row["operator_id"],
        "operator_name": reviewer_name(row["operator_id"]),
        "action_type": row["action_type"],
        "action_label": ACTION_LABELS.get(row["action_type"], row["action_type"]),
        "action_remark": row["action_remark"],
        "created_at": row["created_at"],
    }


def get_case_logs(conn: Connection, case_id: int) -> dict[str, Any]:
    """查询案件审核日志。"""
    case = db.query_one(conn, "SELECT id FROM risk_cases WHERE id = ?", (case_id,))
    if case is None:
        raise AppError(f"案件不存在：{case_id}", status_code=404)
    rows = db.query_all(conn, "SELECT * FROM review_logs WHERE case_id = ? ORDER BY id ASC", (case_id,))
    return {"case_id": case_id, "case_no": format_case_no(case_id), "items": [_serialize_log(row) for row in rows], "total": len(rows)}


def list_cases(conn: Connection,
    case_status: str | None = None,
    risk_level: str | None = None,
    keyword: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """案件列表，支持状态、等级、关键字筛选与分页。"""
    page = max(1, int(page))
    page_size = max(1, min(100, int(page_size)))
    where = " WHERE 1 = 1"
    params: list[Any] = []
    if case_status:
        if case_status not in CASE_STATUSES:
            raise AppError(f"不支持的案件状态：{case_status}")
        where += " AND c.case_status = ?"
        params.append(case_status)
    if risk_level:
        if risk_level not in RISK_LEVELS:
            raise AppError(f"不支持的风险等级：{risk_level}")
        where += " AND a.risk_level = ?"
        params.append(risk_level)
    if keyword:
        term = keyword.strip()
        like = f"%{term}%"
        where += " AND (e.user_id LIKE ? OR e.order_id LIKE ? OR u.user_name LIKE ? OR c.reviewer_id LIKE ?"
        params.extend([like, like, like, like])
        match = re.fullmatch(r"(?:CASE-)?0*(\d+)", term, flags=re.IGNORECASE)
        if match:
            where += " OR c.id = ?"
            params.append(int(match.group(1)))
        where += ")"
    total = int(
        db.query_one(
            conn,
            f"""
            SELECT COUNT(*) AS c
            FROM risk_cases c
            JOIN risk_assessments a ON a.id = c.assessment_id
            JOIN risk_events e ON e.id = a.event_id
            LEFT JOIN biz_users u ON u.user_id = c.user_id
            {where}
            """,
            params,
        )["c"]
    )
    rows = db.query_all(
        conn,
        f"""
        SELECT c.*, a.risk_score, a.risk_level, a.decision, e.event_type,
               u.user_name,
               (SELECT COUNT(*) FROM rule_hits h WHERE h.assessment_id = a.id) AS hit_count
        FROM risk_cases c
        JOIN risk_assessments a ON a.id = c.assessment_id
        JOIN risk_events e ON e.id = a.event_id
        LEFT JOIN biz_users u ON u.user_id = c.user_id
        {where}
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT ? OFFSET ?
        """,
        [*params, page_size, (page - 1) * page_size],
    )
    items = [
        {
            "case_id": row["id"],
            "case_no": format_case_no(row["id"]),
            "assessment_id": row["assessment_id"],
            "user_id": row["user_id"],
            "user_name": row.get("user_name"),
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
            "review_result": row["review_result"],
            "review_result_label": CASE_STATUSES.get(row["review_result"]) if row["review_result"] else None,
            "hit_count": int(row["hit_count"] or 0),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]
    status_stats = {key: 0 for key in CASE_STATUSES}
    for stat in db.query_all(conn, "SELECT case_status, COUNT(*) AS c FROM risk_cases GROUP BY case_status"):
        status_stats[stat["case_status"]] = int(stat["c"])
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, math.ceil(total / page_size)),
        "status_stats": status_stats,
        "status_labels": CASE_STATUSES,
    }


def get_case_detail(conn: Connection, case_id: int) -> dict[str, Any]:
    """案件详情：风险结果、命中规则、特征快照、审核记录与审核表单数据。"""
    row = db.query_one(
        conn,
        """
        SELECT c.*, a.risk_score, a.risk_level, a.decision, a.event_id, a.created_at AS assessment_created_at,
               e.event_type, e.source_id, e.user_id, e.order_id,
               u.user_name, u.phone, u.credit_score, u.vip_level,
               o.amount AS order_amount, o.category AS order_category, o.pay_method, o.created_at AS order_created_at,
               (SELECT COUNT(*) FROM rule_hits h WHERE h.assessment_id = a.id) AS hit_count
        FROM risk_cases c
        JOIN risk_assessments a ON a.id = c.assessment_id
        JOIN risk_events e ON e.id = a.event_id
        LEFT JOIN biz_users u ON u.user_id = c.user_id
        LEFT JOIN biz_orders o ON o.order_id = c.order_id
        WHERE c.id = ?
        """,
        (case_id,),
    )
    if row is None:
        raise AppError(f"案件不存在：{case_id}", status_code=404)
    assessment_id = int(row["assessment_id"])
    snapshot_row = db.query_one(conn, "SELECT feature_json FROM feature_snapshots WHERE assessment_id = ?", (assessment_id,))
    feature_snapshot = json_loads(snapshot_row["feature_json"], default={}) if snapshot_row else {}
    logs_rows = db.query_all(conn, "SELECT * FROM review_logs WHERE case_id = ? ORDER BY id ASC", (case_id,))
    review_logs = [_serialize_log(item) for item in logs_rows]
    final_log = next(
        (item for item in reversed(review_logs) if item["action_type"] in CASE_FINAL_STATUSES),
        None,
    )
    return {
        "case_id": row["id"],
        "case_no": format_case_no(row["id"]),
        "case_status": row["case_status"],
        "case_status_label": CASE_STATUSES.get(row["case_status"], row["case_status"]),
        "reviewer_id": row["reviewer_id"],
        "reviewer_name": reviewer_name(row["reviewer_id"]),
        "review_result": row["review_result"],
        "review_result_label": CASE_STATUSES.get(row["review_result"]) if row["review_result"] else None,
        "review_remark": final_log["action_remark"] if final_log else "",
        "reviewed_at": final_log["created_at"] if final_log else None,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "assessment": {
            "assessment_id": assessment_id,
            "assessment_no": f"AS-{assessment_id:06d}",
            "risk_score": round(float(row["risk_score"]), 1),
            "risk_level": row["risk_level"],
            "risk_level_label": RISK_LEVELS.get(row["risk_level"], row["risk_level"]),
            "decision": row["decision"],
            "decision_label": DECISIONS.get(row["decision"], row["decision"]),
            "event_id": row["event_id"],
            "event_type": row["event_type"],
            "event_type_label": EVENT_TYPES.get(row["event_type"], row["event_type"]),
            "source_id": row["source_id"],
            "created_at": row["assessment_created_at"],
        },
        "user": {
            "user_id": row["user_id"],
            "user_name": row.get("user_name"),
            "phone": mask_phone(row.get("phone")),
            "credit_score": row.get("credit_score"),
            "vip_level": row.get("vip_level"),
        },
        "order": {
            "order_id": row["order_id"],
            "amount": round(float(row["order_amount"]), 2) if row.get("order_amount") is not None else None,
            "category": row.get("order_category"),
            "pay_method": row.get("pay_method"),
            "created_at": row.get("order_created_at"),
        },
        "hit_count": int(row["hit_count"] or 0),
        "rule_hits": get_rule_hits(conn, assessment_id),
        "blacklist_hits": get_blacklist_hits(conn, assessment_id),
        "feature_snapshot": feature_snapshot,
        "feature_total": len(FEATURE_MAP),
        "review_logs": review_logs,
        "trace": load_trace(conn, assessment_id),
    }


def review_case(conn: Connection,
    case_id: int,
    review_result: str,
    review_remark: str = "",
    reviewer_id: str = "RV001",
) -> dict[str, Any]:
    """提交案件审核结论，更新案件并写入审核日志。"""
    if review_result not in REVIEW_RESULTS:
        raise AppError("审核结论必须为 approved、rejected 或 resolved")
    reviewer_id = str(reviewer_id or "RV001").strip()
    if not reviewer_id or len(reviewer_id) > 50:
        raise AppError("审核人编号不能为空且不能超过 50 个字符")
    remark = str(review_remark or "").strip()
    if len(remark) > 500:
        raise AppError("审核备注不能超过 500 个字符")
    case = db.query_one(conn, "SELECT * FROM risk_cases WHERE id = ?", (case_id,))
    if case is None:
        raise AppError(f"案件不存在：{case_id}", status_code=404)
    if case["case_status"] in CASE_FINAL_STATUSES:
        raise AppError(f"案件已审核（{CASE_STATUSES.get(case['case_status'], case['case_status'])}），请勿重复提交")
    now = format_dt(now_dt())
    conn.execute(
        """
        UPDATE risk_cases
        SET case_status = ?, reviewer_id = ?, review_result = ?, updated_at = ?
        WHERE id = ?
        """,
        (review_result, reviewer_id, review_result, now, case_id),
    )
    conn.execute(
        """
        INSERT INTO review_logs (case_id, operator_id, action_type, action_remark, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (case_id, reviewer_id, review_result, remark, now),
    )
    return get_case_detail(conn, case_id)
