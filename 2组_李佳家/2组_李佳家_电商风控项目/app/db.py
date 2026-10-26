"""SQLite 数据访问层。

设计要点：
1. 使用标准库 sqlite3，不依赖 ORM；
2. 每次请求通过 ``get_conn()`` 获取连接，退出上下文时自动提交/回滚；
3. 数据库文件默认位于 ``data/risk_control.db``，首次启动自动执行 schema.sql 并灌入演示数据；
4. 通过 ``RISK_DB_PATH`` 环境变量或 ``set_db_path()`` 支持测试使用临时数据库。
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB_PATH = BASE_DIR / "data" / "risk_control.db"

_db_path: Path = Path(os.environ.get("RISK_DB_PATH", str(DEFAULT_DB_PATH)))


def get_db_path() -> Path:
    """返回当前数据库文件路径。"""
    return _db_path


def set_db_path(path: str | Path) -> None:
    """切换数据库路径（测试或多环境部署时使用）。"""
    global _db_path
    _db_path = Path(path)


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """将 sqlite3.Row 转换为普通字典。"""
    return dict(row) if row is not None else None


def rows_to_dicts(rows: Sequence[sqlite3.Row]) -> list[dict[str, Any]]:
    """批量转换查询结果。"""
    return [dict(row) for row in rows]


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    """获取数据库连接上下文，正常结束提交，异常回滚。"""
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(seed: bool = True) -> None:
    """初始化数据库：建表 + 首次启动灌入演示数据。"""
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_conn() as conn:
        conn.executescript(schema_sql)
        count = conn.execute("SELECT COUNT(*) AS c FROM biz_users").fetchone()["c"]
    if seed and count == 0:
        from app.seed import seed_demo_data

        seed_demo_data()


def reset_db(seed: bool = True) -> None:
    """删除数据库文件并重新初始化（仅测试/重置演示环境使用）。"""
    if _db_path.exists():
        _db_path.unlink()
    init_db(seed=seed)


def query_one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
    """查询单行。"""
    return row_to_dict(conn.execute(sql, params).fetchone())


def query_all(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
    """查询多行。"""
    return rows_to_dicts(conn.execute(sql, params).fetchall())


def count_rows(conn: sqlite3.Connection, table: str, where: str = "", params: Sequence[Any] = ()) -> int:
    """统计表行数，table 仅允许内部常量调用。"""
    sql = f"SELECT COUNT(*) AS c FROM {table}"
    if where:
        sql += f" WHERE {where}"
    row = conn.execute(sql, params).fetchone()
    return int(row["c"]) if row else 0
