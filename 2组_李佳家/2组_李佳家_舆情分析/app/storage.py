"""本地持久化层：严格按需求文档 2.2.7 的目录布局读写。"""
from __future__ import annotations

import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .utils import (
    atomic_write_json,
    atomic_write_text,
    date_key,
    fmt_dt,
    iso,
    iso_ms,
    now,
    read_json,
    read_text,
    tail,
    truncate,
)

_APP_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
_LOG_LINE_RE = re.compile(
    r"^(?P<time>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) \[(?P<level>[A-Z]+)\] \[(?P<stream>[a-z]+)\] (?P<message>.*)$"
)


class Storage:
    """所有落盘路径的唯一入口，便于测试时替换根目录。"""

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root else PROJECT_ROOT
        self.runtime_dir = self.root / "runtime"
        self.apps_dir = self.runtime_dir / "apps"
        self.forum_dir = self.runtime_dir / "forum"
        self.forum_history_dir = self.forum_dir / "history"
        self.reports_dir = self.root / "reports"
        self.graphs_dir = self.root / "graphs"
        self.outputs_dir = self.root / "outputs"
        self.data_dir = self.root / "data"
        self.system_log_path = self.runtime_dir / "system.log"
        self._lock = threading.RLock()
        self.ensure_dirs()

    # ------------------------------------------------------------------ 目录
    def ensure_dirs(self) -> None:
        for path in (
            self.apps_dir,
            self.forum_history_dir,
            self.reports_dir,
            self.graphs_dir,
            self.outputs_dir,
            self.data_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def sample_data_dir(self) -> Path:
        """样例数据目录：优先项目根目录，测试临时目录下不存在时回落到代码仓库。"""
        local = self.data_dir
        try:
            if any(local.glob("*.json")):
                return local
        except OSError:
            pass
        return PROJECT_ROOT / "data"

    @staticmethod
    def _safe_app(app_name: str) -> str:
        if not _APP_NAME_RE.match(app_name or ""):
            raise ValueError(f"非法应用名称: {app_name!r}")
        return app_name

    # ------------------------------------------------------------------ 应用日志
    def app_log_path(self, app_name: str) -> Path:
        return self.apps_dir / f"{self._safe_app(app_name)}.log"

    def append_app_log(
        self,
        app_name: str,
        message: str,
        level: str = "INFO",
        stream: str = "stdout",
    ) -> dict[str, Any]:
        level = (level or "INFO").upper()
        stream = stream if stream in ("stdout", "stderr") else "stdout"
        timestamp = now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{timestamp} [{level}] [{stream}] {message}"
        path = self.app_log_path(app_name)
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        return {"time": timestamp, "level": level, "stream": stream, "message": message, "raw": line}

    def read_app_log(self, app_name: str, limit: int = 200) -> dict[str, Any]:
        path = self.app_log_path(app_name)
        raw_lines = tail(path, limit)
        records = []
        for raw in raw_lines:
            match = _LOG_LINE_RE.match(raw)
            if match:
                records.append({**match.groupdict(), "raw": raw})
            elif raw.strip():
                records.append(
                    {"time": "", "level": "INFO", "stream": "stdout", "message": raw, "raw": raw}
                )
        total = 0
        if path.exists():
            try:
                with path.open("r", encoding="utf-8", errors="replace") as fh:
                    total = sum(1 for _ in fh)
            except OSError:
                total = len(records)
        return {
            "app_name": app_name,
            "log_path": self.rel(path),
            "exists": path.exists(),
            "total_lines": total,
            "returned_lines": len(records),
            "lines": records,
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }

    # ------------------------------------------------------------------ 最近输出
    def output_path(self, app_name: str) -> Path:
        return self.outputs_dir / self._safe_app(app_name) / "latest.txt"

    def write_output(self, app_name: str, text: str) -> Path:
        path = self.output_path(app_name)
        with self._lock:
            atomic_write_text(path, text)
        return path

    def read_output(self, app_name: str) -> dict[str, Any]:
        path = self.output_path(app_name)
        exists = path.exists()
        text = read_text(path) if exists else ""
        updated = iso(datetime.fromtimestamp(path.stat().st_mtime)) if exists else None
        lines = [line for line in text.splitlines() if line.strip()]
        return {
            "app_name": app_name,
            "output_path": self.rel(path),
            "exists": exists,
            "output_text": text,
            "summary": truncate(" ".join(lines[:6]), 180) if text else "",
            "line_count": len(lines),
            "updated_at": updated,
        }

    # ------------------------------------------------------------------ 论坛日志
    @property
    def forum_latest_path(self) -> Path:
        return self.forum_dir / "latest.log"

    def forum_history_path(self, date: str) -> Path:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date or ""):
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        return self.forum_history_dir / f"{date}.json"

    def append_forum_record(self, record: dict[str, Any]) -> dict[str, Any]:
        record = dict(record)
        created = now()
        record.setdefault("time", iso_ms(created))
        record.setdefault("date", date_key(created))
        record.setdefault("event_type", "collect")
        record.setdefault("task_status", "running")
        record.setdefault("level", "INFO")
        record.setdefault("seq", 0)
        text = f"{fmt_dt(record['time'], '%Y-%m-%d %H:%M:%S')} [{record['level']}] {record['event_type']} · {record['message']}"
        record["text"] = text

        with self._lock:
            self.forum_latest_path.parent.mkdir(parents=True, exist_ok=True)
            with self.forum_latest_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            history_path = self.forum_history_path(record["date"])
            history = read_json(history_path, default=[])
            if not isinstance(history, list):
                history = []
            history.append(record)
            if len(history) > 3000:
                history = history[-3000:]
            atomic_write_json(history_path, history)
        return record

    def read_forum_latest(self, limit: int = 100) -> list[dict[str, Any]]:
        path = self.forum_latest_path
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        for raw in tail(path, max(limit, 1)):
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError:
                continue
        return records[-limit:]

    def read_forum_history(self, date: str) -> list[dict[str, Any]]:
        path = self.forum_history_path(date)
        data = read_json(path, default=[])
        return data if isinstance(data, list) else []

    def forum_dates(self) -> list[dict[str, Any]]:
        dates = []
        for path in sorted(self.forum_history_dir.glob("*.json"), reverse=True):
            try:
                records = read_json(path, default=[])
                dates.append(
                    {
                        "date": path.stem,
                        "count": len(records) if isinstance(records, list) else 0,
                        "path": self.rel(path),
                    }
                )
            except OSError:
                continue
        return dates

    # ------------------------------------------------------------------ 系统日志
    def append_system_log(self, level: str, module: str, message: str) -> dict[str, Any]:
        timestamp = now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"{timestamp} [{level.upper()}] [{module}] {message}"
        with self._lock:
            self.system_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.system_log_path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        return {"time": timestamp, "level": level.upper(), "module": module, "message": message}

    def read_system_log(self, limit: int = 100) -> list[str]:
        return tail(self.system_log_path, limit)

    # ------------------------------------------------------------------ 报告
    def report_dir(self, report_id: str) -> Path:
        if not re.match(r"^[A-Za-z0-9_-]{4,64}$", report_id or ""):
            raise ValueError("非法报告编号")
        return self.reports_dir / report_id

    def report_paths(self, report_id: str) -> dict[str, Path]:
        base = self.report_dir(report_id)
        return {
            "dir": base,
            "markdown": base / "report.md",
            "json": base / "report.json",
            "meta": base / "meta.json",
            "search": base / "search.json",
        }

    def save_report(
        self,
        report_id: str,
        markdown: str,
        report_json: dict[str, Any],
        search_meta: dict[str, Any],
    ) -> dict[str, str]:
        paths = self.report_paths(report_id)
        with self._lock:
            paths["dir"].mkdir(parents=True, exist_ok=True)
            atomic_write_text(paths["markdown"], markdown)
            atomic_write_json(paths["json"], report_json)
            atomic_write_json(paths["search"], search_meta)
            meta = {
                "report_id": report_id,
                "topic": report_json.get("topic", ""),
                "created_at": report_json.get("created_at", ""),
                "query": report_json.get("query", ""),
                "source_count": len(report_json.get("sources", [])),
                "evidence_count": len(report_json.get("evidence", [])),
                "sentiment": report_json.get("sentiment", {}),
                "risk_level": report_json.get("risk_summary", {}).get("level", ""),
                "summary": truncate(report_json.get("event_overview", {}).get("text", ""), 120),
                "duration_ms": search_meta.get("duration_ms", 0),
            }
            atomic_write_json(paths["meta"], meta)
        return {key: self.rel(value) for key, value in paths.items() if key != "dir"}

    def load_report(self, report_id: str) -> dict[str, Any] | None:
        paths = self.report_paths(report_id)
        data = read_json(paths["json"], default=None)
        if not isinstance(data, dict):
            return None
        data.setdefault("report_id", report_id)
        return data

    def load_report_markdown(self, report_id: str) -> str:
        return read_text(self.report_paths(report_id)["markdown"])

    def load_search_meta(self, report_id: str) -> dict[str, Any] | None:
        data = read_json(self.report_paths(report_id)["search"], default=None)
        return data if isinstance(data, dict) else None

    def list_reports(self, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.reports_dir.exists():
            return items
        for child in self.reports_dir.iterdir():
            if not child.is_dir():
                continue
            meta = read_json(child / "meta.json", default=None)
            if not isinstance(meta, dict):
                report = read_json(child / "report.json", default=None)
                if not isinstance(report, dict):
                    continue
                meta = {
                    "report_id": child.name,
                    "topic": report.get("topic", ""),
                    "created_at": report.get("created_at", ""),
                    "source_count": len(report.get("sources", [])),
                }
            meta["report_id"] = child.name
            meta["has_graph"] = (self.graphs_dir / child.name / "graph.json").exists()
            meta["report_path"] = self.rel(child / "report.md")
            items.append(meta)
        items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return items[:limit]

    # ------------------------------------------------------------------ 图谱
    def graph_path(self, report_id: str) -> Path:
        self.report_dir(report_id)  # 复用编号校验
        return self.graphs_dir / report_id / "graph.json"

    def save_graph(self, report_id: str, graph: dict[str, Any]) -> Path:
        path = self.graph_path(report_id)
        with self._lock:
            atomic_write_json(path, graph)
        return path

    def load_graph(self, report_id: str) -> dict[str, Any] | None:
        data = read_json(self.graph_path(report_id), default=None)
        return data if isinstance(data, dict) else None

    def list_graphs(self, limit: int = 50) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if not self.graphs_dir.exists():
            return items
        for child in self.graphs_dir.iterdir():
            path = child / "graph.json"
            if not path.exists():
                continue
            data = read_json(path, default=None)
            if not isinstance(data, dict):
                continue
            items.append(
                {
                    "report_id": child.name,
                    "topic": data.get("topic", ""),
                    "created_at": data.get("created_at", ""),
                    "node_count": len(data.get("nodes", [])),
                    "edge_count": len(data.get("edges", [])),
                    "graph_path": self.rel(path),
                }
            )
        items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return items[:limit]

    def latest_graph(self) -> dict[str, Any] | None:
        graphs = self.list_graphs(limit=1)
        if not graphs:
            return None
        return self.load_graph(graphs[0]["report_id"])

    # ------------------------------------------------------------------ 辅助
    def rel(self, path: Path | str) -> str:
        try:
            return Path(path).resolve().relative_to(self.root.resolve()).as_posix()
        except (ValueError, OSError):
            return str(path).replace("\\", "/")

    def stats(self) -> dict[str, Any]:
        reports = self.list_reports(limit=500)
        forum_today = self.read_forum_history(date_key())
        return {
            "report_count": len(reports),
            "graph_count": len(self.list_graphs(limit=500)),
            "forum_today_count": len(forum_today),
            "latest_report": reports[0] if reports else None,
            "root": str(self.root),
            "data_dir": self.rel(self.sample_data_dir()),
        }
