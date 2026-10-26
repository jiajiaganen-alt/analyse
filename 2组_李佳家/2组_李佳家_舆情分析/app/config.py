"""配置管理：config.json 的读取、校验、保存与热更新通知。"""
from __future__ import annotations

import copy
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .errors import AppError
from .utils import atomic_write_json, iso, now, read_json

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_TYPES = ["news", "image", "video", "forum_post", "internal_data"]
SOURCE_TYPE_LABELS = {
    "news": "新闻媒体",
    "image": "图片素材",
    "video": "视频内容",
    "forum_post": "论坛帖子",
    "internal_data": "内部数据",
}
APP_NAMES = [
    "topic_search",
    "multimedia_search",
    "insight_analysis",
    "forum_collector",
    "report_writer",
]
APP_LABELS = {
    "topic_search": "主题检索",
    "multimedia_search": "多媒体检索",
    "insight_analysis": "洞察分析",
    "forum_collector": "论坛采集",
    "report_writer": "报告汇总",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "system": {
        "platform_name": "舆情分析平台",
        "version": "1.0.0",
        "host": "127.0.0.1",
        "port": 8714,
        "timezone": "Asia/Shanghai",
        "auto_start_system": True,
        "auto_start_apps": [],
        "data_retention_days": 30,
        "max_concurrent_tasks": 4,
    },
    "collection": {
        "default_source_types": list(SOURCE_TYPES),
        "max_sources_per_search": 60,
        "multimedia_types": ["image", "video"],
        "forum_interval_min_seconds": 1.5,
        "forum_interval_max_seconds": 3.0,
        "forum_keywords": ["预制菜", "校园餐", "家长投诉", "供餐企业", "食品安全"],
        "forum_batch_size": 4,
        "retry_times": 2,
        "timeout_seconds": 10,
    },
    "runtime": {
        "log_tail_lines": 200,
        "poll_interval_ms": 3000,
        "ws_reconnect_ms": 2500,
        "graph_layout": "force",
        "graph_max_nodes": 80,
        "require_apps_running": True,
        "auto_start_apps_for_task": True,
        "report_retention_days": 30,
        "demo_query": "预制菜进校园",
    },
    "apps": {name: True for name in APP_NAMES},
}

