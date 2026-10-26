# 舆情分析平台（Agent 项目）

面向指定主题的舆情分析平台：从新闻、图片、视频、论坛与内部数据五类来源并行采集，经过确定性的 Agent 流水线完成观点 / 情绪 / 风险抽取、洞察汇总、报告生成与图谱构建，并提供可操作的企业级 Web 控制台。

- 主题样例：**预制菜进校园**（48 条来源，主推）、**新能源车电池召回**（36 条来源，备用）
- 技术栈：Python 3.12 + FastAPI + uvicorn + 标准库 `sqlite3` 之外的 JSON 文件存储 + 原生 HTML/CSS/JS
- 完全离线：不调用大模型 API，不依赖 CDN / 外部字体 / 外部图片；图谱与图表全部内联 SVG
- 固定端口：**8714**
- 测试：**27 个 pytest 用例全部通过**
- 截图：`测试截图/` 下 8 张真实 Chrome headless 截图

---

## 1. 快速启动

```powershell
cd "E:\260515\张晨\项目实战_交付\3组_张晨_舆情分析_舆情"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8714
```

或双击 / 运行：

```powershell
.\启动.ps1
```

首次启动会自动初始化 `config.json`、`runtime/`、`reports/`、`graphs/`、`outputs/` 目录，并将系统状态置为 `online`。浏览器打开：

| 页面 | 地址 |
| --- | --- |
| 控制台 | http://127.0.0.1:8714/#/console |
| 主题检索 | http://127.0.0.1:8714/#/search |
| 论坛监控 | http://127.0.0.1:8714/#/forum |
| 图谱查看 | http://127.0.0.1:8714/#/graph |
| 配置管理 | http://127.0.0.1:8714/#/config |
| 系统状态 | http://127.0.0.1:8714/#/status |
| 接口文档 | http://127.0.0.1:8714/docs |
| 图谱查看页（真实路由） | http://127.0.0.1:8714/graph-viewer |
| 指定报告图谱 | http://127.0.0.1:8714/graph-viewer/{report_id} |

### 演示模式

| URL | 行为 |
| --- | --- |
| `#/console?demo=1` | 自动启动 5 个应用，展示运行状态、最近输出与系统资源 |
| `#/search?demo=1` | 自动检索「预制菜进校园」并渲染完整 8 部分报告 |
| `#/search?demo=1&focus=report` | 聚焦报告主体（截图 02 使用） |
| `#/search?demo=1&focus=evidence` | 聚焦「重点证据 + 结论摘要」（截图 03 使用） |
| `#/graph?demo=1` | 自动加载最新图谱；无图谱时自动执行一次主主题检索 |
| `#/forum?demo=1` | 自动启动论坛采集并展示实时日志 |
| `#/status?demo=1` | 展示系统状态、应用状态表、资源与日志 |

> `focus` 是「章节聚焦视图」：会隐藏前置区块，便于在 1150px 高度内完整呈现报告章节，不属于缩放或截图造假。

---

## 2. 单功能应用

| 应用 | 说明 | 状态机 |
| --- | --- | --- |
| `topic_search` 主题检索 | 多来源文本检索、主题匹配、来源摘要 | stopped / starting / running / stopping / failed |
| `multimedia_search` 多媒体检索 | 图片 OCR、视频 ASR 文本抽取，补充证据链 | 同上 |
| `insight_analysis` 洞察分析 | 观点聚类、情绪判定、渠道统计、风险评分 | 同上 |
| `forum_collector` 论坛采集 | 后台线程每 1.5-3 秒追加日志，支持历史查询 | 同上（论坛任务另有 idle/running/stopped/failed） |
| `report_writer` 报告汇总 | 生成 8 部分报告、来源清单与图谱，落盘归档 | 同上 |

