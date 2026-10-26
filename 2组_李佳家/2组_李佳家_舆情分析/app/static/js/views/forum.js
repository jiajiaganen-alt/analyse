import { api, isWSConnected } from "../api.js";
import { esc, fmtTime, icon, loadingBlock, renderInlineError, statusBadge, toast } from "../ui.js";

const state = {
  records: [],
  status: "idle",
  appStatus: "stopped",
  snapshot: null,
  stats: null,
  pollTimer: null,
  history: null,
  historyDate: "",
  busy: false,
  autoScroll: true,
};

function todayString() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function lineHTML(record) {
  const level = String(record.level || "INFO").toLowerCase();
  const status = record.task_status || "running";
  return `<div class="tline" data-seq="${esc(record.seq || "")}">
    <span class="t-time">${fmtTime(record.time, "time")}</span>
    <span class="t-level ${level}">${esc((record.level || "INFO").toUpperCase())}</span>
    <span class="t-event" title="${esc(record.event_type || "")}">${esc(record.event_type || "collect")}</span>
    <span class="t-msg">${esc(record.message || record.message_text || "")}</span>
    <span class="t-status ${status === "running" ? "" : "stopped"}">${esc(status)}</span>
  </div>`;
}

function shellHTML() {
  return `
    <div class="page-head">
      <div>
        <h1 class="page-title">论坛监控</h1>
        <p class="page-sub">启动论坛采集后，后台线程每 1.5-3 秒模拟抓取一条帖子并写入实时日志；停止后线程退出，历史日志按日期归档。</p>
      </div>
      <div class="page-actions">
        <span class="forum-state"><span class="label">采集状态</span><span id="forum-status-badge">${statusBadge(
          "idle"
        )}</span></span>
        <button class="btn btn-primary btn-sm" id="forum-start">${icon("play")} 启动采集</button>
        <button class="btn btn-sm" id="forum-stop">${icon("stop")} 停止采集</button>
        <button class="btn btn-sm" id="forum-refresh">${icon("refresh")} 刷新</button>
      </div>
    </div>

    <div class="forum-stats">
      <div class="stat-card"><div class="k">${icon("terminal")} 今日日志</div><div class="v" id="stat-today">0 <small>条</small></div><div class="sub" id="stat-today-sub">等待采集启动</div></div>
      <div class="stat-card"><div class="k">${icon("activity")} 采集批次</div><div class="v" id="stat-batch">0 <small>批</small></div><div class="sub" id="stat-batch-sub">间隔 1.5-3.0 秒</div></div>
      <div class="stat-card"><div class="k">${icon("alert")} 告警 / 错误</div><div class="v" id="stat-errors">0 <small>条</small></div><div class="sub">写入日志级别 WARN / ERROR</div></div>
      <div class="stat-card"><div class="k">${icon("clock")} 最近更新</div><div class="v" id="stat-last" style="font-size:16px">—</div><div class="sub" id="stat-last-sub">latest.log</div></div>
    </div>

    <div class="forum-grid">
      <div>
        <div class="terminal-card">
          <div class="terminal-head">
            <span class="lights"><i></i><i></i><i></i></span>
            <span class="t-title">runtime/forum/latest.log</span>
            <span class="t-right" id="terminal-meta">tail -f · 实时推送</span>
            <button class="btn btn-sm" id="terminal-scroll" style="height:22px;margin-left:8px;background:#17243a;border-color:#22324a;color:#94a3b8">滚动到底部</button>
          </div>
          <div class="terminal" id="forum-terminal">
            <div class="terminal-empty"><span class="cursor"></span><span>正在读取论坛采集日志…</span></div>
          </div>
        </div>
        <div class="tiny muted" style="margin-top:7px;display:flex;gap:12px">
          <span>日志文件：runtime/forum/latest.log</span>
          <span>历史归档：runtime/forum/history/{YYYY-MM-DD}.json</span>
          <span style="margin-left:auto">WebSocket 优先 · 断线自动降级轮询</span>
        </div>
      </div>

      <aside class="forum-side">
        <div class="side-card">
          <h3>历史日志查询 <span>按日期归档</span></h3>
          <div class="date-row">
            <input type="date" id="history-date" value="${todayString()}">
            <button class="btn btn-sm btn-primary" id="history-query">查询</button>
          </div>
          <div class="tiny muted" id="history-meta" style="margin-bottom:7px">选择日期查询 runtime/forum/history 下的归档记录</div>
          <div class="history-list" id="history-list"><div class="empty" style="padding:12px">尚未查询</div></div>
        </div>

        <div class="side-card">
          <h3>采集参数 <span>config.json</span></h3>
          <div class="sys-status-list">
            <div class="sys-status-row"><span class="k">采集间隔</span><span class="v" id="cfg-interval">1.5 - 3.0 秒</span></div>
            <div class="sys-status-row"><span class="k">单批条数</span><span class="v" id="cfg-batch">4 条</span></div>
            <div class="sys-status-row"><span class="k">日志写入</span><span class="v">JSON Lines</span></div>
            <div class="sys-status-row"><span class="k">历史归档</span><span class="v">按日期 JSON</span></div>
          </div>
          <div class="tiny muted" style="margin-top:8px">关键词</div>
          <div class="chips" style="margin-top:5px" id="cfg-keywords"></div>
        </div>

        <div class="side-card">
          <h3>任务状态 <span>forum_collector</span></h3>
          <div class="sys-status-list">
            <div class="sys-status-row"><span class="k">应用状态</span><span id="forum-app-badge">${statusBadge(
              "stopped"
            )}</span></div>
            <div class="sys-status-row"><span class="k">采集任务</span><span id="forum-task-status" class="v">idle</span></div>
            <div class="sys-status-row"><span class="k">启动时间</span><span class="v" id="forum-started">—</span></div>
            <div class="sys-status-row"><span class="k">最近日志</span><span class="v" id="forum-last">—</span></div>
          </div>
          <div class="tiny muted" id="forum-last-error" style="margin-top:8px;color:#b42318"></div>
        </div>
      </aside>
    </div>
  `;
}

