"""Agent 流水线编排：检索 → 多媒体 → 洞察 → 报告 → 图谱。"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime
from typing import Any, Callable

from .agents.analyzer import Analyzer
from .agents.collector import (
    SourceRepository,
    ensure_non_empty_query,
    normalize_source_types,
    percent,
)
from .agents.graph import GraphBuilder
from .agents.reporter import Reporter
from .config import SOURCE_TYPE_LABELS
from .errors import AppError
from .events import EventBus
from .process_manager import ProcessManager
from .storage import Storage
from .utils import atomic_write_json, fmt_dt, iso, now, truncate

REQUIRED_APPS = ["topic_search", "multimedia_search", "insight_analysis", "report_writer"]


def _new_report_id() -> str:
    moment = now()
    digest = hashlib.sha1(f"{moment.timestamp()}".encode("utf-8")).hexdigest()[:4].upper()
    return f"RPT-{moment.strftime('%Y%m%d-%H%M%S')}-{digest}"


class PipelineService:
    def __init__(
        self,
        storage: Storage,
        config,
        process_manager: ProcessManager,
        bus: EventBus,
        repository: SourceRepository,
    ) -> None:
        self.storage = storage
        self.config = config
        self.pm = process_manager
        self.bus = bus
        self.repository = repository
        self.analyzer = Analyzer()
        self.reporter = Reporter()
        self.graph_builder = GraphBuilder()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ 检索
    def search(
        self,
        query: str,
        source_types: list[str] | None = None,
        max_sources: int | None = None,
        auto_start: bool = True,
    ) -> dict[str, Any]:
        query = ensure_non_empty_query(query)
        types = normalize_source_types(source_types)
        collection = self.config.section("collection")
        limit = int(max_sources or collection.get("max_sources_per_search", 60))
        limit = max(5, min(200, limit))

        self.pm.ensure_apps(REQUIRED_APPS, auto_start=auto_start)
        started = time.perf_counter()
        base = now()
        steps: list[dict[str, Any]] = []
        report_id = _new_report_id()

        def run_step(
            key: str,
            title: str,
            agent: str,
            app_name: str,
            func: Callable[[], dict[str, Any]],
            index: int,
        ) -> dict[str, Any]:
            step_start = time.perf_counter()
            started_at = iso(now())
            self.pm.append_app_log(app_name, f"[pipeline] 开始执行「{title}」（report_id={report_id}）")
            try:
                detail = func()
            except AppError as exc:
                duration = round((time.perf_counter() - step_start) * 1000, 1)
                steps.append(
                    {
                        "index": index,
                        "key": key,
                        "title": title,
                        "agent": agent,
                        "app_name": app_name,
                        "status": "failed",
                        "started_at": started_at,
                        "duration_ms": duration,
                        "summary": exc.message,
                        "metrics": {},
                    }
                )
                self.pm.append_app_log(app_name, f"[pipeline] 「{title}」失败：{exc.message}", level="ERROR")
                raise
            except Exception as exc:  # 未预期异常
                duration = round((time.perf_counter() - step_start) * 1000, 1)
                steps.append(
                    {
                        "index": index,
                        "key": key,
                        "title": title,
                        "agent": agent,
                        "app_name": app_name,
                        "status": "failed",
                        "started_at": started_at,
                        "duration_ms": duration,
                        "summary": f"执行异常：{exc}",
                        "metrics": {},
                    }
                )
                self.pm.mark_failed(app_name, f"{title}执行异常：{exc}")
                raise AppError(
                    f"{title}执行异常：{exc}",
                    status_code=500,
                    module=app_name,
                ) from exc
            duration = round((time.perf_counter() - step_start) * 1000, 1)
            step = {
                "index": index,
                "key": key,
                "title": title,
                "agent": agent,
                "app_name": app_name,
                "status": "success",
                "started_at": started_at,
                "duration_ms": duration,
                "summary": detail.get("summary", ""),
                "metrics": detail.get("metrics", {}),
            }
            steps.append(step)
            self.pm.append_app_log(
                app_name,
                f"[pipeline] 「{title}」完成，耗时 {duration}ms：{detail.get('summary', '')}",
            )
            return detail

        # 1. 多来源检索 -----------------------------------------------------
        def collect() -> dict[str, Any]:
            result = self.repository.search(query, types, limit)
            if result is None:
                available = "、".join(self.repository.topics())
                raise AppError(
                    f"未找到与「{query}」匹配的样例主题。当前可用主题：{available}",
                    status_code=404,
                    module="topic_search",
                    detail={"available_topics": self.repository.topics()},
                )
            if not result["sources"]:
                raise AppError(
                    f"主题「{result['dataset']['topic']}」在所选来源类型下暂无数据，请扩大来源范围",
                    status_code=404,
                    module="topic_search",
                    detail={"source_types": types},
                )
            counts = result["source_counts"]
            summary = (
                f"命中 {len(result['sources'])} 条来源，覆盖 "
                + "、".join(f"{SOURCE_TYPE_LABELS[name]} {count}" for name, count in counts.items() if count)
            )
            detail = {
                "summary": summary,
                "metrics": {
                    "source_count": len(result["sources"]),
                    "source_counts": counts,
                    "span_days": result["date_range"]["span_days"],
                    "query": query,
                },
                "result": result,
            }
            top_sources = sorted(
                result["sources"],
                key=lambda item: float(item.get("influence", 0)),
                reverse=True,
            )[:6]
            output = [
                "主题检索 · 最近一次输出",
                f"主题：{result['dataset']['topic']}",
                f"查询词：{query}",
                f"执行时间：{iso(now())}",
                f"来源范围：{'、'.join(SOURCE_TYPE_LABELS[name] for name in types)}",
                f"来源总数：{len(result['sources'])} 条（可用 {result['total_available']} 条）",
                f"时间跨度：{result['date_range']['span_days']} 天",
                f"来源类型：{' / '.join(f'{SOURCE_TYPE_LABELS[name]} {count}' for name, count in counts.items())}",
                "",
                "高影响力来源：",
            ]
            for source in top_sources:
                output.append(
                    f"[{source['ref']}] {source['source_type_label']}｜{source['title']}（{source['source']}）"
                )
            self.pm.note_task(
                "topic_search",
                "\n".join(output),
                [
                    (f"接收主题检索任务：query={query}，source_types={','.join(types)}", "INFO"),
                    (f"主题匹配成功：{result['dataset']['topic']}（{result['dataset']['_path']}）", "INFO"),
                    (f"检索命中 {len(result['sources'])} 条来源，时间跨度 {result['date_range']['span_days']} 天", "INFO"),
                ],
            )
            return detail

        collect_detail = run_step("collect", "多来源检索", "collector", "topic_search", collect, 1)
        search_result = collect_detail["result"]

        # 2. 多媒体解析 -----------------------------------------------------
        def multimedia() -> dict[str, Any]:
            digest = self.repository.multimedia_digest(search_result["sources"])
            summary = (
                f"解析 {digest['asset_count']} 个多媒体素材（图片 {digest['image_count']} / "
                f"视频 {digest['video_count']}），OCR {digest['ocr_count']} 条、ASR {digest['asr_count']} 条"
            )
            detail = {
                "summary": summary,
                "metrics": {
                    "asset_count": digest["asset_count"],
                    "image_count": digest["image_count"],
                    "video_count": digest["video_count"],
                    "ocr_count": digest["ocr_count"],
                    "asr_count": digest["asr_count"],
                    "total_duration_seconds": digest["total_duration_seconds"],
                },
                "digest": digest,
            }
            output = [
                "多媒体检索 · 最近一次输出",
                f"素材总数：{digest['asset_count']}（图片 {digest['image_count']} / 视频 {digest['video_count']}）",
                f"OCR 文本：{digest['ocr_count']} 条",
                f"ASR 字幕：{digest['asr_count']} 条",
                f"视频总时长：{digest['total_duration_seconds']} 秒",
                "平台分布：" + "、".join(f"{item['name']} {item['count']}" for item in digest["platforms"][:5]),
                "",
                "OCR 摘要：",
            ]
            for item in digest["ocr_items"][:5]:
                output.append(f"[{item['ref']}] {truncate(item['text'], 48)}")
            output.append("")
            output.append("ASR 摘要：")
            for item in digest["asr_items"][:5]:
                output.append(f"[{item['ref']}] {truncate(item['text'], 48)}")
            self.pm.note_task(
                "multimedia_search",
                "\n".join(output),
                [
                    (f"开始多媒体解析：素材 {digest['asset_count']} 个", "INFO"),
                    (f"OCR 命中 {digest['ocr_count']} 条，ASR 命中 {digest['asr_count']} 条", "INFO"),
                ],
            )
            return detail

        multimedia_detail = run_step(
            "multimedia", "多媒体解析", "multimedia", "multimedia_search", multimedia, 2
        )

        # 3. 洞察分析 -------------------------------------------------------
        def insight() -> dict[str, Any]:
            analysis = self.analyzer.analyze(search_result["dataset"], search_result["sources"], base)
            summary = (
                f"情绪：正 {analysis['sentiment']['ratios']['positive']}% / 中 "
                f"{analysis['sentiment']['ratios']['neutral']}% / 负 "
                f"{analysis['sentiment']['ratios']['negative']}%；观点组 {len(analysis['opinions'])} 个；"
                f"风险 {analysis['risk_summary']['level_label']}（{analysis['risk_summary']['score']}）"
            )
            detail = {
                "summary": summary,
                "metrics": {
                    "opinion_groups": len(analysis["opinions"]),
                    "risk_count": len(analysis["risks"]),
                    "risk_score": analysis["risk_summary"]["score"],
                    "negative_ratio": analysis["sentiment"]["ratios"]["negative"],
                    "keyword_count": len(analysis["keywords"]),
                },
                "analysis": analysis,
            }
            output = [
                "洞察分析 · 最近一次输出",
                f"主题：{search_result['dataset']['topic']}",
                f"情绪分布：正向 {analysis['sentiment']['ratios']['positive']}% / 中性 "
                f"{analysis['sentiment']['ratios']['neutral']}% / 负向 {analysis['sentiment']['ratios']['negative']}%",
                f"整体判断：{analysis['sentiment']['label']}",
                f"趋势：{analysis['sentiment']['trend']}",
                f"观点组：{'、'.join(item['role'] for item in analysis['opinions'])}",
                f"风险评分：{analysis['risk_summary']['score']}/100（{analysis['risk_summary']['level_label']}）",
                f"关键词：{'、'.join(item['keyword'] for item in analysis['keywords'][:8])}",
                "",
                "高危风险点：",
            ]
            for risk in analysis["risks"]:
                if risk["level"] == "high":
                    output.append(f"- {risk['title']}：{risk['description']} {risk['citation']}")
            self.pm.note_task(
                "insight_analysis",
                "\n".join(output),
                [
                    (f"开始洞察分析：来源 {len(search_result['sources'])} 条", "INFO"),
                    (
                        f"情绪判定完成：负向占比 {analysis['sentiment']['ratios']['negative']}%，"
                        f"观点组 {len(analysis['opinions'])} 个",
                        "INFO",
                    ),
                    (
                        f"风险评分 {analysis['risk_summary']['score']}/100，"
                        f"高风险点 {analysis['risk_summary']['high_count']} 个",
                        "INFO",
                    ),
                ],
            )
            return detail

        insight_detail = run_step(
            "insight", "洞察分析", "analyzer", "insight_analysis", insight, 3
        )
        analysis = insight_detail["analysis"]

        # 4. 报告生成 -------------------------------------------------------
        def report_step() -> dict[str, Any]:
            report = self.reporter.build(
                report_id,
                query,
                search_result["dataset"],
                search_result,
                analysis,
                steps,
            )
            markdown = report.pop("markdown")
            search_meta = {
                "report_id": report_id,
                "topic": search_result["dataset"]["topic"],
                "query": query,
                "executed_at": iso(now()),
                "source_types": types,
                "source_summary": {
                    "total": len(search_result["sources"]),
                    "by_type": search_result["source_counts"],
                    "date_range": search_result["date_range"],
                    "top_sources": [
                        {
                            "ref": source["ref"],
                            "id": source["id"],
                            "title": source["title"],
                            "source": source["source"],
                            "type": source["source_type"],
                            "published_at": source["published_at"],
                        }
                        for source in sorted(
                            search_result["sources"],
                            key=lambda item: float(item.get("influence", 0)),
                            reverse=True,
                        )[:10]
                    ],
                },
                "analysis_output": {
                    "sentiment": analysis["sentiment"],
                    "risk_summary": analysis["risk_summary"],
                    "opinion_groups": [
                        {"role": item["role"], "stance": item["stance"], "count": item["count"]}
                        for item in analysis["opinions"]
                    ],
                    "keywords": analysis["keywords"][:10],
                },
                "agent_steps": steps,
                "multimedia": multimedia_detail["metrics"],
            }
            paths = self.storage.save_report(report_id, markdown, report, search_meta)
            report["paths"] = paths
            report["graph_summary"] = None
            summary = (
                f"报告 {report_id} 生成完成：8 个章节，来源 {len(search_result['sources'])} 条，"
                f"引用 {len(analysis['evidence'])} 条重点证据"
            )
            detail = {
                "summary": summary,
                "metrics": {
                    "sections": 8,
                    "evidence_count": len(analysis["evidence"]),
                    "source_count": len(search_result["sources"]),
                },
                "report": report,
                "markdown": markdown,
                "search_meta": search_meta,
                "paths": paths,
            }
            output = self.reporter.output_summary(report)
            self.pm.note_task(
                "report_writer",
                output,
                [
                    (f"开始生成报告 {report_id}，8 个章节", "INFO"),
                    (f"报告写入 {paths.get('markdown')}，引用 {len(analysis['evidence'])} 条重点证据", "INFO"),
                    (f"检索元数据写入 {paths.get('search')}", "INFO"),
                ],
            )
            return detail

        report_detail = run_step("report", "报告生成", "reporter", "report_writer", report_step, 4)
        report = report_detail["report"]
        search_meta = report_detail["search_meta"]

        # 5. 图谱构建 -------------------------------------------------------
        def graph_step() -> dict[str, Any]:
            max_nodes = int(self.config.section("runtime").get("graph_max_nodes", 80))
            graph = self.graph_builder.build(
                report_id,
                search_result["dataset"],
                search_result["sources"],
                analysis,
                max_nodes=max_nodes,
            )
            graph_path = self.storage.save_graph(report_id, graph)
            summary = (
                f"图谱构建完成：{graph['stats']['node_count']} 个节点、{graph['stats']['edge_count']} 条关系，"
                f"覆盖 {graph['stats']['source_node_count']} 条来源"
            )
            detail = {
                "summary": summary,
                "metrics": {
                    "node_count": graph["stats"]["node_count"],
                    "edge_count": graph["stats"]["edge_count"],
                    "source_node_count": graph["stats"]["source_node_count"],
                },
                "graph": graph,
                "graph_path": graph_path,
            }
            search_meta["graph"] = {
                "graph_path": self.storage.rel(graph_path),
                "node_count": graph["stats"]["node_count"],
                "edge_count": graph["stats"]["edge_count"],
            }
            atomic_write_json(self.storage.report_paths(report_id)["search"], search_meta)
            graph_summary = {
                "report_id": report_id,
                "topic": graph["topic"],
                "node_count": graph["stats"]["node_count"],
                "edge_count": graph["stats"]["edge_count"],
                "type_counts": graph["stats"]["type_counts"],
                "relation_counts": graph["stats"]["relation_counts"],
                "graph_path": self.storage.rel(graph_path),
                "created_at": graph["created_at"],
                "top_node": graph["stats"]["top_node"],
            }
            report["graph_summary"] = graph_summary
            report["paths"] = {**report["paths"], "graph": self.storage.rel(graph_path)}
            atomic_write_json(self.storage.report_paths(report_id)["json"], report)
            self.bus.publish(
                {
                    "type": "graph_ready",
                    "report_id": report_id,
                    "graph_path": self.storage.rel(graph_path),
                    "node_count": graph["stats"]["node_count"],
                    "edge_count": graph["stats"]["edge_count"],
                }
            )
            self.pm.note_task(
                "report_writer",
                self.reporter.output_summary(report) + f"\n图谱：{summary}",
                [
                    (f"开始构建图谱：来源 {len(search_result['sources'])} 条", "INFO"),
                    (
                        f"图谱写入 {self.storage.rel(graph_path)}，节点 {graph['stats']['node_count']}，"
                        f"边 {graph['stats']['edge_count']}",
                        "INFO",
                    ),
                ],
            )
            return detail

        graph_detail = run_step("graph", "图谱构建", "graph", "report_writer", graph_step, 5)
        graph = graph_detail["graph"]
        graph_summary = report.get("graph_summary") or {}

        # 五段流水线全部完成后，用完整步骤列表回写报告与检索元数据
        report["agent_steps"] = steps
        search_meta["agent_steps"] = steps
        atomic_write_json(self.storage.report_paths(report_id)["json"], report)
        atomic_write_json(self.storage.report_paths(report_id)["search"], search_meta)

        total_duration = round((time.perf_counter() - started) * 1000, 1)
        response = {
            "ok": True,
            "report_id": report_id,
            "topic": report["topic"],
            "query": query,
            "executed_at": report["created_at"],
            "duration_ms": total_duration,
            "agent_steps": steps,
            "source_summary": {
                "total": len(search_result["sources"]),
                "by_type": search_result["source_counts"],
                "by_type_labels": {
                    SOURCE_TYPE_LABELS[name]: count
                    for name, count in search_result["source_counts"].items()
                    if count
                },
                "date_range": search_result["date_range"],
                "sentiment": analysis["sentiment"]["counts"],
            },
            "report": report,
            "graph": graph_summary,
            "paths": {
                "report_md": self.storage.rel(self.storage.report_paths(report_id)["markdown"]),
                "report_json": self.storage.rel(self.storage.report_paths(report_id)["json"]),
                "search_json": self.storage.rel(self.storage.report_paths(report_id)["search"]),
                "graph_json": self.storage.rel(self.storage.graph_path(report_id)),
            },
            "source_count": len(search_result["sources"]),
            "catalog": self.repository.catalog(),
        }
        self.storage.append_system_log(
            "INFO",
            "pipeline",
            f"检索完成 report_id={report_id}，来源 {len(search_result['sources'])} 条，"
            f"总耗时 {total_duration}ms",
        )
        return response

    # ------------------------------------------------------------------ 查询
    def get_report(self, report_id: str) -> dict[str, Any]:
        report = self.storage.load_report(report_id)
        if report is None:
            raise AppError(
                f"报告不存在：{report_id}",
                status_code=404,
                module="report_writer",
                detail={"report_id": report_id},
            )
        markdown = self.storage.load_report_markdown(report_id)
        search_meta = self.storage.load_search_meta(report_id) or {}
        return {
            "ok": True,
            "report": report,
            "markdown": markdown,
            "search_meta": search_meta,
            "paths": {
                "report_md": self.storage.rel(self.storage.report_paths(report_id)["markdown"]),
                "report_json": self.storage.rel(self.storage.report_paths(report_id)["json"]),
                "search_json": self.storage.rel(self.storage.report_paths(report_id)["search"]),
                "graph_json": self.storage.rel(self.storage.graph_path(report_id)),
            },
        }

    def list_reports(self) -> dict[str, Any]:
        reports = self.storage.list_reports(limit=100)
        graphs = {item["report_id"] for item in self.storage.list_graphs(limit=200)}
        for report in reports:
            report["has_graph"] = report["report_id"] in graphs
        return {
            "ok": True,
            "reports": reports,
            "total": len(reports),
            "latest": reports[0] if reports else None,
        }

    def graph_payload(self, report_id: str) -> dict[str, Any]:
        graph = self.storage.load_graph(report_id)
        if graph is None:
            raise AppError(
                f"报告 {report_id} 暂无图谱数据",
                status_code=404,
                module="graph",
                detail={"report_id": report_id},
            )
        return {
            "ok": True,
            "report_id": report_id,
            "topic": graph.get("topic"),
            "created_at": graph.get("created_at"),
            "nodes": graph.get("nodes", []),
            "edges": graph.get("edges", []),
            "stats": graph.get("stats", {}),
            "paths": {"graph_json": self.storage.rel(self.storage.graph_path(report_id))},
        }

    def latest_graph(self) -> dict[str, Any]:
        graphs = self.storage.list_graphs(limit=1)
        if not graphs:
            raise AppError(
                "暂无图谱数据，请先发起一次主题检索",
                status_code=404,
                module="graph",
                detail={"suggestion": "在主题检索页发起分析后再查看图谱"},
            )
        return self.graph_payload(graphs[0]["report_id"])
