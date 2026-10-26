"""案件管理与审核接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_conn
from app.models import CaseReviewRequest
from app.services.case_service import get_case_detail, get_case_logs, list_cases, review_case

router = APIRouter(prefix="/api/risk/cases", tags=["案件管理"])


@router.get("", summary="查询案件列表", description="支持案件状态、风险等级、关键字筛选与分页，返回状态统计。")
def cases_list(
    case_status: str | None = Query(None, description="案件状态：pending / reviewing / approved / rejected / resolved"),
    status: str | None = Query(None, description="案件状态别名"),
    risk_level: str | None = Query(None, description="风险等级：low / medium / high"),
    keyword: str | None = Query(None, description="案件号、用户、订单或审核人关键字"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict:
    with get_conn() as conn:
        return list_cases(
            conn,
            case_status=case_status or status,
            risk_level=risk_level,
            keyword=keyword,
            page=page,
            page_size=page_size,
        )


@router.post("/review", summary="提交案件审核", description="审核结论 approved / rejected / resolved，写入审核日志并更新案件状态。")
def case_review(payload: CaseReviewRequest) -> dict:
    with get_conn() as conn:
        return review_case(
            conn,
            payload.case_id,
            payload.review_result,
            payload.review_remark,
            payload.reviewer_id,
        )


@router.get("/{case_id}", summary="查询案件详情", description="返回风险结果、命中规则、特征快照、黑名单命中、审核记录与 Agent 轨迹。")
def case_detail(case_id: int) -> dict:
    with get_conn() as conn:
        return get_case_detail(conn, case_id)


@router.get("/{case_id}/logs", summary="查询审核日志", description="返回案件的全部审核操作记录。")
def case_logs(case_id: int) -> dict:
    with get_conn() as conn:
        return get_case_logs(conn, case_id)
