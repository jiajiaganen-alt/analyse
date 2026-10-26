import { api, isWSConnected } from "../api.js";
import { esc, fmtNumber, fmtTime, icon, loadingBlock, renderInlineError, statusBadge, statusMeta, toast } from "../ui.js";

const state = {
  data: null,
  pollTimer: null,
  wsRefreshTimer: null,
  logApp: "",
  logLines: [],
  refreshing: false,
  el: null,
};

const APP_ORDER = ["topic_search", "multimedia_search", "insight_analysis", "forum_collector", "report_writer"];

function gaugeHTML(value, label, sub, color) {
  const percent = Math.max(0, Math.min(100, Number(value) || 0));
  const circumference = 2 * Math.PI * 26;
  const dash = (percent / 100) * circumference;
  return `<div class="gauge">
    <svg viewBox="0 0 64 64">
      <circle class="bg" cx="32" cy="32" r="26"></circle>
      <circle class="val" cx="32" cy="32" r="26" stroke="${color}" stroke-dasharray="${dash.toFixed(
        1
      )} ${circumference.toFixed(1)}"></circle>
      <text x="32" y="34" text-anchor="middle" style="font-size:13px;font-weight:700;fill:#172033">${Math.round(
        percent
      )}%</text>
    </svg>
    <div class="g-info"><div class="v">${esc(sub)}</div><div class="k">${esc(label)}</div><div class="s">${
    percent > 80 ? "接近上限" : "运行正常"
  }</div></div>
  </div>`;
}

function appsTableHTML(data) {
  return `<div class="table-wrap">
    <table class="table status-table">
      <thead><tr>
        <th>应用</th><th>状态</th><th>启动时间</th><th>任务数</th><th>最近输出</th><th>状态流转</th><th style="width:104px">操作</th>
      </tr></thead>
      <tbody>
        ${(data.apps || [])
          .map((app) => {
            const transitions = (app.transitions || []).slice(-3).map((item) => statusMeta(item.status).label).join(" → ");
            return `<tr>
              <td><div class="app-name">${esc(app.display_name)}</div><div class="app-code">${esc(app.app_name)}</div></td>
              <td>${statusBadge(app.status)}</td>
              <td class="muted nowrap">${app.started_at ? fmtTime(app.started_at, "short") : "—"}</td>
              <td class="nowrap">${fmtNumber(app.task_count)}</td>
              <td class="muted nowrap">${app.last_output_at ? fmtTime(app.last_output_at, "short") : "—"}</td>
              <td class="tiny muted">${esc(transitions || "—")}</td>
              <td>
                <button class="btn btn-sm" data-status-start="${esc(app.app_name)}" ${
                  ["running", "starting"].includes(app.status) ? "disabled" : ""
                }>启动</button>
                <button class="btn btn-sm" data-status-stop="${esc(app.app_name)}" ${
                  ["stopped", "failed", "stopping"].includes(app.status) ? "disabled" : ""
                }>停止</button>
              </td>
            </tr>`;
          })
          .join("")}
      </tbody>
    </table>
  </div>`;
}

function logsHTML(data) {
  const appOptions = (data.apps || [])
    .map(
      (app) =>
        `<option value="${esc(app.app_name)}" ${state.logApp === app.app_name ? "selected" : ""}>${esc(
          app.display_name
        )}日志</option>`
    )
    .join("");
  return `<div class="log-panel">
    <div class="log-toolbar">
      <select id="status-log-select">
        <option value="">系统日志</option>
        ${appOptions}
      </select>
      <button class="btn btn-sm" id="status-log-refresh">${icon("refresh")} 刷新</button>
      <span class="tiny" style="margin-left:auto;color:#64748b" id="status-log-meta">${esc(
        state.logApp ? "runtime/apps/" + state.logApp + ".log" : "runtime/system.log"
      )}</span>
    </div>
    <div class="log-body" id="status-log-body"></div>
  </div>`;
}

