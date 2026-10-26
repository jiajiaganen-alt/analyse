import { api } from "../api.js";
import {
  esc,
  fmtNumber,
  fmtTime,
  icon,
  loadingBlock,
  openLogModal,
  renderInlineError,
  statusBadge,
  statusMeta,
  toast,
} from "../ui.js";

let refreshTimer = null;

function appCard(app) {
  const meta = statusMeta(app.status);
  const canStart = !["running", "starting", "stopping"].includes(app.status);
  const canStop = ["running", "starting"].includes(app.status) && app.status !== "stopping";
  const summary = app.output_summary
    ? esc(app.output_summary)
    : `<span class="placeholder">暂无输出，启动应用并执行任务后生成</span>`;
  return `
    <article class="app-card ${esc(app.status)}" data-app="${esc(app.app_name)}">
      <div class="app-head">
        <span class="app-icon ${esc(app.icon)}">${icon(
          app.icon === "search" ? "search" : app.icon === "media" ? "activity" : app.icon === "insight" ? "target" : app.icon === "forum" ? "users" : "file"
        )}</span>
        <div class="app-titles">
          <h4>${esc(app.display_name)} <code>${esc(app.app_name)}</code></h4>
        </div>
        <span class="app-badge" data-role="app-badge">${statusBadge(app.status)}</span>
      </div>
      <p class="app-desc">${esc(app.description)}</p>
      <div class="app-output">
        <div class="lbl"><span>最近输出</span><span data-role="output-time">${
          app.last_output_at ? fmtTime(app.last_output_at, "hm") : "—"
        }</span></div>
        <div class="txt ${app.output_summary ? "" : "placeholder"}" data-role="output-text">${summary}</div>
      </div>
      <div class="app-foot">
        <span class="app-meta" data-role="task-count">任务 ${fmtNumber(app.task_count)} · ${
          app.started_at ? "启动 " + fmtTime(app.started_at, "hm") : "未启动"
        }</span>
        <div class="app-actions">
          <button class="btn btn-primary btn-sm" data-action="start" data-app="${esc(app.app_name)}" ${
            canStart ? "" : "disabled"
          }>启动</button>
          <button class="btn btn-sm" data-action="stop" data-app="${esc(app.app_name)}" ${
            canStop ? "" : "disabled"
          }>停止</button>
          <button class="btn btn-link" data-action="log" data-app="${esc(app.app_name)}" data-name="${esc(
            app.display_name
          )}">日志</button>
        </div>
      </div>
    </article>
  `;
}

function errorsPanel(status) {
  const errors = status.recent_errors || [];
  if (!errors.length) {
    const warnings = (status.apps || []).filter((app) => ["failed", "stopping"].includes(app.status));
    if (!warnings.length) {
      return `<div class="empty" style="padding:22px 16px">${icon("shield")}<div>暂无错误记录，运行状态正常</div>
        <div class="tiny" style="margin-top:3px">错误会写入 runtime/system.log 并实时推送 error 事件</div></div>`;
    }
    return `<div class="warn-list">${warnings
      .map(
        (app) =>
          `<div class="warn-item"><span class="dot"></span>${esc(app.display_name)} 当前状态为 ${
            statusMeta(app.status).label
          }</div>`
      )
      .join("")}</div>`;
  }
  return `<div class="error-list">${errors
    .slice(0, 4)
    .map(
      (item) => `
      <div class="error-item">
        <span class="error-icon">${icon("alert")}</span>
        <div class="error-body">
          <div class="msg">${esc(item.error_message || item.message || "")}</div>
          <div class="meta"><span>${esc(item.module_name || "system")}</span><span>${esc(
        item.time_label || fmtTime(item.time, "time")
      )}</span></div>
        </div>
      </div>`
    )
    .join("")}</div>`;
}

