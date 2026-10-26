"""离线接口文档页（/docs）。不依赖任何 CDN，确保无网络环境可正常展示。"""
from __future__ import annotations

import html
from typing import Any

BASE_STYLE = """
:root {
  --bg: #f4f7fb; --panel: #ffffff; --ink: #172033; --muted: #667085;
  --line: #e4eaf2; --brand: #2563eb; --brand-soft: #e8f0ff; --dark: #0f172a;
  --green: #0f9d76; --green-soft: #e6f7f1; --amber: #b7791f;
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; }
body {
  background: var(--bg); color: var(--ink); font-family: "Microsoft YaHei", "PingFang SC",
  "Segoe UI", "Helvetica Neue", Arial, sans-serif; font-size: 13.5px; line-height: 1.6;
}
a { color: var(--brand); text-decoration: none; }
code, pre { font-family: Consolas, "Cascadia Mono", Menlo, monospace; }
.sidebar {
  position: fixed; inset: 0 auto 0 0; width: 248px; background: linear-gradient(180deg,#0b1424,#111f36 55%,#0b1424);
  color: #cbd5e1; padding: 22px 18px; display: flex; flex-direction: column; gap: 18px;
}
.brand { display:flex; gap: 11px; align-items:center; padding-bottom: 16px; border-bottom: 1px solid rgba(148,163,184,.18); }
.brand .logo { width: 38px; height: 38px; border-radius: 11px; background: linear-gradient(135deg,#3b82f6,#22d3ee); display:flex; align-items:center; justify-content:center; }
.brand .logo svg { width: 22px; height: 22px; }
.brand h1 { font-size: 15px; color: #f8fafc; margin: 0; letter-spacing: .5px; }
.brand p { margin: 2px 0 0; font-size: 10.5px; color: #7c8ba1; letter-spacing: 1.2px; }
.side-label { font-size: 10.5px; color: #64748b; letter-spacing: 1.5px; margin: 4px 0 -6px 8px; }
.nav { display: flex; flex-direction: column; gap: 2px; }
.nav a { color: #aebcd2; padding: 8px 10px; border-radius: 8px; font-size: 12.5px; display:flex; gap: 9px; align-items:center; }
.nav a:hover { background: rgba(59,130,246,.12); color: #e2e8f0; }
.nav a .dot { width: 5px; height: 5px; border-radius: 50%; background: #3b82f6; opacity: .8; }
.side-foot { margin-top: auto; font-size: 11px; color: #64748b; border-top: 1px solid rgba(148,163,184,.16); padding-top: 14px; }
.side-foot code { color: #93c5fd; font-size: 10.5px; }
.main { margin-left: 248px; padding: 30px 38px 70px; max-width: 1280px; }
.page-head { display:flex; justify-content:space-between; align-items:flex-start; gap: 20px; margin-bottom: 20px; }
.eyebrow { font-size: 11px; letter-spacing: 2px; color: var(--brand); font-weight: 700; text-transform: uppercase; }
h1.title { font-size: 29px; margin: 4px 0 6px; letter-spacing: -0.4px; }
.subtitle { color: var(--muted); margin: 0; max-width: 720px; font-size: 13px; }
.head-meta { display:flex; gap: 8px; flex-wrap: wrap; justify-content:flex-end; max-width: 340px; }
.pill { border: 1px solid var(--line); background: #fff; border-radius: 999px; padding: 5px 12px; font-size: 11.5px; color: #475467; white-space: nowrap; }
.pill.blue { background: var(--brand-soft); border-color: #cfe0ff; color: #1d4ed8; }
.pill.green { background: var(--green-soft); border-color: #c7ecdf; color: #0b7a5b; }
.cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin: 20px 0 26px; }
.stat { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 14px 16px; box-shadow: 0 1px 2px rgba(16,24,40,.03); }
.stat .k { color: var(--muted); font-size: 11.5px; }
.stat .v { font-size: 23px; font-weight: 700; margin-top: 3px; letter-spacing: -0.5px; }
.stat .v small { font-size: 11px; color: var(--muted); font-weight: 400; margin-left: 4px; }
.section { margin-bottom: 26px; scroll-margin-top: 20px; }
.section-head { display:flex; align-items: baseline; gap: 10px; margin-bottom: 10px; }
.section-head h2 { font-size: 17px; margin: 0; }
.section-head .count { color: #98a2b3; font-size: 11.5px; }
.section-head .hint { margin-left: auto; color: var(--muted); font-size: 11.5px; }
.endpoint { background: var(--panel); border: 1px solid var(--line); border-radius: 11px; margin-bottom: 9px; overflow: hidden; }
.endpoint summary { list-style: none; cursor: pointer; display: flex; align-items: center; gap: 12px; padding: 11px 15px; }
.endpoint summary::-webkit-details-marker { display: none; }
.method { font-size: 10.5px; font-weight: 800; letter-spacing: .6px; padding: 4px 8px; border-radius: 6px; min-width: 52px; text-align:center; }
.method.get { background: #e8f0ff; color: #1d4ed8; }
.method.post { background: #e6f7f1; color: #0b7a5b; }
.method.ws { background: #f3e8ff; color: #7e22ce; }
.path { font-family: Consolas, monospace; font-size: 12.5px; color: #101828; font-weight: 600; }
.desc { color: var(--muted); font-size: 12px; margin-left: auto; text-align: right; max-width: 46%; }
.chev { color: #98a2b3; font-size: 11px; }
.endpoint[open] summary { border-bottom: 1px solid #eef2f7; background: #fbfcfe; }
.endpoint-body { padding: 12px 15px 14px; display: grid; grid-template-columns: 1.1fr 1fr; gap: 16px; }
.endpoint-body h4 { font-size: 11px; color: #667085; letter-spacing: .8px; margin: 0 0 5px; font-weight: 700; }
.endpoint-body p { margin: 0 0 6px; font-size: 12px; color: #475467; }
.param { font-family: Consolas, monospace; font-size: 11.5px; color: #344054; }
.param b { color: #1d4ed8; font-weight: 600; }
pre.sample { margin: 0; background: #0f172a; color: #cbd5e1; border-radius: 8px; padding: 10px 12px; font-size: 11px; line-height: 1.55; overflow: auto; max-height: 190px; }
.ws-table, .layout-table { width: 100%; border-collapse: collapse; background: #fff; border: 1px solid var(--line); border-radius: 11px; overflow: hidden; font-size: 12px; }
.ws-table th, .layout-table th { text-align: left; background: #f8fafc; color: #667085; font-weight: 600; padding: 9px 12px; border-bottom: 1px solid var(--line); font-size: 11px; letter-spacing: .4px; }
.ws-table td, .layout-table td { padding: 9px 12px; border-bottom: 1px solid #eef2f7; vertical-align: top; }
.ws-table tr:last-child td, .layout-table tr:last-child td { border-bottom: 0; }
.ws-table code, .layout-table code { font-size: 11px; color: #1d4ed8; }
.tree { background: #0f172a; color: #cbd5e1; border-radius: 11px; padding: 15px 18px; font-size: 11.8px; line-height: 1.8; overflow: auto; }
.tree .c { color: #64748b; }
.quick { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.quick .box { background: #fff; border: 1px solid var(--line); border-radius: 11px; padding: 13px 15px; }
.quick h4 { margin: 0 0 7px; font-size: 12px; }
.quick pre { margin: 0; background: #f8fafc; border: 1px solid #eef2f7; border-radius: 7px; padding: 9px 11px; font-size: 11px; color: #344054; overflow:auto; }
.note { background: #fffbeb; border: 1px solid #fdecc8; color: #7c5a12; border-radius: 9px; padding: 9px 13px; font-size: 11.8px; margin-top: 10px; }
.footer { margin-top: 34px; color: #98a2b3; font-size: 11px; border-top: 1px solid var(--line); padding-top: 14px; }
@media (max-width: 1100px) { .cards { grid-template-columns: repeat(2, 1fr); } .endpoint-body { grid-template-columns: 1fr; } }
"""

