"""接口冒烟脚本：对运行中的服务发起一轮真实调用，并输出关键结果。

用法：
    1. 先启动服务：python -m uvicorn app.main:app --host 127.0.0.1 --port 8713
    2. 另开终端：python tests/smoke_test.py

脚本会真实写入一条风险评估并审核它自动生成的案件，同时临时新增/删除一条黑名单。
这是测试环境行为，不影响代码本身。
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

import httpx

BASE_URL = os.environ.get("RISK_BASE_URL", "http://127.0.0.1:8713")
call_count = 0


def section(title: str) -> None:
    print("\n" + "=" * 68)
    print(title)
    print("=" * 68)


def call(client: httpx.Client, method: str, path: str, **kwargs: Any) -> Any:
    """执行请求并打印状态。"""
    global call_count
    response = client.request(method, path, **kwargs)
    call_count += 1
    print(f"[{response.status_code}] {method} {path}")
    if response.status_code >= 400:
        print("响应内容:", response.text[:800])
        raise SystemExit(f"接口调用失败：{method} {path} -> {response.status_code}")
    return response.json()


def main() -> int:
    """运行冒烟流程。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    print("电商风险控制系统 - 接口冒烟测试")
    print("目标服务:", BASE_URL)
    client = httpx.Client(base_url=BASE_URL, timeout=30)

    try:
        section("1. 健康检查")
        health = call(client, "GET", "/api/health")
        print("服务状态:", health["status"], "| 数据库:", health["database"])
        print("数据量:", health["counts"])

        section("2. 规则、特征与演示样本")
        meta = call(client, "GET", "/api/risk/meta")
        rules = call(client, "GET", "/api/risk/rules")
        features = call(client, "GET", "/api/risk/features")
        samples = call(client, "GET", "/api/risk/demo-samples")
        print("事件类型:", [item["label"] for item in meta["event_types"]])
        print("规则数量:", rules["total"], "| 启用:", rules["enabled_count"], "| 累计命中:", rules["total_hits"])
        print("特征数量:", features["total"], "| 分组:", [group["group_name"] for group in features["groups"]])
        print("演示样本:", [(item["sample_key"], item["user_id"], item["order_id"]) for item in samples["items"]])

        section("3. 发起风险检查（U1001 高危售后）")
        checked = call(
            client,
            "POST",
            "/api/risk/check",
            json={
                "event_type": "after_sale_apply",
                "source_id": "APP",
                "user_id": "U1001",
                "order_id": "O1101",
            },
        )
        print("评估编号:", checked["assessment_no"], "| 评分:", checked["risk_score"], "| 等级:", checked["risk_level"], "| 建议:", checked["decision"])
        print("命中规则:", [(hit["rule_code"], hit["rule_name"], hit["hit_score"]) for hit in checked["rule_hits"]])
        print("黑名单命中:", [(hit["blacklist_type"], hit["blacklist_value"], hit["added_score"]) for hit in checked["blacklist_hits"]])
        print("自动案件:", checked["case_no"], "| Agent 步骤:", [step["name"] for step in checked["trace"]])

        section("4. 评估详情与特征快照回查")
        assessment = call(client, "GET", f"/api/risk/assessments/{checked['assessment_id']}")
        print("风险结果:", assessment["risk_score"], assessment["risk_level"], assessment["decision"])
        print("特征数:", len(assessment["feature_snapshot"]), "| 命中规则数:", len(assessment["rule_hits"]), "| 轨迹步数:", len(assessment["trace"]))
        print("关键特征:", {key: assessment["feature_snapshot"][key] for key in ("user_register_days", "user_refund_rate", "blacklist_hit_cnt", "order_address_distance_km")})
        assessments = call(client, "GET", "/api/risk/assessments", params={"page": 1, "page_size": 5})
        print("最近评估:", assessments["total"], "条，当前页:", len(assessments["items"]))

        section("5. 案件列表、详情、审核与日志")
        cases = call(client, "GET", "/api/risk/cases", params={"page_size": 100})
        print("案件总数:", cases["total"], "| 状态分布:", cases["status_stats"])
        case_id = checked["case_id"]
        detail = call(client, "GET", f"/api/risk/cases/{case_id}")
        print("案件详情:", detail["case_no"], detail["case_status"], "| 规则:", len(detail["rule_hits"]), "| 特征:", len(detail["feature_snapshot"]))
        reviewed = call(
            client,
            "POST",
            "/api/risk/cases/review",
            json={
                "case_id": case_id,
                "review_result": "approved",
                "review_remark": "冒烟测试：已电话核实为本人操作，风险信号解除，同意放行。",
                "reviewer_id": "RV001",
            },
        )
        print("审核后状态:", reviewed["case_status"], "| 审核人:", reviewed["reviewer_name"], "| 审核时间:", reviewed["reviewed_at"])
        logs = call(client, "GET", f"/api/risk/cases/{case_id}/logs")
        print("审核日志:", [(item["action_type"], item["operator_name"], item["action_remark"]) for item in logs["items"]])

        section("6. 黑名单新增、查询与删除")
        blacklists = call(client, "GET", "/api/risk/blacklists")
        print("黑名单总数:", blacklists["total"], "| 类型统计:", blacklists["type_stats"])
        temp_value = f"DEV-SMOKE-{int(time.time())}"
        created = call(
            client,
            "POST",
            "/api/risk/blacklists",
            json={"blacklist_type": "device", "blacklist_value": temp_value, "remark": "冒烟测试临时条目", "status": "active"},
        )
        print("新增黑名单:", created["id"], created["blacklist_type_label"], created["blacklist_value"])
        filtered = call(client, "GET", "/api/risk/blacklists", params={"keyword": temp_value})
        print("按关键字查询:", filtered["filtered_total"], "条")
        removed = call(client, "POST", "/api/risk/blacklists/delete", json={"id": created["id"]})
        print("删除结果:", removed)

        section("7. 用户画像与运营看板")
        profile = call(client, "GET", "/api/risk/users/U1001/profile")
        print("用户:", profile["user"]["user_name"], profile["user"]["user_id"], "| 黑名单:", profile["user"]["blacklisted"])
        print("画像统计:", profile["stats"])
        print("最近事件:", len(profile["recent_events"]), "条 | 关联案件:", len(profile["cases"]), "个 | 趋势点:", len(profile["risk_trend"]))
        dashboard = call(client, "GET", "/api/risk/dashboard")
        print("看板 KPI:", dashboard["kpi"])
        print("等级分布:", dashboard["level_distribution"], "| 近7日:", [(item["label"], item["event_count"], item["high_count"]) for item in dashboard["trend_7d"]])

        section("冒烟结果")
        print(f"全部接口调用成功，共 {call_count} 次请求。")
        print("提示：本次冒烟新增了 1 条风险事件和 1 个已审核案件，演示前可删除 data/risk_control.db 重新初始化。")
        return 0
    except httpx.ConnectError:
        print(f"\n[错误] 无法连接 {BASE_URL}，请先启动服务：")
        print("  python -m uvicorn app.main:app --host 127.0.0.1 --port 8713")
        return 2
    except SystemExit as exc:
        print("\n[失败]", exc)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