function logLineHTML(line) {
  if (typeof line === "string") {
    const match = line.match(/^(\S+ \S+) \[(\w+)\] \[([^\]]+)\] (.*)$/);
    if (match) {
      const level = match[2].toLowerCase();
      return `<div class="ll"><span class="lt">${esc(match[1])}</span><span class="lm ${level === "error" ? "err" : level === "warn" ? "warn" : ""}">[${esc(
        match[2]
      )}] [${esc(match[3])}] ${esc(match[4])}</span></div>`;
    }
    return `<div class="ll"><span class="lt"></span><span class="lm">${esc(line)}</span></div>`;
  }
  return `<div class="ll"><span class="lt">${esc(line.time || "")}</span><span class="lm ${
    (line.level || "").toUpperCase() === "ERROR" ? "err" : (line.level || "").toUpperCase() === "WARN" ? "warn" : ""
  }">[${esc(line.level || "INFO")}] ${esc(line.message || line.raw || "")}</span></div>`;
}

function render(el, data) {
  state.data = data;
  const system = data.system || {};
  const resources = data.resources || {};
  const reports = data.reports || {};
  const forum = data.forum || {};
  const online = system.system_status === "online";
  el.innerHTML = `
    <div class="page-head">
      <div>
        <h1 class="page-title">系统状态</h1>
        <p class="page-sub">整体服务状态、单功能应用状态机、最近错误与资源运行概况。页面每 5 秒降级轮询，WebSocket 事件到达时即时刷新。</p>
      </div>
      <div class="page-actions">
        <button class="btn btn-sm" id="status-refresh">${icon("refresh")} 刷新</button>
        ${
          online
            ? `<button class="btn btn-sm btn-danger" id="status-shutdown">${icon("stop")} 关闭系统</button>`
            : `<button class="btn btn-sm btn-primary" id="status-start">${icon("play")} 启动系统</button>`
        }
      </div>
    </div>

    <div class="status-banner ${online ? "" : "offline"}">
      <div class="big">
        <div class="status-orbe"><i></i></div>
        <div>
          <h2>${esc(system.platform_name || "舆情分析平台")} · ${esc(system.status_label || "离线")}</h2>
          <div class="sub">FastAPI 服务 · 127.0.0.1:8714 · 版本 ${esc(system.version || "1.0.0")} · 已运行 ${esc(
            system.uptime_text || "—"
          )}</div>
        </div>
      </div>
      <div class="metrics">
        <div class="m"><div class="v">${fmtNumber(system.running_apps || 0)}<small> / ${fmtNumber(
          system.total_apps || 5
        )}</small></div><div class="k">运行应用</div></div>
        <div class="m"><div class="v">${fmtNumber(reports.report_count || 0)}</div><div class="k">已生成报告</div></div>
        <div class="m"><div class="v">${fmtNumber(forum.today_count || 0)}</div><div class="k">今日论坛日志</div></div>
        <div class="m"><div class="v">${fmtNumber(system.ws_clients || 0)}</div><div class="k">WS 客户端</div></div>
      </div>
    </div>

    <div class="status-grid">
      <div>
        <div class="card" style="margin-bottom:14px">
          <div class="card-head"><h3>${icon("activity")} 单功能应用状态</h3><span class="hint">stopped → starting → running → stopping → stopped，独立日志与输出</span></div>
          ${appsTableHTML(data)}
        </div>

        <div class="card" style="margin-bottom:14px">
          <div class="card-head"><h3>${icon("alert")} 最近错误</h3><span class="hint">runtime/system.log</span></div>
          <div class="card-body" style="padding:6px 18px 10px">
            ${
              (data.recent_errors || []).length
                ? `<div class="error-list">${data.recent_errors
                    .map(
                      (item) => `<div class="error-item">
                        <span class="error-icon">${icon("alert")}</span>
                        <div class="error-body">
                          <div class="msg">${esc(item.error_message || "")}</div>
                          <div class="meta"><span>${esc(item.module_name || "")}</span><span>${esc(
                        item.time_label || fmtTime(item.time, "time")
                      )}</span></div>
                        </div>
                      </div>`
                    )
                    .join("")}</div>`
                : `<div class="empty" style="padding:18px">${icon("shield")}<div>暂无错误记录，所有应用运行正常</div></div>`
            }
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>${icon("terminal")} 运行日志 tail</h3><span class="hint">系统日志 / 应用日志</span></div>
          <div class="card-body" style="padding:10px 12px">${logsHTML(data)}</div>
        </div>
      </div>

      <aside>
        <div class="resource-grid" style="margin-bottom:12px">
          ${gaugeHTML(resources.cpu_percent, "服务 CPU 占用", `${fmtNumber(resources.cpu_percent || 0)}%`, "#2563eb")}
          ${gaugeHTML(resources.memory_percent, "内存使用率", `${fmtNumber(resources.memory_percent || 0)}%`, "#0d9488")}
          ${gaugeHTML(resources.disk_percent, "磁盘占用", `${fmtNumber(resources.disk_percent || 0)}%`, "#d97706")}
          ${gaugeHTML(
            Math.min(100, (resources.threads || 0) * 2),
            "进程线程",
            `${fmtNumber(resources.threads || 0)} 个`,
            "#7c3aed"
          )}
        </div>

        <div class="side-card">
          <h3>资源概况 <span>${esc(resources.source === "psutil" ? "psutil 实时采集" : "稳定模拟值")}</span></h3>
          <div class="kv-row"><span class="k">内存使用</span><span class="v">${fmtNumber(
            resources.memory_used_gb || 0
          )} / ${fmtNumber(resources.memory_total_gb || 0)} GB</span></div>
          <div class="kv-row"><span class="k">进程内存</span><span class="v">${fmtNumber(resources.process_rss_mb || 0)} MB</span></div>
          <div class="kv-row"><span class="k">磁盘可用</span><span class="v">${fmtNumber(resources.disk_free_gb || 0)} GB</span></div>
          <div class="kv-row"><span class="k">CPU 核心</span><span class="v">${fmtNumber(resources.cpu_count || 0)} 核</span></div>
          <div class="kv-row"><span class="k">服务运行时长</span><span class="v">${esc(resources.uptime_text || "—")}</span></div>
          <div class="kv-row"><span class="k">采样时间</span><span class="v">${fmtTime(resources.sampled_at, "time")}</span></div>
        </div>

        <div class="side-card">
          <h3>数据与通道 <span>Runtime</span></h3>
          <div class="sys-status-list">
            <div class="sys-status-row"><span class="k">WebSocket</span><span class="v" id="status-ws-value">${
              isWSConnected() ? "已连接" : "连接中 / 降级轮询"
            }</span></div>
            <div class="sys-status-row"><span class="k">最近报告</span><span class="v" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(
              reports.latest_report?.topic || "暂无"
            )}</span></div>
            <div class="sys-status-row"><span class="k">图谱数量</span><span class="v">${fmtNumber(reports.graph_count || 0)}</span></div>
            <div class="sys-status-row"><span class="k">论坛状态</span><span>${statusBadge(forum.status || "idle")}</span></div>
            <div class="sys-status-row"><span class="k">服务端时间</span><span class="v">${fmtTime(data.server_time, "time")}</span></div>
          </div>
        </div>

        <div class="side-card">
          <h3>存储路径 <span>Files</span></h3>
          <div class="tiny mono" style="color:#667085;line-height:1.9;word-break:break-all">
            runtime/apps/{app}.log<br>
            runtime/forum/latest.log<br>
            reports/{report_id}/report.md<br>
            graphs/{report_id}/graph.json<br>
            outputs/{app}/latest.txt
          </div>
        </div>
      </aside>
    </div>
  `;
  bind(el);
  loadLogs();
}