- 每个应用独立保存状态、`runtime/apps/{app_name}.log`（stdout/stderr）与 `outputs/{app_name}/latest.txt`。
- 停止应用后不再接收新任务，但输出与日志保留；检索接口会明确返回 409 并提示启动所需应用。
- `apps` 配置开关禁用应用后，应用无法启动；如正在运行，保存配置会触发热更新并自动停止该应用。

### Agent 流水线（确定性，无大模型）

```
主题检索 → 多媒体解析 → 洞察分析 → 报告生成 → 图谱构建
collector   multimedia    analyzer     reporter     graph
```

每段执行步骤、耗时、指标都会随 `/api/search` 返回，并展示在主题检索页顶部的步骤条；相同输入产生相同结论。主主题一次检索约 0.3-0.7 秒，图谱规模 51 节点 / 91 条边（上限随配置与来源数量变化）。

---

## 3. 接口清单

核心接口严格对应需求文档 2.2.9（18 个），另有 `GET /api/health`、`WS /api/ws` 与若干辅助接口。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/status` | 控制台状态与 5 个应用状态 |
| GET | `/api/start/{app_name}` | 启动应用（`?wait=1` 等待状态稳定） |
| GET | `/api/stop/{app_name}` | 停止应用 |
| GET | `/api/output/{app_name}` | 最近输出 |
| GET | `/api/test_log/{app_name}` | 应用测试日志尾部 |
| POST | `/api/search` | 主题检索（`query`、`source_types`、`auto_start`） |
| GET | `/api/forum/start` | 启动论坛采集 |
| GET | `/api/forum/stop` | 停止论坛采集 |
| GET | `/api/forum/log` | 最新论坛日志 |
| POST | `/api/forum/log/history` | 按日期查询历史日志 |
| GET | `/api/config` | 读取配置与表单 Schema |
| POST | `/api/config` | 保存配置并热更新 |
| GET | `/api/system/status` | 整体服务状态、资源、最近错误、系统日志 |
| POST | `/api/system/start` | 启动整体服务 |
| POST | `/api/system/shutdown` | 关闭整体服务 |
| GET | `/api/graph/latest` | 最新图谱 |
| GET | `/api/graph/{report_id}` | 指定报告图谱 |
| POST | `/api/graph/query` | 按节点类型 / 关键词 / 关系 / 来源编号查询 |
| GET | `/graph-viewer` | 图谱查看页（真实页面路由） |
| GET | `/graph-viewer/{report_id}` | 指定报告图谱查看页 |
| WS | `/api/ws` | 实时消息推送 |
| GET | `/api/reports` | 报告列表（辅助） |
| GET | `/api/report/{report_id}` | 报告 JSON + Markdown（辅助） |
| GET | `/api/report/{report_id}/markdown` | 下载 Markdown（辅助） |
| GET | `/api/topics` | 样例主题目录（辅助） |
| GET | `/api/system/logs` | 系统/应用日志尾部（辅助） |

完整参数、响应示例与 WebSocket 字段见 `http://127.0.0.1:8714/docs`（离线自绘文档页，无 CDN 依赖）。

### WebSocket 消息类型

`/api/ws` 连接后先发送 `hello` 快照，之后推送：

- `app_status`：`app_name`、`status`、`display_name`、`time`
- `app_output`：`app_name`、`output_text`、`output_path`、`time`
- `forum_log`：`message_text`、`task_status`、`event_type`、`level`、`time`、`seq`
- `system_status`：`system_status`、`running_apps`、`time`
- `graph_ready`：`report_id`、`graph_path`、`node_count`、`edge_count`
- `error`：`module_name`、`error_message`、`time`

前端优先使用 WebSocket；断线后自动重连，并将控制台状态、论坛日志、状态页切换为轮询降级。

---

## 4. 存储布局（真实落盘）

