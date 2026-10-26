import { api } from "./api.js";

const ICONS = {
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/>',
  play: '<path d="M8 5.5v13l11-6.5L8 5.5Z"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
  log: '<path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5"/>',
  terminal: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M13 15h4"/>',
  graph: '<circle cx="6" cy="6" r="2.4"/><circle cx="18" cy="7" r="2.4"/><circle cx="12" cy="17.5" r="2.4"/><path d="M8.1 7.2 15.8 7M7.3 8.1l3.4 7.3M16.8 9l-3.4 6.4"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l2-2a5 5 0 0 0-7-7l-1.2 1.2"/><path d="M14 11a5 5 0 0 0-7.5-.5l-2 2a5 5 0 0 0 7 7l1.2-1.2"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8L3 5Z"/>',
  alert: '<path d="M12 3 2.8 19h18.4L12 3Z"/><path d="M12 9v4M12 16.2v.2"/>',
  check: '<path d="m4 12 5 5L20 6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  cpu: '<rect x="7" y="7" width="10" height="10" rx="2"/><path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3"/>',
  memory: '<path d="M4 8h16v8H4z"/><path d="M7 8V5M12 8V5M17 8V5M7 16v3M12 16v3M17 16v3M4 12h16"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  activity: '<path d="M3 12h4l2.2-6 3.6 12 2.2-6h6"/>',
  layers: '<path d="m12 3 9 5-9 5-9-5 9-5Z"/><path d="m3 12 9 5 9-5M3 16l9 5 9-5"/>',
  zoomIn: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21M10.5 8v5M8 10.5h5"/>',
  zoomOut: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21M8 10.5h5"/>',
  reset: '<path d="M4 4v6h6"/><path d="M20 20v-6h-6"/><path d="M20 9A8 8 0 0 0 6.2 5.2L4 10M4 15a8 8 0 0 0 13.8 3.8L20 14"/>',
  arrowRight: '<path d="M4 12h15M14 7l5 5-5 5"/>',
  database: '<ellipse cx="12" cy="5.5" rx="8" ry="3"/><path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  users: '<circle cx="9" cy="8" r="3"/><path d="M3 20a6 6 0 0 1 12 0"/><path d="M16 5.5a3 3 0 0 1 0 5.8M17.5 14.5A5 5 0 0 1 21 20"/>',
  shield: '<path d="M12 3 5 6v5.5c0 4.3 3 8 7 9.5 4-1.5 7-5.2 7-9.5V6l-7-3Z"/><path d="m9 12 2 2 4-4"/>',
  file: '<path d="M6 3h8l4 4v14H6V3Z"/><path d="M14 3v5h5M9 12h6M9 16h6"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
  chevronDown: '<path d="m6 9 6 6 6-6"/>',
  chevronRight: '<path d="m9 6 6 6-6 6"/>',
  send: '<path d="m22 2-7 20-4-9-9-4 20-7Z"/><path d="M22 2 11 13"/>',
  save: '<path d="M4 4h13l3 3v13H4V4Z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/>',
  wifi: '<path d="M2.5 8.5a15 15 0 0 1 19 0M5.5 12a10 10 0 0 1 13 0M8.5 15.5a5 5 0 0 1 7 0"/><circle cx="12" cy="19" r="1" fill="currentColor"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.2"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06-2.83 2.83-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1.03 1.56V21h-4v-.08A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.87.34l-.06.06-2.83-2.83.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-1.56-1.03H3v-4h.08A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06 2.83-2.83.06.06A1.7 1.7 0 0 0 9 4.64h.01A1.7 1.7 0 0 0 10 3.08V3h4v.08A1.7 1.7 0 0 0 15 4.64a1.7 1.7 0 0 0 1.87-.34l.06-.06 2.83 2.83-.06.06A1.7 1.7 0 0 0 19.36 9v.01A1.7 1.7 0 0 0 20.92 10H21v4h-.08A1.7 1.7 0 0 0 19.4 15Z"/>',
};

