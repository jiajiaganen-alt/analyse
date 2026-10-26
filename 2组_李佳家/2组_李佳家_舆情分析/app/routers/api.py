"""REST 接口与 WebSocket 路由，严格对应需求文档 2.2.9 / 2.2.10。"""
from __future__ import annotations

import asyncio
import re
from typing import Any

from fastapi import APIRouter, Body, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from ..agents.graph import NODE_TYPES
from ..config import APP_LABELS, APP_NAMES, SOURCE_TYPES
from ..errors import AppError
from ..utils import iso, iso_ms, now

router = APIRouter()

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ctx(request: Request):
    return request.app.state.storage, request.app.state.pm, request.app.state.bus


def _check_app(pm, app_name: str) -> None:
    if app_name not in APP_NAMES:
        raise AppError(
            f"未知应用：{app_name}",
            status_code=404,
            module="process_manager",
            detail={"available_apps": APP_NAMES},
        )


# ---------------------------------------------------------------------- 健康
@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    storage, pm, bus = ctx(request)
    system = pm.system_payload()
    return {
        "status": "ok" if system["system_status"] in ("online", "starting") else "degraded",
        "ok": True,
        "app": system["platform_name"],
        "version": system["version"],
        "system_status": system["system_status"],
        "running_apps": system["running_apps"],
        "uptime_seconds": system["uptime_seconds"],
        "ws_clients": bus.client_count,
        "report_count": storage.stats()["report_count"],
        "time": iso(now()),
    }


# ---------------------------------------------------------------------- 控制台
@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    _, pm, bus = ctx(request)
    payload = pm.status_payload()
    payload["ok"] = True
    payload["system"]["ws_clients"] = bus.client_count
    payload["app_definitions"] = [
        {
            "app_name": app["app_name"],
            "display_name": app["display_name"],
            "description": app["description"],
            "status": app["status"],
            "enabled": app["enabled"],
        }
        for app in payload["apps"]
    ]
    return payload


@router.get("/start/{app_name}")
def start_app(request: Request, app_name: str, wait: int = Query(default=0, ge=0, le=1)) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    _check_app(pm, app_name)
    app = pm.start_app(app_name, wait=bool(wait))
    return {
        "ok": True,
        "app_name": app_name,
        "status": app["status"],
        "message": f"应用「{app['display_name']}」{app['status_label']}",
        "app": app,
    }


@router.get("/stop/{app_name}")
def stop_app(request: Request, app_name: str, wait: int = Query(default=0, ge=0, le=1)) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    _check_app(pm, app_name)
    app = pm.stop_app(app_name, wait=bool(wait))
    return {
        "ok": True,
        "app_name": app_name,
        "status": app["status"],
        "message": f"应用「{app['display_name']}」{app['status_label']}",
        "app": app,
    }


@router.get("/output/{app_name}")
def app_output(request: Request, app_name: str) -> dict[str, Any]:
    storage, pm, _ = ctx(request)
    _check_app(pm, app_name)
    data = storage.read_output(app_name)
    snapshot = pm.app_snapshot(app_name)
    return {
        **data,
        "ok": True,
        "status": snapshot["status"],
        "display_name": snapshot["display_name"],
        "task_count": snapshot["task_count"],
        "updated_label": data.get("updated_at"),
    }


@router.get("/test_log/{app_name}")
def test_log(
    request: Request,
    app_name: str,
    lines: int = Query(default=0, ge=0, le=2000),
) -> dict[str, Any]:
    storage, pm, _ = ctx(request)
    _check_app(pm, app_name)
    limit = lines or int(pm.config.section("runtime").get("log_tail_lines", 200))
    data = storage.read_app_log(app_name, limit=limit)
    return {**data, "ok": True, "display_name": pm.app_snapshot(app_name)["display_name"]}


# ---------------------------------------------------------------------- 检索
class SearchRequest(BaseModel):
    query: str = Field(default="", description="主题词/关键词")
    source_types: list[str] | None = Field(default=None, description="来源类型多选")
    max_sources: int | None = Field(default=None, ge=5, le=200)
    auto_start: bool = Field(default=True, description="是否自动启动未运行的分析应用")


@router.post("/search")
def search(request: Request, payload: SearchRequest) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    pipeline = request.app.state.pipeline
    return pipeline.search(
        payload.query,
        source_types=payload.source_types,
        max_sources=payload.max_sources,
        auto_start=payload.auto_start,
    )


