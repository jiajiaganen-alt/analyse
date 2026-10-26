"""电商风险控制系统 API 自动化测试。

测试使用临时 SQLite 数据库：会话开始时生成一份完整演示数据模板，
每个用例复制模板，保证用例之间互不影响。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import db
from app.errors import AppError
from app.rule_engine import evaluate_condition, validate_condition

BASE_URL = "http://testserver"
HIGH_CHECK = {"event_type": "after_sale_apply", "source_id": "APP", "user_id": "U1001", "order_id": "O1101"}
LOW_CHECK = {"event_type": "order_pay", "source_id": "WEB", "user_id": "U1010", "order_id": "O101001"}


@pytest.fixture(scope="session")
def template_db(tmp_path_factory) -> Path:
    """会话级模板库：完整灌入一次演示数据。"""
    path = tmp_path_factory.mktemp("template") / "template.db"
    db.set_db_path(path)
    db.init_db(seed=True)
    return path


@pytest.fixture()
def client(template_db: Path, tmp_path: Path):
    """函数级隔离库：复制模板后启动 TestClient。"""
    test_db = tmp_path / "test.db"
    shutil.copyfile(template_db, test_db)
    db.set_db_path(test_db)
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def _check(client: TestClient, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行风险检查并断言成功。"""
    response = client.post("/api/risk/check", json=payload or HIGH_CHECK)
    assert response.status_code == 200, response.text
    return response.json()


def _pending_case(client: TestClient) -> dict[str, Any]:
    """获取一个待审核案件。"""
    response = client.get("/api/risk/cases", params={"case_status": "pending", "page_size": 50})
    assert response.status_code == 200
    data = response.json()
    assert data["items"], "演示数据中应存在待审核案件"
    return data["items"][0]


def test_health(client: TestClient) -> None:
    """健康检查与首次启动自动建库。"""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "ready"
    assert data["counts"]["users"] == 30
    assert data["counts"]["orders"] == 60
    assert data["counts"]["rules"] == 30
    assert data["counts"]["events"] == 40
    assert data["counts"]["cases"] == 12
    assert data["counts"]["blacklists"] == 8


def test_rules_catalog(client: TestClient) -> None:
    """规则不少于 24 条且字段、条件 AST 完整。"""
    data = client.get("/api/risk/rules").json()
    assert data["total"] >= 24
    assert data["total"] == 30
    assert data["enabled_count"] == 28
    required = {"id", "rule_code", "rule_name", "rule_status", "priority", "score", "condition_json", "description", "updated_at"}
    for item in data["items"]:
        assert required.issubset(item.keys())
        assert item["rule_code"].startswith("R")
        assert 1 <= item["priority"] <= 10
        assert 0 <= item["score"] <= 100
        condition = json.loads(item["condition_json"])
        validate_condition(condition)
    assert len({item["rule_code"] for item in data["items"]}) == 30


def test_feature_catalog(client: TestClient) -> None:
    """特征定义不少于 25 项，覆盖用户、订单、地址维度。"""
    data = client.get("/api/risk/features").json()
    assert data["total"] >= 25
    assert len(data["items"]) == data["total"]
    groups = {item["group"] for item in data["items"]}
    assert {"user", "order", "address", "blacklist", "event"}.issubset(groups)
    keys = [item["key"] for item in data["items"]]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    "event_type",
    ["order_create", "order_pay", "after_sale_apply", "logistics_complaint"],
)
def test_four_event_types(client: TestClient, event_type: str) -> None:
    """四类业务事件均可发起检查。"""
    payload = dict(HIGH_CHECK, event_type=event_type)
    data = _check(client, payload)
    assert data["event_type"] == event_type
    assert data["event_label"]
    assert data["assessment_status"] == "completed"