```
config.json                          # 系统配置 / 采集配置 / 运行参数 / 应用开关
runtime/
  apps/{app_name}.log                # 标准输出 + 错误输出
  forum/latest.log                   # 论坛最新日志（JSON Lines，字段完整）
  forum/history/{YYYY-MM-DD}.json    # 按日期归档
  system.log                         # 系统级日志
reports/{report_id}/
  report.md                          # 8 部分结构化报告 + 来源清单
  report.json                        # 前端渲染用报告
  search.json                        # 主题词、执行时间、来源摘要、分析输出
graphs/{report_id}/graph.json        # 节点 + 边 + 统计
outputs/{app_name}/latest.txt        # 应用最近一次文本输出
data/
  sources_zhuncaijinxiaoyuan.json    # 主主题 48 条来源
  sources_xinnengyuan_huizhao.json   # 备用主题 36 条来源
```

- 报告结论全部带 `[S01]` 形式的来源引用，文末附完整来源清单，可按编号回溯。
- 图谱节点含 `id / label / type / source_refs`，边含 `source / target / relation / label / source_refs`，支持按报告编号、节点类型、关系与来源编号查询。

---

## 5. 演示流程

1. 打开控制台，等待系统状态为 **在线**，依次点击 5 个应用的「启动」（或直接打开 `#/console?demo=1`）。
2. 进入 **主题检索**，主题词输入「预制菜进校园」，勾选五类来源，点击「开始分析」。页面展示 Agent 步骤条与 8 部分报告。
3. 在报告顶部点击「查看图谱」，或用 `#/graph?demo=1` 打开力导向图谱；点击节点查看属性、关系与来源引用，使用条件查询筛选。
4. 进入 **论坛监控**，点击「启动采集」，观察终端每 1.5-3 秒追加日志；用右侧日期选择器查询历史归档。
5. 进入 **配置管理**，修改轮询间隔或关闭某应用开关，点击「保存并生效」，观察提示与运行状态变化。
6. 进入 **系统状态**，查看应用状态机流转、资源概况、最近错误和系统日志 tail；可演示关闭 / 启动整体系统。
7. 打开 `http://127.0.0.1:8714/docs` 查看接口文档；打开 `/graph-viewer/{report_id}` 验证真实页面路由。

---

## 6. 测试与截图

```powershell
python -m pytest -q
```

当前结果：`27 passed`（约 41 秒）。测试使用 `tmp_path` 作为临时根目录，不污染交付的 `config.json`、`data/` 与运行数据。

重新生成 8 张截图（需要服务已启动，或由脚本自动启动）：

```powershell
.\截图脚本.ps1
```

截图文件：

```
测试截图/01_控制台首页_应用运行状态.png
测试截图/02_主题检索_结构化报告.png
测试截图/03_主题检索_来源证据与结论.png
测试截图/04_图谱查看器.png
测试截图/05_论坛监控_实时日志.png
测试截图/06_配置管理.png
测试截图/07_系统状态.png
测试截图/08_接口文档.png
```

截图均由真实 Chrome headless 打开运行中的服务生成，宽度 1440、高度 1150。

---

## 7. 环境与依赖

已预装（无需联网安装）：

```
Python 3.12.8
fastapi 0.136.3
uvicorn 0.49.0
pytest 9.1.1
httpx 0.28.1
websockets
psutil 7.2.2
```

`requirements.txt` 仅用于记录运行环境，评审机无需联网。前端不包含任何 CDN 资源。

---

## 8. 已知限制与说明

- 样例数据中的新闻 / 论坛 / 内部系统 URL 为**演示用虚构地址**，不对应真实网页；接口、状态机、落盘文件与报告结论均真实生成。
- Agent 为确定性规则流水线（关键词匹配、情绪聚合、风险评分、模板化结论），不调用大模型，不具备真实互联网采集能力。
- 论坛采集为后台线程模拟，间隔与批量可在配置中调整；停止后线程退出并保留归档。
- 图谱布局为前端自绘 SVG（力导向 / 分层可切换）；节点较多时默认隐藏低连接度节点与来源标签，点击节点后展示完整属性与引用。
- 报告 / 图谱 / 日志可在界面上一键重新生成；`docs/` 内保留设计、测试与验收说明。