function render(el, status) {
  const system = status.system || {};
  const apps = status.apps || [];
  const running = apps.filter((app) => app.status === "running").length;
  const forum = status.forum || {};
  const reports = status.reports || {};
  const latest = reports.latest_report;
  const resources = status.resources || {};
  const online = system.system_status === "online";

  const appCards = apps.map(appCard).join("");
  const latestGraph = latest && latest.has_graph;

  el.innerHTML = `
    <section class="hero">
      <div class="hero-main">
        <div class="hero-eyebrow"><i class="live"></i> SYSTEM ${esc(
          (system.system_status || "unknown").toUpperCase()
        )} · AGENT PIPELINE ONLINE</div>
        <h2>${online ? "系统运行中" : system.status_label || "系统未上线"}</h2>
        <p>已运行 <b>${running} / ${apps.length}</b> 个单功能应用 · 系统运行 <b>${esc(
    system.uptime_text || "—"
  )}</b> · 最近报告 <b>${esc(latest ? latest.topic : "暂无，去发起一次主题检索")}</b></p>
      </div>
      <div class="hero-right">
        <div class="hero-stats">
          <div class="hero-stat"><div class="v">${running}<small>/ ${apps.length}</small></div><div class="k">运行应用</div></div>
          <div class="hero-stat"><div class="v">${fmtNumber(forum.today_count || 0)}<small>条</small></div><div class="k">今日论坛日志</div></div>
          <div class="hero-stat"><div class="v">${fmtNumber(reports.report_count || 0)}<small>份</small></div><div class="k">已生成报告</div></div>
        </div>
        <div class="hero-actions">
          <a class="btn btn-primary" href="#/search">${icon("search")} 发起主题检索</a>
          <button class="btn btn-ghost" data-action="refresh">${icon("refresh")} 刷新状态</button>
        </div>
      </div>
    </section>

    <div class="console-grid">
      <div>
        <div class="section-label"><h3>单功能应用</h3><span>独立状态机 · 独立日志与最近输出</span></div>
        <div class="app-grid" id="app-grid">${appCards}</div>

        <div class="card" style="margin-top:16px">
          <div class="card-head">
            <h3>${icon("alert")} 最近错误</h3>
            <span class="hint">data/runtime · 最近 ${Math.min(4, (status.recent_errors || []).length)} 条</span>
          </div>
          <div class="card-body" style="padding:8px 18px">${errorsPanel(status)}</div>
        </div>
      </div>

      <aside>
        <div class="side-card">
          <h3>系统资源 <span>${esc(resources.source === "psutil" ? "psutil 实时" : "模拟值")}</span></h3>
          <div class="res-metric">
            <div class="res-line"><span>服务 CPU 占用</span><b>${fmtNumber(resources.cpu_percent || 0)}%</b></div>
            <div class="progress"><i style="width:${Math.min(100, resources.cpu_percent || 0)}%"></i></div>
          </div>
          <div class="res-metric">
            <div class="res-line"><span>内存使用率</span><b>${fmtNumber(resources.memory_percent || 0)}%</b></div>
            <div class="progress green"><i style="width:${Math.min(100, resources.memory_percent || 0)}%"></i></div>
          </div>
          <div class="res-metric">
            <div class="res-line"><span>运行线程 / 进程内存</span><b>${fmtNumber(resources.threads || 0)} / ${fmtNumber(
    resources.process_rss_mb || 0
  )} MB</b></div>
            <div class="progress"><i style="width:${Math.min(100, (resources.threads || 0) * 2)}%"></i></div>
          </div>
          <div class="kv-row" style="margin-top:8px"><span class="k">系统运行时长</span><span class="v">${esc(
            system.uptime_text || "—"
          )}</span></div>
          <div class="kv-row"><span class="k">采样时间</span><span class="v">${fmtTime(resources.sampled_at, "time")}</span></div>
        </div>

        <div class="side-card">
          <h3>运行状态 <span>Console</span></h3>
          <div class="sys-status-list">
            <div class="sys-status-row"><span class="k"><i class="dot ${esc(
              system.system_status
            )}"></i>系统服务</span>${statusBadge(system.system_status, system.status_label)}</div>
            <div class="sys-status-row"><span class="k"><i class="dot ${forum.status === "running" ? "running" : "stopped"}"></i>论坛采集</span>${statusBadge(
    forum.status || "idle"
  )}</div>
            <div class="sys-status-row"><span class="k"><i class="dot running"></i>实时通道</span><span class="v">WebSocket 优先</span></div>
            <div class="sys-status-row"><span class="k">今日论坛日志</span><span class="v">${fmtNumber(
              forum.today_count || 0
            )} 条</span></div>
            <div class="sys-status-row"><span class="k">最近错误</span><span class="v">${fmtNumber(
              (status.recent_errors || []).length
            )} 条</span></div>
          </div>
        </div>

        <div class="side-card">
          <h3>数据资产 <span>Reports</span></h3>
          ${
            latest
              ? `<div class="kv-row"><span class="k">最新报告</span><span class="v" style="max-width:190px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(
                  latest.topic
                )}</span></div>
                 <div class="kv-row"><span class="k">报告编号</span><span class="v mono" style="font-size:9px">${esc(
                   latest.report_id
                 )}</span></div>
                 <div class="kv-row"><span class="k">来源 / 证据</span><span class="v">${fmtNumber(
                   latest.source_count || 0
                 )} / ${fmtNumber(latest.evidence_count || 0)}</span></div>
                 <div class="kv-row"><span class="k">图谱文件</span><span class="v">${
                   latest.has_graph ? "已生成" : "未生成"
                 }</span></div>
                 <div style="display:flex;gap:7px;margin-top:10px">
                   ${latestGraph ? `<a class="btn btn-sm" href="#/graph?report=${esc(latest.report_id)}">${icon("graph")} 查看图谱</a>` : ""}
                   <a class="btn btn-sm" href="#/search">${icon("search")} 新检索</a>
                 </div>`
              : `<div class="empty" style="padding:8px 0">${icon("file")}<div>暂无报告</div></div>`
          }
        </div>

        <div class="side-card">
          <h3>快捷入口 <span>Shortcuts</span></h3>
          <div class="quick-actions">
            <a href="#/forum">${icon("terminal")} 论坛日志</a>
            <a href="#/graph">${icon("graph")} 图谱查看</a>
            <a href="#/config">${icon("settings")} 配置管理</a>
            <a href="/docs" target="_blank" rel="noopener">${icon("file")} 接口文档</a>
          </div>
        </div>
      </aside>
    </div>
  `;

  bind(el);
}

