"""通用工具：时间格式化、JSON 读写、数值处理、地理距离计算。"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from typing import Any

TIME_FMT = "%Y-%m-%d %H:%M:%S"


def now_dt() -> datetime:
    """当前本地时间（秒级）。"""
    return datetime.now().replace(microsecond=0)


def format_dt(value: datetime | None = None) -> str:
    """格式化时间为数据库存储格式。"""
    return (value or now_dt()).strftime(TIME_FMT)


def parse_dt(value: str | None) -> datetime | None:
    """解析数据库时间字符串。"""
    if not value:
        return None
    try:
        return datetime.strptime(value, TIME_FMT)
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def json_dumps(value: Any) -> str:
    """稳定、中文友好的 JSON 序列化。"""
    return json.dumps(value, ensure_ascii=False, default=str)


def json_loads(value: str | None, default: Any = None) -> Any:
    """安全 JSON 反序列化。"""
    if not value:
        return default
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def round_value(value: float, digits: int = 2) -> float:
    """避免 -0.0 与过长小数。"""
    result = round(float(value), digits)
    return 0.0 if result == 0 else result


def safe_div(numerator: float, denominator: float, digits: int = 4) -> float:
    """安全除法，分母为 0 时返回 0。"""
    if not denominator:
        return 0.0
    return round_value(numerator / denominator, digits)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """根据经纬度计算球面距离（公里）。"""
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return round_value(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 1)


def days_between(start: datetime | None, end: datetime | None = None) -> int:
    """计算整天数，至少为 0。"""
    if start is None:
        return 0
    end = end or now_dt()
    return max(0, (end - start).days)


def hours_between(start: datetime | None, end: datetime | None = None) -> float:
    """计算小时数，保留 1 位小数。"""
    if start is None:
        return 0.0
    end = end or now_dt()
    return round_value(max(0.0, (end - start).total_seconds() / 3600.0), 1)


def last_n_days(n: int, end: datetime | None = None) -> list[str]:
    """返回包含今天在内、连续 n 天的日期字符串列表。"""
    end = end or now_dt()
    return [(end - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(n - 1, -1, -1)]


def format_case_no(case_id: int | None) -> str:
    """案件展示编号：CASE-000001。"""
    if not case_id:
        return ""
    return f"CASE-{int(case_id):06d}"


def format_assessment_no(assessment_id: int | None) -> str:
    """评估展示编号：AS-000001。"""
    if not assessment_id:
        return ""
    return f"AS-{int(assessment_id):06d}"
