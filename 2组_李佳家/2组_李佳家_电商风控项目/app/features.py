"""特征计算模块。

根据业务事件、用户、订单、地址、设备、登录日志与黑名单数据，
生成 39 个风险特征（用户维度 / 订单维度 / 地址维度 / 黑名单维度 / 事件维度）。
特征快照最终以键值对 JSON 落库到 ``feature_snapshots``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from sqlite3 import Connection
from typing import Any

from app import db
from app.blacklist_matcher import match_blacklists
from app.constants import BLACKLIST_BONUS, BLACKLIST_TYPES, REMOTE_PROVINCES
from app.utils import days_between, format_dt, haversine_km, parse_dt, round_value, safe_div

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_CITY_CACHE: dict[str, dict[str, Any]] | None = None


# 特征元数据：前端按 group 分组展示，规则校验也以此为准
FEATURE_DEFINITIONS: list[dict[str, str]] = [
    # 事件维度
    {"key": "event_type", "name": "事件类型", "group": "event", "group_name": "事件维度", "unit": "", "value_type": "str", "description": "本次风险检查的业务事件类型"},
    # 用户维度
    {"key": "user_register_days", "name": "注册天数", "group": "user", "group_name": "用户维度", "unit": "天", "value_type": "int", "description": "用户注册至本次事件发生的天数"},
    {"key": "user_order_cnt_30d", "name": "近30天下单数", "group": "user", "group_name": "用户维度", "unit": "单", "value_type": "int", "description": "近 30 天该用户的订单数量"},
    {"key": "user_order_cnt_90d", "name": "近90天下单数", "group": "user", "group_name": "用户维度", "unit": "单", "value_type": "int", "description": "近 90 天该用户的订单数量"},
    {"key": "user_refund_cnt", "name": "退款次数", "group": "user", "group_name": "用户维度", "unit": "次", "value_type": "int", "description": "用户历史退款申请次数"},
    {"key": "user_refund_rate", "name": "退款率", "group": "user", "group_name": "用户维度", "unit": "", "value_type": "float", "description": "退款次数 / 近 90 天下单数"},
    {"key": "user_complaint_cnt", "name": "投诉次数", "group": "user", "group_name": "用户维度", "unit": "次", "value_type": "int", "description": "用户历史物流投诉次数"},
    {"key": "user_high_risk_cnt", "name": "历史高风险次数", "group": "user", "group_name": "用户维度", "unit": "次", "value_type": "int", "description": "用户历史评估中高风险结论的次数"},
    {"key": "user_device_cnt", "name": "关联设备数", "group": "user", "group_name": "用户维度", "unit": "台", "value_type": "int", "description": "账号历史关联的设备数量"},
    {"key": "user_login_city_cnt", "name": "登录地数量", "group": "user", "group_name": "用户维度", "unit": "个", "value_type": "int", "description": "近 90 天登录城市数量"},
    {"key": "user_address_cnt", "name": "收货地址数", "group": "user", "group_name": "用户维度", "unit": "个", "value_type": "int", "description": "用户维护的收货地址数量"},
    {"key": "user_blacklist_hit", "name": "用户黑名单命中", "group": "user", "group_name": "用户维度", "unit": "", "value_type": "int", "description": "用户编号是否命中黑名单：1 是 / 0 否"},
    {"key": "user_avg_order_amount", "name": "客单价", "group": "user", "group_name": "用户维度", "unit": "元", "value_type": "float", "description": "用户历史订单平均金额"},
    {"key": "user_night_order_ratio", "name": "夜间下单占比", "group": "user", "group_name": "用户维度", "unit": "", "value_type": "float", "description": "22:00-06:00 下单数 / 近 90 天下单数"},
    {"key": "user_credit_score", "name": "用户信用分", "group": "user", "group_name": "用户维度", "unit": "分", "value_type": "int", "description": "平台信用评分，越低风险越高"},
    {"key": "user_is_enterprise", "name": "企业用户标识", "group": "user", "group_name": "用户维度", "unit": "", "value_type": "int", "description": "是否企业采购账号：1 是 / 0 否"},
    # 订单维度
    {"key": "order_amount", "name": "订单金额", "group": "order", "group_name": "订单维度", "unit": "元", "value_type": "float", "description": "本次事件关联订单的实付金额"},
    {"key": "order_discount_rate", "name": "折扣率", "group": "order", "group_name": "订单维度", "unit": "", "value_type": "float", "description": "优惠金额占订单原价比例"},
    {"key": "order_freight_ratio", "name": "运费占比", "group": "order", "group_name": "订单维度", "unit": "", "value_type": "float", "description": "运费 / 订单金额"},
    {"key": "order_pay_method", "name": "支付方式", "group": "order", "group_name": "订单维度", "unit": "", "value_type": "str", "description": "订单使用的支付渠道"},
    {"key": "order_pay_interval_sec", "name": "下单到支付间隔", "group": "order", "group_name": "订单维度", "unit": "秒", "value_type": "int", "description": "订单创建至支付完成的时间间隔"},
    {"key": "order_address_distance_km", "name": "收货地址与注册地距离", "group": "order", "group_name": "订单维度", "unit": "公里", "value_type": "float", "description": "收货城市与用户注册城市的球面距离"},
    {"key": "order_category", "name": "商品类目", "group": "order", "group_name": "订单维度", "unit": "", "value_type": "str", "description": "订单主要商品类目"},
    {"key": "order_category_risk_score", "name": "商品类目风险分", "group": "order", "group_name": "订单维度", "unit": "分", "value_type": "int", "description": "平台维护的商品类目风险评分"},
    {"key": "order_ip_order_cnt", "name": "同IP订单数", "group": "order", "group_name": "订单维度", "unit": "单", "value_type": "int", "description": "近 7 天同一 IP 的下单数量"},
    {"key": "order_device_order_cnt", "name": "同设备订单数", "group": "order", "group_name": "订单维度", "unit": "单", "value_type": "int", "description": "近 7 天同一设备的下单数量"},
    {"key": "order_item_cnt", "name": "订单商品件数", "group": "order", "group_name": "订单维度", "unit": "件", "value_type": "int", "description": "订单包含的商品总件数"},
    {"key": "order_hour", "name": "下单小时", "group": "order", "group_name": "订单维度", "unit": "时", "value_type": "int", "description": "订单创建时的小时（0-23）"},
    {"key": "order_is_new_address", "name": "是否新收货地址", "group": "order", "group_name": "订单维度", "unit": "", "value_type": "int", "description": "收货地址是否在近 7 天内新增：1 是 / 0 否"},
    # 地址维度
    {"key": "address_concentration", "name": "收货地址集中度", "group": "address", "group_name": "地址维度", "unit": "", "value_type": "float", "description": "寄往最常用地址的订单占比"},
    {"key": "address_change_cnt", "name": "地址变更次数", "group": "address", "group_name": "地址维度", "unit": "次", "value_type": "int", "description": "用户名下地址累计变更次数"},
    {"key": "address_phone_consistency", "name": "地址与手机号归属地一致性", "group": "address", "group_name": "地址维度", "unit": "", "value_type": "int", "description": "收货城市与手机号归属地一致为 1，不一致为 0"},
    {"key": "address_province_risk", "name": "偏远地区标识", "group": "address", "group_name": "地址维度", "unit": "", "value_type": "int", "description": "收货省份是否属于平台偏远地区名单"},
    {"key": "address_blacklist_hit", "name": "地址黑名单命中", "group": "address", "group_name": "地址维度", "unit": "", "value_type": "int", "description": "收货地址是否命中黑名单：1 是 / 0 否"},
    # 黑名单维度
    {"key": "blacklist_hit_cnt", "name": "黑名单命中总数", "group": "blacklist", "group_name": "黑名单维度", "unit": "次", "value_type": "int", "description": "本次检查命中的黑名单条目数量"},
    {"key": "device_blacklist_hit", "name": "设备黑名单命中", "group": "blacklist", "group_name": "黑名单维度", "unit": "", "value_type": "int", "description": "下单设备是否命中黑名单：1 是 / 0 否"},
    {"key": "phone_blacklist_hit", "name": "手机号黑名单命中", "group": "blacklist", "group_name": "黑名单维度", "unit": "", "value_type": "int", "description": "用户手机号是否命中黑名单：1 是 / 0 否"},
    {"key": "ip_blacklist_hit", "name": "IP黑名单命中", "group": "blacklist", "group_name": "黑名单维度", "unit": "", "value_type": "int", "description": "下单 IP 是否命中黑名单：1 是 / 0 否"},
    {"key": "blacklist_hit_detail", "name": "黑名单命中明细", "group": "blacklist", "group_name": "黑名单维度", "unit": "", "value_type": "str", "description": "命中黑名单的类型、取值与加权分值"},
]

FEATURE_MAP: dict[str, dict[str, str]] = {item["key"]: item for item in FEATURE_DEFINITIONS}
FEATURE_GROUPS: list[dict[str, str]] = [
    {"group": "event", "group_name": "事件维度"},
    {"group": "user", "group_name": "用户维度"},
    {"group": "order", "group_name": "订单维度"},
    {"group": "address", "group_name": "地址维度"},
    {"group": "blacklist", "group_name": "黑名单维度"},
]


@dataclass
class FeatureResult:
    """特征计算结果：快照 + 黑名单命中 + 计算上下文。"""

    snapshot: dict[str, Any]
    blacklist_hits: list[dict[str, Any]]
    user: dict[str, Any]
    order: dict[str, Any] | None
    address: dict[str, Any] | None


def load_city_coordinates() -> dict[str, dict[str, Any]]:
    """加载城市经纬度字典（带进程内缓存）。"""
    global _CITY_CACHE
    if _CITY_CACHE is None:
        raw = json.loads((DATA_DIR / "cities.json").read_text(encoding="utf-8"))
        _CITY_CACHE = raw
    return _CITY_CACHE


def get_feature_value(features: dict[str, Any], key: str) -> Any:
    """读取特征值，缺失时抛出明确异常。"""
    if key not in features:
        raise KeyError(f"未知特征：{key}")
    return features[key]


def build_feature_snapshot(conn: Connection,
    *,
    event_type: str,
    user_id: str,
    order_id: str | None,
    occurred_at: datetime,
) -> FeatureResult:
    """根据事件上下文生成特征快照。

    ``occurred_at`` 为事件发生时间：实时检查传入当前时间，历史演示数据传入历史时间，
    从而保证历史特征只使用该时间点之前的数据，避免“用未来数据评估过去”。
    """
    user = db.query_one(conn, "SELECT * FROM biz_users WHERE user_id = ?", (user_id,))
    if user is None:
        raise ValueError(f"用户不存在：{user_id}")
    order = db.query_one(conn, "SELECT * FROM biz_orders WHERE order_id = ?", (order_id,)) if order_id else None
    address = db.query_one(conn, "SELECT * FROM biz_addresses WHERE address_id = ?", (order["address_id"],)) if order else None
    city_map = load_city_coordinates()
    now_str = format_dt(occurred_at)
    day30 = format_dt(occurred_at - timedelta(days=30))
    day90 = format_dt(occurred_at - timedelta(days=90))
    day7 = format_dt(occurred_at - timedelta(days=7))
    register_dt = parse_dt(user["register_at"])

    # ---- 用户维度 ----
    order_cnt_30d = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_orders WHERE user_id = ? AND created_at >= ? AND created_at <= ?",
            (user_id, day30, now_str),
        )["c"]
    )
    order_cnt_90d = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_orders WHERE user_id = ? AND created_at >= ? AND created_at <= ?",
            (user_id, day90, now_str),
        )["c"]
    )
    refund_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_after_sales WHERE user_id = ? AND apply_type = 'refund' AND created_at <= ?",
            (user_id, now_str),
        )["c"]
    )
    complaint_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_after_sales WHERE user_id = ? AND apply_type = 'complaint' AND created_at <= ?",
            (user_id, now_str),
        )["c"]
    )
    high_risk_cnt = int(
        db.query_one(
            conn,
            """
            SELECT COUNT(*) AS c
            FROM risk_assessments a
            JOIN risk_events e ON e.id = a.event_id
            WHERE e.user_id = ? AND a.risk_level = 'high' AND a.created_at <= ?
            """,
            (user_id, now_str),
        )["c"]
    )
    device_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(DISTINCT device_id) AS c FROM biz_devices WHERE user_id = ? AND first_seen <= ?",
            (user_id, now_str),
        )["c"]
    )
    login_city_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(DISTINCT city) AS c FROM biz_login_logs WHERE user_id = ? AND login_at >= ? AND login_at <= ?",
            (user_id, day90, now_str),
        )["c"]
    )
    address_cnt = int(
        db.query_one(
            conn,
            "SELECT COUNT(*) AS c FROM biz_addresses WHERE user_id = ? AND created_at <= ?",
            (user_id, now_str),
        )["c"]
    )
    all_orders = db.query_all(
        conn,
        "SELECT amount, created_at, address_id FROM biz_orders WHERE user_id = ? AND created_at <= ?",
        (user_id, now_str),
    )
    avg_amount = safe_div(sum(float(item["amount"]) for item in all_orders), len(all_orders), 2)
    night_orders = 0
    for item in all_orders:
        created = parse_dt(item["created_at"])
        if created and (created.hour < 6 or created.hour >= 22):
            night_orders += 1
    night_ratio = safe_div(night_orders, len(all_orders), 4)

    # ---- 地址维度（依赖订单） ----
    receive_province = order["receive_province"] if order else (address["province"] if address else "")
    receive_city = order["receive_city"] if order else (address["city"] if address else "")
    address_change_cnt = int(
        db.query_one(
            conn,
            "SELECT COALESCE(SUM(change_cnt), 0) AS c FROM biz_addresses WHERE user_id = ? AND created_at <= ?",
            (user_id, now_str),
        )["c"]
    )
    address_counts: dict[str, int] = {}
    for item in all_orders:
        key = item["address_id"] or "unknown"
        address_counts[key] = address_counts.get(key, 0) + 1
    concentration = safe_div(max(address_counts.values()), sum(address_counts.values()), 4) if address_counts else 0.0
    phone_consistency = 1 if user["phone_city"] == receive_city else 0
    province_risk = 1 if receive_province in REMOTE_PROVINCES else 0

    # ---- 订单维度 ----
    amount = round_value(float(order["amount"]), 2) if order else 0.0
    freight_ratio = safe_div(float(order["freight"]), float(order["amount"]), 4) if order and order["amount"] else 0.0
    distance = 0.0
    if order:
        origin = city_map.get(user["register_city"])
        target = city_map.get(order["receive_city"])
        if origin and target:
            distance = haversine_km(origin["lat"], origin["lng"], target["lat"], target["lng"])
    ip_order_cnt = 0
    device_order_cnt = 0
    if order:
        ip_order_cnt = int(
            db.query_one(
                conn,
                "SELECT COUNT(*) AS c FROM biz_orders WHERE ip = ? AND created_at >= ? AND created_at <= ?",
                (order["ip"], day7, now_str),
            )["c"]
        )
        device_order_cnt = int(
            db.query_one(
                conn,
                "SELECT COUNT(*) AS c FROM biz_orders WHERE device_id = ? AND created_at >= ? AND created_at <= ?",
                (order["device_id"], day7, now_str),
            )["c"]
        )
    order_is_new_address = 0
    if address:
        address_created = parse_dt(address["created_at"])
        if address_created and address_created >= occurred_at - timedelta(days=7):
            order_is_new_address = 1
    order_hour = 0
    pay_interval = 0
    if order:
        created = parse_dt(order["created_at"])
        order_hour = created.hour if created else 0
        pay_interval = int(order["pay_interval_sec"] or 0)

    # ---- 黑名单维度 ----
    blacklist_hits = match_blacklists(
        conn,
        user_id=user_id,
        phone=user["phone"],
        order=order,
        address=address,
        occurred_at=occurred_at,
    )
    type_flags = {key: 0 for key in BLACKLIST_TYPES}
    for hit in blacklist_hits:
        type_flags[hit["blacklist_type"]] = 1
    detail = "；".join(
        f"{BLACKLIST_TYPES.get(hit['blacklist_type'], hit['blacklist_type'])}:{hit['blacklist_value']}(+{hit['added_score']:.0f})"
        for hit in blacklist_hits
    )

    snapshot: dict[str, Any] = {
        "event_type": event_type,
        "user_register_days": days_between(register_dt, occurred_at),
        "user_order_cnt_30d": order_cnt_30d,
        "user_order_cnt_90d": order_cnt_90d,
        "user_refund_cnt": refund_cnt,
        "user_refund_rate": safe_div(refund_cnt, order_cnt_90d, 4),
        "user_complaint_cnt": complaint_cnt,
        "user_high_risk_cnt": high_risk_cnt,
        "user_device_cnt": device_cnt,
        "user_login_city_cnt": login_city_cnt,
        "user_address_cnt": address_cnt,
        "user_blacklist_hit": type_flags["user"],
        "user_avg_order_amount": avg_amount,
        "user_night_order_ratio": night_ratio,
        "user_credit_score": int(user["credit_score"]),
        "user_is_enterprise": int(user["is_enterprise"]),
        "order_amount": amount,
        "order_discount_rate": round_value(float(order["discount_rate"]), 4) if order else 0.0,
        "order_freight_ratio": freight_ratio,
        "order_pay_method": order["pay_method"] if order else "未知",
        "order_pay_interval_sec": pay_interval,
        "order_address_distance_km": distance,
        "order_category": order["category"] if order else "未知",
        "order_category_risk_score": int(order["category_risk_score"]) if order else 0,
        "order_ip_order_cnt": ip_order_cnt,
        "order_device_order_cnt": device_order_cnt,
        "order_item_cnt": int(order["item_count"]) if order else 0,
        "order_hour": order_hour,
        "order_is_new_address": order_is_new_address,
        "address_concentration": concentration,
        "address_change_cnt": address_change_cnt,
        "address_phone_consistency": phone_consistency,
        "address_province_risk": province_risk,
        "address_blacklist_hit": type_flags["address"],
        "blacklist_hit_cnt": len(blacklist_hits),
        "device_blacklist_hit": type_flags["device"],
        "phone_blacklist_hit": type_flags["phone"],
        "ip_blacklist_hit": type_flags["ip"],
        "blacklist_hit_detail": detail or "无",
    }
    return FeatureResult(snapshot=snapshot, blacklist_hits=blacklist_hits, user=user, order=order, address=address)


def feature_definitions_for_api() -> dict[str, Any]:
    """返回前端需要的特征元数据。"""
    return {
        "items": FEATURE_DEFINITIONS,
        "groups": FEATURE_GROUPS,
        "total": len(FEATURE_DEFINITIONS),
    }