async function loadLogs() {
  const body = document.getElementById("status-log-body");
  if (!body) return;
  body.innerHTML = `<div class="ll"><span class="lt"></span><span class="lm">读取日志…</span></div>`;
  try {
    const data = await api.systemLogs(state.logApp, 160);
    state.logLines = data.lines || [];
    body.innerHTML = state.logLines.length
      ? state.logLines.map(logLineHTML).join("")
      : `<div class="ll"><span class="lt"></span><span class="lm">暂无日志</span></div>`;
    body.scrollTop = body.scrollHeight;
    const meta = document.getElementById("status-log-meta");
    if (meta) meta.textContent = data.path || (state.logApp ? `runtime/apps/${state.logApp}.log` : "runtime/system.log");
  } catch (error) {
    body.innerHTML = `<div class="ll"><span class="lt"></span><span class="lm err">日志读取失败：${esc(error.message)}</span></div>`;
  }
}

async function refresh(el) {
  if (state.refreshing) return;
  state.refreshing = true;
  try {
    const data = await api.systemStatus();
    render(el, data);
  } catch (error) {
    toast(error.message || "刷新失败", "error");
  } finally {
    state.refreshing = false;
  }
}

function bind(el) {
  document.getElementById("status-refresh")?.addEventListener("click", () => refresh(el));
  document.getElementById("status-log-refresh")?.addEventListener("click", loadLogs);
  document.getElementById("status-log-select")?.addEventListener("change", (event) => {
    state.logApp = event.target.value;
    loadLogs();
  });
  document.getElementById("status-start")?.addEventListener("click", async () => {
    try {
      await api.systemStart();
      toast("系统已启动，状态 online", "success");
      await refresh(el);
    } catch (error) {
      toast(error.message || "启动失败", "error");
    }
  });
  document.getElementById("status-shutdown")?.addEventListener("click", async () => {
    try {
      const result = await api.systemShutdown();
      toast(result.message || "系统已关闭", "success");
      await refresh(el);
    } catch (error) {
      toast(error.message || "关闭失败", "error");
    }
  });
  el.querySelectorAll("[data-status-start]").forEach((button) =>
    button.addEventListener("click", async () => {
      try {
        await api.startApp(button.dataset.statusStart, true);
        toast("应用已启动", "success");
        await refresh(el);
      } catch (error) {
        toast(error.message || "启动失败", "error");
      }
    })
  );
  el.querySelectorAll("[data-status-stop]").forEach((button) =>
    button.addEventListener("click", async () => {
      try {
        await api.stopApp(button.dataset.statusStop, true);
        toast("应用已停止", "success");
        await refresh(el);
      } catch (error) {
        toast(error.message || "停止失败", "error");
      }
    })
  );
  state.pollTimer = setInterval(() => {
    if (isWSConnected()) return;
    if (!document.getElementById("status-log-body")) return;
    refresh(el);
  }, 5000);
}

