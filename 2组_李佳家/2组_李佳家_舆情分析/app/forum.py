"""论坛采集模块：后台线程模拟采集、实时日志与历史归档。"""
from __future__ import annotations

import random
import threading
from typing import Any

from .config import ConfigManager
from .events import EventBus
from .storage import Storage
from .utils import date_key, fmt_dt, iso, iso_ms, now, truncate

POST_TEMPLATES = [
    ("家长群转发：学校午餐又换供应商了，有家长知道是哪家吗？", "负向", "collect_post"),
    ("实拍今日校园餐：两荤一素，菜品和公示菜单一致", "中性", "collect_post"),
    ("供餐企业开放日报名帖：想去看中央厨房的家长接龙", "正向", "collect_post"),
    ("孩子回来说午饭是加热的料理包，有没有同款学校的家长？", "负向", "collect_post"),
    ("教育局回应预制菜问题，大家怎么看？", "中性", "collect_post"),
    ("陪餐第七天：菜单终于和实物对上了", "正向", "collect_post"),
    ("学校公示栏更新了检测报告，拍下来给大家看看", "中性", "collect_post"),
    ("预包装原料标签没有生产日期，这算不算违规？", "负向", "collect_post"),
    ("家委会通知：本周五下午召开校园餐听证会", "中性", "collect_post"),
    ("食堂后厨直播链接汇总，家长可以随时看", "正向", "collect_post"),
]

EVENT_WEIGHTS = [
    ("collect_post", 40),
    ("keyword_hit", 18),
    ("sentiment", 14),
    ("filter", 10),
    ("save", 10),
    ("archive", 8),
]


