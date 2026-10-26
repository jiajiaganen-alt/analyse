"""运营看板接口。"""

from __future__ import annotations

from fastapi import APIRouter

from app.db import get_conn
from app.services.dashboard_service import get_dashboard

router = APIRouter(prefix="/api/risk", tags=["运营看板"])


@router.get("/dashboard", summary="查询运营看板", description="返回事件总数、高风险占比、案件处理效率、规则命中排行、黑名单命中与近 7 日趋势。")
def dashboard() -> dict:
    with get_conn() as conn:
        return get_dashboard(conn)
