"""分析 Agent：情绪、关键词、观点聚类、传播渠道与风险判断。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..config import SOURCE_TYPES, SOURCE_TYPE_LABELS
from ..utils import clamp, fmt_dt, iso, now, truncate
from .collector import (
    SENTIMENT_LABELS,
    SENTIMENT_ORDER,
    percent,
    top_keywords,
    weighted_mean,
    weighted_ratio,
)

RISK_LEVEL_LABELS = {"high": "高风险", "medium": "中风险", "low": "低风险"}
RISK_LEVEL_ORDER = {"high": 3, "medium": 2, "low": 1}


def format_citations(refs: list[str] | None) -> str:
    seen: list[str] = []
    for ref in refs or []:
        if ref and ref not in seen:
            seen.append(ref)
    return "".join(f"[{ref}]" for ref in seen)


def unique_refs(sources: list[dict[str, Any]], limit: int | None = None) -> list[str]:
    refs: list[str] = []
    for source in sources:
        ref = source.get("ref")
        if ref and ref not in refs:
            refs.append(ref)
    return refs[:limit] if limit else refs


def _sentiment_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts = {name: 0 for name in SENTIMENT_ORDER}
    for source in sources:
        if source.get("sentiment") in counts:
            counts[source["sentiment"]] += 1
    return counts


def _sentiment_block(sources: list[dict[str, Any]]) -> dict[str, Any]:
    counts = _sentiment_counts(sources)
    total = len(sources)
    ratios = {name: percent(counts[name], total) for name in SENTIMENT_ORDER}
    return {
        "counts": counts,
        "ratios": ratios,
        "labels": {name: SENTIMENT_LABELS[name] for name in SENTIMENT_ORDER},
    }


class Analyzer:
    """确定性洞察分析：相同输入始终产生相同结论。"""

    def analyze(
        self,
        dataset: dict[str, Any],
        sources: list[dict[str, Any]],
        base: datetime | None = None,
    ) -> dict[str, Any]:
        base = base or now()
        sentiment = self._sentiment(sources, base)
        channels = self._channels(sources)
        opinions = self._opinions(sources)
        risks = self._risks(dataset, sources)
        timeline = self._timeline(dataset, sources)
        evidence = self._evidence(sources, limit=10)
        risk_summary = self._risk_summary(sources, risks, sentiment, channels)
        keywords = top_keywords(sources, 12)
        stats = self._stats(sources, dataset, sentiment, channels, risk_summary)
        conclusion = self._conclusion(dataset, sources, sentiment, risks, risk_summary, opinions, keywords)
        return {
            "sentiment": sentiment,
            "channels": channels,
            "opinions": opinions,
            "risks": risks,
            "timeline": timeline,
            "evidence": evidence,
            "risk_summary": risk_summary,
            "keywords": keywords,
            "stats": stats,
            "conclusion": conclusion,
        }

    # ------------------------------------------------------------------ 情绪
    def _sentiment(self, sources: list[dict[str, Any]], base: datetime) -> dict[str, Any]:
        block = _sentiment_block(sources)
        counts, ratios = block["counts"], block["ratios"]
        total = len(sources)
        negative = counts["negative"]
        positive = counts["positive"]
        neutral = counts["neutral"]
        if total == 0:
            judgement = "暂无足够来源，无法判断整体情绪倾向。"
            label = "未知"
        elif ratios["negative"] >= 45:
            judgement = f"整体偏负向：负面来源占 {ratios['negative']}%，负面情绪处于高位，需优先处置高风险议题。"
            label = "整体偏负"
        elif ratios["negative"] > ratios["positive"]:
            judgement = f"整体中性偏负：负面占 {ratios['negative']}%、中性 {ratios['neutral']}%、正向 {ratios['positive']}%，质疑情绪仍占上风。"
            label = "中性偏负"
        elif ratios["positive"] > ratios["negative"]:
            judgement = f"整体中性偏正：正向占 {ratios['positive']}%，但仍有过半来源持中性观望态度。"
            label = "中性偏正"
        else:
            judgement = "正负情绪基本持平，舆论处于分歧状态。"
            label = "分歧"

        recent_cutoff = base - timedelta(days=7)
        recent = [
            source
            for source in sources
            if datetime.fromisoformat(source["published_at"]) >= recent_cutoff
        ]
        earlier = [
            source
            for source in sources
            if datetime.fromisoformat(source["published_at"]) < recent_cutoff
        ]
        recent_ratio = weighted_ratio(recent, "negative")
        earlier_ratio = weighted_ratio(earlier, "negative")
        if recent and earlier:
            diff = round(recent_ratio - earlier_ratio, 1)
            if diff >= 4:
                trend = f"近 7 天负面声量较前期上升 {diff} 个百分点，情绪有升温迹象。"
                trend_direction = "up"
            elif diff <= -4:
                trend = f"近 7 天负面声量较前期回落 {abs(diff)} 个百分点，情绪趋于缓和。"
                trend_direction = "down"
            else:
                trend = "近 7 天负面声量与前期基本持平，情绪处于平台期。"
                trend_direction = "stable"
        else:
            trend = "来源时间分布不足以进行趋势对比。"
            trend_direction = "unknown"

        return {
            **block,
            "total": total,
            "judgement": judgement,
            "label": label,
            "trend": trend,
            "trend_direction": trend_direction,
            "recent_negative_ratio": recent_ratio,
            "earlier_negative_ratio": earlier_ratio,
            "dominant": max(SENTIMENT_ORDER, key=lambda name: counts[name]) if total else "neutral",
        }

    # ------------------------------------------------------------------ 渠道
    def _channels(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        channels: list[dict[str, Any]] = []
        for source_type in SOURCE_TYPES:
            items = [source for source in sources if source["source_type"] == source_type]
            if not items:
                continue
            block = _sentiment_block(items)
            names: list[str] = []
            for item in sorted(items, key=lambda source: float(source.get("influence", 0)), reverse=True):
                if item["source"] not in names:
                    names.append(item["source"])
            channels.append(
                {
                    "source_type": source_type,
                    "label": SOURCE_TYPE_LABELS[source_type],
                    "count": len(items),
                    "ratio": percent(len(items), len(sources)),
                    "sentiment": block["counts"],
                    "sentiment_ratios": block["ratios"],
                    "negative_ratio": block["ratios"]["negative"],
                    "avg_influence": weighted_mean([float(item.get("influence", 0)) for item in items]),
                    "reach": round(sum(float(item.get("influence", 0)) for item in items), 1),
                    "top_sources": names[:2],
                    "refs": unique_refs(
                        sorted(items, key=lambda source: float(source.get("influence", 0)), reverse=True),
                        2,
                    ),
                }
            )
        channels.sort(key=lambda item: (item["count"], item["reach"]), reverse=True)
        return channels

    # ------------------------------------------------------------------ 观点
    def _opinions(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for source in sources:
            role = (source.get("author_role") or "其他").strip() or "其他"
            groups.setdefault(role, []).append(source)
        opinions: list[dict[str, Any]] = []
        for role, items in groups.items():
            items = sorted(items, key=lambda source: float(source.get("influence", 0)), reverse=True)
            block = _sentiment_block(items)
            ratios = block["ratios"]
            if ratios["negative"] >= 50:
                stance, tone = "质疑 / 担忧", "negative"
            elif ratios["positive"] >= 50:
                stance, tone = "认可 / 支持", "positive"
            else:
                stance, tone = "理性观望", "neutral"
            highlights = [
                {
                    "ref": item["ref"],
                    "source_id": item["id"],
                    "text": item.get("quote", ""),
                    "position": item.get("quote_position", ""),
                    "title": item["title"],
                    "source": item["source"],
                }
                for item in items[:3]
                if item.get("quote")
            ]
            summary_parts = [item.get("opinion", "") for item in items[:2] if item.get("opinion")]
            summary = "；".join(summary_parts)
            summary = f"{summary}（{role}群体共 {len(items)} 条来源，负面占比 {ratios['negative']}%）"
            opinions.append(
                {
                    "role": role,
                    "stance": stance,
                    "tone": tone,
                    "count": len(items),
                    "sentiment": block["counts"],
                    "sentiment_ratios": ratios,
                    "summary": summary,
                    "highlights": highlights,
                    "refs": unique_refs(items, 4),
                    "source_types": sorted({item["source_type"] for item in items}),
                }
            )
        opinions.sort(key=lambda item: (item["count"], sum(item["sentiment"].values())), reverse=True)
        return opinions[:7]

    # ------------------------------------------------------------------ 时间线
    def _timeline(self, dataset: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ref_by_id = {source["id"]: source["ref"] for source in sources}
        timeline: list[dict[str, Any]] = []
        for index, event in enumerate(dataset.get("timeline", []), start=1):
            published = now() - timedelta(hours=float(event.get("hours_ago", 24 * 30)))
            refs = [ref_by_id[sid] for sid in event.get("source_ids", []) if sid in ref_by_id]
            if not refs:
                continue
            timeline.append(
                {
                    "id": event.get("id", f"E{index:02d}"),
                    "time": iso(published),
                    "date_label": fmt_dt(published, "%m-%d"),
                    "time_label": fmt_dt(published, "%H:%M"),
                    "datetime_label": fmt_dt(published, "%Y-%m-%d %H:%M"),
                    "title": event.get("title", ""),
                    "description": event.get("description", ""),
                    "importance": event.get("importance", "medium"),
                    "refs": refs,
                    "source_ids": [sid for sid in event.get("source_ids", []) if sid in ref_by_id],
                    "entity_ids": event.get("entity_ids", []),
                }
            )
        timeline.sort(key=lambda item: item["time"])
        return timeline

    # ------------------------------------------------------------------ 风险
    def _risks(self, dataset: dict[str, Any], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ref_by_id = {source["id"]: source["ref"] for source in sources}
        source_by_id = {source["id"]: source for source in sources}
        risks: list[dict[str, Any]] = []
        for risk in dataset.get("risks", []):
            refs = [ref_by_id[sid] for sid in risk.get("source_ids", []) if sid in ref_by_id]
            if not refs:
                continue
            related = [source_by_id[sid] for sid in risk.get("source_ids", []) if sid in source_by_id]
            risks.append(
                {
                    "level": risk.get("level", "medium"),
                    "level_label": RISK_LEVEL_LABELS.get(risk.get("level", "medium"), "中风险"),
                    "title": risk.get("title", ""),
                    "description": risk.get("description", ""),
                    "indicators": risk.get("indicators", []),
                    "refs": refs,
                    "citation": format_citations(refs),
                    "related_count": len(related),
                    "related_sentiment": _sentiment_counts(related),
                    "related_titles": [item["title"] for item in related[:3]],
                }
            )
        risks.sort(key=lambda item: RISK_LEVEL_ORDER.get(item["level"], 0), reverse=True)
        return risks

    def _risk_summary(
        self,
        sources: list[dict[str, Any]],
        risks: list[dict[str, Any]],
        sentiment: dict[str, Any],
        channels: list[dict[str, Any]],
    ) -> dict[str, Any]:
        high = sum(1 for risk in risks if risk["level"] == "high")
        medium = sum(1 for risk in risks if risk["level"] == "medium")
        low = sum(1 for risk in risks if risk["level"] == "low")
        forum = [source for source in sources if source["source_type"] == "forum_post"]
        video = [source for source in sources if source["source_type"] == "video"]
        forum_negative = weighted_ratio(forum, "negative")
        video_negative = weighted_ratio(video, "negative")
        score = (
            sentiment["ratios"]["negative"] * 0.7
            + forum_negative * 0.15
            + high * 7.0
            + video_negative * 0.08
        )
        score = round(clamp(score, 0, 100), 1)
        if score >= 65:
            level, level_label = "high", "高"
        elif score >= 50:
            level, level_label = "medium", "较高"
        elif score >= 35:
            level, level_label = "low", "中"
        else:
            level, level_label = "low", "低"
        basis = [
            f"负面来源占比 {sentiment['ratios']['negative']}%",
            f"高风险点 {high} 项",
            f"论坛负面占比 {forum_negative}%",
            f"视频负面占比 {video_negative}%",
        ]
        return {
            "score": score,
            "level": level,
            "level_label": level_label,
            "high_count": high,
            "medium_count": medium,
            "low_count": low,
            "basis": basis,
            "forum_negative_ratio": forum_negative,
            "video_negative_ratio": video_negative,
            "dominant_channel": channels[0]["label"] if channels else "-",
        }

    # ------------------------------------------------------------------ 证据
    def _evidence(self, sources: list[dict[str, Any]], limit: int = 10) -> list[dict[str, Any]]:
        ordered = sorted(sources, key=lambda source: float(source.get("influence", 0)), reverse=True)
        chosen: list[dict[str, Any]] = []
        used_types: set[str] = set()
        for source in ordered:
            if source["source_type"] not in used_types:
                chosen.append(source)
                used_types.add(source["source_type"])
            if len(chosen) >= len(SOURCE_TYPES):
                break
        for source in ordered:
            if len(chosen) >= limit:
                break
            if source not in chosen:
                chosen.append(source)
        chosen.sort(key=lambda source: float(source.get("influence", 0)), reverse=True)
        evidence: list[dict[str, Any]] = []
        for index, source in enumerate(chosen[:limit], start=1):
            evidence.append(
                {
                    "rank": index,
                    "ref": source["ref"],
                    "source_id": source["id"],
                    "title": source["title"],
                    "url": source["url"],
                    "source": source["source"],
                    "author": source.get("author", ""),
                    "author_role": source.get("author_role", ""),
                    "source_type": source["source_type"],
                    "source_type_label": SOURCE_TYPE_LABELS[source["source_type"]],
                    "published_at": source["published_at"],
                    "published_label": source["published_label"],
                    "summary": source["summary"],
                    "quote": source.get("quote", ""),
                    "quote_position": source.get("quote_position", ""),
                    "sentiment": source.get("sentiment", "neutral"),
                    "sentiment_label": SENTIMENT_LABELS.get(source.get("sentiment"), "中性"),
                    "keywords": source.get("keywords", []),
                    "influence": source.get("influence", 0),
                    "credibility": source.get("credibility", 0),
                }
            )
        return evidence

    # ------------------------------------------------------------------ 统计
    def _stats(
        self,
        sources: list[dict[str, Any]],
        dataset: dict[str, Any],
        sentiment: dict[str, Any],
        channels: list[dict[str, Any]],
        risk_summary: dict[str, Any],
    ) -> dict[str, Any]:
        type_counts = {name: 0 for name in SOURCE_TYPES}
        for source in sources:
            type_counts[source["source_type"]] = type_counts.get(source["source_type"], 0) + 1
        published = sorted(source["published_at"] for source in sources)
        span_days = 0.0
        if published:
            span_days = round(
                (datetime.fromisoformat(published[-1]) - datetime.fromisoformat(published[0])).total_seconds()
                / 86400,
                1,
            )
        return {
            "source_count": len(sources),
            "type_counts": type_counts,
            "type_coverage": sum(1 for count in type_counts.values() if count > 0),
            "date_range": {"earliest": published[0] if published else None, "latest": published[-1] if published else None},
            "span_days": span_days,
            "avg_influence": weighted_mean([float(source.get("influence", 0)) for source in sources]),
            "avg_credibility": round(
                sum(float(source.get("credibility", 0)) for source in sources) / max(1, len(sources)), 2
            ),
            "negative_ratio": sentiment["ratios"]["negative"],
            "channel_top": channels[0]["label"] if channels else "-",
            "risk_score": risk_summary["score"],
            "risk_level": risk_summary["level_label"],
            "category": dataset.get("category", ""),
        }

    # ------------------------------------------------------------------ 结论
    def _conclusion(
        self,
        dataset: dict[str, Any],
        sources: list[dict[str, Any]],
        sentiment: dict[str, Any],
        risks: list[dict[str, Any]],
        risk_summary: dict[str, Any],
        opinions: list[dict[str, Any]],
        keywords: list[dict[str, Any]],
    ) -> dict[str, Any]:
        roles = [opinion["role"] for opinion in opinions[:3]]
        role_text = "、".join(roles) if roles else "各方"
        top_risks = risks[:2]
        risk_names = "、".join(risk["title"] for risk in top_risks) if top_risks else "暂未识别突出风险"
        top_keywords = "、".join(item["keyword"] for item in keywords[:5])
        summary = (
            f"综合 {len(sources)} 条来源与 {len(risks)} 项风险点，「{dataset['topic']}」舆情整体处于"
            f"{risk_summary['level_label']}风险区间，负面情绪占 {sentiment['ratios']['negative']}%。"
            f"讨论集中在{role_text}等群体，核心议题为{top_keywords}；{risk_names}是当前最需要回应的风险点。"
            f"{sentiment['trend']}"
        )
        recommendations = []
        for risk in top_risks:
            recommendations.append(
                {
                    "title": f"优先处置：{risk['title']}",
                    "text": (
                        f"由主管部门与责任主体在 24 小时内明确回应口径和处置时间表，优先公开"
                        f"{'、'.join(risk['indicators'][:2])}等可核验信息，避免以笼统表态替代事实说明。"
                    ),
                    "refs": risk["refs"][:3],
                }
            )
        if sentiment["ratios"]["negative"] > 0:
            top_channel = risk_summary["dominant_channel"]
            recommendations.append(
                {
                    "title": "统一信息发布节奏",
                    "text": (
                        f"当前声量主要集中在{top_channel}，建议建立“事实通报 + 进展更新 + 问答口径”三段式发布机制，"
                        "对不实信息在 4 小时内完成首次澄清，并保留可回溯的发布记录。"
                    ),
                    "refs": [item["ref"] for item in sources[:2]],
                }
            )
        recommendations.append(
            {
                "title": "建立可核查的长效机制",
                "text": (
                    f"针对{role_text}的知情与参与诉求，将公示、查询、反馈固化为制度流程，"
                    "定期公开整改进度并引入第三方核验，避免舆情回落即停止改进。"
                ),
                "refs": [item["ref"] for item in sources[:3]],
            }
        )
        type_coverage = len({source["source_type"] for source in sources})
        confidence = round(min(0.96, 0.62 + type_coverage * 0.045 + min(0.14, len(sources) / 300)), 2)
        return {
            "summary": summary,
            "recommendations": recommendations,
            "confidence": confidence,
            "refs": [item["ref"] for item in sources[:4]],
        }
