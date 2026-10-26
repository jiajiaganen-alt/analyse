"""元数据接口：枚举字典、特征定义与演示样本。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app import db
from app.constants import (
    BLACKLIST_BONUS,
    BLACKLIST_TYPES,
    CASE_STATUSES,
    DECISIONS,
    EVENT_TYPES,
    LEVEL_THRESHOLDS,
    REJECT_THRESHOLD,
    REVIEWERS,
    RISK_LEVELS,
)
from app.db import get_conn
from app.features import feature_definitions_for_api

router = APIRouter(prefix="/api/risk", tags=["系统元数据"])


def _option_dict(mapping: dict[str, str]) -> list[dict[str, str]]:
    return [{"value": key, "label": label} for key, label in mapping.items()]


@router.get("/meta", summary="查询系统字典", description="返回事件类型、风险等级、处理建议、案件状态、黑名单类型、审核人、特征定义与评分阈值。")
def meta() -> dict[str, Any]:
    features = feature_definitions_for_api()
    return {
        "app_name": "电商风险控制系统",
        "version": "1.0.0",
        "event_types": _option_dict(EVENT_TYPES),
        "risk_levels": _option_dict(RISK_LEVELS),
        "decisions": _option_dict(DECISIONS),
        "case_statuses": _option_dict(CASE_STATUSES),
        "blacklist_types": [
            {"value": key, "label": label, "bonus_score": BLACKLIST_BONUS.get(key, 0)}
            for key, label in BLACKLIST_TYPES.items()
        ],
        "reviewers": [{"reviewer_id": key, "name": name} for key, name in REVIEWERS.items() if key != "SYSTEM"],
        "thresholds": {
            "low_max": LEVEL_THRESHOLDS[0],
            "medium_max": LEVEL_THRESHOLDS[1],
            "reject_min": REJECT_THRESHOLD,
        },
        "features": features,
    }


@router.get("/features", summary="查询特征定义", description="返回 39 项风险特征的名称、分组、单位、类型与说明。")
def features() -> dict[str, Any]:
    return feature_definitions_for_api()


def _latest_order(conn, user_id: str, min_amount: float = 0.0) -> dict[str, Any] | None:
    return db.query_one(
        conn,
        """
        SELECT o.*, u.user_name
        FROM biz_orders o
        JOIN biz_users u ON u.user_id = o.user_id
        WHERE o.user_id = ? AND o.amount >= ?
        ORDER BY o.created_at DESC, o.order_id DESC
        LIMIT 1
        """,
        (user_id, min_amount),
    )


@router.get("/demo-samples", summary="查询演示样本", description="从真实业务数据中选取四类事件样本，供风险检查页一键填充。")
def demo_samples() -> dict[str, Any]:
    scenarios = [
        ("high", "U1001", 2000.0, "after_sale_apply", "高危售后场景", "新账号 + 高退款率 + 黑名单设备，预期自动建案", "APP"),
        ("medium", "U1002", 5000.0, "order_create", "中风险大额下单", "新账号大额订单叠加高折扣，预期人工审核", "H5"),
        ("low", "U1010", 0.0, "order_pay", "低风险正常支付", "老账号正常消费，预期放行", "MINI_PROGRAM"),
        ("complaint", "U1005", 0.0, "logistics_complaint", "物流投诉聚集", "短周期多笔售后与投诉，预期高风险", "APP"),
    ]
    items: list[dict[str, Any]] = []
    with get_conn() as conn:
        for key, user_id, min_amount, event_type, label, description, source in scenarios:
            order = _latest_order(conn, user_id, min_amount)
            if not order:
                continue
            items.append(
                {
                    "sample_key": key,
                    "label": f"{label} · {user_id}",
                    "description": description,
                    "event_type": event_type,
                    "event_type_label": EVENT_TYPES.get(event_type, event_type),
                    "user_id": user_id,
                    "user_name": order["user_name"],
                    "order_id": order["order_id"],
                    "order_amount": round(float(order["amount"]), 2),
                    "source_id": source,
                }
            )
    return {"items": items, "total": len(items)}
