# 电商风险控制系统（RiskShield）

面向电商业务的实时风险控制平台，覆盖 **风险识别 → 规则判断 → 人工复核 → 处置留痕 → 结果回查** 的完整闭环。

项目采用 Python 3.12 + FastAPI + SQLite（标准库 `sqlite3`）构建后端，前端为纯原生 HTML/CSS/JS 单页应用，**不依赖任何 CDN、外部字体、外部图片或大模型 API**，可完全离线运行。

> 风险 Agent 使用确定性六步编排：**事件校验 → 特征计算 → 规则匹配 → 评分决策 → 黑名单校验 → 案件生成**，每一步的耗时、状态、摘要均作为 trace 返回并落库。

---

## 一、快速启动

```powershell
cd "E:\260515\张晨\项目实战_交付\3组_张晨_电商风控_电商"

# 方式一：直接启动
python -m uvicorn app.main:app --host 127.0.0.1 --port 8713

# 方式二：一键脚本（自动提示地址）
.\启动.ps1
```

浏览器打开：<http://127.0.0.1:8713>

- 接口文档：<http://127.0.0.1:8713/docs>（离线自绘文档，不依赖 Swagger CDN）
- 健康检查：<http://127.0.0.1:8713/api/health>
- 首次启动会自动创建 `data/risk_control.db`，并灌入 30 个用户、60 笔订单、40 条历史评估、12 个案件、8 条黑名单及审核日志。
- 如果 `fastapi / uvicorn / pytest / httpx` 已安装，**无需再安装任何依赖**；`requirements.txt` 仅用于说明版本。

环境：Windows + Python 3.12，已在 Chrome / Edge 中验证。

---

## 二、演示链路（建议按此顺序）

1. **风险检查**：打开 `#/check?demo=1`，页面自动填充主演示用户 `U1001` 与订单 `O1101`，发起 `after_sale_apply` 检查。
   - 评分 **100.0**，等级 **high**，建议 **reject**；
   - 命中 **10 条规则**（新账号高额交易、退款率异常、历史高风险、高额售后等）；
   - 命中 **2 条黑名单**（设备 `DEV-7788`、IP `203.88.12.7`）；
   - 自动生成案件 `CASE-000013`；
   - 右侧可查看 39 项特征快照、命中原因、评分构成和 6 步 Agent 轨迹。
2. **规则管理**：打开 `#/rules`，查看 30 条规则、启停用开关、命中次数；可新增/编辑/删除规则，编辑弹窗内可直接修改并校验 `condition_json`。
3. **案件管理**：打开 `#/cases`，按状态/等级筛选案件；点击行打开右侧详情抽屉。
4. **案件审核**：打开 `#/cases?demo=1`，自动打开主演示案件；在抽屉底部选择审核结论、填写备注并提交，审核日志立即追加。
5. **黑名单**：打开 `#/blacklist`，查看 5 类黑名单、命中次数与类型分布；可新增、删除、批量导入。
6. **用户画像**：打开 `#/profile?demo=1`，查看 `U1001` 的订单、退款、投诉、地址、设备、最近风险事件、关联案件与风险趋势。
7. **运营看板**：打开 `#/dashboard`，查看 6 个 KPI、近 7 日趋势、等级分布、规则命中 TOP 与黑名单命中。
8. **接口文档**：打开 <http://127.0.0.1:8713/docs>，查看 24 个接口、请求字段、响应状态与 cURL 示例。

> 每次执行检查都会真实写库；如需恢复干净的 40 条评估 / 12 个案件基线，停止服务后删除 `data/risk_control.db`，重新启动即可自动重建。

---

## 三、页面与功能

| 页面 | Hash 路由 | 主要能力 |
| --- | --- | --- |
| 风险检查 | `#/check` | 四类事件、示例场景、评分仪表、等级/建议徽章、命中规则、39 项特征快照、Agent 轨迹 |
| 规则管理 | `#/rules` | 30 条规则、统计卡、搜索/状态筛选、启停用、新增、编辑条件 JSON、删除 |
| 案件管理 | `#/cases` | 状态/等级筛选、案件表格、右侧详情抽屉、命中规则、特征快照、审核记录、审核表单 |
| 黑名单管理 | `#/blacklist` | 5 类统计、类型/状态/关键字筛选、新增、删除、批量导入、类型分布、近期命中 |
| 用户画像 | `#/profile` | 用户检索、信用与会员信息、6 项统计、最近风险事件、关联案件、风险趋势、地址、黑名单命中 |
| 运营看板 | `#/dashboard` | 事件总数、高风险占比、待处理案件、平均处理时长、规则命中、黑名单命中、趋势/环形/条形图 |
| 接口文档 | `/docs` | 24 个接口目录、参数表、请求体字段、响应状态、cURL 示例、统一响应约定 |

