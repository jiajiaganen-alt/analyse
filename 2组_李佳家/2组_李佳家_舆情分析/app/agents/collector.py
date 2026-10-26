"""采集 Agent：加载样例来源、主题匹配、来源筛选与编号。"""
from __future__ import annotations

import json
import math
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..config import SOURCE_TYPES, SOURCE_TYPE_LABELS
from ..errors import AppError
from ..utils import fmt_dt, iso, now, truncate

SOURCE_TYPE_ORDER = {name: index for index, name in enumerate(SOURCE_TYPES)}
SENTIMENT_LABELS = {"positive": "正向", "neutral": "中性", "negative": "负向"}
SENTIMENT_ORDER = ["positive", "neutral", "negative"]


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


class SourceRepository:
    """从 data/*.json 加载主题数据集，常驻内存，只读。"""

    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self._lock = threading.RLock()
        self._datasets: list[dict[str, Any]] | None = None
        self._loaded_at: str | None = None

    # ------------------------------------------------------------------ 加载
    def _load(self) -> list[dict[str, Any]]:
        with self._lock:
            if self._datasets is not None:
                return self._datasets
            datasets: list[dict[str, Any]] = []
            for path in sorted(self.data_dir.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError):
                    continue
                if not isinstance(data, dict) or "topic" not in data or "sources" not in data:
                    continue
                dataset = dict(data)
                dataset["_path"] = path.name
                dataset.setdefault("aliases", [])
                dataset.setdefault("timeline", [])
                dataset.setdefault("risks", [])
                dataset.setdefault("entities", [])
                dataset.setdefault("entity_relations", [])
                dataset["sources"] = [src for src in dataset["sources"] if src.get("id")]
                datasets.append(dataset)
            self._datasets = datasets
            self._loaded_at = iso(now())
            return datasets

    def reload(self) -> None:
        with self._lock:
            self._datasets = None

    def catalog(self) -> list[dict[str, Any]]:
        result = []
        for dataset in self._load():
            counts = {name: 0 for name in SOURCE_TYPES}
            for src in dataset["sources"]:
                if src.get("source_type") in counts:
                    counts[src["source_type"]] += 1
            result.append(
                {
                    "topic": dataset["topic"],
                    "aliases": dataset["aliases"],
                    "category": dataset.get("category", ""),
                    "overview": dataset.get("overview", ""),
                    "source_count": len(dataset["sources"]),
                    "source_counts": counts,
                    "sample_file": dataset["_path"],
                }
            )
        return result

    def loaded_at(self) -> str | None:
        return self._loaded_at

    # ------------------------------------------------------------------ 匹配
    @staticmethod
    def _score(dataset: dict[str, Any], query: str) -> float:
        q = normalize(query)
        if not q:
            return 0.0
        topic = normalize(dataset["topic"])
        best = 0.0
        if q == topic:
            best = 120.0
        elif q in topic or topic in q:
            best = 95.0
        for alias in dataset.get("aliases", []):
            a = normalize(alias)
            if not a:
                continue
            if q == a:
                best = max(best, 100.0)
            elif a in q or q in a:
                best = max(best, 78.0 + min(len(a), 8))
        for src in dataset["sources"]:
            for keyword in src.get("keywords", []):
                k = normalize(keyword)
                if len(k) >= 2 and k in q:
                    best = max(best, 40.0 + min(len(k), 6))
        return best

    def find_dataset(self, query: str) -> dict[str, Any] | None:
        best: dict[str, Any] | None = None
        best_score = 0.0
        for dataset in self._load():
            score = self._score(dataset, query)
            if score > best_score:
                best, best_score = dataset, score
        return best

    def topics(self) -> list[str]:
        return [dataset["topic"] for dataset in self._load()]

    # ------------------------------------------------------------------ 检索
    def search(
        self,
        query: str,
        source_types: list[str] | None = None,
        limit: int = 60,
    ) -> dict[str, Any] | None:
        dataset = self.find_dataset(query)
        if dataset is None:
            return None
        allowed = [name for name in (source_types or SOURCE_TYPES) if name in SOURCE_TYPES]
        if not allowed:
            allowed = list(SOURCE_TYPES)
        base = now()
        selected: list[dict[str, Any]] = []
        for raw in dataset["sources"]:
            if raw.get("source_type") not in allowed:
                continue
            source = dict(raw)
            source["published_at"] = self._published_at(base, source.get("hours_ago", 24))
            source["published_label"] = fmt_dt(source["published_at"], "%Y-%m-%d %H:%M")
            source["source_type_label"] = SOURCE_TYPE_LABELS.get(source["source_type"], source["source_type"])
            source["sentiment_label"] = SENTIMENT_LABELS.get(source.get("sentiment"), "中性")
            source["ref"] = ""
            selected.append(source)

        selected.sort(key=lambda item: float(item.get("influence", 0)), reverse=True)
        if limit and len(selected) > limit:
            selected = selected[:limit]
        assign_refs(selected)
        selected.sort(key=lambda item: item["published_at"], reverse=True)
        for source in selected:
            source["age_days"] = round(
                max(0.0, (base - datetime.fromisoformat(source["published_at"])).total_seconds() / 3600.0) / 24.0,
                1,
            )

        counts = {name: 0 for name in SOURCE_TYPES}
        for source in selected:
            counts[source["source_type"]] = counts.get(source["source_type"], 0) + 1
        sentiment_counts = {name: 0 for name in SENTIMENT_ORDER}
        for source in selected:
            if source.get("sentiment") in sentiment_counts:
                sentiment_counts[source["sentiment"]] += 1
        dates = sorted(source["published_at"] for source in selected)
        return {
            "dataset": dataset,
            "sources": selected,
            "source_counts": counts,
            "sentiment_counts": sentiment_counts,
            "date_range": {
                "earliest": dates[0] if dates else None,
                "latest": dates[-1] if dates else None,
                "span_days": (
                    round(
                        (
                            datetime.fromisoformat(dates[-1]) - datetime.fromisoformat(dates[0])
                        ).total_seconds()
                        / 86400,
                        1,
                    )
                    if dates
                    else 0
                ),
            },
            "query": query,
            "source_types": allowed,
            "total_available": len(dataset["sources"]),
        }

    @staticmethod
    def _published_at(base: datetime, hours_ago: float) -> str:
        return iso(base - timedelta(hours=float(hours_ago)))

    # ------------------------------------------------------------------ 多媒体
    @staticmethod
    def multimedia_digest(sources: list[dict[str, Any]]) -> dict[str, Any]:
        assets = [src for src in sources if src["source_type"] in ("image", "video")]
        image_count = sum(1 for src in assets if src["source_type"] == "image")
        video_count = sum(1 for src in assets if src["source_type"] == "video")
        ocr_items = []
        asr_items = []
        for asset in assets:
            meta = asset.get("media_meta", {})
            if asset["source_type"] == "image" and meta.get("ocr_text"):
                ocr_items.append(
                    {
                        "ref": asset["ref"],
                        "asset_id": asset["id"],
                        "title": asset["title"],
                        "text": meta["ocr_text"],
                    }
                )
            if asset["source_type"] == "video" and meta.get("asr_excerpt"):
                asr_items.append(
                    {
                        "ref": asset["ref"],
                        "asset_id": asset["id"],
                        "title": asset["title"],
                        "text": meta["asr_excerpt"],
                        "duration_seconds": meta.get("duration_seconds"),
                    }
                )
        platforms: dict[str, int] = {}
        for asset in assets:
            platform = asset.get("media_meta", {}).get("platform") or asset.get("source", "未知")
            platforms[platform] = platforms.get(platform, 0) + 1
        total_duration = sum(
            int(asset.get("media_meta", {}).get("duration_seconds") or 0) for asset in assets
        )
        return {
            "asset_count": len(assets),
            "image_count": image_count,
            "video_count": video_count,
            "ocr_count": len(ocr_items),
            "asr_count": len(asr_items),
            "platforms": [
                {"name": name, "count": count}
                for name, count in sorted(platforms.items(), key=lambda pair: pair[1], reverse=True)
            ],
            "total_duration_seconds": total_duration,
            "ocr_items": ocr_items,
            "asr_items": asr_items,
            "assets": [
                {
                    "ref": asset["ref"],
                    "id": asset["id"],
                    "source_type": asset["source_type"],
                    "title": asset["title"],
                    "source": asset["source"],
                    "published_at": asset["published_at"],
                    "url": asset["url"],
                    "meta": asset.get("media_meta", {}),
                }
                for asset in sorted(assets, key=lambda item: float(item.get("influence", 0)), reverse=True)
            ],
        }