def test_high_risk_result(client: TestClient) -> None:
    """主演示用户产生高风险结果、>=4 条命中规则与自动案件。"""
    data = _check(client)
    assert data["risk_score"] >= 80
    assert data["risk_level"] == "high"
    assert data["decision"] in {"manual_review", "reject"}
    assert len(data["rule_hits"]) >= 4
    for hit in data["rule_hits"]:
        assert hit["rule_name"] and hit["hit_message"] and hit["hit_score"] > 0
    assert data["blacklist_hits"], "主演示用户应命中黑名单"
    assert data["case_id"] is not None
    assert data["case_no"] == f"CASE-{data['case_id']:06d}"
    assert len(data["trace"]) == 6
    assert [item["name"] for item in data["trace"]] == ["事件校验", "特征计算", "规则匹配", "评分决策", "黑名单校验", "案件生成"]


def test_low_risk_result(client: TestClient) -> None:
    """正常用户低风险放行，不创建案件。"""
    data = _check(client, LOW_CHECK)
    assert data["risk_score"] < 30
    assert data["risk_level"] == "low"
    assert data["decision"] == "pass"
    assert data["case_id"] is None
    assert data["rule_hits"] == []
    assert data["blacklist_hits"] == []


def test_feature_snapshot_persistence(client: TestClient) -> None:
    """特征快照、命中规则与 Agent 轨迹完整落库并可回查。"""
    checked = _check(client)
    assessment_id = checked["assessment_id"]
    detail = client.get(f"/api/risk/assessments/{assessment_id}").json()
    assert detail["risk_score"] == checked["risk_score"]
    assert detail["risk_level"] == checked["risk_level"]
    assert detail["decision"] == checked["decision"]
    assert len(detail["feature_snapshot"]) == 39
    assert detail["feature_snapshot"]["user_register_days"] == 12
    assert detail["feature_snapshot"]["blacklist_hit_cnt"] == 2
    assert "DEV-7788" in detail["feature_snapshot"]["blacklist_hit_detail"]
    assert len(detail["rule_hits"]) == len(checked["rule_hits"])
    assert len(detail["trace"]) == 6
    assert detail["case_id"] == checked["case_id"]

    with db.get_conn() as conn:
        snapshot = db.query_one(conn, "SELECT * FROM feature_snapshots WHERE assessment_id = ?", (assessment_id,))
        event = db.query_one(conn, "SELECT * FROM risk_events WHERE id = ?", (detail["event_id"],))
        hits = db.query_one(conn, "SELECT COUNT(*) AS c FROM rule_hits WHERE assessment_id = ?", (assessment_id,))
        trace = db.query_one(conn, "SELECT * FROM assessment_traces WHERE assessment_id = ?", (assessment_id,))
    assert snapshot is not None
    assert len(json.loads(snapshot["feature_json"])) == 39
    assert json.loads(event["event_payload_json"])["user_id"] == "U1001"
    assert hits["c"] == len(checked["rule_hits"])
    assert len(json.loads(trace["trace_json"])) == 6


def test_single_case_per_assessment(client: TestClient) -> None:
    """一次评估只自动创建一个案件。"""
    checked = _check(client)
    with db.get_conn() as conn:
        count = db.query_one(conn, "SELECT COUNT(*) AS c FROM risk_cases WHERE assessment_id = ?", (checked["assessment_id"],))
    assert count["c"] == 1
    detail = client.get(f"/api/risk/cases/{checked['case_id']}").json()
    assert detail["assessment"]["assessment_id"] == checked["assessment_id"]
    assert detail["case_status"] == "pending"


def test_case_list_and_detail(client: TestClient) -> None:
    """案件列表字段、状态筛选与详情结构。"""
    listing = client.get("/api/risk/cases", params={"page_size": 50}).json()
    assert listing["total"] == 12
    assert listing["status_stats"]["pending"] == 2
    assert listing["status_stats"]["reviewing"] == 2
    assert listing["status_stats"]["approved"] == 4
    required = {"case_id", "case_no", "user_id", "order_id", "risk_level", "case_status", "reviewer_id", "created_at"}
    for item in listing["items"]:
        assert required.issubset(item.keys())

    filtered = client.get("/api/risk/cases", params={"case_status": "pending"}).json()
    assert filtered["total"] == 2
    assert all(item["case_status"] == "pending" for item in filtered["items"])

    case = _pending_case(client)
    detail = client.get(f"/api/risk/cases/{case['case_id']}").json()
    assert detail["assessment"]["risk_level"] in {"medium", "high"}
    assert detail["rule_hits"]
    assert detail["feature_snapshot"]
    assert detail["review_logs"]
    logs = client.get(f"/api/risk/cases/{case['case_id']}/logs").json()
    assert logs["total"] == len(detail["review_logs"])