export async function renderStatus(el, params) {
  state.el = el;
  state.logApp = "";
  state.logLines = [];
  state.refreshing = false;
  el.innerHTML = loadingBlock("读取系统状态…");
  try {
    const data = await api.systemStatus();
    render(el, data);
    if (params.demo === "1") {
      // demo 模式保持在线状态，不自动关闭
    }
  } catch (error) {
    el.innerHTML = renderInlineError(error, "重新加载");
    el.querySelector("[data-retry]")?.addEventListener("click", () => renderStatus(el, params));
  }
}

export function onStatusEvent(event) {
  if (!event || !["app_status", "system_status"].includes(event.type)) return;
  if (!document.getElementById("status-log-body")) return;
  const el = document.getElementById("view");
  if (el) refresh(el);
}

export function onWSState(connState) {
  const el = document.getElementById("status-ws-value");
  if (el) el.textContent = connState === "live" ? "已连接" : "连接中 / 降级轮询";
  if (connState === "live" && document.getElementById("status-log-body")) {
    if (state.wsRefreshTimer) clearTimeout(state.wsRefreshTimer);
    state.wsRefreshTimer = setTimeout(() => {
      state.wsRefreshTimer = null;
      const view = document.getElementById("view");
      if (view && document.getElementById("status-log-body")) refresh(view);
    }, 500);
  }
}

export function cleanupStatus() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  if (state.wsRefreshTimer) clearTimeout(state.wsRefreshTimer);
  state.pollTimer = null;
  state.wsRefreshTimer = null;
}
