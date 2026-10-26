"""规则管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_conn
from app.models import RuleCreateRequest, RuleDeleteRequest, RuleStatusRequest, RuleUpdateRequest
from app.services.rule_service import create_rule, delete_rule, list_rules, set_rule_status, update_rule

router = APIRouter(prefix="/api/risk/rules", tags=["规则管理"])


@router.get("", summary="查询规则列表", description="返回规则明细、命中次数与启用数量、累计命中、平均分等统计。")
def rules_list(
    keyword: str | None = Query(None, description="规则编码或名称关键字"),
    status: str | None = Query(None, description="规则状态：enabled / disabled"),
) -> dict:
    with get_conn() as conn:
        return list_rules(conn, keyword=keyword, status=status)


@router.post("", summary="新增规则", description="校验规则字段与条件 AST 后创建规则。")
def rule_create(payload: RuleCreateRequest) -> dict:
    with get_conn() as conn:
        return create_rule(conn, payload.model_dump())


@router.post("/update", summary="更新规则", description="支持修改规则名称、优先级、分值、状态、条件与描述。")
def rule_update(payload: RuleUpdateRequest) -> dict:
    data = payload.model_dump(exclude_unset=True)
    rule_id = int(data.pop("rule_id"))
    with get_conn() as conn:
        return update_rule(conn, rule_id, data)


@router.post("/status", summary="启停用规则", description="切换规则状态，停用后规则不再参与风险检查。")
def rule_status(payload: RuleStatusRequest) -> dict:
    with get_conn() as conn:
        return set_rule_status(conn, payload.rule_id, payload.rule_status)


@router.post("/delete", summary="删除规则", description="删除规则并同步清理该规则的历史命中明细，保证统计口径一致。")
def rule_delete(payload: RuleDeleteRequest) -> dict:
    with get_conn() as conn:
        return delete_rule(conn, payload.rule_id)
