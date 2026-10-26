"""页面路由：单页应用入口、图谱查看页与自定义接口文档。"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@router.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@router.get("/graph-viewer", include_in_schema=False)
def graph_viewer() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@router.get("/graph-viewer/{report_id}", include_in_schema=False)
def graph_viewer_report(report_id: str) -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@router.get("/docs", include_in_schema=False)
def docs(request: Request) -> HTMLResponse:
    from .docs_page import render_docs

    base = str(request.base_url).rstrip("/")
    return HTMLResponse(render_docs(base))
