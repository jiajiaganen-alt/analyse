"""通用工具：时间、原子写入、JSON 读取、文本截断。"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


def now() -> datetime:
    """统一使用带本地时区的 aware datetime，避免与 ISO 字符串比较时报错。"""
    return datetime.now().astimezone()


def iso(dt: datetime | None = None) -> str:
    """本地时间 ISO 字符串（精确到秒，带时区偏移）。"""
    return (dt or now()).astimezone().isoformat(timespec="seconds")


def iso_ms(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone().isoformat(timespec="milliseconds")


def fmt_dt(value: datetime | str | None, pattern: str = "%Y-%m-%d %H:%M") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    return value.strftime(pattern)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def atomic_write_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, data: Any) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return default


def read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return default


def tail(path: Path, limit: int = 200) -> list[str]:
    if limit <= 0 or not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return []
    return [line.rstrip("\n") for line in lines[-limit:]]


def human_duration(seconds: float | int | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(max(0, seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}天{hours}小时"
    if hours:
        return f"{hours}小时{minutes}分"
    if minutes:
        return f"{minutes}分{secs}秒"
    return f"{secs}秒"


def truncate(text: str, limit: int = 160) -> str:
    text = (text or "").replace("\r", " ").replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def date_key(dt: datetime | None = None) -> str:
    return (dt or now()).strftime("%Y-%m-%d")


def hours_ago(hours: float, base: datetime | None = None) -> datetime:
    return (base or now()) - timedelta(hours=float(hours))