def test_case_review_flow(client: TestClient) -> None:
    """案件审核流转、审核人/备注/时间与审核日志。"""
    case = _pending_case(client)
    response = client.post(
        "/api/risk/cases/review",
        json={
            "case_id": case["case_id"],
            "review_result": "approved",
            "review_remark": "已电话核实为本人操作，同意放行。",
            "reviewer_id": "RV001",
        },
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["case_status"] == "approved"
    assert detail["case_status_label"] == "已通过"
    assert detail["reviewer_id"] == "RV001"
    assert detail["reviewer_name"] == "张审核"
    assert detail["review_remark"] == "已电话核实为本人操作，同意放行。"
    assert detail["reviewed_at"]

    logs = client.get(f"/api/risk/cases/{case['case_id']}/logs").json()
    assert logs["items"][-1]["action_type"] == "approved"
    assert logs["items"][-1]["operator_name"] == "张审核"
    assert any(item["action_type"] == "create_case" for item in logs["items"])

    repeat = client.post(
        "/api/risk/cases/review",
        json={"case_id": case["case_id"], "review_result": "rejected", "review_remark": "重复提交"},
    )
    assert repeat.status_code == 400

    invalid = client.post(
        "/api/risk/cases/review",
        json={"case_id": case["case_id"], "review_result": "unknown", "review_remark": "非法结论"},
    )
    assert invalid.status_code == 400


def test_blacklist_crud_and_hit(client: TestClient) -> None:
    """黑名单新增后在风险检查中生效，删除后失效。"""
    before = _check(client, LOW_CHECK)
    assert before["risk_score"] == 0

    created = client.post(
        "/api/risk/blacklists",
        json={"blacklist_type": "user", "blacklist_value": "U1010", "remark": "测试拉黑", "status": "active"},
    )
    assert created.status_code == 200, created.text
    blacklist_id = created.json()["id"]

    after = _check(client, LOW_CHECK)
    assert after["risk_score"] > before["risk_score"]
    assert after["feature_snapshot"]["user_blacklist_hit"] == 1
    assert after["feature_snapshot"]["blacklist_hit_cnt"] == 1
    assert any(item["rule_code"] == "R011" for item in after["rule_hits"])
    assert any(item["blacklist_value"] == "U1010" for item in after["blacklist_hits"])

    deleted = client.post("/api/risk/blacklists/delete", json={"id": blacklist_id})
    assert deleted.status_code == 200
    assert deleted.json()["deleted_count"] == 1

    restored = _check(client, LOW_CHECK)
    assert restored["feature_snapshot"]["user_blacklist_hit"] == 0
    assert restored["feature_snapshot"]["blacklist_hit_cnt"] == 0
    assert all(item["blacklist_value"] != "U1010" for item in restored["blacklist_hits"])


def test_blacklist_import(client: TestClient) -> None:
    """批量导入黑名单并返回失败明细。"""
    response = client.post(
        "/api/risk/blacklists/import",
        json={
            "items": [
                {"blacklist_type": "phone", "blacklist_value": "13600001111", "remark": "导入测试一"},
                {"blacklist_type": "device", "blacklist_value": "DEV-IMPORT-01", "remark": "导入测试二"},
                {"blacklist_type": "ip", "blacklist_value": "not@ip", "remark": "非法 IP"},
            ]
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["success_count"] == 2
    assert result["failed_count"] == 1
    listing = client.get("/api/risk/blacklists", params={"keyword": "导入测试"}).json()
    assert listing["filtered_total"] == 2
    ids = [item["id"] for item in listing["items"]]
    removed = client.post("/api/risk/blacklists/delete", json={"ids": ids}).json()
    assert removed["deleted_count"] == 2


def test_blacklist_filters(client: TestClient) -> None:
    """黑名单类型筛选与统计。"""
    data = client.get("/api/risk/blacklists", params={"blacklist_type": "device"}).json()
    assert data["total"] == 8
    assert data["filtered_total"] == 2
    assert all(item["blacklist_type"] == "device" for item in data["items"])
    assert data["type_stats"]["device"] == 2
    assert data["type_stats"]["ip"] == 1
    assert data["type_stats"]["user"] == 1


def test_user_profile(client: TestClient) -> None:
    """用户画像聚合订单、退款、投诉、地址、设备、事件与案件。"""
    data = client.get("/api/risk/users/U1001/profile").json()
    assert data["user"]["user_id"] == "U1001"
    assert data["user"]["blacklisted"] is False
    assert data["stats"]["order_count"] == 7
    assert data["stats"]["refund_count"] == 4
    assert data["stats"]["complaint_count"] == 3
    assert data["stats"]["address_count"] == 3
    assert data["stats"]["device_count"] == 3
    assert data["stats"]["login_city_count"] == 3
    assert data["stats"]["high_risk_count"] == 3
    assert len(data["recent_events"]) == 3
    assert len(data["cases"]) == 3
    assert len(data["risk_trend"]) == 3
    assert len(data["addresses"]) == 3


def test_dashboard(client: TestClient) -> None:
    """运营看板核心指标、趋势与排行。"""
    data = client.get("/api/risk/dashboard").json()
    kpi = data["kpi"]
    assert kpi["event_total"] == 40
    assert kpi["high_risk_count"] == 8
    assert kpi["high_risk_ratio"] == 20.0
    assert kpi["case_total"] == 12
    assert kpi["pending_case_count"] == 4
    assert kpi["rule_hit_total"] > 0
    assert kpi["blacklist_hit_total"] == 13
    assert data["level_distribution"] == {"low": 28, "medium": 4, "high": 8}
    assert sum(data["level_distribution"].values()) == 40
    assert len(data["trend_7d"]) == 7
    assert sum(item["event_count"] for item in data["trend_7d"]) == 40
    assert data["rule_hit_top"]
    assert data["blacklist_hits"]
    assert {item["rule_code"] for item in data["rule_hit_top"]}


def test_rule_status_toggle(client: TestClient) -> None:
    """规则启停用影响风险检查命中。"""
    rules = client.get("/api/risk/rules").json()["items"]
    rule = next(item for item in rules if item["rule_code"] == "R001")
    disabled = client.post("/api/risk/rules/status", json={"rule_id": rule["id"], "rule_status": "disabled"})
    assert disabled.status_code == 200
    assert disabled.json()["rule_status"] == "disabled"

    checked = _check(client)
    assert all(item["rule_code"] != "R001" for item in checked["rule_hits"])

    enabled = client.post("/api/risk/rules/status", json={"rule_id": rule["id"], "rule_status": "enabled"})
    assert enabled.status_code == 200
    rechecked = _check(client)
    assert any(item["rule_code"] == "R001" for item in rechecked["rule_hits"])


def test_rule_create_update_delete(client: TestClient) -> None:
    """规则新增、编辑、删除与列表统计变化。"""
    create_payload = {
        "rule_code": "R901",
        "rule_name": "测试大额规则",
        "rule_status": "enabled",
        "priority": 6,
        "score": 12,
        "condition_json": {"field": "order_amount", "op": ">=", "value": 100},
        "description": "自动化测试专用规则",
    }
    created = client.post("/api/risk/rules", json=create_payload)
    assert created.status_code == 200, created.text
    rule = created.json()
    assert rule["rule_code"] == "R901"
    assert json.loads(rule["condition_json"])["field"] == "order_amount"

    updated = client.post(
        "/api/risk/rules/update",
        json={"rule_id": rule["id"], "rule_name": "测试大额规则（已更新）", "score": 15, "priority": 7},
    )
    assert updated.status_code == 200
    assert updated.json()["rule_name"] == "测试大额规则（已更新）"
    assert updated.json()["score"] == 15

    listing = client.get("/api/risk/rules", params={"keyword": "R901"}).json()
    assert listing["filtered_total"] == 1
    assert listing["total"] == 31

    deleted = client.post("/api/risk/rules/delete", json={"rule_id": rule["id"]})
    assert deleted.status_code == 200
    assert deleted.json()["deleted_id"] == rule["id"]
    after = client.get("/api/risk/rules").json()
    assert after["total"] == 30


def test_rule_invalid_condition(client: TestClient) -> None:
    """非法条件 JSON、未知字段与非法运算符均被拒绝。"""
    base = {
        "rule_code": "R902",
        "rule_name": "非法规则",
        "rule_status": "enabled",
        "priority": 5,
        "score": 10,
        "description": "测试",
    }
    bad_field = dict(base, condition_json={"field": "not_exists", "op": ">", "value": 1})
    assert client.post("/api/risk/rules", json=bad_field).status_code == 400

    bad_op = dict(base, condition_json={"field": "order_amount", "op": "like", "value": 1})
    assert client.post("/api/risk/rules", json=bad_op).status_code == 400

    bad_json = dict(base, condition_json="{not-json")
    assert client.post("/api/risk/rules", json=bad_json).status_code == 400

    empty_and = dict(base, condition_json={"and": []})
    assert client.post("/api/risk/rules", json=empty_and).status_code == 400


def test_assessment_list(client: TestClient) -> None:
    """最近评估列表分页与等级筛选。"""
    data = client.get("/api/risk/assessments", params={"page_size": 5}).json()
    assert data["total"] == 40
    assert len(data["items"]) == 5
    assert data["pages"] == 8
    assert data["items"][0]["assessment_id"] > data["items"][-1]["assessment_id"]
    high = client.get("/api/risk/assessments", params={"risk_level": "high", "page_size": 50}).json()
    assert high["total"] == 8
    assert all(item["risk_level"] == "high" for item in high["items"])


def test_check_validation(client: TestClient) -> None:
    """非法事件、未知用户、订单归属校验。"""
    bad_event = dict(HIGH_CHECK, event_type="unknown_event")
    assert client.post("/api/risk/check", json=bad_event).status_code == 400

    unknown_user = dict(HIGH_CHECK, user_id="U9999")
    assert client.post("/api/risk/check", json=unknown_user).status_code == 404

    wrong_order = dict(HIGH_CHECK, order_id="O2001")
    assert client.post("/api/risk/check", json=wrong_order).status_code == 400

    assert client.get("/api/risk/users/U9999/profile").status_code == 404
    assert client.get("/api/risk/cases/99999").status_code == 404


def test_condition_operators() -> None:
    """规则条件 AST 的比较、包含、属于、与或非运算。"""
    features = {
        "order_amount": 2680.0,
        "user_register_days": 12,
        "order_pay_method": "虚拟卡",
        "order_category": "虚拟充值",
        "user_is_enterprise": 0,
        "event_type": "after_sale_apply",
    }
    condition = {
        "and": [
            {"field": "order_amount", "op": ">", "value": 2000},
            {"field": "user_register_days", "op": "<", "value": 30},
            {"field": "order_pay_method", "op": "in", "value": ["虚拟卡", "游戏点卡"]},
            {"field": "order_category", "op": "contains", "value": "虚拟"},
            {"not": {"field": "user_is_enterprise", "op": "==", "value": 1}},
            {"or": [{"field": "event_type", "op": "==", "value": "order_pay"}, {"field": "event_type", "op": "!=", "value": "order_create"}]},
        ]
    }
    validate_condition(condition)
    assert evaluate_condition(condition, features) is True
    assert evaluate_condition({"field": "order_amount", "op": "<=", "value": 100}, features) is False
    assert evaluate_condition({"field": "order_pay_method", "op": "!=", "value": "支付宝"}, features) is True
    assert evaluate_condition({"field": "order_amount", "op": "==", "value": 2680}, features) is True

    with pytest.raises(AppError):
        validate_condition({"field": "order_amount", "op": ">=", "value": "高"})
    with pytest.raises(AppError):
        validate_condition({"and": [{"field": "order_amount", "op": ">", "value": 1}]})