function bind(el) {
  el.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", async () => {
      const action = button.dataset.action;
      if (action === "refresh") {
        await refresh(el);
        return;
      }
      if (action === "log") {
        await openLogModal(button.dataset.app, button.dataset.name || button.dataset.app);
        return;
      }
      const appName = button.dataset.app;
      if (!appName) return;
      const original = button.textContent;
      button.disabled = true;
      button.textContent = action === "start" ? "启动中…" : "停止中…";
      try {
        const result = action === "start" ? await api.startApp(appName, true) : await api.stopApp(appName, true);
        toast(result.message || "操作完成", "success");
      } catch (error) {
        toast(error.message || "操作失败", "error");
        button.disabled = false;
        button.textContent = original;
        return;
      }
      await refresh(document.getElementById("view"));
    });
  });
}

async function refresh(el) {
  if (!el) return;
  try {
    const status = await api.getStatus();
    render(el, status);
    updateShell(status);
  } catch (error) {
    toast(error.message || "刷新失败", "error");
  }
}

export function updateShell(status) {
  const system = status.system || {};
  const apps = status.apps || [];
  const running = apps.filter((app) => app.status === "running").length;
  const badge = document.getElementById("side-system-badge");
  if (badge) {
    badge.className = `badge badge-${statusMeta(system.system_status).cls}`;
    badge.innerHTML = `<i class="dot ${statusMeta(system.system_status).cls}"></i>${esc(
      system.status_label || ""
    )}`;
  }
  const runningEl = document.getElementById("side-running-apps");
  if (runningEl) runningEl.textContent = `${running} / ${apps.length}`;
  const progressEl = document.getElementById("side-app-progress");
  if (progressEl) progressEl.style.width = `${apps.length ? (running / apps.length) * 100 : 0}%`;
  const pill = document.getElementById("sys-pill");
  if (pill) {
    pill.className = `sys-pill ${system.system_status || ""}`;
    pill.innerHTML = `<i class="dot"></i><span>${esc(system.platform_name || "舆情分析平台")} · ${esc(
      system.status_label || ""
    )}</span>`;
  }
  const wsEl = document.getElementById("side-ws");
  if (wsEl) wsEl.textContent = `${system.ws_clients || 0} 个客户端`;
}

export async function renderConsole(el, params) {
  el.innerHTML = loadingBlock("加载控制台状态…");
  let status;
  try {
    status = await api.getStatus();
  } catch (error) {
    el.innerHTML = renderInlineError(error, "重新加载");
    el.querySelector("[data-retry]")?.addEventListener("click", () => renderConsole(el, params));
    return;
  }
  if (params.demo === "1") {
    const todo = (status.apps || []).filter(
      (app) => app.enabled && !["running", "starting"].includes(app.status)
    );
    if (status.system.system_status === "offline") {
      try {
        await api.systemStart();
      } catch (error) {
        /* ignore */
      }
    }
    if (todo.length) {
      await Promise.all(todo.map((app) => api.startApp(app.app_name, true).catch(() => null)));
      try {
        status = await api.getStatus();
      } catch (error) {
        /* keep previous */
      }
    }
  }
  if (!document.getElementById("view") || document.getElementById("view") !== el) return;
  render(el, status);
  updateShell(status);
}

export function onConsoleEvent(event) {
  if (!event || !["app_status", "system_status"].includes(event.type)) return;
  if (!document.querySelector(".console-grid")) return;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = setTimeout(() => {
    refreshTimer = null;
    const el = document.getElementById("view");
    if (el) refresh(el);
  }, 700);
}
