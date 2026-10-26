"""舆情分析平台接口测试（TestClient，临时目录隔离）。"""
from __future__ import annotations

import json
import sys
import time
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import APP_NAMES, PROJECT_ROOT as CODE_ROOT  # noqa: E402
from app.main import create_app  # noqa: E402

REQUIRED_APPS = ["topic_search", "multimedia_search", "insight_analysis", "report_writer"]
SEARCH_SECTIONS = [
    "event_overview",
    "timeline",
    "channels",
    "opinions",
    "sentiment",
    "risks",
    "evidence",
    "conclusion",
]


@pytest.fixture()
def app_client(tmp_path: Path):
    application = create_app(tmp_path)
    with TestClient(application) as client:
        yield application, client, tmp_path


def start_required(client: TestClient) -> None:
    for app_name in REQUIRED_APPS:
        response = client.get(f"/api/start/{app_name}?wait=1")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "running"


def run_main_search(client: TestClient) -> dict:
    start_required(client)
    response = client.post("/api/search", json={"query": "预制菜进校园"})
    assert response.status_code == 200, response.text
    return response.json()


# ------------------------------------------------------------------ 健康/状态
def test_health_ok(app_client):
    _, client, _ = app_client
    data = client.get("/api/health").json()
    assert data["status"] == "ok"
    assert data["system_status"] == "online"
    assert data["version"] == "1.0.0"


def test_status_contains_apps_and_resources(app_client):
    _, client, _ = app_client
    data = client.get("/api/status").json()
    assert data["ok"] is True
    assert data["system"]["system_status"] == "online"
    assert len(data["apps"]) == 5
    assert [app["app_name"] for app in data["apps"]] == APP_NAMES
    assert all(app["status"] == "stopped" for app in data["apps"])
    assert "cpu_percent" in data["resources"]
    assert data["resources"]["source"] in ("psutil", "fallback")
    assert data["forum"]["status"] in ("idle", "stopped")