def assign_refs(sources: list[dict[str, Any]]) -> None:
    """按影响力降序分配 [S01] 形式的引用编号。"""
    ordered = sorted(
        sources,
        key=lambda item: (float(item.get("influence", 0)), item.get("published_at", "")),
        reverse=True,
    )
    for index, source in enumerate(ordered, start=1):
        source["ref"] = f"S{index:02d}"


def ref_map(sources: list[dict[str, Any]]) -> dict[str, str]:
    return {source["id"]: source["ref"] for source in sources if source.get("ref")}


def top_keywords(sources: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    weights: dict[str, float] = {}
    counts: dict[str, int] = {}
    for source in sources:
        weight = 1.0 + float(source.get("influence", 0)) / 100.0
        for keyword in source.get("keywords", []):
            weights[keyword] = weights.get(keyword, 0.0) + weight
            counts[keyword] = counts.get(keyword, 0) + 1
    ordered = sorted(weights.items(), key=lambda pair: pair[1], reverse=True)[:limit]
    return [{"keyword": key, "score": round(value, 2), "count": counts[key]} for key, value in ordered]


def keyword_cloud(sources: list[dict[str, Any]], limit: int = 10) -> list[str]:
    return [item["keyword"] for item in top_keywords(sources, limit)]


def summarize_source(source: dict[str, Any], length: int = 70) -> str:
    return truncate(source.get("summary", ""), length)


def weighted_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 1)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def percent(part: int, total: int) -> float:
    if not total:
        return 0.0
    return round(part * 100.0 / total, 1)