# ---------------------------------------------------------------------- 论坛
@router.get("/forum/start")
def forum_start(request: Request) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    if pm.system_status != "online":
        raise AppError(
            "系统未上线，无法启动论坛采集",
            status_code=409,
            module="forum_collector",
            detail={"system_status": pm.system_status},
        )
    if not pm.config.app_enabled("forum_collector"):
        raise AppError(
            "论坛采集应用已在配置中禁用",
            status_code=409,
            module="forum_collector",
            detail={"enabled": False},
        )
    snapshot = pm.app_snapshot("forum_collector")
    if snapshot["status"] != "running":
        if snapshot["manual_stop"]:
            raise AppError(
                "论坛采集应用已被手动停止，请先在控制台启动该应用",
                status_code=409,
                module="forum_collector",
                detail={"status": snapshot["status"]},
            )
        pm.start_app("forum_collector", wait=True)
    forum = pm.forum.start()
    return {
        "ok": True,
        "status": forum["status"],
        "message": "论坛采集已启动，后台线程每 1.5-3 秒追加一条日志",
        "forum": forum,
        "stats": pm.forum.stats(),
    }


@router.get("/forum/stop")
def forum_stop(request: Request) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    forum = pm.forum.stop()
    return {
        "ok": True,
        "status": forum["status"],
        "message": "论坛采集已停止，后台线程不再追加日志",
        "forum": forum,
        "stats": pm.forum.stats(),
    }


@router.get("/forum/log")
def forum_log(
    request: Request,
    limit: int = Query(default=80, ge=1, le=500),
) -> dict[str, Any]:
    storage, pm, _ = ctx(request)
    records = storage.read_forum_latest(limit)
    forum = pm.forum.snapshot()
    return {
        "ok": True,
        "status": forum["status"],
        "task_status": forum["status"],
        "records": records,
        "count": len(records),
        "today_count": forum["today_count"],
        "last_time": records[-1]["time"] if records else None,
        "log_path": forum["log_path"],
        "history_path": forum["history_today_path"],
        "stats": pm.forum.stats(),
    }


class ForumHistoryRequest(BaseModel):
    date: str = Field(description="日期，格式 YYYY-MM-DD")


@router.post("/forum/log/history")
def forum_history(request: Request, payload: ForumHistoryRequest) -> dict[str, Any]:
    storage, pm, _ = ctx(request)
    date = (payload.date or "").strip()
    if not DATE_RE.match(date):
        raise AppError(
            "日期格式必须为 YYYY-MM-DD",
            status_code=400,
            module="forum_collector",
            detail={"date": date},
        )
    records = storage.read_forum_history(date)
    by_event: dict[str, int] = {}
    for record in records:
        by_event[record.get("event_type", "unknown")] = by_event.get(record.get("event_type", "unknown"), 0) + 1
    return {
        "ok": True,
        "date": date,
        "count": len(records),
        "records": records,
        "exists": storage.forum_history_path(date).exists(),
        "path": storage.rel(storage.forum_history_path(date)),
        "by_event": by_event,
        "available_dates": storage.forum_dates()[:14],
        "status": pm.forum.status,
    }


# ---------------------------------------------------------------------- 配置
@router.get("/config")
def get_config(request: Request) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    config = pm.config
    schema = config.schema()
    return {
        "ok": True,
        "config": config.get(),
        "updated_at": config.updated_at,
        "path": config.path.name,
        "schema": schema["schema"],
        "source_type_labels": schema["source_type_labels"],
        "app_labels": APP_LABELS,
        "source_types": SOURCE_TYPES,
    }