# ------------------------------------------------------------------ 应用状态机
def test_app_start_stop_state_machine(app_client):
    _, client, root = app_client
    response = client.get("/api/start/topic_search?wait=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    app = payload["app"]
    transitions = [item["status"] for item in app["transitions"]]
    assert "starting" in transitions and transitions[-1] == "running"

    log_path = root / "runtime/apps/topic_search.log"
    assert log_path.exists()
    assert "starting" in log_path.read_text(encoding="utf-8")

    stopped = client.get("/api/stop/topic_search?wait=1").json()
    assert stopped["status"] == "stopped"
    assert "stopped" in [item["status"] for item in stopped["app"]["transitions"]]
    assert log_path.exists()
    assert "已停止" in log_path.read_text(encoding="utf-8")


def test_start_unknown_app_returns_404(app_client):
    _, client, _ = app_client
    response = client.get("/api/start/not_exists?wait=1")
    assert response.status_code == 404
    assert response.json()["error"]["module_name"] == "process_manager"


def test_disabled_app_cannot_start(app_client):
    _, client, _ = app_client
    config = client.get("/api/config").json()["config"]
    config["apps"]["topic_search"] = False
    saved = client.post("/api/config", json={"config": config})
    assert saved.status_code == 200
    response = client.get("/api/start/topic_search?wait=1")
    assert response.status_code == 409
    assert response.json()["error"]["module_name"] == "topic_search"


def test_output_before_task_is_empty(app_client):
    _, client, _ = app_client
    client.get("/api/start/topic_search?wait=1")
    data = client.get("/api/output/topic_search").json()
    assert data["ok"] is True
    assert data["exists"] is False
    assert data["output_text"] == ""


# ------------------------------------------------------------------ 检索与报告
def test_search_returns_structured_report(app_client):
    _, client, _ = app_client
    data = run_main_search(client)
    assert data["report_id"].startswith("RPT-")
    assert len(data["agent_steps"]) == 5
    assert all(step["status"] == "success" for step in data["agent_steps"])
    report = data["report"]
    for section in SEARCH_SECTIONS:
        assert section in report, section
    assert report["source_count"] == 48
    assert len(report["sources"]) == 48
    assert len(report["evidence"]) == 10
    assert len(report["timeline"]) == 8
    assert sum(report["sentiment"]["counts"].values()) == 48
    assert report["risk_summary"]["level_label"] in ("高", "较高", "中", "低")
    assert report["conclusion"]["confidence"] > 0.5
    assert all(source["ref"].startswith("S") for source in report["sources"])


def test_search_writes_report_graph_and_outputs(app_client):
    _, client, root = app_client
    data = run_main_search(client)
    report_id = data["report_id"]
    report_md = root / "reports" / report_id / "report.md"
    report_json = root / "reports" / report_id / "report.json"
    search_json = root / "reports" / report_id / "search.json"
    graph_json = root / "graphs" / report_id / "graph.json"
    for path in (report_md, report_json, search_json, graph_json):
        assert path.exists(), path
        assert path.stat().st_size > 0
    markdown = report_md.read_text(encoding="utf-8")
    for heading in ("事件概述", "时间线", "传播渠道", "主要观点", "情绪倾向", "风险判断", "重点证据", "结论摘要", "来源清单"):
        assert heading in markdown
    assert "[S01]" in markdown
    assert "附：来源清单" in markdown

    search_meta = json.loads(search_json.read_text(encoding="utf-8"))
    assert search_meta["query"] == "预制菜进校园"
    assert search_meta["executed_at"]
    assert search_meta["source_summary"]["total"] == 48
    assert search_meta["analysis_output"]["sentiment"]["counts"]["negative"] >= 0

    output = (root / "outputs/topic_search/latest.txt").read_text(encoding="utf-8")
    assert "预制菜进校园" in output
    assert (root / "outputs/report_writer/latest.txt").exists()
    assert (root / "outputs/multimedia_search/latest.txt").exists()
    assert (root / "outputs/insight_analysis/latest.txt").exists()


def test_search_second_demo_topic(app_client):
    _, client, _ = app_client
    start_required(client)
    response = client.post("/api/search", json={"query": "新能源车电池召回"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["topic"] == "新能源车电池召回"
    assert data["source_count"] == 36
    assert len(data["report"]["evidence"]) >= 5
    assert len(data["report"]["risks"]) >= 3
    assert data["graph"]["node_count"] >= 15
    assert data["graph"]["edge_count"] >= 20


def test_search_filters_source_types(app_client):
    _, client, _ = app_client
    start_required(client)
    response = client.post(
        "/api/search",
        json={"query": "预制菜进校园", "source_types": ["news", "forum_post"]},
    )
    assert response.status_code == 200, response.text
    report = response.json()["report"]
    assert set(report["source_types"]) == {"news", "forum_post"}
    assert all(source["source_type"] in ("news", "forum_post") for source in report["sources"])
    assert len(report["channels"]) == 2


def test_search_invalid_inputs(app_client):
    _, client, _ = app_client
    start_required(client)
    assert client.post("/api/search", json={"query": ""}).status_code == 400
    assert client.post("/api/search", json={"query": "不存在的主题"}).status_code == 404
    assert (
        client.post(
            "/api/search", json={"query": "预制菜进校园", "source_types": ["unknown"]}
        ).status_code
        == 400
    )


def test_search_blocked_after_manual_stop(app_client):
    _, client, _ = app_client
    start_required(client)
    client.get("/api/stop/multimedia_search?wait=1")
    response = client.post("/api/search", json={"query": "预制菜进校园"})
    assert response.status_code == 409
    error = response.json()["error"]
    assert "multimedia_search" in json.dumps(error, ensure_ascii=False)


def test_output_and_test_log_after_search(app_client):
    _, client, root = app_client
    run_main_search(client)
    output = client.get("/api/output/topic_search").json()
    assert output["exists"] is True
    assert "主题检索" in output["output_text"]
    assert output["output_path"] == "outputs/topic_search/latest.txt"
    log = client.get("/api/test_log/topic_search?lines=50").json()
    assert log["total_lines"] >= 3
    assert any("检索" in line["message"] for line in log["lines"])
    assert (root / "runtime/apps/insight_analysis.log").exists()


# ------------------------------------------------------------------ 图谱
def test_graph_latest_and_by_report(app_client):
    _, client, _ = app_client
    data = run_main_search(client)
    report_id = data["report_id"]
    latest = client.get("/api/graph/latest").json()
    by_id = client.get(f"/api/graph/{report_id}").json()
    assert latest["report_id"] == report_id
    assert by_id["stats"]["node_count"] == latest["stats"]["node_count"]
    assert by_id["stats"]["node_count"] >= 15
    assert by_id["stats"]["edge_count"] >= 20
    node = by_id["nodes"][0]
    assert {"id", "label", "type", "source_refs"} <= set(node)
    edge = by_id["edges"][0]
    assert {"source", "target", "relation", "label", "source_refs"} <= set(edge)
    types = {node["type"] for node in by_id["nodes"]}
    assert "topic" in types and "source" in types


def test_graph_query_by_node_and_relation(app_client):
    _, client, _ = app_client
    report_id = run_main_search(client)["report_id"]
    response = client.post(
        "/api/graph/query",
        json={"report_id": report_id, "node_type": "org", "keyword": "教育"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["stats"]["matched"] is True
    assert data["nodes"]
    assert all(node["type"] == "org" for node in data["nodes"])
    assert any("教育" in node["label"] for node in data["nodes"])

    relations = client.post(
        "/api/graph/query", json={"report_id": report_id, "relation": "contains"}
    ).json()
    assert relations["edges"]
    assert all(edge["relation"] == "contains" for edge in relations["edges"])

    refs = client.post(
        "/api/graph/query", json={"report_id": report_id, "source_ref": "S01"}
    ).json()
    assert refs["stats"]["matched"] is True


def test_graph_query_invalid_type(app_client):
    _, client, _ = app_client
    report_id = run_main_search(client)["report_id"]
    response = client.post(
        "/api/graph/query", json={"report_id": report_id, "node_type": "unknown"}
    )
    assert response.status_code == 400


def test_graph_viewer_pages(app_client):
    _, client, _ = app_client
    report_id = run_main_search(client)["report_id"]
    for path in ("/graph-viewer", f"/graph-viewer/{report_id}"):
        response = client.get(path)
        assert response.status_code == 200
        assert 'id="view"' in response.text
        assert "/static/js/app.js" in response.text


def test_reports_list_and_markdown_download(app_client):
    _, client, _ = app_client
    report_id = run_main_search(client)["report_id"]
    reports = client.get("/api/reports").json()
    assert reports["total"] >= 1
    assert reports["reports"][0]["has_graph"] is True
    response = client.get(f"/api/report/{report_id}/markdown")
    assert response.status_code == 200
    assert response.text.lstrip("\ufeff").startswith("# 舆情分析报告")
    assert "attachment" in response.headers["content-disposition"]


# ------------------------------------------------------------------ 论坛
def test_forum_start_log_stop(app_client):
    _, client, root = app_client
    started = client.get("/api/forum/start")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "running"

    log = client.get("/api/forum/log?limit=50").json()
    assert log["status"] == "running"
    assert len(log["records"]) >= 4
    record = log["records"][0]
    assert {"time", "event_type", "message", "task_status"} <= set(record)
    assert (root / "runtime/forum/latest.log").exists()

    count_before = len(log["records"])
    stopped = client.get("/api/forum/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    after_stop = client.get("/api/forum/log?limit=50").json()
    assert after_stop["status"] == "stopped"
    assert len(after_stop["records"]) >= count_before
    assert after_stop["records"][-1]["event_type"] == "task_stop"
    stable_count = len(after_stop["records"])
    time.sleep(0.5)
    after = client.get("/api/forum/log?limit=50").json()
    assert after["status"] == "stopped"
    assert len(after["records"]) == stable_count


def test_forum_history_by_date(app_client):
    _, client, root = app_client
    client.get("/api/forum/start")
    today = date.today().isoformat()
    response = client.post("/api/forum/log/history", json={"date": today})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["date"] == today
    assert data["count"] >= 4
    assert data["exists"] is True
    history_path = root / "runtime/forum/history" / f"{today}.json"
    assert history_path.exists()
    assert len(json.loads(history_path.read_text(encoding="utf-8"))) >= 4

    invalid = client.post("/api/forum/log/history", json={"date": "2026/10/24"})
    assert invalid.status_code == 400


# ------------------------------------------------------------------ 配置
def test_config_read_update_and_persist(app_client):
    _, client, root = app_client
    original = client.get("/api/config").json()
    assert original["config"]["runtime"]["poll_interval_ms"] == 3000
    response = client.post(
        "/api/config",
        json={"config": {"runtime": {"poll_interval_ms": 3500}}},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ok"] is True
    assert "runtime.poll_interval_ms" in data["changed_keys"]
    assert data["config"]["runtime"]["poll_interval_ms"] == 3500
    on_disk = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert on_disk["runtime"]["poll_interval_ms"] == 3500
    assert client.get("/api/config").json()["config"]["runtime"]["poll_interval_ms"] == 3500


def test_config_invalid_value_rejected(app_client):
    _, client, root = app_client
    before = json.loads((root / "config.json").read_text(encoding="utf-8"))
    response = client.post("/api/config", json={"config": {"system": {"port": 99999}}})
    assert response.status_code == 400
    after = json.loads((root / "config.json").read_text(encoding="utf-8"))
    assert after["system"]["port"] == before["system"]["port"]


def test_config_app_switch_stops_running_app(app_client):
    _, client, _ = app_client
    client.get("/api/start/topic_search?wait=1")
    response = client.post("/api/config", json={"config": {"apps": {"topic_search": False}}})
    assert response.status_code == 200
    apps = client.get("/api/status").json()["apps"]
    topic = next(app for app in apps if app["app_name"] == "topic_search")
    assert topic["status"] == "stopped"
    assert topic["enabled"] is False


# ------------------------------------------------------------------ 系统
def test_system_shutdown_and_start(app_client):
    _, client, _ = app_client
    client.get("/api/start/topic_search?wait=1")
    shutdown = client.post("/api/system/shutdown")
    assert shutdown.status_code == 200
    assert shutdown.json()["system_status"] == "offline"
    status = client.get("/api/system/status").json()
    assert status["system"]["system_status"] == "offline"
    assert all(app["status"] == "stopped" for app in status["apps"])
    assert client.get("/api/start/topic_search?wait=1").status_code == 409

    started = client.post("/api/system/start")
    assert started.status_code == 200
    assert started.json()["system_status"] == "online"
    assert client.get("/api/start/topic_search?wait=1").status_code == 200


def test_system_status_includes_logs_and_resources(app_client):
    _, client, _ = app_client
    data = client.get("/api/system/status").json()
    assert data["ok"] is True
    assert "logs" in data
    assert data["log_path"] == "runtime/system.log"
    assert "memory_percent" in data["resources"]


# ------------------------------------------------------------------ 页面/WS
def test_docs_page(app_client):
    _, client, _ = app_client
    response = client.get("/docs")
    assert response.status_code == 200
    assert "接口文档" in response.text
    assert "/api/search" in response.text


def test_websocket_pushes_app_status(app_client):
    _, client, _ = app_client
    with client.websocket_connect("/api/ws") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert hello["system_status"] == "online"
        response = client.get("/api/start/topic_search?wait=1")
        assert response.status_code == 200
        statuses = []
        for _ in range(8):
            event = websocket.receive_json()
            if event.get("type") == "app_status":
                statuses.append(event)
                if event.get("status") == "running":
                    break
        assert any(event["status"] == "running" for event in statuses)
        assert all(event["app_name"] == "topic_search" for event in statuses)