`?demo=1` 用于截图/演示：

- `#/check?demo=1`：自动填充并执行 `U1001` 高风险检查；
- `#/cases?demo=1`：自动打开待审核案件详情抽屉；
- `#/profile?demo=1`：自动加载 `U1001` 画像（默认也会加载 U1001）。

---

## 四、项目结构

```text
3组_张晨_电商风控_电商/
├─ README.md                    项目说明、启动、演示、接口清单
├─ requirements.txt             版本说明（本机已安装，无需联网安装）
├─ 启动.ps1                     一键启动并打印地址
├─ 截图脚本.ps1                 一键重跑 8 张截图
├─ app/
│  ├─ main.py                   FastAPI 入口、健康检查、离线文档、静态资源
│  ├─ db.py                     SQLite 连接、初始化、种子触发
│  ├─ schema.sql                核心 8 表 + 业务表 + 审计辅助表
│  ├─ seed.py                   演示数据初始化与 40 次历史 Agent 评估
│  ├─ features.py               39 项特征计算与特征元数据
│  ├─ rule_engine.py            条件 AST 校验、匹配、命中解释、评分决策
│  ├─ risk_agent.py             六步确定性编排、trace、案件生成
│  ├─ blacklist_matcher.py      五类黑名单匹配与加权
│  ├─ constants.py              事件/等级/建议/状态/黑名单/审核人字典
│  ├─ models.py                 Pydantic 请求模型
│  ├─ errors.py                 业务异常
│  ├─ utils.py                  时间、JSON、距离、脱敏辅助
│  ├─ services/                 规则、黑名单、评估、案件、画像、看板服务
│  ├─ routers/                  风险、规则、案件、黑名单、画像、看板、元数据路由
│  └─ static/
│     ├─ index.html             单页应用外壳
│     ├─ app.js                 原生 JS 路由与六个页面
│     ├─ styles.css             企业级风控后台样式
│     └─ docs.html              离线接口文档
├─ data/
│  ├─ rules.json                30 条规则定义（条件 AST）
│  ├─ demo_data.json            30 用户 / 60 订单 / 40 历史检查计划等
│  └─ cities.json               城市经纬度（地址距离特征）
├─ tests/
│  ├─ test_api.py               24 个 pytest 用例
│  └─ smoke_test.py             接口冒烟脚本（需先启动服务）
├─ docs/
│  ├─ 设计说明.md               架构、Agent、特征表、规则表、表结构、接口表
│  ├─ 测试记录.md               pytest / 冒烟 / 截图记录
│  └─ 验收对照.md               2.3.11 验收标准逐条对照
└─ 测试截图/                    8 张真实 Chrome headless 截图
```

---

## 五、核心设计

### 5.1 数据表

严格实现需求文档 2.3.8 的 8 张核心表：

`risk_events`、`risk_assessments`、`feature_snapshots`、`risk_rules`、`rule_hits`、`risk_cases`、`blacklists`、`review_logs`。

另含支撑表：

- `biz_users`、`biz_orders`、`biz_addresses`、`biz_devices`、`biz_login_logs`、`biz_after_sales`：真实业务数据来源；
- `assessment_traces`：Agent 六步轨迹；
- `blacklist_hit_records`：黑名单命中留痕（删除黑名单后仍保留历史）。

### 5.2 特征（39 项）

覆盖事件、用户、订单、地址、黑名单五个维度：

- 用户：注册天数、近 30/90 天下单数、退款次数/退款率、投诉次数、历史高风险次数、设备数、登录地数量、地址数、用户黑名单命中、客单价、夜间下单占比、信用分、企业标识；
- 订单：金额、折扣率、运费占比、支付方式、支付间隔、收货地与注册地距离、类目、类目风险分、同 IP 订单数、同设备订单数、商品件数、下单小时、是否新地址；
- 地址：地址集中度、地址变更次数、手机号归属地一致性、偏远地区标识、地址黑名单命中；
- 黑名单：命中总数、设备/手机号/IP 黑名单命中、命中明细；
- 事件：事件类型。

完整特征表见 [docs/设计说明.md](docs/设计说明.md)。

### 5.3 规则（30 条）

每条规则包含 `rule_code`、`rule_name`、`rule_status`、`priority`、`score`、`condition_json`、`description`、`updated_at`。

条件 AST 示例：

```json
{
  "and": [
    {"field": "user_register_days", "op": "<", "value": 30},
    {"field": "order_amount", "op": ">=", "value": 2000}
  ]
}
```

支持 `>` `<` `>=` `<=` `==` `!=` `contains` `in` `and` `or` `not`。前端在规则弹窗中可编辑 JSON，提供格式化、客户端校验，后端再次校验字段、运算符、嵌套深度与阈值类型。

### 5.4 评分与决策

