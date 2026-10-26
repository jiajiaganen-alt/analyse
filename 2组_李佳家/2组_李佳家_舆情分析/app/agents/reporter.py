"""报告 Agent：将分析结果组装为 8 部分结构化报告与 Markdown 文档。"""
from __future__ import annotations

from typing import Any

from ..config import SOURCE_TYPE_LABELS
from ..utils import fmt_dt, now
from .analyzer import format_citations


def _cell(text: Any) -> str:
    return str(text if text is not None else "").replace("|", "｜").replace("\n", " ").strip()


class Reporter:
    """生成报告 JSON（供前端渲染）与 Markdown（落盘归档）。"""

    SECTION_TITLES = [
        ("event_overview", "事件概述"),
        ("timeline", "时间线"),
        ("channels", "传播渠道"),
        ("opinions", "主要观点"),
        ("sentiment", "情绪倾向"),
        ("risks", "风险判断"),
        ("evidence", "重点证据"),
        ("conclusion", "结论摘要"),
    ]

    def build(
        self,
        report_id: str,
        query: str,
        dataset: dict[str, Any],
        search_result: dict[str, Any],
        analysis: dict[str, Any],
        steps: list[dict[str, Any]],
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        created_at = generated_at or now().astimezone().isoformat(timespec="seconds")
        sources = sorted(search_result["sources"], key=lambda item: item.get("ref", ""))
        stats = analysis["stats"]
        evidence = analysis["evidence"]
        overview = self._overview(dataset, analysis, search_result, created_at)
        channels = analysis["channels"]
        sentiment = analysis["sentiment"]
        sentiment_refs = self._sentiment_refs(sources, sentiment)
        report = {
            "report_id": report_id,
            "topic": dataset["topic"],
            "query": query,
            "category": dataset.get("category", ""),
            "created_at": created_at,
            "generated_label": fmt_dt(created_at, "%Y-%m-%d %H:%M:%S"),
            "source_types": search_result.get("source_types", []),
            "source_type_labels": [SOURCE_TYPE_LABELS[name] for name in search_result.get("source_types", [])],
            "source_count": len(sources),
            "agent_steps": steps,
            "event_overview": overview,
            "timeline": analysis["timeline"],
            "channels": channels,
            "opinions": analysis["opinions"],
            "sentiment": {**sentiment, "refs": sentiment_refs},
            "risks": analysis["risks"],
            "risk_summary": analysis["risk_summary"],
            "evidence": evidence,
            "conclusion": analysis["conclusion"],
            "keywords": analysis["keywords"],
            "stats": stats,
            "sources": [self._public_source(source) for source in sources],
        }
        report["markdown"] = self.render_markdown(report, dataset)
        return report

    # ------------------------------------------------------------------ 字段
    def _overview(
        self,
        dataset: dict[str, Any],
        analysis: dict[str, Any],
        search_result: dict[str, Any],
        created_at: str,
    ) -> dict[str, Any]:
        stats = analysis["stats"]
        date_range = stats["date_range"]
        range_text = ""
        if date_range["earliest"] and date_range["latest"]:
            range_text = (
                f"{fmt_dt(date_range['earliest'], '%Y-%m-%d')} 至 "
                f"{fmt_dt(date_range['latest'], '%Y-%m-%d')}"
            )
        paragraphs = [
            dataset.get("overview", ""),
            dataset.get("scope", ""),
            (
                f"本次检索于 {fmt_dt(created_at, '%Y-%m-%d %H:%M')} 执行，命中 {stats['source_count']} 条来源，"
                f"覆盖 {stats['type_coverage']} 类传播渠道，时间跨度为 {range_text}（{stats['span_days']} 天）。"
                f"来源平均可信度 {stats['avg_credibility']}，平均影响力 {stats['avg_influence']}，"
                f"负面来源占比 {stats['negative_ratio']}%。"
            ),
        ]
        refs = [item["ref"] for item in analysis["evidence"][:4]]
        if analysis["timeline"]:
            refs.append(analysis["timeline"][0]["refs"][0])
        refs = list(dict.fromkeys(refs))
        return {
            "text": "\n\n".join(paragraphs),
            "paragraphs": [paragraph for paragraph in paragraphs if paragraph],
            "refs": refs,
            "citation": format_citations(refs),
            "stats": stats,
        }

    @staticmethod
    def _sentiment_refs(sources: list[dict[str, Any]], sentiment: dict[str, Any]) -> list[str]:
        negative = [source["ref"] for source in sources if source.get("sentiment") == "negative"][:2]
        positive = [source["ref"] for source in sources if source.get("sentiment") == "positive"][:1]
        neutral = [source["ref"] for source in sources if source.get("sentiment") == "neutral"][:1]
        return list(dict.fromkeys(negative + neutral + positive))

    @staticmethod
    def _public_source(source: dict[str, Any]) -> dict[str, Any]:
        return {
            "ref": source.get("ref", ""),
            "id": source.get("id", ""),
            "source_type": source.get("source_type", ""),
            "source_type_label": SOURCE_TYPE_LABELS.get(source.get("source_type", ""), ""),
            "title": source.get("title", ""),
            "source": source.get("source", ""),
            "author": source.get("author", ""),
            "author_role": source.get("author_role", ""),
            "published_at": source.get("published_at", ""),
            "published_label": source.get("published_label", ""),
            "url": source.get("url", ""),
            "summary": source.get("summary", ""),
            "sentiment": source.get("sentiment", "neutral"),
            "sentiment_label": source.get("sentiment_label", "中性"),
            "keywords": source.get("keywords", []),
            "influence": source.get("influence", 0),
            "credibility": source.get("credibility", 0),
        }

    # ------------------------------------------------------------------ Markdown
    def render_markdown(self, report: dict[str, Any], dataset: dict[str, Any]) -> str:
        lines: list[str] = []
        overview = report["event_overview"]
        sentiment = report["sentiment"]
        risk_summary = report["risk_summary"]
        lines.append(f"# 舆情分析报告：{report['topic']}")
        lines.append("")
        lines.append("| 项目 | 内容 |")
        lines.append("| --- | --- |")
        lines.append(f"| 报告编号 | `{report['report_id']}` |")
        lines.append(f"| 生成时间 | {report['generated_label']} |")
        lines.append(f"| 检索主题 | {_cell(report['query'])} |")
        lines.append(f"| 来源范围 | {'、'.join(report['source_type_labels'])} |")
        lines.append(f"| 来源总数 | {report['source_count']} 条 |")
        lines.append(f"| 综合风险 | {risk_summary['level_label']}（评分 {risk_summary['score']}） |")
        lines.append("")
        lines.append("## 一、事件概述")
        lines.append("")
        for paragraph in overview["paragraphs"]:
            lines.append(paragraph)
            lines.append("")
        lines.append(f"**引用**：{overview['citation']}")
        lines.append("")

        lines.append("## 二、时间线")
        lines.append("")
        lines.append("| 时间 | 关键事件 | 说明 | 来源 |")
        lines.append("| --- | --- | --- | --- |")
        for event in report["timeline"]:
            lines.append(
                f"| {event['datetime_label']} | {_cell(event['title'])} | {_cell(event['description'])} | "
                f"{format_citations(event['refs'])} |"
            )
        lines.append("")

        lines.append("## 三、传播渠道")
        lines.append("")
        lines.append("| 来源类型 | 数量 | 占比 | 负面占比 | 代表来源 | 引用 |")
        lines.append("| --- | ---: | ---: | ---: | --- | --- |")
        for channel in report["channels"]:
            lines.append(
                f"| {channel['label']} | {channel['count']} | {channel['ratio']}% | {channel['negative_ratio']}% | "
                f"{_cell('、'.join(channel['top_sources']))} | {format_citations(channel['refs'])} |"
            )
        lines.append("")

        lines.append("## 四、主要观点")
        lines.append("")
        for opinion in report["opinions"]:
            lines.append(f"### {opinion['role']} · {opinion['stance']}")
            lines.append("")
            lines.append(opinion["summary"])
            lines.append("")
            for highlight in opinion["highlights"]:
                quote = _cell(highlight["text"])
                lines.append(
                    f"> “{quote}” —— {highlight['source']}，{highlight['position']} [{highlight['ref']}]"
                )
                lines.append("")
            lines.append(f"**引用**：{format_citations(opinion['refs'])}")
            lines.append("")

        lines.append("## 五、情绪倾向")
        lines.append("")
        lines.append("| 倾向 | 数量 | 占比 |")
        lines.append("| --- | ---: | ---: |")
        for key, label in (("positive", "正向"), ("neutral", "中性"), ("negative", "负向")):
            lines.append(f"| {label} | {sentiment['counts'][key]} | {sentiment['ratios'][key]}% |")
        lines.append("")
        lines.append(f"**整体判断**：{sentiment['judgement']}")
        lines.append("")
        lines.append(f"**趋势**：{sentiment['trend']}")
        lines.append("")
        lines.append(f"**引用**：{format_citations(sentiment['refs'])}")
        lines.append("")

        lines.append("## 六、风险判断")
        lines.append("")
        for risk in report["risks"]:
            lines.append(f"### 【{risk['level_label']}】{risk['title']}")
            lines.append("")
            lines.append(risk["description"])
            lines.append("")
            lines.append(f"- 观察指标：{'；'.join(risk['indicators'])}")
            lines.append(f"- 关联来源：{risk['related_count']} 条")
            lines.append(f"- 引用：{risk['citation']}")
            lines.append("")
        lines.append(
            f"**综合风险**：{risk_summary['level_label']}（评分 {risk_summary['score']} / 100），"
            f"判断依据：{'；'.join(risk_summary['basis'])}。"
        )
        lines.append("")

        lines.append("## 七、重点证据")
        lines.append("")
        lines.append("| 编号 | 标题 | 来源 / 类型 | 发布时间 | 引用位置 | 摘要 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for item in report["evidence"]:
            lines.append(
                f"| [{item['ref']}] | [{_cell(item['title'])}]({item['url']}) | {_cell(item['source'])} / "
                f"{item['source_type_label']} | {fmt_dt(item['published_at'], '%Y-%m-%d %H:%M')} | "
                f"{_cell(item['quote_position'])} | {_cell(item['summary'])} |"
            )
        lines.append("")

        lines.append("## 八、结论摘要")
        lines.append("")
        lines.append(report["conclusion"]["summary"])
        lines.append("")
        lines.append("### 建议")
        lines.append("")
        for index, item in enumerate(report["conclusion"]["recommendations"], start=1):
            lines.append(f"{index}. **{item['title']}**：{item['text']} {format_citations(item['refs'])}")
        lines.append("")
        lines.append(f"**结论置信度**：{report['conclusion']['confidence']}")
        lines.append("")

        lines.append("## 附：来源清单")
        lines.append("")
        lines.append("| 编号 | 类型 | 标题 | 来源 | 发布时间 | 情绪 | 链接 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- |")
        for source in report["sources"]:
            lines.append(
                f"| [{source['ref']}] | {source['source_type_label']} | {_cell(source['title'])} | "
                f"{_cell(source['source'])} | {fmt_dt(source['published_at'], '%Y-%m-%d %H:%M')} | "
                f"{source['sentiment_label']} | [原文]({source['url']}) |"
            )
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(
            "本报告由舆情分析平台 Agent 流水线自动生成（多来源检索 → 观点/情绪/风险抽取 → 洞察汇总 → "
            "报告生成 → 图谱构建），全部结论均标注来源编号，可在 `附：来源清单` 中回溯。"
        )
        lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ 输出摘要
    @staticmethod
    def output_summary(report: dict[str, Any]) -> str:
        sentiment = report["sentiment"]
        return (
            f"报告 {report['report_id']} 已生成\n"
            f"主题：{report['topic']}\n"
            f"来源：{report['source_count']} 条 / {len(report['channels'])} 类渠道\n"
            f"情绪：正向 {sentiment['ratios']['positive']}% / 中性 {sentiment['ratios']['neutral']}% / "
            f"负向 {sentiment['ratios']['negative']}%\n"
            f"风险：{report['risk_summary']['level_label']}（{report['risk_summary']['score']}/100）\n"
            f"章节：事件概述、时间线、传播渠道、主要观点、情绪倾向、风险判断、重点证据、结论摘要\n"
            f"报告文件：reports/{report['report_id']}/report.md\n"
            f"图谱文件：graphs/{report['report_id']}/graph.json"
        )