function updateStatusUI() {
  const badge = document.getElementById("forum-status-badge");
  if (badge) badge.innerHTML = statusBadge(state.status === "running" ? "running" : state.status);
  const appBadge = document.getElementById("forum-app-badge");
  if (appBadge) appBadge.innerHTML = statusBadge(state.appStatus);
  const task = document.getElementById("forum-task-status");
  if (task) task.textContent = state.status;
  const start = document.getElementById("forum-start");
  const stop = document.getElementById("forum-stop");
  if (start) start.disabled = state.status === "running" || state.busy;
  if (stop) stop.disabled = state.status !== "running" || state.busy;
  const snapshot = state.snapshot || {};
  const interval = document.getElementById("cfg-interval");
  if (interval && snapshot.interval) interval.textContent = `${snapshot.interval[0]} - ${snapshot.interval[1]} 秒`;
  const keywords = document.getElementById("cfg-keywords");
  if (keywords && snapshot.keywords) {
    keywords.innerHTML = snapshot.keywords
      .slice(0, 8)
      .map((keyword) => `<span class="chip">${esc(keyword)}</span>`)
      .join("");
  }
  const started = document.getElementById("forum-started");
  if (started) started.textContent = snapshot.started_at ? fmtTime(snapshot.started_at, "datetime") : "—";
  const last = document.getElementById("forum-last");
  if (last) last.textContent = snapshot.last_time ? fmtTime(snapshot.last_time, "short") : "—";
  const lastError = document.getElementById("forum-last-error");
  if (lastError) lastError.textContent = snapshot.last_error ? `最近错误：${snapshot.last_error}` : "";
}

