"""进程管理模块：系统状态机、单功能应用状态机、日志/输出与资源采集。"""
from __future__ import annotations

import math
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Callable

from .config import APP_LABELS, APP_NAMES, ConfigManager
from .errors import AppError
from .events import EventBus
from .forum import ForumCollector
from .storage import Storage
from .utils import fmt_dt, human_duration, iso, now, parse_dt, truncate

APP_STATES = ["stopped", "starting", "running", "stopping", "failed"]
SYSTEM_STATES = ["offline", "starting", "online", "shutting_down"]

APP_DEFINITIONS = [
    {
        "app_name": "topic_search",
        "display_name": "主题检索",
        "description": "多来源文本检索与主题匹配，输出来源摘要与检索指标",
        "icon": "search",
        "capability": "按主题词在新闻、论坛与内部台账中召回来源",
    },
    {
        "app_name": "multimedia_search",
        "display_name": "多媒体检索",
        "description": "图片 OCR 与视频 ASR 文本抽取，补充多媒体证据链",
        "icon": "media",
        "capability": "识别图片/视频素材并抽取 OCR、字幕与时长信息",
    },
    {
        "app_name": "insight_analysis",
        "display_name": "洞察分析",
        "description": "观点聚类、情绪判定、传播渠道统计与风险评分",
        "icon": "insight",
        "capability": "按来源与角色聚类观点，计算情绪与风险指标",
    },
    {
        "app_name": "forum_collector",
        "display_name": "论坛采集",
        "description": "后台轮询论坛新帖，持续写入实时日志与历史归档",
        "icon": "forum",
        "capability": "1.5-3 秒间隔模拟采集，支持历史按日期查询",
    },
    {
        "app_name": "report_writer",
        "display_name": "报告汇总",
        "description": "生成 8 部分结构化报告、结论引用与来源清单",
        "icon": "report",
        "capability": "汇总流水线结果并落盘 report.md 与图谱",
    },
]


