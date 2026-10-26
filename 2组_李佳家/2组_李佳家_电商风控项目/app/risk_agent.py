"""风险 Agent：确定性的六步编排。

    事件校验 → 特征计算 → 规则匹配 → 评分决策 → 黑名单校验 → 案件生成

每一步的耗时、状态、摘要与关键数据都会写入 trace，随检查结果返回并落库，
前端以时间线形式展示。整个流程不依赖任何大模型或外部网络。
"""

from __future__ import annotations

from datetime import datetime
from sqlite3 import Connection
from time import perf_counter
from typing import Any

from app import db
from app.constants import CASE_STATUSES, DECISIONS, EVENT_TYPES, RISK_LEVELS
from app.errors import AppError
from app.features import FEATURE_DEFINITIONS, build_feature_snapshot
from app.rule_engine import calculate_decision, match_rules
from app.utils import format_case_no, format_dt, json_dumps, json_loads, now_dt, parse_dt


class TraceBuilder:
    """记录 Agent 每一步的执行情况。"""

    def __init__(self, started_at: datetime) -> None:
        self.started_at = started_at
        self.steps: list[dict[str, Any]] = []

    def add(
        self,
        name: str,
        begin: float,
        summary: str,
        detail: dict[str, Any] | None = None,
        status: str = "success",
    ) -> None:
        duration = round(max(0.01, (perf_counter() - begin) * 1000), 2)
        self.steps.append(
            {
                "step": len(self.steps) + 1,
                "name": name,
                "status": status,
                "duration_ms": duration,
                "summary": summary,
                "detail": detail or {},
                "at": format_dt(self.started_at),
            }
        )

    def total_ms(self) -> float:
        return round(sum(step["duration_ms"] for step in self.steps), 2)