- 单条命中分：`score × 优先级权重`，权重 `1 + (priority - 1) × 1%`；
- 黑名单：命中后按类型直接加分（用户 20、手机号 15、地址 12、设备 15、IP 10）；
- 总分：`min(100, 规则加总 + 黑名单加总)`；
- 等级：`<30 low`、`30-69 medium`、`>=70 high`；
- 建议：`<30 pass`、`30-84 manual_review`、`>=85 reject`；
- `high` 或建议为 `manual_review / reject` 时自动创建案件，一次评估只创建一个案件。

### 5.5 Agent 轨迹

每次检查保存 6 步 trace：步骤序号、名称、状态（success / warning / skipped）、耗时（毫秒）、摘要、关键数据。前端以时间线卡片展示。

---

## 六、接口清单

基础地址：`http://127.0.0.1:8713`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/risk/check` | 发起风险检查（事件校验、特征、规则、决策、黑名单、建案） |
| GET | `/api/risk/assessments/{assessment_id}` | 评估详情：评分、等级、建议、特征快照、命中规则、轨迹 |
| GET | `/api/risk/assessments` | 最近评估列表（补充接口） |
| GET | `/api/risk/rules` | 规则列表 + 命中统计 |
| POST | `/api/risk/rules` | 新增规则 |
| POST | `/api/risk/rules/update` | 更新规则 |
| POST | `/api/risk/rules/status` | 启停用规则 |
| POST | `/api/risk/rules/delete` | 删除规则 |
| GET | `/api/risk/cases` | 案件列表（状态/等级/关键字） |
| GET | `/api/risk/cases/{case_id}` | 案件详情 |
| GET | `/api/risk/cases/{case_id}/logs` | 审核日志（补充接口） |
| POST | `/api/risk/cases/review` | 提交审核结论 |
| GET | `/api/risk/blacklists` | 黑名单列表 + 类型统计 |
| POST | `/api/risk/blacklists` | 新增黑名单 |
| POST | `/api/risk/blacklists/delete` | 删除黑名单 |
| POST | `/api/risk/blacklists/import` | 批量导入（补充接口） |
| GET | `/api/risk/users/{user_id}/profile` | 用户画像 |
| GET | `/api/risk/users` | 用户检索（补充接口） |
| GET | `/api/risk/dashboard` | 运营看板 |
| GET | `/api/risk/meta` | 枚举、特征、审核人、阈值（补充接口） |
| GET | `/api/risk/features` | 特征定义（补充接口） |
| GET | `/api/risk/demo-samples` | 演示样本（补充接口） |
| GET | `/api/health` | 健康检查（补充接口） |
| GET | `/api/meta/dicts` | 基础字典（补充接口） |

列表响应统一为 `{items, total, page, page_size, pages}`；业务异常返回 `{detail, code, data}`。

> `/docs` 为离线接口文档页，不计入上述 24 个 API。

---

## 七、测试

```powershell
# 24 个 pytest 用例（临时数据库，自动灌入模板数据）
python -m pytest -q

# 接口冒烟（需先启动服务）
python tests/smoke_test.py
```

覆盖点包括：健康检查、30 条规则、39 项特征、四类事件、评分/等级/建议、命中规则、特征快照落库、高风险自动建案、案件列表/详情、审核流转与日志、黑名单新增删除与命中、用户画像、运营看板、规则启停用/增删改、非法条件、参数校验等。

测试结果与截图记录见 [docs/测试记录.md](docs/测试记录.md)。

---

## 八、交付说明

- 数据库文件、`__pycache__`、`.pytest_cache`、临时日志均已清理；首次启动自动建库。
- 前端不引用任何外部资源，断网可用。
- 图表（评分圆环、趋势折线、等级环形图、条形排行）均使用内联 SVG / CSS 绘制。
- 截图使用真实 Chrome headless（1440×1150）生成，共 8 张，位于 `测试截图/`。

如页面截图需要重跑：

```powershell
.\截图脚本.ps1
```

脚本会自动检查/启动 8713 端口服务，并校验每张图大于 40KB。

---

## 九、已知限制

1. 演示环境不包含登录鉴权，审核人固定为 `RV001 张审核`；真实项目应接入统一身份认证与 RBAC。
2. 数据库为 SQLite 单文件，适合课程演示与单机部署；高并发生产环境应替换为 PostgreSQL/MySQL 并引入缓存与消息队列。
3. 规则条件为确定性 AST，不支持脚本执行、跨事件窗口聚合与模型评分；这保证了离线、可解释、可测试。
4. 日期数据相对首次启动时间生成，因此重新建库后具体日期会变化，但分布与评分稳定。
5. 接口文档为项目自绘的离线页面，不是 Swagger UI，目的是在无外网环境下仍能完整展示接口。
