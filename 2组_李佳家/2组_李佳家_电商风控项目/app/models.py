"""API 请求模型（Pydantic）。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RiskCheckRequest(BaseModel):
    """风险检查请求。"""

    event_type: str = Field(..., description="业务事件类型：order_create / order_pay / after_sale_apply / logistics_complaint")
    user_id: str = Field(..., description="用户编号")
    order_id: str = Field(..., description="订单编号")
    source_id: str = Field("WEB", description="来源编号，例如 APP、H5、MINI_PROGRAM")


class RuleCreateRequest(BaseModel):
    """新增规则请求。"""

    rule_code: str = Field(..., description="规则编码，字母开头，2-20 位")
    rule_name: str = Field(..., description="规则名称")
    rule_status: str = Field("enabled", description="规则状态：enabled / disabled")
    priority: int = Field(5, description="优先级 1-10")
    score: int = Field(10, description="命中分值 0-100")
    condition_json: Any = Field(..., description="条件 AST（JSON 对象或 JSON 字符串）")
    description: str = Field("", description="规则描述")


class RuleUpdateRequest(BaseModel):
    """更新规则请求（支持部分字段）。"""

    rule_id: int
    rule_code: str | None = None
    rule_name: str | None = None
    rule_status: str | None = None
    priority: int | None = None
    score: int | None = None
    condition_json: Any | None = None
    description: str | None = None


class RuleStatusRequest(BaseModel):
    """启停用规则请求。"""

    rule_id: int
    rule_status: str = Field(..., description="enabled / disabled")


class RuleDeleteRequest(BaseModel):
    """删除规则请求。"""

    rule_id: int


class CaseReviewRequest(BaseModel):
    """案件审核请求。"""

    case_id: int
    review_result: str = Field(..., description="审核结论：approved / rejected / resolved")
    review_remark: str = Field("", description="审核备注")
    reviewer_id: str = Field("RV001", description="审核人编号")


class BlacklistCreateRequest(BaseModel):
    """新增黑名单请求。"""

    blacklist_type: str = Field(..., description="user / phone / address / device / ip")
    blacklist_value: str
    remark: str = ""
    status: str = Field("active", description="active / inactive")


class BlacklistDeleteRequest(BaseModel):
    """删除黑名单请求，支持单个 id 或 ids 数组。"""

    id: int | None = None
    ids: list[int] | None = None


class BlacklistImportItem(BaseModel):
    """批量导入的单条黑名单。"""

    blacklist_type: str
    blacklist_value: str
    remark: str = ""
    status: str = "active"


class BlacklistImportRequest(BaseModel):
    """批量导入请求。"""

    items: list[BlacklistImportItem]
