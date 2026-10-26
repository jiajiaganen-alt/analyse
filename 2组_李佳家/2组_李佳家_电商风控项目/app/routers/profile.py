"""用户画像与用户检索接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app import db
from app.db import get_conn
from app.services.case_service import mask_phone
from app.services.profile_service import get_user_profile

router = APIRouter(prefix="/api/risk/users", tags=["用户画像"])


@router.get("", summary="用户检索", description="按用户编号或姓名检索用户，供画像页搜索与检查页选择演示样本。")
def users_list(
    keyword: str | None = Query(None, description="用户编号或姓名关键字"),
    limit: int = Query(20, ge=1, le=50),
) -> dict:
    with get_conn() as conn:
        sql = "SELECT user_id, user_name, phone, register_city, credit_score, vip_level FROM biz_users WHERE 1 = 1"
        params: list = []
        if keyword:
            like = f"%{keyword.strip()}%"
            sql += " AND (user_id LIKE ? OR user_name LIKE ?)"
            params.extend([like, like])
        sql += " ORDER BY user_id LIMIT ?"
        params.append(limit)
        rows = db.query_all(conn, sql, params)
        items = [
            {
                "user_id": row["user_id"],
                "user_name": row["user_name"],
                "phone": mask_phone(row["phone"]),
                "register_city": row["register_city"],
                "credit_score": row["credit_score"],
                "vip_level": row["vip_level"],
            }
            for row in rows
        ]
    return {"items": items, "total": len(items)}


@router.get("/{user_id}/profile", summary="查询用户画像", description="聚合历史订单、退款、投诉、地址、设备、最近风险事件、关联案件与风险趋势。")
def user_profile(user_id: str) -> dict:
    with get_conn() as conn:
        return get_user_profile(conn, user_id)