ENDPOINTS: list[dict[str, Any]] = [
    {
        "group": "控制台与状态",
        "id": "console",
        "hint": "应用启停 / 状态查询 / 输出与日志",
        "items": [
            {
                "method": "GET",
                "path": "/api/health",
                "desc": "健康检查，截图与探活脚本使用",
                "params": "无",
                "response": '{\n  "status": "ok",\n  "system_status": "online",\n  "running_apps": 5,\n  "version": "1.0.0",\n  "ws_clients": 1\n}',
            },
            {
                "method": "GET",
                "path": "/api/status",
                "desc": "控制台状态：系统、5 个应用、资源、论坛、报告",
                "params": "无",
                "response": '{\n  "ok": true,\n  "system": { "system_status": "online", "running_apps": 5 },\n  "apps": [{ "app_name": "topic_search", "status": "running" }],\n  "resources": { "cpu_percent": 18.4, "memory_percent": 56.2 }\n}',
            },
            {
                "method": "GET",
                "path": "/api/start/{app_name}",
                "desc": "启动单功能应用（stopped → starting → running）",
                "params": "app_name：topic_search / multimedia_search / insight_analysis / forum_collector / report_writer；wait=1 等待状态稳定",
                "response": '{\n  "ok": true,\n  "app_name": "topic_search",\n  "status": "running",\n  "message": "应用「主题检索」运行中"\n}',
            },
            {
                "method": "GET",
                "path": "/api/stop/{app_name}",
                "desc": "停止单功能应用，保留输出与日志",
                "params": "app_name：同上；wait=1",
                "response": '{\n  "ok": true,\n  "app_name": "topic_search",\n  "status": "stopped"\n}',
            },
            {
                "method": "GET",
                "path": "/api/output/{app_name}",
                "desc": "最近一次文本输出（outputs/{app}/latest.txt）",
                "params": "app_name",
                "response": '{\n  "ok": true,\n  "output_text": "主题检索 · 最近一次输出...",\n  "output_path": "outputs/topic_search/latest.txt",\n  "updated_at": "2026-10-24T15:44:02+08:00"\n}',
            },
            {
                "method": "GET",
                "path": "/api/test_log/{app_name}",
                "desc": "应用测试日志尾部，标准输出与错误输出分离标记",
                "params": "app_name；lines=200",
                "response": '{\n  "ok": true,\n  "total_lines": 26,\n  "lines": [{ "time": "2026-10-24 15:44:02.118", "level": "INFO", "stream": "stdout", "message": "..." }]\n}',
            },
        ],
    },
    {
        "group": "检索与分析",
        "id": "search",
        "hint": "Agent 流水线入口",
        "items": [
            {
                "method": "POST",
                "path": "/api/search",
                "desc": "发起主题检索，执行 5 段 Agent 流水线并返回 8 部分报告",
                "params": 'query（必填）、source_types（数组，5 类来源）、max_sources、auto_start',
                "response": '{\n  "ok": true,\n  "report_id": "RPT-20261024-154402-7F3A",\n  "agent_steps": [{ "title": "多来源检索", "duration_ms": 3.4, "status": "success" }],\n  "report": { "event_overview": {}, "timeline": [], "channels": [], "opinions": [],\n              "sentiment": {}, "risks": [], "evidence": [], "conclusion": {} },\n  "graph": { "node_count": 49, "edge_count": 92 },\n  "paths": { "report_md": "reports/RPT-.../report.md", "graph_json": "graphs/RPT-.../graph.json" }\n}',
            },
            {
                "method": "GET",
                "path": "/api/reports",
                "desc": "报告列表（辅助），用于图谱报告选择器",
                "params": "无",
                "response": '{\n  "ok": true,\n  "total": 1,\n  "reports": [{ "report_id": "RPT-...", "topic": "预制菜进校园", "has_graph": true }]\n}',
            },
            {
                "method": "GET",
                "path": "/api/report/{report_id}",
                "desc": "报告详情 + Markdown 原文（辅助）",
                "params": "report_id",
                "response": '{\n  "ok": true,\n  "report": { "report_id": "RPT-..." },\n  "markdown": "# 舆情分析报告：预制菜进校园..."\n}',
            },
            {
                "method": "GET",
                "path": "/api/topics",
                "desc": "样例主题目录与 demo 主题（辅助）",
                "params": "无",
                "response": '{\n  "ok": true,\n  "topics": [{ "topic": "预制菜进校园", "source_count": 48 }],\n  "demo_query": "预制菜进校园"\n}',
            },
        ],
    },
    {
        "group": "论坛采集",
        "id": "forum",
        "hint": "实时日志与历史归档",
        "items": [
            {
                "method": "GET",
                "path": "/api/forum/start",
                "desc": "启动论坛采集，后台线程每 1.5-3 秒追加日志",
                "params": "无",
                "response": '{\n  "ok": true,\n  "status": "running",\n  "forum": { "today_count": 12, "interval": [1.5, 3.0] }\n}',
            },
            {
                "method": "GET",
                "path": "/api/forum/stop",
                "desc": "停止论坛采集，停止后不再追加日志",
                "params": "无",
                "response": '{\n  "ok": true,\n  "status": "stopped",\n  "message": "论坛采集已停止"\n}',
            },
            {
                "method": "GET",
                "path": "/api/forum/log",
                "desc": "查询最新论坛日志（JSON 记录含 time/event_type/message/task_status）",
                "params": "limit=80",
                "response": '{\n  "ok": true,\n  "status": "running",\n  "records": [{ "time": "...", "event_type": "collect_post",\n                "message": "抓取到新帖...", "task_status": "running" }]\n}',
            },
            {
                "method": "POST",
                "path": "/api/forum/log/history",
                "desc": "按日期查询历史论坛日志",
                "params": '{ "date": "2026-10-24" }',
                "response": '{\n  "ok": true,\n  "date": "2026-10-24",\n  "count": 42,\n  "records": [],\n  "path": "runtime/forum/history/2026-10-24.json"\n}',
            },
        ],
    },
    {
        "group": "配置与系统",
        "id": "system",
        "hint": "配置热更新 / 整体服务启停",
        "items": [
            {
                "method": "GET",
                "path": "/api/config",
                "desc": "读取 config.json 与表单 Schema",
                "params": "无",
                "response": '{\n  "ok": true,\n  "config": { "system": {}, "collection": {}, "runtime": {}, "apps": {} },\n  "updated_at": "2026-10-24T15:40:00+08:00"\n}',
            },
            {
                "method": "POST",
                "path": "/api/config",
                "desc": "保存配置并触发热更新（应用开关立即生效）",
                "params": '完整配置对象，或 { "config": { ... } }',
                "response": '{\n  "ok": true,\n  "message": "配置已保存并热更新生效",\n  "changed_keys": ["runtime.poll_interval_ms"],\n  "config": {}\n}',
            },
            {
                "method": "GET",
                "path": "/api/system/status",
                "desc": "整体服务状态、资源、最近错误与系统日志",
                "params": "无",
                "response": '{\n  "ok": true,\n  "system": { "system_status": "online", "uptime_text": "1分20秒" },\n  "logs": ["2026-10-24 ... [INFO] [system] ..."]\n}',
            },
            {
                "method": "POST",
                "path": "/api/system/start",
                "desc": "启动整体服务（offline → starting → online）",
                "params": "无",
                "response": '{ "ok": true, "system_status": "online" }',
            },
            {
                "method": "POST",
                "path": "/api/system/shutdown",
                "desc": "关闭整体服务，停止全部应用与论坛采集",
                "params": "无",
                "response": '{ "ok": true, "system_status": "offline" }',
            },
            {
                "method": "GET",
                "path": "/api/system/logs",
                "desc": "系统日志或指定应用日志尾部（辅助）",
                "params": "app_name?；lines=120",
                "response": '{ "ok": true, "source": "system", "lines": [] }',
            },
        ],
    },
    {
        "group": "图谱与页面",
        "id": "graph",
        "hint": "图谱回查 / 条件查询 / 页面路由",
        "items": [
            {
                "method": "GET",
                "path": "/api/graph/latest",
                "desc": "查询最新图谱（节点 + 边 + 统计）",
                "params": "无",
                "response": '{\n  "ok": true,\n  "report_id": "RPT-...",\n  "nodes": [{ "id": "TOPIC", "type": "topic", "source_refs": ["S01"] }],\n  "edges": [{ "source": "TOPIC", "target": "E01", "relation": "contains" }]\n}',
            },
            {
                "method": "GET",
                "path": "/api/graph/{report_id}",
                "desc": "按报告编号回查图谱",
                "params": "report_id",
                "response": '{ "ok": true, "report_id": "RPT-...", "nodes": [], "edges": [], "stats": {} }',
            },
            {
                "method": "POST",
                "path": "/api/graph/query",
                "desc": "按节点类型、关键词、关系、来源编号查询",
                "params": '{ "report_id": "RPT-...", "node_type": "org", "keyword": "教育", "relation": "mentions", "source_ref": "S01" }',
                "response": '{\n  "ok": true,\n  "nodes": [],\n  "edges": [],\n  "stats": { "node_count": 6, "edge_count": 9, "matched": true }\n}',
            },
            {
                "method": "GET",
                "path": "/graph-viewer",
                "desc": "图谱查看页（自动加载最新图谱）",
                "params": "无",
                "response": "text/html 单页应用",
            },
            {
                "method": "GET",
                "path": "/graph-viewer/{report_id}",
                "desc": "指定报告图谱查看页",
                "params": "report_id",
                "response": "text/html 单页应用，自动定位报告",
            },
        ],
    },
    {
        "group": "WebSocket 实时消息",
        "id": "ws",
        "hint": "/api/ws",
        "items": [
            {
                "method": "WS",
                "path": "/api/ws",
                "desc": "推送 app_status / app_output / forum_log / system_status / graph_ready / error",
                "params": "连接后先收到 hello 快照，之后按事件推送；20 秒无事件发送 ping",
                "response": '{ "type": "app_status", "app_name": "topic_search", "status": "running" }\n{ "type": "forum_log", "message_text": "...", "task_status": "running" }',
            }
        ],
    },
]


