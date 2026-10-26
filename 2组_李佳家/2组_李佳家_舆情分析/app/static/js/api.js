const JSON_HEADERS = { "Content-Type": "application/json" };

export class ApiError extends Error {
  constructor(message, status = 0, payload = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.payload = payload || {};
    this.detail = this.payload.detail || message;
    this.error = this.payload.error || {};
  }
}

async function request(path, { method = "GET", body, timeout = 30000 } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  let response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? JSON_HEADERS : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
  } catch (error) {
    clearTimeout(timer);
    const message = error.name === "AbortError" ? "请求超时，请稍后重试" : "网络请求失败，请确认服务已启动";
    throw new ApiError(message, 0, { error: { module_name: "frontend", error_message: message } });
  }
  clearTimeout(timer);
  let payload = null;
  const text = await response.text();
  try {
    payload = text ? JSON.parse(text) : {};
  } catch (error) {
    payload = { detail: text || "响应解析失败" };
  }
  if (!response.ok) {
    const message =
      (payload && (payload.detail || (payload.error && payload.error.error_message))) ||
      `请求失败（HTTP ${response.status}）`;
    throw new ApiError(message, response.status, payload);
  }
  return payload;
}

export const api = {
  request,
  get: (path, options) => request(path, options),
  post: (path, body, options = {}) => request(path, { ...options, method: "POST", body }),
  health: () => request("/api/health"),
  getStatus: () => request("/api/status"),
  systemStatus: () => request("/api/system/status"),
  startApp: (name, wait = true) => request(`/api/start/${name}${wait ? "?wait=1" : ""}`),
  stopApp: (name, wait = true) => request(`/api/stop/${name}${wait ? "?wait=1" : ""}`),
  output: (name) => request(`/api/output/${name}`),
  testLog: (name, lines = 200) => request(`/api/test_log/${name}?lines=${lines}`),
  search: (payload) => request("/api/search", { method: "POST", body: payload, timeout: 60000 }),
  topics: () => request("/api/topics"),
  reports: () => request("/api/reports"),
  report: (id) => request(`/api/report/${id}`),
  forumStart: () => request("/api/forum/start"),
  forumStop: () => request("/api/forum/stop"),
  forumLog: (limit = 120) => request(`/api/forum/log?limit=${limit}`),
  forumHistory: (date) => request("/api/forum/log/history", { method: "POST", body: { date } }),
  config: () => request("/api/config"),
  saveConfig: (config) => request("/api/config", { method: "POST", body: { config } }),
  systemStart: () => request("/api/system/start", { method: "POST", body: {} }),
  systemShutdown: () => request("/api/system/shutdown", { method: "POST", body: {} }),
  systemLogs: (appName = "", lines = 120) =>
    request(`/api/system/logs?lines=${lines}${appName ? `&app_name=${appName}` : ""}`),
  graphLatest: () => request("/api/graph/latest"),
  graph: (reportId) => request(`/api/graph/${reportId}`),
  graphQuery: (payload) => request("/api/graph/query", { method: "POST", body: payload }),
};

/* ---------------------------------------------------------------- WebSocket */
let socket = null;
let reconnectTimer = null;
let reconnectDelay = 2500;
let manualClose = false;
let connState = "connecting";
let stateHandler = null;
let eventHandler = null;

function setState(next) {
  connState = next;
  if (stateHandler) stateHandler(next);
}

function scheduleReconnect() {
  if (manualClose || reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    open();
  }, reconnectDelay);
}

function open() {
  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${protocol}//${location.host}/api/ws`;
  setState("connecting");
  try {
    socket = new WebSocket(url);
  } catch (error) {
    setState("down");
    scheduleReconnect();
    return;
  }
  socket.addEventListener("open", () => {
    setState("live");
    reconnectDelay = 2500;
  });
  socket.addEventListener("message", (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (error) {
      return;
    }
    if (eventHandler) eventHandler(data);
  });
  socket.addEventListener("close", () => {
    setState("down");
    socket = null;
    scheduleReconnect();
  });
  socket.addEventListener("error", () => {
    try {
      socket.close();
    } catch (error) {
      /* ignore */
    }
  });
}

export function connectWS({ onEvent, onState } = {}) {
  eventHandler = onEvent || null;
  stateHandler = onState || null;
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    if (stateHandler) stateHandler(connState);
    return;
  }
  manualClose = false;
  open();
}

export function isWSConnected() {
  return connState === "live";
}

export function getWSState() {
  return connState;
}