def _validate_payload(conn: Connection, payload: dict[str, Any], occurred_at: datetime) -> tuple[str, str, str, str, dict[str, Any]]:
    """校验事件参数并确认用户、订单存在且匹配。"""
    event_type = str(payload.get("event_type") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    order_id = str(payload.get("order_id") or "").strip()
    source_id = str(payload.get("source_id") or "WEB").strip() or "WEB"

    if event_type not in EVENT_TYPES:
        raise AppError(f"不支持的事件类型：{event_type or '空'}，可选值：{', '.join(EVENT_TYPES)}")
    if not user_id:
        raise AppError("用户编号不能为空")
    if len(source_id) > 50:
        raise AppError("来源编号长度不能超过 50 个字符")
    if not order_id:
        raise AppError("订单编号不能为空")
    user = db.query_one(conn, "SELECT * FROM biz_users WHERE user_id = ?", (user_id,))
    if user is None:
        raise AppError(f"用户不存在：{user_id}", status_code=404)
    order = db.query_one(conn, "SELECT * FROM biz_orders WHERE order_id = ?", (order_id,))
    if order is None:
        raise AppError(f"订单不存在：{order_id}", status_code=404)
    if order["user_id"] != user_id:
        raise AppError(f"订单 {order_id} 不属于用户 {user_id}")
    order_created = parse_dt(order["created_at"])
    if order_created and order_created > occurred_at:
        raise AppError("订单创建时间晚于事件发生时间，无法进行风险评估")
    normalized = {
        "event_type": event_type,
        "source_id": source_id,
        "user_id": user_id,
        "order_id": order_id,
    }
    return event_type, user_id, order_id, source_id, normalized


def run_risk_check(conn: Connection, payload: dict[str, Any], occurred_at: datetime | None = None) -> dict[str, Any]:
    """执行一次完整的风险检查，写入事件、评估、快照、命中、轨迹与案件。"""
    overall_begin = perf_counter()
    occurred = occurred_at or now_dt()
    created_at = format_dt(occurred)
    trace = TraceBuilder(occurred)

    # 1. 事件校验
    begin = perf_counter()
    event_type, user_id, order_id, source_id, normalized_payload = _validate_payload(conn, payload, occurred)
    trace.add(
        "事件校验",
        begin,
        f"{EVENT_TYPES[event_type]}事件校验通过",
        {
            "event_type": event_type,
            "event_label": EVENT_TYPES[event_type],
            "user_id": user_id,
            "order_id": order_id,
            "source_id": source_id,
        },
    )

    cursor = conn.execute(
        "INSERT INTO risk_events (event_type, source_id, user_id, order_id, event_payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (event_type, source_id, user_id, order_id, json_dumps(normalized_payload), created_at),
    )
    event_id = int(cursor.lastrowid)

    # 2. 特征计算
    begin = perf_counter()
    try:
        feature_result = build_feature_snapshot(
            conn,
            event_type=event_type,
            user_id=user_id,
            order_id=order_id,
            occurred_at=occurred,
        )
    except ValueError as exc:
        raise AppError(str(exc), status_code=404) from exc
    features = feature_result.snapshot
    trace.add(
        "特征计算",
        begin,
        f"生成 {len(features)} 项特征，黑名单初筛命中 {len(feature_result.blacklist_hits)} 项",
        {
            "feature_count": len(features),
            "feature_total": len(FEATURE_DEFINITIONS),
            "blacklist_hit_count": len(feature_result.blacklist_hits),
            "register_days": features["user_register_days"],
            "refund_rate": features["user_refund_rate"],
            "order_amount": features["order_amount"],
        },
    )

    # 3. 规则匹配
    begin = perf_counter()
    rule_hits, evaluated_rules = match_rules(conn, features)
    trace.add(
        "规则匹配",
        begin,
        f"启用规则 {evaluated_rules} 条，命中 {len(rule_hits)} 条",
        {
            "enabled_rules": evaluated_rules,
            "hit_count": len(rule_hits),
            "rule_codes": [item["rule_code"] for item in rule_hits],
        },
    )

    # 4. 评分决策（规则分）
    begin = perf_counter()
    preliminary = calculate_decision(rule_hits, [])
    trace.add(
        "评分决策",
        begin,
        f"规则得分 {preliminary['risk_score']:g}，初步等级 {RISK_LEVELS[preliminary['risk_level']]}，建议 {DECISIONS[preliminary['decision']]}",
        {
            "rule_score_total": preliminary["rule_score_total"],
            "preliminary_score": preliminary["risk_score"],
            "preliminary_level": preliminary["risk_level"],
            "preliminary_decision": preliminary["decision"],
            "thresholds": {"low": "<30", "medium": "30-69", "high": ">=70"},
        },
    )

    # 5. 黑名单校验（直接加权）
    begin = perf_counter()
    blacklist_hits = feature_result.blacklist_hits
    final = calculate_decision(rule_hits, blacklist_hits)
    if blacklist_hits:
        blacklist_summary = (
            f"命中黑名单 {len(blacklist_hits)} 条，加权 +{final['blacklist_score_total']:g}；"
            f"最终得分 {final['risk_score']:g}，等级 {RISK_LEVELS[final['risk_level']]}"
        )
    else:
        blacklist_summary = f"未命中黑名单，最终得分 {final['risk_score']:g}，等级 {RISK_LEVELS[final['risk_level']]}"
    trace.add(
        "黑名单校验",
        begin,
        blacklist_summary,
        {
            "hit_count": len(blacklist_hits),
            "blacklist_score_total": final["blacklist_score_total"],
            "items": [
                {"type": hit["blacklist_type"], "value": hit["blacklist_value"], "added_score": hit["added_score"]}
                for hit in blacklist_hits
            ],
            "final_score": final["risk_score"],
            "risk_level": final["risk_level"],
            "decision": final["decision"],
        },
        status="warning" if blacklist_hits else "success",
    )

    # 落库：评估结果
    cursor = conn.execute(
        """
        INSERT INTO risk_assessments (event_id, risk_score, risk_level, decision, assessment_status, created_at)
        VALUES (?, ?, ?, ?, 'completed', ?)
        """,
        (event_id, final["risk_score"], final["risk_level"], final["decision"], created_at),
    )
    assessment_id = int(cursor.lastrowid)

    # 落库：特征快照
    conn.execute(
        "INSERT INTO feature_snapshots (assessment_id, feature_json, created_at) VALUES (?, ?, ?)",
        (assessment_id, json_dumps(features), created_at),
    )

    # 落库：命中规则
    for hit in rule_hits:
        conn.execute(
            "INSERT INTO rule_hits (assessment_id, rule_id, hit_score, hit_message, created_at) VALUES (?, ?, ?, ?, ?)",
            (assessment_id, hit["rule_id"], hit["hit_score"], hit["hit_message"], created_at),
        )

    # 落库：黑名单命中留痕
    for hit in blacklist_hits:
        conn.execute(
            """
            INSERT INTO blacklist_hit_records
                (assessment_id, blacklist_id, blacklist_type, blacklist_value, added_score, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                assessment_id,
                hit["blacklist_id"],
                hit["blacklist_type"],
                hit["blacklist_value"],
                hit["added_score"],
                created_at,
            ),
        )

    # 6. 案件生成
    begin = perf_counter()
    case_id: int | None = None
    should_create_case = final["risk_level"] == "high" or final["decision"] in {"manual_review", "reject"}
    if should_create_case:
        cursor = conn.execute(
            """
            INSERT INTO risk_cases (assessment_id, user_id, order_id, case_status, reviewer_id, review_result, created_at, updated_at)
            VALUES (?, ?, ?, 'pending', NULL, NULL, ?, ?)
            """,
            (assessment_id, user_id, order_id, created_at, created_at),
        )
        case_id = int(cursor.lastrowid)
        conn.execute(
            """
            INSERT INTO review_logs (case_id, operator_id, action_type, action_remark, created_at)
            VALUES (?, 'SYSTEM', 'create_case', ?, ?)
            """,
            (
                case_id,
                f"风险评分 {final['risk_score']:g}，等级 {RISK_LEVELS[final['risk_level']]}，系统自动创建案件",
                created_at,
            ),
        )
        trace.add(
            "案件生成",
            begin,
            f"触发自动建案，生成案件 {format_case_no(case_id)}",
            {"case_created": True, "case_id": case_id, "case_no": format_case_no(case_id), "case_status": "pending"},
        )
    else:
        trace.add(
            "案件生成",
            begin,
            "风险等级为低且建议放行，不创建案件",
            {"case_created": False, "reason": "low_risk_pass"},
            status="skipped",
        )

    # 落库：Agent 轨迹
    conn.execute(
        "INSERT INTO assessment_traces (assessment_id, trace_json, created_at) VALUES (?, ?, ?)",
        (assessment_id, json_dumps(trace.steps), created_at),
    )

    elapsed_ms = round((perf_counter() - overall_begin) * 1000, 2)

    return {
        "assessment_id": assessment_id,
        "assessment_no": f"AS-{assessment_id:06d}",
        "event_id": event_id,
        "event_type": event_type,
        "event_label": EVENT_TYPES[event_type],
        "source_id": source_id,
        "user_id": user_id,
        "order_id": order_id,
        "risk_score": final["risk_score"],
        "risk_level": final["risk_level"],
        "risk_level_label": RISK_LEVELS[final["risk_level"]],
        "decision": final["decision"],
        "decision_label": DECISIONS[final["decision"]],
        "assessment_status": "completed",
        "feature_snapshot": features,
        "rule_hits": rule_hits,
        "blacklist_hits": blacklist_hits,
        "case_id": case_id,
        "case_no": format_case_no(case_id),
        "case_status": "pending" if case_id else None,
        "case_status_label": CASE_STATUSES["pending"] if case_id else None,
        "score_detail": {
            "rule_score_total": final["rule_score_total"],
            "blacklist_score_total": final["blacklist_score_total"],
            "raw_score": final["raw_score"],
            "risk_score": final["risk_score"],
            "score_capped": final["score_capped"],
        },
        "trace": trace.steps,
        "agent_elapsed_ms": elapsed_ms,
        "created_at": created_at,
    }


def load_trace(conn: Connection, assessment_id: int) -> list[dict[str, Any]]:
    """读取评估对应的 Agent 轨迹。"""
    row = db.query_one(conn, "SELECT trace_json FROM assessment_traces WHERE assessment_id = ?", (assessment_id,))
    if not row:
        return []
    value = json_loads(row["trace_json"], default=[])
    return value if isinstance(value, list) else []
