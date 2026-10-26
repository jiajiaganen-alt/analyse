"""黑名单管理接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.db import get_conn
from app.models import BlacklistCreateRequest, BlacklistDeleteRequest, BlacklistImportRequest
from app.services.blacklist_service import (
    create_blacklist,
    delete_blacklists,
    import_blacklists,
    list_blacklists,
)

router = APIRouter(prefix="/api/risk/blacklists", tags=["黑名单管理"])


@router.get("", summary="查询黑名单", description="支持类型、状态、关键字筛选，返回类型统计与命中次数。")
def blacklists_list(
    blacklist_type: str | None = Query(None, description="类型：user / phone / address / device / ip"),
    keyword: str | None = Query(None, description="取值或备注关键字"),
    status: str | None = Query(None, description="active / inactive"),
) -> dict:
    with get_conn() as conn:
        return list_blacklists(conn, blacklist_type=blacklist_type, keyword=keyword, status=status)


@router.post("", summary="新增黑名单", description="新增单条黑名单，类型支持用户、手机号、地址、设备、IP。")
def blacklist_create(payload: BlacklistCreateRequest) -> dict:
    with get_conn() as conn:
        return create_blacklist(conn, payload.model_dump())


@router.post("/delete", summary="删除黑名单", description="按 id 或 ids 数组批量删除黑名单，历史命中留痕保留。")
def blacklist_delete(payload: BlacklistDeleteRequest) -> dict:
    ids = list(payload.ids or [])
    if payload.id is not None:
        ids.append(payload.id)
    with get_conn() as conn:
        return delete_blacklists(conn, ids)


@router.post("/import", summary="批量导入黑名单", description="逐条校验导入内容，返回成功数量与失败明细。")
def blacklist_import(payload: BlacklistImportRequest) -> dict:
    with get_conn() as conn:
        return import_blacklists(conn, [item.model_dump() for item in payload.items])