export function icon(name, className = "") {
  const body = ICONS[name] || ICONS.info;
  return `<svg class="${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export function esc(value) {
  return String(value === undefined || value === null ? "" : value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const STATUS_MAP = {
  running: { label: "运行中", cls: "running" },
  starting: { label: "启动中", cls: "starting" },
  stopping: { label: "停止中", cls: "stopping" },
  stopped: { label: "已停止", cls: "stopped" },
  failed: { label: "异常", cls: "failed" },
  idle: { label: "空闲", cls: "idle" },
  online: { label: "在线", cls: "online" },
  offline: { label: "离线", cls: "offline" },
  shutting_down: { label: "关闭中", cls: "shutting_down" },
  success: { label: "成功", cls: "running" },
  pending: { label: "等待", cls: "stopped" },
};

export function statusMeta(status) {
  return STATUS_MAP[status] || { label: status || "未知", cls: "stopped" };
}

export function statusBadge(status, label) {
  const meta = statusMeta(status);
  return `<span class="badge badge-${meta.cls}"><i class="dot ${meta.cls}"></i>${esc(label || meta.label)}</span>`;
}

export function riskBadge(level, label) {
  const map = { high: "badge-high", medium: "badge-medium", low: "badge-low" };
  const text = label || { high: "高风险", medium: "中风险", low: "低风险" }[level] || level;
  return `<span class="badge ${map[level] || "badge-low"}">${esc(text)}</span>`;
}

export function sentimentBadge(sentiment, label) {
  const map = { positive: "badge-positive", neutral: "badge-neutral", negative: "badge-negative" };
  const text = label || { positive: "正向", neutral: "中性", negative: "负向" }[sentiment] || sentiment;
  return `<span class="badge ${map[sentiment] || "badge-neutral"}">${esc(text)}</span>`;
}

export function cite(refs) {
  const list = Array.isArray(refs) ? refs : String(refs || "").match(/S\d{2}/g) || [];
  return list
    .filter((ref, index) => ref && list.indexOf(ref) === index)
    .map((ref) => `<span class="cite">${esc(ref)}</span>`)
    .join(" ");
}

export function fmtTime(value, mode = "datetime") {
  if (!value) return "—";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return esc(String(value));
  const pad = (n) => String(n).padStart(2, "0");
  const y = date.getFullYear();
  const m = pad(date.getMonth() + 1);
  const d = pad(date.getDate());
  const hh = pad(date.getHours());
  const mm = pad(date.getMinutes());
  const ss = pad(date.getSeconds());
  if (mode === "time") return `${hh}:${mm}:${ss}`;
  if (mode === "hm") return `${hh}:${mm}`;
  if (mode === "date") return `${y}-${m}-${d}`;
  if (mode === "short") return `${m}-${d} ${hh}:${mm}`;
  return `${y}-${m}-${d} ${hh}:${mm}:${ss}`;
}

export function fmtNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "0";
  if (Number.isInteger(number)) return String(number);
  return number.toFixed(1).replace(/\.0$/, "");
}

export function clamp(value, low, high) {
  return Math.max(low, Math.min(high, value));
}

export function debounce(fn, wait = 250) {
  let timer = null;
  return (...args) => {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}

export function toast(message, type = "info", duration = 3800) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const mark = type === "success" ? "✓" : type === "error" ? "!" : type === "warn" ? "!" : "i";
  el.innerHTML = `<span class="t-icon">${mark}</span><div>${esc(message)}</div>`;
  root.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(-4px)";
    el.style.transition = "all .2s";
    setTimeout(() => el.remove(), 220);
  }, duration);
}

export function emptyState(text, detail = "") {
  return `<div class="empty">${icon("database")}<div>${esc(text)}</div>${
    detail ? `<div class="tiny" style="margin-top:4px">${esc(detail)}</div>` : ""
  }</div>`;
}

export function loadingBlock(text = "加载中…") {
  return `<div class="page-loading"><div class="spinner"></div><span>${esc(text)}</span></div>`;
}

/* ---------------------------------------------------------------- Modal */
export function openModal({ title, sub = "", body = "", footer = "" }) {
  const root = document.getElementById("modal-root");
  const mask = document.createElement("div");
  mask.className = "modal-mask";
  mask.innerHTML = `
    <div class="modal" role="dialog" aria-modal="true">
      <div class="modal-head">
        <h3>${esc(title)}</h3>
        <span class="m-sub">${esc(sub)}</span>
        <button class="icon-btn" data-modal-close title="关闭">${icon("close")}</button>
      </div>
      <div class="modal-body">${body}</div>
      ${footer ? `<div class="modal-foot">${footer}</div>` : ""}
    </div>
  `;
  const close = () => {
    mask.remove();
    document.removeEventListener("keydown", onKey);
  };
  const onKey = (event) => {
    if (event.key === "Escape") close();
  };
  mask.addEventListener("click", (event) => {
    if (event.target === mask) close();
  });
  mask.querySelector("[data-modal-close]").addEventListener("click", close);
  document.addEventListener("keydown", onKey);
  root.appendChild(mask);
  return { root: mask, close, body: mask.querySelector(".modal-body") };
}

export async function openLogModal(appName, displayName, statusLabel = "") {
  const modal = openModal({
    title: `应用日志 · ${displayName}`,
    sub: appName,
    body: `<div class="modal-terminal"><div class="page-loading" style="height:200px"><div class="spinner"></div><span>读取日志…</span></div></div>`,
    footer: `<button class="btn" data-modal-close>关闭</button>`,
  });
  modal.root.querySelectorAll("[data-modal-close]").forEach((btn) => btn.addEventListener("click", modal.close));
  try {
    const data = await api.testLog(appName, 400);
    const lines = data.lines || [];
    modal.body.innerHTML = `<div class="modal-terminal" id="modal-log-body">${
      lines.length
        ? lines
            .map(
              (line) =>
                `<div class="ml"><span class="mt">${esc(line.time || "")}</span><span class="mv ${
                  (line.level || "").toUpperCase() === "ERROR" ? "error" : ""
                }">[${esc(line.level || "INFO")}] ${esc(line.message || line.raw || "")}</span></div>`
            )
            .join("")
        : `<div style="color:#64748b;padding:20px">暂无日志，启动应用后会自动写入 runtime/apps/${esc(appName)}.log</div>`
    }</div>`;
    modal.body.querySelector("#modal-log-body").scrollTop = 999999;
  } catch (error) {
    modal.body.innerHTML = `<div class="modal-terminal" style="color:#f87171;padding:18px">日志读取失败：${esc(
      error.message
    )}</div>`;
  }
}

export function renderInlineError(error, retryLabel = "重试") {
  const detail = error && error.detail ? error.detail : error && error.message ? error.message : "未知错误";
  return `<div class="card card-pad" style="border-color:#f3cccc;background:#fffafa">
    <div style="display:flex;gap:10px;align-items:flex-start">
      <span style="width:26px;height:26px;border-radius:8px;background:#fdeeee;color:#b42318;display:flex;align-items:center;justify-content:center;flex:0 0 26px">${icon(
        "alert"
      )}</span>
      <div style="flex:1">
        <div style="font-weight:600;margin-bottom:3px">请求未完成</div>
        <div class="muted" style="font-size:11.5px">${esc(detail)}</div>
      </div>
      <button class="btn btn-sm" data-retry>${esc(retryLabel)}</button>
    </div>
  </div>`;
}

export function highlightJSON(value) {
  const json = JSON.stringify(value, null, 2);
  return esc(json)
    .replace(/(&quot;[\w.-]+&quot;)(\s*:)/g, '<span class="k">$1</span>$2')
    .replace(/:\s*(&quot;.*?&quot;)/g, ': <span class="s">$1</span>')
    .replace(/:\s*(-?\d+(?:\.\d+)?)/g, ': <span class="n">$1</span>')
    .replace(/:\s*(true|false|null)/g, ': <span class="b">$1</span>');
}