function updateStats() {
  const stats = state.stats || {};
  const snapshot = state.snapshot || {};
  const today = document.getElementById("stat-today");
  if (today) today.innerHTML = `${snapshot.today_count || state.records.length || 0} <small>条</small>`;
  const todaySub = document.getElementById("stat-today-sub");
  if (todaySub)
    todaySub.textContent = state.records.length ? `最新 ${fmtTime(state.records[state.records.length - 1].time, "hm")}` : "等待采集启动";
  const batch = document.getElementById("stat-batch");
  if (batch) batch.innerHTML = `${snapshot.batch || 0} <small>批</small>`;
  const batchSub = document.getElementById("stat-batch-sub");
  if (batchSub && snapshot.interval) batchSub.textContent = `间隔 ${snapshot.interval[0]}-${snapshot.interval[1]} 秒`;
  const errors = document.getElementById("stat-errors");
  if (errors) errors.innerHTML = `${stats.errors || 0} <small>条</small>`;
  const last = document.getElementById("stat-last");
  if (last && state.records.length)
    last.textContent = fmtTime(state.records[state.records.length - 1].time, "time");
  const meta = document.getElementById("terminal-meta");
  if (meta) meta.textContent = `${state.records.length} 条 · tail -f · ${isWSConnected() ? "WebSocket" : "轮询"}`;
}

function paintTerminal() {
  const terminal = document.getElementById("forum-terminal");
  if (!terminal) return;
  if (!state.records.length) {
    terminal.innerHTML = `<div class="terminal-empty"><span class="cursor"></span><span>暂无日志，点击「启动采集」开始模拟抓取</span></div>`;
    return;
  }
  terminal.innerHTML = state.records.map(lineHTML).join("");
  if (state.autoScroll) terminal.scrollTop = terminal.scrollHeight;
}

function renderRecords() {
  paintTerminal();
  updateStats();
  updateStatusUI();
}

function appendRecord(record) {
  if (!record) return;
  const key = `${record.seq || ""}|${record.time || ""}|${record.message || ""}`;
  if (
    state.records.some(
      (item) => `${item.seq || ""}|${item.time || ""}|${item.message || ""}` === key
    )
  ) {
    return;
  }
  state.records.push(record);
  if (state.records.length > 240) state.records = state.records.slice(-240);
  if (state.snapshot) {
    state.snapshot.today_count = Math.max(state.snapshot.today_count || 0, state.records.length);
  }
  const terminal = document.getElementById("forum-terminal");
  if (!terminal) return;
  if (state.records.length === 1) terminal.innerHTML = "";
  terminal.insertAdjacentHTML("beforeend", lineHTML(record));
  while (terminal.children.length > 240) terminal.removeChild(terminal.firstElementChild);
  if (state.autoScroll) terminal.scrollTop = terminal.scrollHeight;
  updateStats();
}

async function refreshAll(el) {
  const [log, status] = await Promise.all([api.forumLog(160), api.getStatus()]);
  state.records = log.records || [];
  state.status = log.status || "idle";
  state.snapshot = status.forum || {};
  state.stats = log.stats || {};
  const app = (status.apps || []).find((item) => item.app_name === "forum_collector");
  state.appStatus = app ? app.status : "stopped";
  renderRecords();
  const lastError = document.getElementById("forum-last-error");
  if (lastError && state.snapshot.last_error) lastError.textContent = `最近错误：${state.snapshot.last_error}`;
  return log;
}

async function queryHistory() {
  const input = document.getElementById("history-date");
  const date = (input && input.value) || todayString();
  const meta = document.getElementById("history-meta");
  const list = document.getElementById("history-list");
  if (meta) meta.textContent = "查询中…";
  try {
    const data = await api.forumHistory(date);
    state.history = data;
    state.historyDate = date;
    if (meta) {
      meta.innerHTML = `${esc(date)} · ${data.count} 条记录 · <span class="mono">${esc(data.path)}</span>`;
    }
    if (list) {
      if (!data.records.length) {
        list.innerHTML = `<div class="empty" style="padding:12px">该日期暂无归档记录</div>`;
      } else {
        list.innerHTML = data.records
          .slice(-14)
          .reverse()
          .map(
            (record) => `<div class="history-item">
              <div class="ht"><span>${fmtTime(record.time, "hm")}</span><span>${esc(record.event_type || "")}</span><span>${esc(
                record.task_status || ""
              )}</span></div>
              <div class="hm">${esc(record.message || "")}</div>
            </div>`
          )
          .join("");
      }
    }
  } catch (error) {
    if (meta) meta.textContent = `查询失败：${error.message}`;
    if (list) list.innerHTML = `<div class="empty" style="padding:12px">${esc(error.message)}</div>`;
  }
}