@router.post("/config")
def update_config(request: Request, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    config = pm.config
    incoming = payload.get("config") if isinstance(payload.get("config"), dict) else payload
    if not isinstance(incoming, dict):
        raise AppError("配置内容必须为 JSON 对象", status_code=400, module="config")
    old = config.get()
    new = config.save(incoming, partial=True)
    changed = config.changed_keys(old, new)
    return {
        "ok": True,
        "message": "配置已保存并热更新生效",
        "config": new,
        "changed_keys": changed,
        "updated_at": config.updated_at,
        "path": config.path.name,
    }


# ---------------------------------------------------------------------- 系统
@router.get("/system/status")
def system_status(request: Request) -> dict[str, Any]:
    storage, pm, bus = ctx(request)
    payload = pm.status_payload()
    return {
        "ok": True,
        **payload,
        "system": {**payload["system"], "ws_clients": bus.client_count},
        "logs": storage.read_system_log(60),
        "log_path": storage.rel(storage.system_log_path),
    }


@router.post("/system/start")
def system_start(request: Request) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    system = pm.start_system(wait=True)
    return {
        "ok": True,
        "message": "系统服务已启动",
        "system": system,
        "system_status": system["system_status"],
    }


@router.post("/system/shutdown")
def system_shutdown(request: Request) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    system = pm.shutdown_system(wait=True)
    return {
        "ok": True,
        "message": "系统服务已关闭，应用与论坛采集均已停止",
        "system": system,
        "system_status": system["system_status"],
    }


@router.get("/system/logs")
def system_logs(
    request: Request,
    app_name: str | None = Query(default=None),
    lines: int = Query(default=120, ge=1, le=2000),
) -> dict[str, Any]:
    storage, pm, _ = ctx(request)
    if app_name:
        _check_app(pm, app_name)
        data = storage.read_app_log(app_name, limit=lines)
        return {"ok": True, "source": app_name, **data}
    return {
        "ok": True,
        "source": "system",
        "lines": storage.read_system_log(lines),
        "path": storage.rel(storage.system_log_path),
    }


# ---------------------------------------------------------------------- 图谱
@router.get("/graph/latest")
def graph_latest(request: Request) -> dict[str, Any]:
    return request.app.state.pipeline.latest_graph()


@router.get("/graph/{report_id}")
def graph_by_report(request: Request, report_id: str) -> dict[str, Any]:
    return request.app.state.pipeline.graph_payload(report_id)


class GraphQueryRequest(BaseModel):
    report_id: str | None = None
    node_type: str | None = None
    keyword: str | None = None
    relation: str | None = None
    source_ref: str | None = None
    limit: int = Field(default=120, ge=1, le=300)


@router.post("/graph/query")
def graph_query(request: Request, payload: GraphQueryRequest) -> dict[str, Any]:
    storage, pm, _ = ctx(request)
    pipeline = request.app.state.pipeline
    if payload.node_type and payload.node_type not in NODE_TYPES:
        raise AppError(
            "node_type 仅支持：" + "、".join(NODE_TYPES),
            status_code=400,
            module="graph",
            detail={"node_types": NODE_TYPES},
        )
    if payload.report_id:
        graph = storage.load_graph(payload.report_id)
        if graph is None:
            raise AppError(
                f"报告 {payload.report_id} 暂无图谱数据",
                status_code=404,
                module="graph",
                detail={"report_id": payload.report_id},
            )
    else:
        latest = storage.latest_graph()
        if latest is None:
            raise AppError(
                "暂无图谱数据，请先发起一次主题检索",
                status_code=404,
                module="graph",
            )
        graph = latest
    result = request.app.state.graph_builder.query(
        graph,
        node_type=payload.node_type,
        keyword=payload.keyword,
        relation=payload.relation,
        source_ref=payload.source_ref,
        limit=payload.limit,
    )
    result["ok"] = True
    result["paths"] = {"graph_json": storage.rel(storage.graph_path(graph["report_id"]))}
    return result


# ---------------------------------------------------------------------- 报告
@router.get("/reports")
def reports(request: Request) -> dict[str, Any]:
    return request.app.state.pipeline.list_reports()


@router.get("/report/{report_id}")
def report_detail(request: Request, report_id: str) -> dict[str, Any]:
    return request.app.state.pipeline.get_report(report_id)


@router.get("/report/{report_id}/markdown", response_class=PlainTextResponse)
def report_markdown(request: Request, report_id: str) -> PlainTextResponse:
    storage, _, _ = ctx(request)
    if storage.load_report(report_id) is None:
        raise AppError("报告不存在：" + report_id, status_code=404, module="report_writer")
    markdown = storage.load_report_markdown(report_id)
    return PlainTextResponse(
        "\ufeff" + markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.md"'},
    )


@router.get("/topics")
def topics(request: Request) -> dict[str, Any]:
    _, pm, _ = ctx(request)
    repository = request.app.state.repository
    return {
        "ok": True,
        "topics": repository.catalog(),
        "demo_query": pm.config.section("runtime").get("demo_query", "预制菜进校园"),
        "source_types": SOURCE_TYPES,
    }


# ---------------------------------------------------------------------- WebSocket
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    bus = websocket.app.state.bus
    pm = websocket.app.state.pm
    storage = websocket.app.state.storage
    sub_id, queue = bus.register()
    system = pm.system_payload()
    try:
        await websocket.send_json(
            {
                "type": "hello",
                "ts": iso_ms(now()),
                "system_status": system["system_status"],
                "running_apps": system["running_apps"],
                "apps": [
                    {"app_name": name, "status": pm.apps[name]["status"]} for name in APP_NAMES
                ],
                "forum_status": pm.forum.status,
                "ws_clients": bus.client_count,
                "recent_events": bus.snapshot(4),
            }
        )
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=20.0)
                await websocket.send_json(event)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping", "ts": iso_ms(now())})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        bus.unregister(sub_id)