class ForumCollector:
    def __init__(self, storage: Storage, config: ConfigManager, bus: EventBus) -> None:
        self.storage = storage
        self.config = config
        self.bus = bus
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = "idle"
        self.started_at: str | None = None
        self.stopped_at: str | None = None
        self.last_error: str | None = None
        self.seq = 0
        self.batch = 0
        self.total = 0
        self._random = random.Random(8714)
        self._rng = random.Random()

    # ------------------------------------------------------------------ 快照
    def snapshot(self) -> dict[str, Any]:
        today = date_key()
        history = self.storage.read_forum_history(today)
        latest = self.storage.read_forum_latest(1)
        collection = self.config.section("collection")
        return {
            "status": self.status,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "last_error": self.last_error,
            "interval": [
                collection.get("forum_interval_min_seconds", 1.5),
                collection.get("forum_interval_max_seconds", 3.0),
            ],
            "keywords": collection.get("forum_keywords", []),
            "today_count": len(history),
            "total_count": len(history),
            "last_time": latest[-1]["time"] if latest else None,
            "log_path": self.storage.rel(self.storage.forum_latest_path),
            "history_today_path": self.storage.rel(self.storage.forum_history_path(today)),
            "dates": self.storage.forum_dates()[:7],
            "batch": self.batch,
            "seq": self.seq,
            "running": self.status == "running",
        }

    def stats(self) -> dict[str, Any]:
        records = self.storage.read_forum_history(date_key())
        by_event: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for record in records:
            by_event[record.get("event_type", "unknown")] = by_event.get(record.get("event_type", "unknown"), 0) + 1
            by_status[record.get("task_status", "unknown")] = (
                by_status.get(record.get("task_status", "unknown"), 0) + 1
            )
        errors = sum(1 for record in records if record.get("level") in ("ERROR", "WARN"))
        return {
            "date": date_key(),
            "total": len(records),
            "by_event": by_event,
            "by_status": by_status,
            "errors": errors,
            "last_time": records[-1]["time"] if records else None,
        }

    # ------------------------------------------------------------------ 控制
    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.status == "running":
                return self.snapshot()
            self._stop_event.clear()
            self.status = "running"
            self.started_at = iso(now())
            self.stopped_at = None
            self.last_error = None
            self.batch = 0
            self._write_app_state("running")
            self._emit("task_start", "论坛采集任务启动，目标论坛 3 个，后台线程开始轮询", level="INFO")
            self._emit("source_connected", "已连接来源：城市家长论坛、本地贴吧、微博话题", level="INFO")
            keywords = self.config.section("collection").get("forum_keywords", [])
            self._emit("keyword_loaded", f"加载采集关键词：{'、'.join(keywords[:5])}", level="INFO")
            self._emit("batch_start", "首轮采集开始，命中新帖 6 条，进入去重与情绪判定队列", level="INFO")
            self._emit("filter", "过滤广告与重复内容 3 条，加入待分析队列 6 条", level="INFO")
            self._emit(
                "sentiment",
                "完成首轮情绪判定：负向 2 条 / 中性 3 条 / 正向 1 条",
                level="INFO",
            )
            self._emit(
                "collect_post",
                "抓取到新帖《家长群转发：学校午餐又换供应商了》，回复 86 条，情绪倾向：负向",
                level="INFO",
            )
            self._emit("save", f"首轮采集结果已写入 history/{date_key()}.json，共 10 条记录", level="INFO")
            self._emit("archive", "滚动归档检查完成，latest.log 与历史文件保持一致", level="INFO")
            self.batch = 1
            self._thread = threading.Thread(
                target=self._loop,
                name="forum-collector",
                daemon=True,
            )
            self._thread.start()
        self._publish_status()
        return self.snapshot()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            was_running = self.status == "running"
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread and thread.is_alive():
            thread.join(timeout=6)
        with self._lock:
            self.status = "stopped"
            self.stopped_at = iso(now())
            if was_running:
                self._emit("task_stop", "论坛采集任务已停止，后台线程退出，已采集日志保留", level="INFO")
            self._write_app_state("stopped")
        self._publish_status()
        return self.snapshot()

    def fail(self, message: str) -> None:
        with self._lock:
            self.status = "failed"
            self.last_error = message
            self._stop_event.set()
            self._emit("error", f"论坛采集异常：{message}", level="ERROR")
            self._write_app_state("failed")

    # ------------------------------------------------------------------ 线程
    def _loop(self) -> None:
        while not self._stop_event.is_set():
            collection = self.config.section("collection")
            low = float(collection.get("forum_interval_min_seconds", 1.5) or 1.5)
            high = float(collection.get("forum_interval_max_seconds", 3.0) or 3.0)
            if high < low:
                high = low
            interval = round(self._rng.uniform(low, high), 2)
            if self._stop_event.wait(interval):
                break
            try:
                with self._lock:
                    if self.status != "running":
                        break
                    self.batch += 1
                    self._emit_batch()
            except Exception as exc:  # 采集线程不能静默退出
                with self._lock:
                    self.last_error = str(exc)
                    self._emit("error", f"采集轮次异常：{exc}", level="ERROR")
                self.bus.publish(
                    {
                        "type": "error",
                        "module_name": "forum_collector",
                        "error_message": f"论坛采集轮次异常：{exc}",
                    }
                )

    def _emit_batch(self) -> None:
        collection = self.config.section("collection")
        keywords = collection.get("forum_keywords") or ["校园餐"]
        batch_size = int(collection.get("forum_batch_size", 4) or 4)
        keyword = self._rng.choice(keywords)
        event_type = self._weighted_event()
        if event_type == "collect_post":
            title, sentiment, _ = self._rng.choice(POST_TEMPLATES)
            replies = self._rng.randint(3, 216)
            self._emit(
                "collect_post",
                f"抓取到新帖《{title}》，回复 {replies} 条，情绪倾向：{sentiment}",
                extra={"keyword": keyword, "replies": replies, "sentiment": sentiment},
            )
        elif event_type == "keyword_hit":
            hits = self._rng.randint(8, 36)
            self._emit(
                "keyword_hit",
                f"关键词「{keyword}」命中 {hits} 条新内容，去重后保留 {max(3, hits // 3)} 条",
                extra={"keyword": keyword},
            )
        elif event_type == "sentiment":
            negative = self._rng.randint(1, max(2, batch_size))
            neutral = self._rng.randint(1, max(2, batch_size))
            self._emit(
                "sentiment",
                f"完成第 {self.batch} 批情绪判定：负向 {negative} 条 / 中性 {neutral} 条 / 正向 "
                f"{max(0, batch_size - 1)} 条",
            )
        elif event_type == "filter":
            removed = self._rng.randint(2, 9)
            self._emit("filter", f"过滤广告与重复内容 {removed} 条，加入待分析队列 {self._rng.randint(4, 12)} 条")
        elif event_type == "save":
            self._emit(
                "save",
                f"采集批次已写入 runtime/forum/history/{date_key()}.json，累计 {self._today_total()} 条",
            )
        elif event_type == "archive":
            self._emit("archive", f"滚动归档检查完成，最新日志文件 {self.storage.rel(self.storage.forum_latest_path)}")
        else:
            self._emit("heartbeat", "采集线程心跳正常")

    def _weighted_event(self) -> str:
        names = [item[0] for item in EVENT_WEIGHTS]
        weights = [item[1] for item in EVENT_WEIGHTS]
        return self._rng.choices(names, weights=weights, k=1)[0]

    def _today_total(self) -> int:
        return len(self.storage.read_forum_history(date_key()))

    def _emit(self, event_type: str, message: str, level: str = "INFO", extra: dict[str, Any] | None = None) -> dict[str, Any]:
        self.seq += 1
        record = {
            "time": iso_ms(now()),
            "date": date_key(),
            "event_type": event_type,
            "message": message,
            "task_status": self.status,
            "level": level,
            "seq": self.seq,
        }
        if extra:
            record.update(extra)
        record = self.storage.append_forum_record(record)
        self.bus.publish(
            {
                "type": "forum_log",
                "message_text": record["message"],
                "message": record["message"],
                "task_status": record["task_status"],
                "event_type": record["event_type"],
                "level": record["level"],
                "time": record["time"],
                "seq": record["seq"],
            }
        )
        try:
            self._refresh_output()
        except Exception:
            pass
        return record

    # ------------------------------------------------------------------ 输出
    def _refresh_output(self) -> None:
        snapshot = self.snapshot()
        self.storage.write_output(
            "forum_collector",
            (
                f"论坛采集状态：{self.status}\n"
                f"采集间隔：{snapshot['interval'][0]}-{snapshot['interval'][1]} 秒\n"
                f"采集关键词：{'、'.join(snapshot['keywords'][:6])}\n"
                f"今日日志：{snapshot['today_count']} 条\n"
                f"最新日志：{self.storage.rel(self.storage.forum_latest_path)}\n"
                f"历史归档：{snapshot['history_today_path']}\n"
            ),
        )

    def _write_app_state(self, state: str) -> None:
        try:
            self._refresh_output()
            self.storage.append_app_log(
                "forum_collector",
                f"论坛采集状态切换为 {state}，今日记录 {self.snapshot()['today_count']} 条",
                level="INFO",
            )
        except Exception:
            pass

    def _publish_status(self) -> None:
        self.bus.publish(
            {
                "type": "app_status",
                "app_name": "forum_collector",
                "status": "running" if self.status == "running" else self.status,
                "forum_status": self.status,
                "display_name": "论坛采集",
                "time": iso(now()),
            }
        )