class ProcessManager:
    def __init__(self, storage: Storage, config: ConfigManager, bus: EventBus) -> None:
        self.storage = storage
        self.config = config
        self.bus = bus
        self._lock = threading.RLock()
        self._threads: dict[str, threading.Thread] = {}
        self.system_status = "offline"
        self.system_started_at: str | None = None
        self.system_stopped_at: str | None = None
        self.boot_at = iso(now())
        self.errors: deque[dict[str, Any]] = deque(maxlen=40)
        self.apps: dict[str, dict[str, Any]] = {}
        for definition in APP_DEFINITIONS:
            self.apps[definition["app_name"]] = {
                "status": "stopped",
                "started_at": None,
                "stopped_at": None,
                "last_error": None,
                "manual_stop": False,
                "task_count": 0,
                "last_output_at": None,
                "transitions": [],
            }
        self.forum = ForumCollector(storage, config, bus)
        self._cpu_primed = False
        self._resource_cache: dict[str, Any] = {"at": 0.0, "data": None}

    # ------------------------------------------------------------------ 初始化
    def initialize(self) -> None:
        self.config.ensure()
        self.storage.append_system_log("INFO", "system", "舆情分析平台后端启动，开始初始化运行目录")
        try:
            import psutil  # noqa: F401

            psutil.cpu_percent(interval=None)
            self._cpu_primed = True
        except Exception:
            self._cpu_primed = False
        if self.config.section("system").get("auto_start_system", True):
            self.start_system(wait=True)
        for app_name in self.config.section("system").get("auto_start_apps", []) or []:
            if app_name in APP_NAMES:
                try:
                    self.start_app(app_name, wait=True)
                except AppError:
                    continue
        self.storage.append_system_log("INFO", "system", "初始化完成，控制台与接口服务就绪")

    # ------------------------------------------------------------------ 系统状态
    def _publish_system(self) -> None:
        payload = {
            "type": "system_status",
            "system_status": self.system_status,
            "running_apps": self.running_app_count(),
            "time": iso(now()),
        }
        self.bus.publish(payload)

    def running_app_count(self) -> int:
        return sum(1 for app in self.apps.values() if app["status"] == "running")

    def system_payload(self) -> dict[str, Any]:
        running = self.running_app_count()
        uptime = 0
        if self.system_started_at:
            started = parse_dt(self.system_started_at)
            if started:
                uptime = max(0, int((datetime.now().astimezone() - started).total_seconds()))
        return {
            "system_status": self.system_status,
            "status_label": {
                "offline": "离线",
                "starting": "启动中",
                "online": "在线",
                "shutting_down": "关闭中",
            }.get(self.system_status, self.system_status),
            "started_at": self.system_started_at,
            "stopped_at": self.system_stopped_at,
            "uptime_seconds": uptime,
            "uptime_text": human_duration(uptime),
            "running_apps": running,
            "total_apps": len(self.apps),
            "boot_at": self.boot_at,
            "version": self.config.section("system").get("version", "1.0.0"),
            "platform_name": self.config.section("system").get("platform_name", "舆情分析平台"),
            "ws_clients": self.bus.client_count,
            "server_time": iso(now()),
        }

    def start_system(self, wait: bool = True) -> dict[str, Any]:
        with self._lock:
            if self.system_status == "online":
                return self.system_payload()
            self.system_status = "starting"
            self.system_stopped_at = None
        self.storage.append_system_log("INFO", "system", "系统进入 starting，正在启动控制面")
        self._publish_system()
        self.bus.publish({"type": "system_status", "system_status": "starting", "running_apps": 0})

        def complete() -> None:
            time.sleep(0.25)
            with self._lock:
                if self.system_status != "starting":
                    return
                self.system_status = "online"
                self.system_started_at = iso(now())
            self.storage.append_system_log("INFO", "system", "系统状态切换为 online，允许启动单功能应用")
            self._publish_system()

        thread = threading.Thread(target=complete, name="system-start", daemon=True)
        thread.start()
        self._threads["system"] = thread
        if wait:
            thread.join(timeout=3)
        return self.system_payload()

    def shutdown_system(self, wait: bool = True) -> dict[str, Any]:
        with self._lock:
            if self.system_status == "offline":
                return self.system_payload()
            self.system_status = "shutting_down"
        self.storage.append_system_log("INFO", "system", "系统进入 shutting_down，停止论坛采集与应用")
        self._publish_system()
        try:
            self.forum.stop()
        except Exception as exc:
            self.record_error("forum_collector", f"关闭论坛采集失败：{exc}")
        for app_name in APP_NAMES:
            try:
                if self.apps[app_name]["status"] in ("starting", "running", "stopping"):
                    self.stop_app(app_name, wait=True)
            except Exception as exc:
                self.record_error(app_name, f"关闭应用失败：{exc}")

        def complete() -> None:
            time.sleep(0.2)
            with self._lock:
                if self.system_status != "shutting_down":
                    return
                self.system_status = "offline"
                self.system_stopped_at = iso(now())
            self.storage.append_system_log("INFO", "system", "系统状态切换为 offline，服务控制面已停止")
            self._publish_system()

        thread = threading.Thread(target=complete, name="system-stop", daemon=True)
        thread.start()
        self._threads["system-stop"] = thread
        if wait:
            thread.join(timeout=3)
        return self.system_payload()

    # ------------------------------------------------------------------ 应用状态机
    def _app_definition(self, app_name: str) -> dict[str, Any]:
        for definition in APP_DEFINITIONS:
            if definition["app_name"] == app_name:
                return definition
        raise AppError(
            f"未知应用：{app_name}",
            status_code=404,
            module="process_manager",
            detail={"available_apps": APP_NAMES},
        )

    def _transition(self, app_name: str, status: str) -> None:
        app = self.apps[app_name]
        app["status"] = status
        app["transitions"].append({"status": status, "time": iso(now())})
        if len(app["transitions"]) > 12:
            app["transitions"] = app["transitions"][-12:]

    def _publish_app(self, app_name: str, status: str) -> None:
        definition = self._app_definition(app_name)
        self.bus.publish(
            {
                "type": "app_status",
                "app_name": app_name,
                "display_name": definition["display_name"],
                "status": status,
                "time": iso(now()),
            }
        )

    def app_snapshot(self, app_name: str) -> dict[str, Any]:
        definition = self._app_definition(app_name)
        app = self.apps[app_name]
        output = self.storage.read_output(app_name)
        return {
            "app_name": app_name,
            "display_name": definition["display_name"],
            "description": definition["description"],
            "icon": definition["icon"],
            "capability": definition["capability"],
            "status": app["status"],
            "status_label": {
                "stopped": "已停止",
                "starting": "启动中",
                "running": "运行中",
                "stopping": "停止中",
                "failed": "异常",
            }.get(app["status"], app["status"]),
            "enabled": self.config.app_enabled(app_name),
            "started_at": app["started_at"],
            "stopped_at": app["stopped_at"],
            "last_error": app["last_error"],
            "manual_stop": app["manual_stop"],
            "task_count": app["task_count"],
            "last_output_at": output.get("updated_at") or app["last_output_at"],
            "output_summary": output.get("summary", ""),
            "output_exists": output.get("exists", False),
            "log_path": self.storage.rel(self.storage.app_log_path(app_name)),
            "output_path": output.get("output_path"),
            "transitions": app["transitions"][-8:],
        }

    def start_app(self, app_name: str, wait: bool = False) -> dict[str, Any]:
        definition = self._app_definition(app_name)
        if not self.config.app_enabled(app_name):
            raise AppError(
                f"应用「{definition['display_name']}」已在 config.json 中禁用，请先在配置管理页启用",
                status_code=409,
                module=app_name,
                detail={"app_name": app_name, "enabled": False},
            )
        with self._lock:
            if self.system_status != "online":
                raise AppError(
                    "系统未处于 online 状态，无法启动应用",
                    status_code=409,
                    module="system",
                    detail={"system_status": self.system_status},
                )
            current = self.apps[app_name]["status"]
            already_active = current in ("running", "starting")
            if not already_active:
                self._transition(app_name, "starting")
                self.apps[app_name]["started_at"] = iso(now())
                self.apps[app_name]["stopped_at"] = None
                self.apps[app_name]["last_error"] = None
                self.apps[app_name]["manual_stop"] = False
        if already_active:
            if wait:
                self._wait_for(lambda: self.apps[app_name]["status"] == "running", 5)
            return self.app_snapshot(app_name)
        self.storage.append_app_log(app_name, "启动请求已接收，应用进入 starting", level="INFO")
        self._publish_app(app_name, "starting")

        def complete() -> None:
            time.sleep(0.3)
            with self._lock:
                if self.apps[app_name]["status"] != "starting":
                    return
                self._transition(app_name, "running")
            self.storage.append_app_log(app_name, "应用初始化完成，状态切换为 running", level="INFO")
            self._publish_app(app_name, "running")

        thread = threading.Thread(target=complete, name=f"start-{app_name}", daemon=True)
        thread.start()
        self._threads[f"start-{app_name}"] = thread
        if wait:
            thread.join(timeout=5)
        return self.app_snapshot(app_name)

    def stop_app(self, app_name: str, wait: bool = False) -> dict[str, Any]:
        definition = self._app_definition(app_name)
        if app_name == "forum_collector":
            try:
                self.forum.stop()
            except Exception as exc:
                self.record_error(app_name, f"停止论坛采集失败：{exc}")
        with self._lock:
            current = self.apps[app_name]["status"]
            if current in ("stopped", "failed"):
                self.apps[app_name]["manual_stop"] = True
                if current == "failed":
                    self.apps[app_name]["status"] = "stopped"
                return self.app_snapshot(app_name)
            self._transition(app_name, "stopping")
            self.apps[app_name]["manual_stop"] = True
        self.storage.append_app_log(app_name, "停止请求已接收，应用进入 stopping，不再接收新任务", level="INFO")
        self._publish_app(app_name, "stopping")

        def complete() -> None:
            time.sleep(0.2)
            with self._lock:
                if self.apps[app_name]["status"] != "stopping":
                    return
                self._transition(app_name, "stopped")
                self.apps[app_name]["stopped_at"] = iso(now())
            self.storage.append_app_log(
                app_name,
                f"应用「{definition['display_name']}」已停止，输出与日志保留",
                level="INFO",
            )
            self._publish_app(app_name, "stopped")

        thread = threading.Thread(target=complete, name=f"stop-{app_name}", daemon=True)
        thread.start()
        self._threads[f"stop-{app_name}"] = thread
        if wait:
            thread.join(timeout=5)
        return self.app_snapshot(app_name)

    def mark_failed(self, app_name: str, message: str) -> None:
        with self._lock:
            if app_name not in self.apps:
                return
            self._transition(app_name, "failed")
            self.apps[app_name]["last_error"] = message
        self.storage.append_app_log(app_name, message, level="ERROR", stream="stderr")
        self._publish_app(app_name, "failed")
        self.record_error(app_name, message)

    def _wait_for(self, predicate: Callable[[], bool], timeout: float) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return True
            time.sleep(0.02)
        return predicate()

    # ------------------------------------------------------------------ 输出/日志
    def set_output(self, app_name: str, text: str) -> None:
        path = self.storage.write_output(app_name, text)
        with self._lock:
            if app_name in self.apps:
                self.apps[app_name]["last_output_at"] = iso(now())
        self.bus.publish(
            {
                "type": "app_output",
                "app_name": app_name,
                "output_text": text,
                "output_path": self.storage.rel(path),
                "time": iso(now()),
            }
        )

    def note_task(self, app_name: str, output_text: str, log_lines: list[tuple[str, str]] | None = None) -> None:
        with self._lock:
            if app_name in self.apps:
                self.apps[app_name]["task_count"] += 1
        if log_lines:
            for message, level in log_lines:
                self.storage.append_app_log(
                    app_name,
                    message,
                    level=level,
                    stream="stderr" if level in ("ERROR", "WARN") else "stdout",
                )
        self.set_output(app_name, output_text)

    def append_app_log(self, app_name: str, message: str, level: str = "INFO") -> None:
        self.storage.append_app_log(
            app_name,
            message,
            level=level,
            stream="stderr" if level in ("ERROR", "WARN") else "stdout",
        )

    # ------------------------------------------------------------------ 错误
    def record_error(self, module_name: str, message: str) -> dict[str, Any]:
        record = {
            "module_name": module_name,
            "error_message": message,
            "time": iso(now()),
            "time_label": fmt_dt(now(), "%H:%M:%S"),
        }
        with self._lock:
            self.errors.appendleft(record)
        self.storage.append_system_log("ERROR", module_name, message)
        self.bus.publish(
            {
                "type": "error",
                "module_name": module_name,
                "error_message": message,
                "time": record["time"],
            }
        )
        return record

    def recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.errors)[:limit]

    # ------------------------------------------------------------------ 资源
    def resources(self) -> dict[str, Any]:
        uptime = self.system_payload()["uptime_seconds"]
        cached = self._resource_cache
        if cached.get("data") and time.time() - float(cached.get("at", 0)) < 1.5:
            return dict(cached["data"])
        try:
            import psutil

            cpu_count = psutil.cpu_count(logical=True) or 1
            process_cpu = process_cpu_value = psutil.Process().cpu_percent(interval=0.08)
            cpu = round(process_cpu_value / cpu_count, 1)
            system_cpu = round(psutil.cpu_percent(interval=None), 1)
            memory = psutil.virtual_memory()
            process = psutil.Process()
            disk = psutil.disk_usage(str(self.storage.root))
            payload = {
                "source": "psutil",
                "cpu_percent": cpu,
                "process_cpu_percent": round(process_cpu_value, 1),
                "system_cpu_percent": system_cpu,
                "cpu_count": cpu_count,
                "memory_percent": round(float(memory.percent), 1),
                "memory_used_gb": round(memory.used / 1024**3, 2),
                "memory_total_gb": round(memory.total / 1024**3, 2),
                "process_rss_mb": round(process.memory_info().rss / 1024**2, 1),
                "threads": process.num_threads(),
                "disk_percent": round(float(disk.percent), 1),
                "disk_free_gb": round(disk.free / 1024**3, 1),
                "uptime_seconds": uptime,
                "uptime_text": human_duration(uptime),
                "sampled_at": iso(now()),
            }
        except Exception:
            phase = (datetime.now().timestamp() % 120) / 120
            payload = {
                "source": "fallback",
                "cpu_percent": round(24 + 12 * abs(math.sin(phase * math.pi)), 1),
                "cpu_count": 8,
                "memory_percent": round(52 + 6 * abs(math.sin(phase * math.pi)), 1),
                "memory_used_gb": 8.6,
                "memory_total_gb": 16.0,
                "process_rss_mb": 128.0,
                "threads": threading.active_count(),
                "disk_percent": 46.0,
                "disk_free_gb": 128.0,
                "uptime_seconds": uptime,
                "uptime_text": human_duration(uptime),
                "sampled_at": iso(now()),
                "note": "psutil 不可用，展示稳定模拟值",
            }
        self._resource_cache = {"at": time.time(), "data": payload}
        return dict(payload)

    # ------------------------------------------------------------------ 汇总
    def status_payload(self) -> dict[str, Any]:
        apps = [self.app_snapshot(name) for name in APP_NAMES]
        forum = self.forum.snapshot()
        reports = self.storage.stats()
        return {
            "system": self.system_payload(),
            "apps": apps,
            "resources": self.resources(),
            "recent_errors": self.recent_errors(8),
            "forum": forum,
            "reports": reports,
            "server_time": iso(now()),
        }

    def config_changed(self, old: dict[str, Any], new: dict[str, Any]) -> None:
        changes = self.config.changed_keys(old, new)
        self.storage.append_system_log(
            "INFO",
            "config",
            f"配置热更新生效（{len(changes)} 项）：{', '.join(changes[:8]) or '无字段变化'}",
        )
        for app_name in APP_NAMES:
            if not new.get("apps", {}).get(app_name, True) and self.apps[app_name]["status"] in (
                "running",
                "starting",
            ):
                try:
                    self.stop_app(app_name, wait=True)
                except Exception:
                    continue
                self.record_error(
                    "config",
                    f"配置中禁用应用「{APP_LABELS[app_name]}」，已自动停止该应用",
                )

    # ------------------------------------------------------------------ 任务保障
    def ensure_apps(self, names: list[str], auto_start: bool = True) -> None:
        system = self.system_payload()
        if system["system_status"] != "online":
            raise AppError(
                "系统未上线，请先在系统状态页启动系统",
                status_code=409,
                module="system",
                detail={"system_status": system["system_status"]},
            )
        runtime = self.config.section("runtime")
        if not runtime.get("require_apps_running", True):
            return
        missing = [name for name in names if self.apps[name]["status"] != "running"]
        if not missing:
            return
        manual = [name for name in missing if self.apps[name]["manual_stop"]]
        if not auto_start or not runtime.get("auto_start_apps_for_task", True) or manual:
            raise AppError(
                "分析流水线所需应用未运行，请先启动：" + "、".join(APP_LABELS[name] for name in missing),
                status_code=409,
                module="process_manager",
                detail={
                    "missing_apps": missing,
                    "manual_stopped": manual,
                    "suggestion": "在控制台启动应用，或使用「启动并检索」按钮",
                },
            )
        for name in missing:
            if not self.config.app_enabled(name):
                raise AppError(
                    f"应用「{APP_LABELS[name]}」已在配置中禁用，无法执行检索",
                    status_code=409,
                    module=name,
                    detail={"missing_apps": missing, "disabled": name},
                )
            self.start_app(name, wait=True)
        still = [name for name in names if self.apps[name]["status"] != "running"]
        if still:
            raise AppError(
                "应用启动超时，请稍后重试：" + "、".join(APP_LABELS[name] for name in still),
                status_code=409,
                module="process_manager",
                detail={"missing_apps": still},
            )

    def shutdown(self) -> None:
        try:
            self.forum.stop()
        except Exception:
            pass
        for app_name in APP_NAMES:
            try:
                if self.apps[app_name]["status"] in ("running", "starting"):
                    self.stop_app(app_name, wait=True)
            except Exception:
                continue