def _endpoint_html(item: dict[str, Any]) -> str:
    method = item["method"].lower()
    method_cls = "ws" if method == "ws" else method
    return f"""
    <details class="endpoint">
      <summary>
        <span class="method {method_cls}">{html.escape(item['method'])}</span>
        <span class="path">{html.escape(item['path'])}</span>
        <span class="desc">{html.escape(item['desc'])}</span>
        <span class="chev">▾</span>
      </summary>
      <div class="endpoint-body">
        <div>
          <h4>请求参数</h4>
          <p class="param">{html.escape(item['params'])}</p>
          <h4>字段说明</h4>
          <p>{html.escape(item['desc'])}。响应统一包含 <code>ok</code> 字段，异常返回 <code>error.module_name</code> 与 <code>error.error_message</code>。</p>
        </div>
        <div>
          <h4>响应示例</h4>
          <pre class="sample">{html.escape(item['response'])}</pre>
        </div>
      </div>
    </details>
    """


def render_docs(base_url: str) -> str:
    sections = []
    total = 0
    for group in ENDPOINTS:
        total += len(group["items"])
        cards = "".join(_endpoint_html(item) for item in group["items"])
        sections.append(
            f"""
            <section class="section" id="{group['id']}">
              <div class="section-head">
                <h2>{html.escape(group['group'])}</h2>
                <span class="count">{len(group['items'])} 个接口</span>
                <span class="hint">{html.escape(group['hint'])}</span>
              </div>
              {cards}
            </section>
            """
        )
    nav_items = "".join(
        f'<a href="#{group["id"]}"><span class="dot"></span>{html.escape(group["group"])}</a>'
        for group in ENDPOINTS
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/static/img/favicon.svg" type="image/svg+xml">
<title>接口文档 · 舆情分析平台</title>
<style>{BASE_STYLE}</style>
</head>
<body>
<aside class="sidebar">
  <div class="brand">
    <div class="logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round">
        <path d="M4 18V9M9.5 18V5M15 18v-6M20.5 18v-9"/>
      </svg>
    </div>
    <div><h1>舆情分析平台</h1><p>PUBLIC OPINION INTELLIGENCE</p></div>
  </div>
  <div class="side-label">接口目录</div>
  <nav class="nav">{nav_items}<a href="#storage"><span class="dot"></span>存储布局</a><a href="#quickstart"><span class="dot"></span>调用示例</a></nav>
  <div class="side-foot">
    <div>服务地址</div>
    <div><code>{html.escape(base_url)}</code></div>
    <div style="margin-top:8px">FastAPI 0.136 · 离线文档</div>
  </div>
</aside>
<main class="main">
  <header class="page-head">
    <div>
      <div class="eyebrow">API DOCUMENTATION</div>
      <h1 class="title">舆情分析平台 · 接口文档</h1>
      <p class="subtitle">控制台、主题检索、论坛采集、报告与图谱服务。共 {total} 个 HTTP / WebSocket 接口，全部接口可在无外网环境运行，接口文档页不依赖 CDN。</p>
    </div>
    <div class="head-meta">
      <span class="pill blue">FastAPI {html.escape("0.136.3")}</span>
      <span class="pill green">Python 3.12</span>
      <span class="pill">端口 8714</span>
      <span class="pill">REST + WebSocket</span>
    </div>
  </header>

  <div class="cards">
    <div class="stat"><div class="k">HTTP 接口</div><div class="v">18<small>核心</small></div></div>
    <div class="stat"><div class="k">实时消息类型</div><div class="v">6<small>WebSocket</small></div></div>
    <div class="stat"><div class="k">单功能应用</div><div class="v">5<small>独立状态机</small></div></div>
    <div class="stat"><div class="k">报告章节</div><div class="v">8<small>结构化输出</small></div></div>
  </div>

  {"".join(sections)}

  <section class="section" id="storage">
    <div class="section-head"><h2>存储布局</h2><span class="hint">相对项目根目录，真实落盘</span></div>
    <pre class="tree">config.json                          <span class="c"># 系统配置 / 采集配置 / 运行参数 / 应用开关</span>
runtime/
  apps/{{app_name}}.log                <span class="c"># 各应用标准输出 + 错误输出</span>
  forum/
    latest.log                       <span class="c"># 论坛采集最新日志（JSON Lines）</span>
    history/{{YYYY-MM-DD}}.json         <span class="c"># 按日期归档的论坛日志</span>
  system.log                         <span class="c"># 系统级日志（启动、配置热更新、错误）</span>
reports/{{report_id}}/
  report.md                          <span class="c"># 8 部分结构化报告 + 来源清单</span>
  report.json                        <span class="c"># 前端渲染用结构化报告</span>
  search.json                        <span class="c"># 主题词、执行时间、来源摘要、分析输出</span>
graphs/{{report_id}}/graph.json        <span class="c"># 节点 + 边 + 统计</span>
outputs/{{app_name}}/latest.txt        <span class="c"># 应用最近一次文本输出</span>
data/*.json                          <span class="c"># 样例来源数据（5 类来源）</span></pre>
  </section>

  <section class="section" id="quickstart">
    <div class="section-head"><h2>调用示例</h2><span class="hint">PowerShell / curl</span></div>
    <div class="quick">
      <div class="box">
        <h4>1. 启动应用并发起检索</h4>
        <pre>Invoke-RestMethod "{html.escape(base_url)}/api/start/topic_search?wait=1"
Invoke-RestMethod -Method Post -Uri "{html.escape(base_url)}/api/search" `
  -ContentType "application/json" `
  -Body '{{"query":"预制菜进校园","source_types":["news","forum_post"]}}'</pre>
      </div>
      <div class="box">
        <h4>2. 打开图谱查看页</h4>
        <pre>{html.escape(base_url)}/graph-viewer
{html.escape(base_url)}/graph-viewer/{{report_id}}
{html.escape(base_url)}/openapi.json</pre>
      </div>
    </div>
    <div class="note">示例数据中的新闻链接、论坛地址与内部系统地址均为演示用虚构地址，不对应真实网页；接口、状态机、落盘文件与报告结论均真实生成。</div>
  </section>

  <div class="footer">舆情分析平台 · 课程项目交付 · 接口文档自动渲染于服务端 · 建议使用 Chrome / Edge 访问</div>
</main>
</body>
</html>
"""
