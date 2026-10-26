"""系统常量与字典：事件类型、风险等级、处理建议、案件状态、黑名单类型等。"""

from __future__ import annotations

from typing import Final

# 业务事件
EVENT_TYPES: Final[dict[str, str]] = {
    "order_create": "下单",
    "order_pay": "支付",
    "after_sale_apply": "售后申请",
    "logistics_complaint": "物流投诉",
}

# 风险等级
RISK_LEVELS: Final[dict[str, str]] = {
    "low": "低风险",
    "medium": "中风险",
    "high": "高风险",
}

# 处理建议
DECISIONS: Final[dict[str, str]] = {
    "pass": "放行",
    "manual_review": "人工审核",
    "reject": "拒绝",
}

# 案件状态
CASE_STATUSES: Final[dict[str, str]] = {
    "pending": "待审核",
    "reviewing": "审核中",
    "approved": "已通过",
    "rejected": "已拒绝",
    "resolved": "已解决",
}

# 黑名单类型
BLACKLIST_TYPES: Final[dict[str, str]] = {
    "user": "用户",
    "phone": "手机号",
    "address": "地址",
    "device": "设备",
    "ip": "IP",
}

# 黑名单命中后的直接加权分值（命中多条可累加）
BLACKLIST_BONUS: Final[dict[str, float]] = {
    "user": 20.0,
    "phone": 15.0,
    "address": 12.0,
    "device": 15.0,
    "ip": 10.0,
}

# 审核人字典（演示环境）
REVIEWERS: Final[dict[str, str]] = {
    "RV001": "张审核",
    "RV002": "李复核",
    "RV003": "王主管",
    "SYSTEM": "系统",
}

# 案件最终状态
CASE_FINAL_STATUSES: Final[set[str]] = {"approved", "rejected", "resolved"}

# 评分分档阈值
LEVEL_THRESHOLDS: Final[tuple[float, float]] = (30.0, 70.0)
REJECT_THRESHOLD: Final[float] = 85.0

# 偏远地区（用于地址维度特征）
REMOTE_PROVINCES: Final[set[str]] = {"新疆", "西藏", "海南", "内蒙古", "青海"}


def level_of(score: float) -> str:
    """按分数返回风险等级：<30 low，30-69 medium，>=70 high。"""
    if score >= LEVEL_THRESHOLDS[1]:
        return "high"
    if score >= LEVEL_THRESHOLDS[0]:
        return "medium"
    return "low"


def decision_of(score: float) -> str:
    """按分数返回处理建议：<30 放行，30-84 人工审核，>=85 拒绝。"""
    if score >= REJECT_THRESHOLD:
        return "reject"
    if score >= LEVEL_THRESHOLDS[0]:
        return "manual_review"
    return "pass"


def priority_weight(priority: int) -> float:
    """优先级计分权重：优先级越高，命中分值获得 1% - 9% 的加权。"""
    priority = max(1, min(10, int(priority)))
    return round(1.0 + (priority - 1) * 0.01, 2)
