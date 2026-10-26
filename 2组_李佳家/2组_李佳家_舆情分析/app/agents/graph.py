"""图谱 Agent：从报告来源与实体构建节点/边，支持条件查询。"""
from __future__ import annotations

from typing import Any

from ..utils import iso, now, truncate
from .analyzer import format_citations

NODE_TYPES = ["topic", "brand", "event", "person", "org", "media", "source"]
NODE_TYPE_LABELS = {
    "topic": "主题",
    "brand": "品牌/产品",
    "event": "事件",
    "person": "人物",
    "org": "机构",
    "media": "媒体",
    "source": "来源",
}
SOURCE_RELATIONS = {
    "news": ("reports", "报道"),
    "image": ("illustrates", "图像佐证"),
    "video": ("covers", "视频报道"),
    "forum_post": ("discusses", "讨论"),
    "internal_data": ("supports", "内部佐证"),
}


class GraphBuilder:
    def build(
        self,
        report_id: str,
        dataset: dict[str, Any],
        sources: list[dict[str, Any]],
        analysis: dict[str, Any],
        max_nodes: int = 80,
    ) -> dict[str, Any]:
        ref_by_id = {source["id"]: source["ref"] for source in sources}
        source_by_id = {source["id"]: source for source in sources}
        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        edge_keys: dict[tuple[str, str, str], dict[str, Any]] = {}

        topic_refs = [item["ref"] for item in analysis["evidence"][:5]]
        nodes.append(
            {
                "id": "TOPIC",
                "label": dataset["topic"],
                "type": "topic",
                "source_refs": topic_refs,
                "description": dataset.get("overview", ""),
                "meta": {"category": dataset.get("category", ""), "report_id": report_id},
            }
        )

        # 事件节点
        event_nodes: list[dict[str, Any]] = []
        for event in analysis["timeline"]:
            node = {
                "id": event["id"],
                "label": event["title"],
                "type": "event",
                "source_refs": event["refs"],
                "description": event["description"],
                "meta": {
                    "time": event["time"],
                    "datetime_label": event["datetime_label"],
                    "importance": event["importance"],
                    "entity_ids": event.get("entity_ids", []),
                },
            }
            event_nodes.append(node)
            nodes.append(node)

        # 实体节点
        entity_nodes: dict[str, dict[str, Any]] = {}
        for entity in dataset.get("entities", []):
            refs = [ref_by_id[sid] for sid in entity.get("source_ids", []) if sid in ref_by_id]
            if not refs:
                continue
            node = {
                "id": entity["id"],
                "label": entity["label"],
                "type": entity.get("type", "org"),
                "source_refs": refs,
                "description": entity.get("description", ""),
                "meta": {"source_ids": [sid for sid in entity.get("source_ids", []) if sid in ref_by_id]},
            }
            entity_nodes[entity["id"]] = node
            nodes.append(node)

        # 来源节点：优先证据来源，再按影响力补齐（控制数量，保证图谱可读性）
        base_count = len(nodes)
        budget = max(8, min(18, len(sources), max_nodes - base_count))
        evidence_ids = [item["source_id"] for item in analysis["evidence"]]
        ordered_sources = sorted(
            sources, key=lambda source: float(source.get("influence", 0)), reverse=True
        )
        selected_sources: list[dict[str, Any]] = []
        for source_id in evidence_ids:
            source = source_by_id.get(source_id)
            if source and source not in selected_sources:
                selected_sources.append(source)
        for source in ordered_sources:
            if len(selected_sources) >= budget:
                break
            if source not in selected_sources:
                selected_sources.append(source)
        source_node_ids: dict[str, str] = {}
        for source in selected_sources:
            node_id = f"SRC-{source['id']}"
            source_node_ids[source["id"]] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "label": truncate(source["title"], 26),
                    "type": "source",
                    "source_refs": [source["ref"]],
                    "description": source.get("summary", ""),
                    "meta": {
                        "source_id": source["id"],
                        "source_type": source["source_type"],
                        "source_type_label": source.get("source_type_label", ""),
                        "source": source.get("source", ""),
                        "published_at": source.get("published_at", ""),
                        "published_label": source.get("published_label", ""),
                        "sentiment": source.get("sentiment", "neutral"),
                        "url": source.get("url", ""),
                        "author_role": source.get("author_role", ""),
                    },
                }
            )

        def add_edge(
            source: str,
            target: str,
            relation: str,
            label: str,
            source_refs: list[str] | None = None,
        ) -> None:
            if not source or not target or source == target:
                return
            key = (source, target, relation)
            refs = [ref for ref in (source_refs or []) if ref]
            if key in edge_keys:
                existing = edge_keys[key]
                for ref in refs:
                    if ref not in existing["source_refs"]:
                        existing["source_refs"].append(ref)
                return
            edge = {
                "id": f"EDGE-{len(edges) + 1:03d}",
                "source": source,
                "target": target,
                "relation": relation,
                "label": label,
                "source_refs": refs,
            }
            edge_keys[key] = edge
            edges.append(edge)

        # 主题 → 事件
        for event in analysis["timeline"]:
            add_edge("TOPIC", event["id"], "contains", "包含事件", event["refs"])

        # 主题 → 媒体
        for entity in dataset.get("entities", []):
            if entity.get("type") != "media":
                continue
            node = entity_nodes.get(entity["id"])
            if node:
                add_edge("TOPIC", entity["id"], "spread_by", "传播渠道", node["source_refs"])

        # 来源 → 主题 / 实体
        for source in selected_sources:
            node_id = source_node_ids[source["id"]]
            relation, label = SOURCE_RELATIONS.get(source["source_type"], ("mentions", "提及"))
            add_edge(node_id, "TOPIC", relation, label, [source["ref"]])
            for entity in dataset.get("entities", []):
                if source["id"] in entity.get("source_ids", []) and entity["id"] in entity_nodes:
                    add_edge(node_id, entity["id"], "mentions", "提及", [source["ref"]])

        # 事件 → 实体
        for event in analysis["timeline"]:
            for entity_id in event.get("entity_ids", []):
                if entity_id in entity_nodes:
                    add_edge(event["id"], entity_id, "involves", "涉及", event["refs"])

        # 媒体 → 来源
        media_labels = {
            entity["label"]: entity["id"]
            for entity in dataset.get("entities", [])
            if entity.get("type") == "media" and entity["id"] in entity_nodes
        }
        for source in selected_sources:
            media_id = media_labels.get(source.get("source", ""))
            if media_id:
                add_edge(media_id, source_node_ids[source["id"]], "published", "发布", [source["ref"]])

        # 实体关系
        for relation in dataset.get("entity_relations", []):
            source_id = "TOPIC" if relation.get("source") == "TOPIC" else relation.get("source")
            target_id = "TOPIC" if relation.get("target") == "TOPIC" else relation.get("target")
            refs = [ref_by_id[sid] for sid in relation.get("source_ids", []) if sid in ref_by_id]
            if not refs:
                continue
            add_edge(
                source_id,
                target_id,
                relation.get("relation", "related_to"),
                relation.get("label", "关联"),
                refs,
            )

        # 主题 → 品牌
        for entity in dataset.get("entities", []):
            if entity.get("type") == "brand" and entity["id"] in entity_nodes:
                add_edge("TOPIC", entity["id"], "related_brand", "关联品牌", entity_nodes[entity["id"]]["source_refs"])

        # 计算度数
        degree: dict[str, int] = {node["id"]: 0 for node in nodes}
        for edge in edges:
            if edge["source"] in degree:
                degree[edge["source"]] += 1
            if edge["target"] in degree:
                degree[edge["target"]] += 1
        for node in nodes:
            node["degree"] = degree.get(node["id"], 0)
            node["type_label"] = NODE_TYPE_LABELS.get(node["type"], node["type"])

        type_counts: dict[str, int] = {name: 0 for name in NODE_TYPES}
        for node in nodes:
            type_counts[node["type"]] = type_counts.get(node["type"], 0) + 1
        relation_counts: dict[str, int] = {}
        for edge in edges:
            relation_counts[edge["relation"]] = relation_counts.get(edge["relation"], 0) + 1
        top_node = max(nodes, key=lambda node: node.get("degree", 0)) if nodes else None
        graph = {
            "report_id": report_id,
            "topic": dataset["topic"],
            "created_at": iso(now()),
            "generator": "graph-agent/1.0",
            "layout": "layered",
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "type_counts": type_counts,
                "relation_counts": relation_counts,
                "source_node_count": len(selected_sources),
                "entity_count": len(entity_nodes),
                "event_count": len(event_nodes),
                "top_node": {
                    "id": top_node["id"],
                    "label": top_node["label"],
                    "degree": top_node["degree"],
                }
                if top_node
                else None,
                "evidence_citation": format_citations(topic_refs),
            },
        }
        return graph

    # ------------------------------------------------------------------ 查询
    def query(
        self,
        graph: dict[str, Any],
        node_type: str | None = None,
        keyword: str | None = None,
        relation: str | None = None,
        source_ref: str | None = None,
        limit: int = 120,
    ) -> dict[str, Any]:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        keyword_norm = (keyword or "").strip().lower()
        source_ref = (source_ref or "").strip().upper() or None
        relation = (relation or "").strip() or None

        node_matched = []
        for node in nodes:
            if node_type and node.get("type") != node_type:
                continue
            if keyword_norm:
                haystack = " ".join(
                    [
                        str(node.get("label", "")),
                        str(node.get("description", "")),
                        str(node.get("id", "")),
                    ]
                ).lower()
                if keyword_norm not in haystack:
                    continue
            if source_ref and source_ref not in node.get("source_refs", []):
                continue
            node_matched.append(node)
        matched_ids = {node["id"] for node in node_matched}

        edge_matched = []
        for edge in edges:
            if relation and relation not in (edge.get("relation"), edge.get("label")):
                continue
            if source_ref and source_ref not in edge.get("source_refs", []):
                continue
            edge_matched.append(edge)

        if relation or source_ref:
            if node_type or keyword:
                allowed = matched_ids
            else:
                allowed = {
                    endpoint
                    for edge in edge_matched
                    for endpoint in (edge["source"], edge["target"])
                } | matched_ids
            matched_ids = matched_ids & allowed if (node_type or keyword) else allowed
            edge_matched = [
                edge
                for edge in edge_matched
                if edge["source"] in matched_ids and edge["target"] in matched_ids
            ]
        else:
            edge_matched = [
                edge
                for edge in edge_matched
                if edge["source"] in matched_ids and edge["target"] in matched_ids
            ]

        ordered_nodes = sorted(
            [node for node in nodes if node["id"] in matched_ids],
            key=lambda node: node.get("degree", 0),
            reverse=True,
        )[: max(1, limit)]
        allowed_ids = {node["id"] for node in ordered_nodes}
        ordered_edges = [
            edge
            for edge in edge_matched
            if edge["source"] in allowed_ids and edge["target"] in allowed_ids
        ]
        return {
            "report_id": graph.get("report_id"),
            "topic": graph.get("topic"),
            "query": {
                "node_type": node_type or "",
                "keyword": keyword or "",
                "relation": relation or "",
                "source_ref": source_ref or "",
            },
            "nodes": ordered_nodes,
            "edges": ordered_edges,
            "stats": {
                "node_count": len(ordered_nodes),
                "edge_count": len(ordered_edges),
                "total_node_count": len(nodes),
                "total_edge_count": len(edges),
                "matched": bool(ordered_nodes or ordered_edges),
            },
        }