# 每个字段用于前端表单渲染的元信息
CONFIG_SCHEMA: dict[str, list[dict[str, Any]]] = {
    "system": [
        {"key": "platform_name", "label": "平台名称", "type": "text", "hint": "控制台左上角展示的名称"},
        {"key": "version", "label": "版本号", "type": "text", "hint": "交付版本标识"},
        {"key": "host", "label": "监听地址", "type": "text", "hint": "默认 127.0.0.1，仅本机访问"},
        {"key": "port", "label": "服务端口", "type": "number", "min": 1, "max": 65535, "hint": "固定 8714，修改后需重启服务"},
        {"key": "timezone", "label": "时区", "type": "text", "hint": "报告与日志时间展示时区"},
        {"key": "auto_start_system", "label": "开机自动上线", "type": "bool", "hint": "服务启动后系统状态自动置为 online"},
        {"key": "data_retention_days", "label": "数据保留天数", "type": "number", "min": 1, "max": 365, "hint": "报告与图谱保留周期"},
        {"key": "max_concurrent_tasks", "label": "最大并发任务", "type": "number", "min": 1, "max": 16, "hint": "流水线并发上限"},
    ],
    "collection": [
        {"key": "default_source_types", "label": "默认来源类型", "type": "multiselect", "options": SOURCE_TYPES, "hint": "主题检索默认勾选的来源范围"},
        {"key": "max_sources_per_search", "label": "单次来源上限", "type": "number", "min": 10, "max": 200, "hint": "单次检索最多纳入的来源条数"},
        {"key": "multimedia_types", "label": "多媒体类型", "type": "multiselect", "options": ["image", "video"], "hint": "多媒体检索纳入的素材类型"},
        {"key": "forum_interval_min_seconds", "label": "论坛采集最小间隔(秒)", "type": "number", "min": 0.5, "max": 60, "step": 0.1, "hint": "模拟采集的最小轮询间隔"},
        {"key": "forum_interval_max_seconds", "label": "论坛采集最大间隔(秒)", "type": "number", "min": 0.5, "max": 60, "step": 0.1, "hint": "需大于等于最小间隔"},
        {"key": "forum_keywords", "label": "论坛采集关键词", "type": "list", "hint": "逗号分隔，实时日志中轮换使用"},
        {"key": "forum_batch_size", "label": "单批采集条数", "type": "number", "min": 1, "max": 50, "hint": "每轮模拟采集的帖子数"},
        {"key": "retry_times", "label": "失败重试次数", "type": "number", "min": 0, "max": 10, "hint": "检索失败时的重试次数"},
        {"key": "timeout_seconds", "label": "采集超时(秒)", "type": "number", "min": 1, "max": 120, "hint": "单次采集的超时保护"},
    ],
    "runtime": [
        {"key": "log_tail_lines", "label": "日志默认行数", "type": "number", "min": 20, "max": 2000, "hint": "日志接口默认返回的尾部行数"},
        {"key": "poll_interval_ms", "label": "轮询间隔(毫秒)", "type": "number", "min": 500, "max": 60000, "hint": "WebSocket 不可用时的降级轮询间隔"},
        {"key": "ws_reconnect_ms", "label": "WS 重连间隔(毫秒)", "type": "number", "min": 500, "max": 60000, "hint": "WebSocket 断线重连间隔"},
        {"key": "graph_layout", "label": "图谱布局", "type": "select", "options": ["layered", "force"], "hint": "图谱查看器默认布局算法"},
        {"key": "graph_max_nodes", "label": "图谱节点上限", "type": "number", "min": 10, "max": 200, "hint": "构建图谱时的节点上限"},
        {"key": "require_apps_running", "label": "检索前校验应用状态", "type": "bool", "hint": "关闭后即使应用停止也允许检索"},
        {"key": "auto_start_apps_for_task", "label": "任务自动拉起应用", "type": "bool", "hint": "检索时自动启动未运行的分析应用"},
        {"key": "report_retention_days", "label": "报告保留天数", "type": "number", "min": 1, "max": 365, "hint": "自动清理历史报告的阈值"},
        {"key": "demo_query", "label": "演示主主题", "type": "text", "hint": "demo=1 与截图脚本使用的默认主题"},
    ],
}


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in (patch or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _validate(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for section in DEFAULT_CONFIG:
        if section not in data or not isinstance(data[section], dict):
            errors.append(f"缺少配置段：{section}")
    if errors:
        return errors

    system = data["system"]
    collection = data["collection"]
    runtime = data["runtime"]
    apps = data["apps"]

    for key in ("platform_name", "version", "host", "timezone"):
        if not isinstance(system.get(key), str) or not str(system.get(key)).strip():
            errors.append(f"system.{key} 必须为非空字符串")
    port = system.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        errors.append("system.port 必须为 1-65535 的整数")
    if not isinstance(system.get("auto_start_system"), bool):
        errors.append("system.auto_start_system 必须为布尔值")
    if not isinstance(system.get("auto_start_apps"), list):
        errors.append("system.auto_start_apps 必须为数组")

    defaults = collection.get("default_source_types")
    if (
        not isinstance(defaults, list)
        or not defaults
        or any(item not in SOURCE_TYPES for item in defaults)
    ):
        errors.append("collection.default_source_types 必须为合法来源类型数组")
    max_sources = collection.get("max_sources_per_search")
    if not isinstance(max_sources, int) or not 10 <= max_sources <= 200:
        errors.append("collection.max_sources_per_search 必须为 10-200 的整数")
    low = collection.get("forum_interval_min_seconds")
    high = collection.get("forum_interval_max_seconds")
    if not isinstance(low, (int, float)) or not 0.5 <= float(low) <= 60:
        errors.append("collection.forum_interval_min_seconds 必须为 0.5-60 秒")
    if not isinstance(high, (int, float)) or not 0.5 <= float(high) <= 60:
        errors.append("collection.forum_interval_max_seconds 必须为 0.5-60 秒")
    if isinstance(low, (int, float)) and isinstance(high, (int, float)) and float(high) < float(low):
        errors.append("collection.forum_interval_max_seconds 不能小于最小间隔")
    if not isinstance(collection.get("forum_keywords"), list):
        errors.append("collection.forum_keywords 必须为数组")
    batch = collection.get("forum_batch_size")
    if not isinstance(batch, int) or not 1 <= batch <= 50:
        errors.append("collection.forum_batch_size 必须为 1-50 的整数")

    if not isinstance(runtime.get("log_tail_lines"), int) or not 20 <= runtime["log_tail_lines"] <= 2000:
        errors.append("runtime.log_tail_lines 必须为 20-2000 的整数")
    if not isinstance(runtime.get("poll_interval_ms"), int) or not 500 <= runtime["poll_interval_ms"] <= 60000:
        errors.append("runtime.poll_interval_ms 必须为 500-60000 的整数")
    if runtime.get("graph_layout") not in ("layered", "force"):
        errors.append("runtime.graph_layout 仅支持 layered / force")
    if not isinstance(runtime.get("graph_max_nodes"), int) or not 10 <= runtime["graph_max_nodes"] <= 200:
        errors.append("runtime.graph_max_nodes 必须为 10-200 的整数")
    for key in ("require_apps_running", "auto_start_apps_for_task"):
        if not isinstance(runtime.get(key), bool):
            errors.append(f"runtime.{key} 必须为布尔值")

    if not isinstance(apps, dict):
        errors.append("apps 必须为对象")
    else:
        for name in APP_NAMES:
            if not isinstance(apps.get(name), bool):
                errors.append(f"apps.{name} 必须为布尔值")
    return errors


class ConfigManager:
    """线程安全的配置管理器。"""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else PROJECT_ROOT
        self.path = self.root / "config.json"
        self._lock = threading.RLock()
        self._data: dict[str, Any] | None = None
        self._mtime: float | None = None
        self.updated_at: str | None = None
        self._listeners: list[Callable[[dict[str, Any], dict[str, Any]], None]] = []

    # ------------------------------------------------------------------ 基础
    def ensure(self) -> dict[str, Any]:
        with self._lock:
            if not self.path.exists():
                atomic_write_json(self.path, DEFAULT_CONFIG)
                self.updated_at = iso(now())
                self._mtime = self.path.stat().st_mtime
            return self.load(force=True)

    def load(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if not force and self._data is not None and self._is_fresh():
                return copy.deepcopy(self._data)
            raw = read_json(self.path, default=None)
            if not isinstance(raw, dict):
                raw = {}
            data = _deep_merge(DEFAULT_CONFIG, raw)
            errors = _validate(data)
            if errors:
                # 磁盘配置损坏时回退到默认值，避免服务无法启动
                data = copy.deepcopy(DEFAULT_CONFIG)
            self._data = data
            self._mtime = self.path.stat().st_mtime if self.path.exists() else None
            if not self.updated_at:
                mtime = self._mtime or datetime.now().timestamp()
                self.updated_at = iso(datetime.fromtimestamp(mtime))
            return copy.deepcopy(self._data)

    def _is_fresh(self) -> bool:
        if not self.path.exists():
            return True
        return self._mtime == self.path.stat().st_mtime

    def get(self) -> dict[str, Any]:
        return self.load()

    def section(self, name: str) -> dict[str, Any]:
        return copy.deepcopy(self.load().get(name, {}))

    def app_enabled(self, app_name: str) -> bool:
        return bool(self.load().get("apps", {}).get(app_name, False))

    def add_listener(self, fn: Callable[[dict[str, Any], dict[str, Any]], None]) -> None:
        self._listeners.append(fn)

    # ------------------------------------------------------------------ 写入
    def save(self, payload: dict[str, Any], partial: bool = True) -> dict[str, Any]:
        with self._lock:
            current = self.load()
            if partial:
                candidate = _deep_merge(current, payload)
            else:
                candidate = _deep_merge(DEFAULT_CONFIG, payload)
            errors = _validate(candidate)
            if errors:
                raise AppError(
                    "配置校验失败：" + "；".join(errors[:4]),
                    status_code=400,
                    module="config",
                    detail={"errors": errors},
                )
            atomic_write_json(self.path, candidate)
            old = current
            self._data = candidate
            self._mtime = self.path.stat().st_mtime
            self.updated_at = iso(now())
        for listener in list(self._listeners):
            try:
                listener(old, copy.deepcopy(candidate))
            except Exception:  # 监听器异常不影响配置保存
                pass
        return copy.deepcopy(candidate)

    def save_full(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.save(payload, partial=True)

    def changed_keys(self, old: dict[str, Any], new: dict[str, Any]) -> list[str]:
        changes: list[str] = []
        for section in new:
            if not isinstance(new[section], dict):
                if old.get(section) != new[section]:
                    changes.append(section)
                continue
            for key, value in new[section].items():
                if not isinstance(old.get(section), dict) or old[section].get(key) != value:
                    changes.append(f"{section}.{key}")
        return changes

    def schema(self) -> dict[str, Any]:
        return {"schema": CONFIG_SCHEMA, "source_type_labels": SOURCE_TYPE_LABELS}