function bind(el) {
  document.getElementById("forum-start")?.addEventListener("click", async () => {
    state.busy = true;
    updateStatusUI();
    try {
      const result = await api.forumStart();
      toast(result.message || "论坛采集已启动", "success");
      await refreshAll(el);
      await queryHistory();
    } catch (error) {
      toast(error.message || "启动失败", "error", 5000);
    } finally {
      state.busy = false;
      updateStatusUI();
    }
  });
  document.getElementById("forum-stop")?.addEventListener("click", async () => {
    state.busy = true;
    updateStatusUI();
    try {
      const result = await api.forumStop();
      toast(result.message || "论坛采集已停止", "success");
      await refreshAll(el);
      await queryHistory();
    } catch (error) {
      toast(error.message || "停止失败", "error");
    } finally {
      state.busy = false;
      updateStatusUI();
    }
  });
  document.getElementById("forum-refresh")?.addEventListener("click", async () => {
    try {
      await refreshAll(el);
      toast("已刷新论坛日志", "success");
    } catch (error) {
      toast(error.message || "刷新失败", "error");
    }
  });
  document.getElementById("history-query")?.addEventListener("click", queryHistory);
  document.getElementById("terminal-scroll")?.addEventListener("click", () => {
    const terminal = document.getElementById("forum-terminal");
    if (terminal) terminal.scrollTop = terminal.scrollHeight;
    state.autoScroll = true;
  });
  const terminal = document.getElementById("forum-terminal");
  if (terminal) {
    terminal.addEventListener("scroll", () => {
      const nearBottom = terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 50;
      state.autoScroll = nearBottom;
    });
  }
  state.pollTimer = setInterval(async () => {
    if (isWSConnected()) return;
    if (!document.getElementById("forum-terminal")) return;
    try {
      const data = await api.forumLog(160);
      state.records = data.records || [];
      state.status = data.status || state.status;
      state.stats = data.stats || state.stats;
      renderRecords();
    } catch (error) {
      /* 静默降级失败 */
    }
  }, 3000);
}

export async function renderForum(el, params) {
  state.records = [];
  state.status = "idle";
  state.history = null;
  state.busy = false;
  el.innerHTML = shellHTML();
  const terminal = document.getElementById("forum-terminal");
  if (terminal) terminal.innerHTML = `<div class="terminal-empty"><span class="cursor"></span><span>正在连接论坛采集日志…</span></div>`;
  bind(el);
  try {
    await refreshAll(el);
  } catch (error) {
    el.innerHTML = renderInlineError(error, "重新加载");
    el.querySelector("[data-retry]")?.addEventListener("click", () => renderForum(el, params));
    return;
  }
  if (params.demo === "1") {
    try {
      await api.forumStart();
    } catch (error) {
      toast(error.message || "演示模式启动论坛采集失败", "warn");
    }
    try {
      await refreshAll(el);
    } catch (error) {
      /* ignore */
    }
  }
  queryHistory();
}

export function onForumEvent(event) {
  if (!event || !document.getElementById("forum-terminal")) return;
  if (event.type === "forum_log") {
    appendRecord({
      time: event.time,
      event_type: event.event_type,
      message: event.message_text,
      task_status: event.task_status,
      level: event.level,
      seq: event.seq,
    });
    if (event.task_status) state.status = event.task_status;
    updateStatusUI();
  } else if (event.type === "app_status" && event.app_name === "forum_collector") {
    state.appStatus = event.status;
    updateStatusUI();
  }
}

export function onWSState() {
  updateStats();
}

export function cleanupForum() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}
