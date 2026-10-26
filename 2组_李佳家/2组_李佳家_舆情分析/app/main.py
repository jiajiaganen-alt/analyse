"""FastAPI 应用工厂与异常处理。"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .agents.collector import SourceRepository
from .config import ConfigManager, PROJECT_ROOT
from .errors import AppError
from .events import EventBus
from .pipeline import PipelineService
from .process_manager import ProcessManager
from .routers import api, pages
from .storage import Storage
from .utils import iso, now

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(root: Path | str | None = None, data_dir: Path | str | None = None) -> FastAPI:
    root_path = Path(root) if root else PROJECT_ROOT
    storage = Storage(root_path)
    config = ConfigManager(root_path)
    config.ensure()
    bus = EventBus()
    process_manager = ProcessManager(storage, config, bus)
    repository = SourceRepository(data_dir or storage.sample_data_dir())
    pipeline = PipelineService(storage, config, process_manager, bus, repository)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bus.attach_loop(asyncio.get_running_loop())
        process_manager.initialize()
        config.add_listener(process_manager.config_changed)
        try:
            yield
        finally:
            process_manager.shutdown()

    app = FastAPI(
        title="舆情分析平台 API",
        description="面向指定主题的多来源舆情采集、洞察分析与报告生成服务",
        version=__version__,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/openapi.json",
    )
    app.state.root = root_path
    app.state.storage = storage
    app.state.config = config
    app.state.bus = bus
    app.state.pm = process_manager
    app.state.repository = repository
    app.state.pipeline = pipeline
    app.state.graph_builder = pipeline.graph_builder

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        try:
            process_manager.record_error(exc.module, exc.message)
        except Exception:
            pass
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "detail": "请求参数校验失败",
                "error": {
                    "module_name": "api",
                    "error_message": "请求参数校验失败",
                    "detail": exc.errors(),
                },
            },
        )

    @app.middleware("http")
    async def add_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Platform"] = "yuqing-analysis-console"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(api.router, prefix="/api")
    app.include_router(pages.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/favicon.svg", include_in_schema=False)
    def favicon():
        from fastapi.responses import FileResponse

        return FileResponse(STATIC_DIR / "img" / "favicon.svg", media_type="image/svg+xml")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon_ico():
        from fastapi.responses import FileResponse

        return FileResponse(STATIC_DIR / "img" / "favicon.svg", media_type="image/svg+xml")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8714, reload=False)
