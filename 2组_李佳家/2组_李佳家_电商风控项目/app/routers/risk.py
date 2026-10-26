"""风险检查与评估查询接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_conn
from app.models import RiskCheckRequest
from app.risk_agent import run_risk_check
from app.services.assessment_service import get_assessment_detail, list_assessments

router = APIRouter(prefix="/api/risk", tags=["风险检查"])


@router.post("/check", summary="发起风险检查", description="执行事件校验、特征计算、规则匹配、评分决策、黑名单校验与案件生成的完整 Agent 流程。")
def risk_check(payload: RiskCheckRequest) -> dict:
    with get_conn() as conn:
        return run_risk_check(conn, payload.model_dump())


@router.get("/assessments", summary="最近评估列表", description="按时间倒序返回风险评估记录，支持风险等级、用户与关键字筛选。")
def assessment_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    risk_level: str | None = Query(None, description="风险等级：low / medium / high"),
    keyword: str | None = Query(None, description="用户编号、订单编号或用户名关键字"),
    user_id: str | None = Query(None, description="用户编号"),
) -> dict:
    with get_conn() as conn:
        return list_assessments(
            conn,
            page=page,
            page_size=page_size,
            risk_level=risk_level,
            keyword=keyword,
            user_id=user_id,
        )


@router.get("/assessments/{assessment_id}", summary="评估详情", description="返回风险评分、等级、处理建议、特征快照、命中规则、黑名单命中与 Agent 轨迹。")
def assessment_detail(assessment_id: int) -> dict:
    with get_conn() as conn:
        return get_assessment_detail(conn, assessment_id)
