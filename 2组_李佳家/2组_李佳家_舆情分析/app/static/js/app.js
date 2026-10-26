import { api, connectWS, isWSConnected } from "./api.js";
import { icon, renderInlineError, statusMeta, toast } from "./ui.js";
import * as consoleView from "./views/console.js";
import * as searchView from "./views/search.js";
import * as forumView from "./views/forum.js";
import * as graphView from "./views/graph.js";
import * as configView from "./views/config.js";
import * as statusView from "./views/status.js";

const ROUTES = {
  console: { title: "控制台", root: "工作台", render: consoleView.renderConsole },
  search: { title: "主题检索", root: "分析", render: searchView.renderSearch },
  forum: { title: "论坛监控", root: "采集", render: forumView.renderForum },
  graph: { title: "图谱查看", root: "分析", render: graphView.renderGraph },
  config: { title: "配置管理", root: "管理", render: configView.renderConfig },
  status: { title: "系统状态", root: "管理", render: statusView.renderStatus },
};

const viewEl = document.getElementById("view");
let current = { name: "", module: null, params: {} };
let shellTimer = null;
let lastStatus = null;
let refreshingShell = false;

function parseHash() {
  const raw = (location.hash || "").replace(/^#\/?/, "");
  if (!raw) return { name: "console", params: {} };
  const [name, query = ""] = raw.split("?");
  return { name: name || "console", params: Object.fromEntries(new URLSearchParams(query)) };
}

function pathRoute() {
  if (location.pathname === "/graph-viewer" || location.pathname === "/graph-viewer/") {
    return { name: "graph", params: { viewer: "1" } };
  }
  if (location.pathname.startsWith("/graph-viewer/")) {
    const parts = location.pathname.split("/").filter(Boolean);
    const queryParams = Object.fromEntries(new URLSearchParams(location.search));
    return {
      name: "graph",
      params: { viewer: "1", report_id: decodeURIComponent(parts[1] || ""), ...queryParams },
    };
  }
  return null;
}

function normalizePath() {
  if (location.pathname.startsWith("/graph-viewer") && location.hash.startsWith("#/")) {
    history.replaceState(null, "", `/${location.hash}`);
  }
}

function runCleanup() {
  if (current.name === "search") searchView.cleanupSearch();
  if (current.name === "forum") forumView.cleanupForum();
  if (current.name === "status") statusView.cleanupStatus();
  if (current.name === "graph") graphView.cleanupGraph();
}

function setActiveNav(name) {
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.route === name);
  });
}

async function renderRoute() {
  normalizePath();
  const route = pathRoute() || parseHash();
  const name = ROUTES[route.name] ? route.name : "console";
  const params = route.params || {};
  if (name === current.name && current.renderedPath === `${location.pathname}${location.hash}`) {
    return;
  }
  runCleanup();
  current = { name, module: ROUTES[name], params, renderedPath: `${location.pathname}${location.hash}` };
  setActiveNav(name);
  const crumbRoot = document.getElementById("crumb-root");
  const crumbPage = document.getElementById("crumb-page");
  if (crumbRoot) crumbRoot.textContent = ROUTES[name].root;
  if (crumbPage) crumbPage.textContent = ROUTES[name].title;
  document.title = `${ROUTES[name].title} · 舆情分析平台`;
  if (location.hash !== "#/search?demo=1") window.scrollTo({ top: 0 });
  viewEl.innerHTML = `<div class="page-loading"><div class="spinner"></div><span>正在加载${ROUTES[name].title}…</span></div>`;
  try {
    await ROUTES[name].render(viewEl, params);
  } catch (error) {
    viewEl.innerHTML = `<div style="padding:20px">${renderInlineError(error, "重新加载")}</div>`;
    viewEl.querySelector("[data-retry]")?.addEventListener("click", () => {
      current = { name: "", module: null, params: {} };
      renderRoute();
    });
    toast(error.message || "页面加载失败", "error");
  }
  refreshShell();
}

function updateWSState(connState) {
  const el = document.getElementById("ws-state");
  if (!el) return;
  el.classList.remove("live", "down");
  if (connState === "live") {
    el.classList.add("live");
    el.querySelector("span").textContent = "实时连接";
  } else if (connState === "connecting") {
    el.querySelector("span").textContent = "连接中";
  } else {
    el.classList.add("down");
    el.querySelector("span").textContent = "轮询模式";
  }
  if (current.name === "forum") forumView.onWSState?.(connState);
  if (current.name === "status") statusView.onWSState?.(connState);
}

function updateSidebar(status) {
  consoleView.updateShell(status);
}

async function refreshShell() {
  if (refreshingShell) return;
  refreshingShell = true;
  try {
    const status = await api.getStatus();
    lastStatus = status;
    updateSidebar(status);
    updateWSState(isWSConnected() ? "live" : "down");
  } catch (error) {
    const pill = document.getElementById("sys-pill");
    if (pill) {
      pill.className = "sys-pill offline";
      pill.innerHTML = `<i class="dot"></i><span>服务不可用</span>`;
    }
  } finally {
    refreshingShell = false;
  }
}

function scheduleShellRefresh() {
  if (shellTimer) clearTimeout(shellTimer);
  shellTimer = setTimeout(() => {
    shellTimer = null;
    refreshShell();
  }, 600);
}

function handleEvent(event) {
  if (!event || event.type === "ping") return;
  if (["app_status", "system_status"].includes(event.type)) {
    scheduleShellRefresh();
  }
  if (current.name === "console") consoleView.onConsoleEvent(event);
  if (current.name === "forum") forumView.onForumEvent(event);
  if (current.name === "status") statusView.onStatusEvent(event);
  if (event.type === "graph_ready") {
    if (current.name === "graph") {
      graphView.renderGraph(viewEl, current.params);
    } else if (current.name === "search") {
      toast(`图谱已生成：${event.node_count} 节点 / ${event.edge_count} 关系`, "success");
    }
  }
  if (event.type === "error") {
    toast(`${event.module_name || "system"}：${event.error_message || "发生错误"}`, "error", 5000);
  }
}

function startClock() {
  const clock = document.getElementById("clock");
  const tick = () => {
    if (!clock) return;
    const now = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    clock.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  };
  tick();
  setInterval(tick, 1000);
}

function startFallbackPolling() {
  setInterval(async () => {
    if (isWSConnected()) return;
    await refreshShell();
    if (current.name === "console") consoleView.onConsoleEvent({ type: "system_status" });
  }, 5000);
}

async function boot() {
  startClock();
  window.addEventListener("hashchange", renderRoute);
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.addEventListener("click", (event) => {
      if (location.pathname.startsWith("/graph-viewer")) {
        // 让 hash 路由生效，同时把路径还原为单页入口
        const href = item.getAttribute("href");
        event.preventDefault();
        history.replaceState(null, "", `/${href}`);
        renderRoute();
      }
    });
  });
  await renderRoute();
  connectWS({ onEvent: handleEvent, onState: updateWSState });
  startFallbackPolling();
}

boot();
