"""电商风险控制系统 FastAPI 入口。

启动命令：
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8713

首次启动会自动建库（data/risk_control.db）并灌入演示数据。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import db
from app.constants import CASE_STATUSES, DECISIONS, EVENT_TYPES, REVIEWERS, RISK_LEVELS
from app.errors import AppError
from app.routers import blacklists, cases, dashboard, meta, profile, risk, rules
from app.utils import format_dt, now_dt

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """应用启动时初始化数据库与演示数据。"""
    db.init_db(seed=True)
    yield


app = FastAPI(
    title="电商风险控制系统",
    description=(
        "面向电商业务的实时风险控制平台，覆盖风险识别、规则判断、人工复核、处置留痕和结果查询的完整闭环。\n\n"
        "风险 Agent 采用确定性六步编排：事件校验 → 特征计算 → 规则匹配 → 评分决策 → 黑名单校验 → 案件生成。"
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "风险检查", "description": "发起风险检查、查询评估结果与特征快照"},
        {"name": "规则管理", "description": "规则增删改查、启停用与条件 AST 校验"},
        {"name": "案件管理", "description": "案件列表、详情、审核流转与审核日志"},
        {"name": "黑名单管理", "description": "黑名单查询、新增、删除与批量导入"},
        {"name": "用户画像", "description": "用户检索与画像聚合查询"},
        {"name": "运营看板", "description": "事件、案件、规则、黑名单统计与趋势"},
        {"name": "系统元数据", "description": "枚举字典、特征定义与演示样本"},
        {"name": "系统", "description": "健康检查与接口文档"},
    ],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    """业务异常统一返回 JSON。"""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code, "data": None},
    )


@app.get("/api/health", tags=["系统"], summary="健康检查", description="返回服务状态、数据库状态与核心数据量。")
def health() -> dict[str, Any]:
    try:
        with db.get_conn() as conn:
            counts = {
                "users": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM biz_users")["c"]),
                "orders": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM biz_orders")["c"]),
                "rules": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_rules")["c"]),
                "events": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_events")["c"]),
                "assessments": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_assessments")["c"]),
                "cases": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_cases")["c"]),
                "blacklists": int(db.query_one(conn, "SELECT COUNT(*) AS c FROM blacklists")["c"]),
            }
        return {
            "status": "ok",
            "app": "电商风险控制系统",
            "version": "1.0.0",
            "database": "ready",
            "database_path": str(db.get_db_path().name),
            "counts": counts,
            "server_time": format_dt(now_dt()),
        }
    except Exception as exc:  # pragma: no cover - 仅在数据库异常时触发
        return {
            "status": "degraded",
            "app": "电商风险控制系统",
            "version": "1.0.0",
            "database": "unavailable",
            "error": str(exc),
            "server_time": format_dt(now_dt()),
        }


@app.get("/api/meta/dicts", tags=["系统"], summary="查询基础字典", description="返回事件、等级、建议、案件状态、黑名单类型等基础字典。")
def dicts() -> dict[str, Any]:
    return {
        "event_types": EVENT_TYPES,
        "risk_levels": RISK_LEVELS,
        "decisions": DECISIONS,
        "case_statuses": CASE_STATUSES,
        "reviewers": REVIEWERS,
    }


@app.get("/docs", include_in_schema=False)
def api_docs() -> FileResponse:
    """离线接口文档页（不依赖任何外部 CDN）。"""
    return FileResponse(STATIC_DIR / "docs.html", media_type="text/html; charset=utf-8")


# 业务路由
app.include_router(risk.router)
app.include_router(rules.router)
app.include_router(cases.router)
app.include_router(blacklists.router)
app.include_router(profile.router)
app.include_router(dashboard.router)
app.include_router(meta.router)

# 静态资源（单页应用）必须最后挂载，避免拦截 API
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