def ensure_non_empty_query(query: str) -> str:
    cleaned = (query or "").strip()
    if not cleaned:
        raise AppError("检索主题不能为空", status_code=400, module="topic_search")
    if len(cleaned) > 60:
        raise AppError("检索主题长度不能超过 60 个字符", status_code=400, module="topic_search")
    return cleaned


def normalize_source_types(source_types: list[str] | None) -> list[str]:
    if source_types is None:
        return list(SOURCE_TYPES)
    if not isinstance(source_types, list):
        raise AppError("source_types 必须为数组", status_code=400, module="topic_search")
    cleaned = [item for item in source_types if item in SOURCE_TYPES]
    if len(cleaned) != len(source_types):
        raise AppError(
            "source_types 包含不支持的来源类型，可选：" + "、".join(SOURCE_TYPES),
            status_code=400,
            module="topic_search",
        )
    if not cleaned:
        raise AppError("请至少选择一种来源类型", status_code=400, module="topic_search")
    return sorted(set(cleaned), key=lambda name: SOURCE_TYPE_ORDER.get(name, 99))


def coverage_score(count: int, types: int) -> float:
    return round(min(1.0, (count / 40.0) * 0.6 + (types / 5.0) * 0.4), 3)


def weighted_ratio(sources: list[dict[str, Any]], sentiment: str) -> float:
    total = sum(float(source.get("influence", 0)) for source in sources)
    if not total:
        return 0.0
    part = sum(float(source.get("influence", 0)) for source in sources if source.get("sentiment") == sentiment)
    return round(part * 100.0 / total, 1)


def log_scale(value: float, base: float = 10.0) -> float:
    return round(math.log1p(max(0.0, value)) / math.log(base), 2)
