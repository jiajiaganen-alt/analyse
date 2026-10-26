import { api } from "../api.js";
import { esc, fmtTime, highlightJSON, icon, loadingBlock, renderInlineError, statusBadge, toast } from "../ui.js";

const state = {
  config: null,
  schema: null,
  updatedAt: "",
  appLabels: {},
  sourceTypeLabels: {},
  saving: false,
  changed: [],
};

const SECTION_META = {
  system: { title: "系统配置", code: "system", desc: "平台标识、监听参数与数据保留策略" },
  collection: { title: "采集配置", code: "collection", desc: "来源范围、多媒体与论坛采集参数" },
  runtime: { title: "运行参数", code: "runtime", desc: "日志、轮询、图谱布局与任务策略" },
  apps: { title: "应用开关", code: "apps", desc: "五个单功能应用是否允许启动" },
};

function fieldHTML(section, field) {
  const value = state.config[section] ? state.config[section][field.key] : undefined;
  const id = `cfg-${section}-${field.key}`;
  const hint = field.hint ? `<div class="hint">${esc(field.hint)}</div>` : "";
  if (field.type === "bool") {
    return `<div class="field full" style="padding:2px 0">
      <div class="switch-row" style="padding:4px 0;border:0">
        <div class="switch-info">
          <div class="t">${esc(field.label)}</div>
          <div class="d">${esc(field.hint || "")}</div>
        </div>
        <label class="switch"><input type="checkbox" id="${id}" data-config-field data-section="${section}" data-key="${
      field.key
    }" data-kind="bool" ${value ? "checked" : ""}><span class="track"></span></label>
      </div>
    </div>`;
  }
  if (field.type === "multiselect") {
    const values = Array.isArray(value) ? value : [];
    return `<div class="field field-multiselect" data-config-field data-section="${section}" data-key="${field.key}" data-kind="multi">
      <label>${esc(field.label)}</label>
      <div class="field-multi">
        ${(field.options || [])
          .map(
            (option) => `
          <label class="check-chip ${values.includes(option) ? "checked" : ""}" data-option="${esc(option)}">
            <input type="checkbox" value="${esc(option)}" ${values.includes(option) ? "checked" : ""}>
            <span class="box">${icon("check")}</span>
            <span>${esc(state.sourceTypeLabels[option] || option)}</span>
          </label>`
          )
          .join("")}
      </div>
      ${hint}
    </div>`;
  }
  if (field.type === "select") {
    return `<div class="field">
      <label>${esc(field.label)}</label>
      <select id="${id}" data-config-field data-section="${section}" data-key="${field.key}" data-kind="string">
        ${(field.options || [])
          .map((option) => `<option value="${esc(option)}" ${value === option ? "selected" : ""}>${esc(option)}</option>`)
          .join("")}
      </select>
      ${hint}
    </div>`;
  }
  if (field.type === "list") {
    const text = Array.isArray(value) ? value.join("、") : String(value || "");
    return `<div class="field full">
      <label>${esc(field.label)}</label>
      <input type="text" id="${id}" data-config-field data-section="${section}" data-key="${
      field.key
    }" data-kind="list" value="${esc(text)}" placeholder="使用逗号分隔">
      ${hint}
    </div>`;
  }
  const type = field.type === "number" ? "number" : "text";
  const step = field.step ? `step="${field.step}"` : type === "number" ? 'step="1"' : "";
  const min = field.min !== undefined ? `min="${field.min}"` : "";
  const max = field.max !== undefined ? `max="${field.max}"` : "";
  return `<div class="field">
    <label>${esc(field.label)}</label>
    <input type="${type}" id="${id}" data-config-field data-section="${section}" data-key="${
    field.key
  }" data-kind="${type === "number" ? "number" : "string"}" value="${esc(value)}" ${step} ${min} ${max}>
    ${hint}
  </div>`;
}

function sectionHTML(sectionName, fields, extra = "") {
  const meta = SECTION_META[sectionName];
  return `<section class="config-section">
    <div class="config-section-head">
      <h3>${esc(meta.title)}</h3><span class="code">${esc(meta.code)}</span>
      <span class="desc">${esc(meta.desc)}</span>
    </div>
    <div class="config-fields">${fields}${extra}</div>
  </section>`;
}

function appsHTML() {
  const labels = state.appLabels || {};
  const apps = state.config.apps || {};
  return Object.entries(apps)
    .map(
      ([name, enabled]) => `
    <div class="switch-row">
      <div class="switch-info">
        <div class="t">${esc(labels[name] || name)} <span class="tiny mono muted">${esc(name)}</span></div>
        <div class="d">禁用后该应用无法启动；若正在运行，保存配置时将自动停止。</div>
      </div>
      <label class="switch"><input type="checkbox" data-config-field data-section="apps" data-key="${esc(
        name
      )}" data-kind="bool" ${enabled ? "checked" : ""}><span class="track"></span></label>
    </div>`
    )
    .join("");
}

function rawJSON() {
  return highlightJSON(state.config || {});
}

function render(el, params) {
  const schema = state.schema || {};
  const systemFields = (schema.system || []).map((field) => fieldHTML("system", field)).join("");
  const collectionFields = (schema.collection || []).map((field) => fieldHTML("collection", field)).join("");
  const runtimeFields = (schema.runtime || []).map((field) => fieldHTML("runtime", field)).join("");
  el.innerHTML = `
    <div class="page-head">
      <div>
        <h1 class="page-title">配置管理</h1>
        <p class="page-sub">读取 config.json 并渲染为表单。保存后热更新立即生效，无需重启服务；应用开关会同步到进程管理模块。</p>
      </div>
      <div class="page-actions">
        <span class="badge badge-info"><i class="dot info"></i>热更新已启用</span>
        <button class="btn btn-sm" id="config-reload">${icon("refresh")} 重新读取</button>
        <button class="btn btn-primary btn-sm" id="config-save-top">${icon("save")} 保存配置</button>
      </div>
    </div>

    <div class="config-banner">
      ${icon("info")}
      <span id="config-banner-text">${esc(
        state.changed.length
          ? `配置已保存，${state.changed.length} 项变更即时生效：${state.changed.slice(0, 4).join("、")}`
          : "修改任意字段后点击保存，系统将校验并写入 config.json，论坛采集间隔、轮询周期与应用开关立即生效。"
      )}</span>
      <span class="time">updated_at ${esc(state.updatedAt || "—")}</span>
    </div>

    <div class="config-savebar">
      <div class="info">配置文件 <b>config.json</b> · 服务监听 <b>127.0.0.1:8714</b> · 变更后由进程管理模块应用</div>
      <div class="actions">
        <button class="btn btn-sm" id="config-copy">${icon("file")} 复制 JSON</button>
        <button class="btn btn-sm btn-ghost" id="config-save-bottom">${icon("save")} 保存并生效</button>
      </div>
    </div>

    <div class="config-grid">
      <div>
        ${sectionHTML("system", systemFields)}
        ${sectionHTML("collection", collectionFields)}
        ${sectionHTML("runtime", runtimeFields)}
        ${sectionHTML("apps", "", appsHTML())}
      </div>
      <aside class="raw-panel">
        <div class="card" style="overflow:hidden">
          <div class="card-head"><h3>${icon("database")} 原始 JSON</h3><span class="hint">config.json</span></div>
          <pre class="raw-json" id="raw-json">${rawJSON()}</pre>
        </div>
        <div class="tiny muted" style="margin-top:8px;line-height:1.7">提示：表单与原始 JSON 同步展示；修改表单后 JSON 面板会即时更新。数值字段保存前由后端做范围校验。</div>
      </aside>
    </div>
  `;
  bind(el);
}

function collectConfig() {
  const next = JSON.parse(JSON.stringify(state.config || {}));
  document.querySelectorAll("[data-config-field]").forEach((input) => {
    const section = input.dataset.section;
    const key = input.dataset.key;
    const kind = input.dataset.kind;
    if (!next[section]) next[section] = {};
    if (input.dataset.kind === "multi") {
      const values = Array.from(input.querySelectorAll("input:checked")).map((item) => item.value);
      next[section][key] = values;
      return;
    }
    if (kind === "bool") {
      next[section][key] = Boolean(input.checked);
    } else if (kind === "number") {
      const number = Number(input.value);
      next[section][key] = Number.isFinite(number) ? number : state.config[section][key];
    } else if (kind === "list") {
      next[section][key] = String(input.value)
        .split(/[,，、]/)
        .map((item) => item.trim())
        .filter(Boolean);
    } else {
      next[section][key] = input.value;
    }
  });
  return next;
}

function refreshRaw() {
  const pre = document.getElementById("raw-json");
  if (!pre) return;
  try {
    pre.innerHTML = highlightJSON(collectConfig());
  } catch (error) {
    /* ignore */
  }
}

async function save(el, params) {
  if (state.saving) return;
  state.saving = true;
  const buttons = document.querySelectorAll("#config-save-top, #config-save-bottom");
  buttons.forEach((button) => {
    button.disabled = true;
  });
  try {
    const payload = collectConfig();
    const result = await api.saveConfig(payload);
    state.config = result.config;
    state.updatedAt = result.updated_at || "";
    state.changed = result.changed_keys || [];
    toast(result.message || "配置已保存并热更新生效", "success", 4500);
    render(el, params);
    if (state.changed.length) {
      const banner = document.getElementById("config-banner-text");
      if (banner) {
        banner.innerHTML = `配置已保存，<b>${state.changed.length}</b> 项变更即时生效：${state.changed
          .slice(0, 6)
          .map((item) => `<span class="chip blue">${esc(item)}</span>`)
          .join(" ")}`;
      }
    }
  } catch (error) {
    toast(error.message || "配置保存失败", "error", 6000);
  } finally {
    state.saving = false;
    buttons.forEach((button) => {
      button.disabled = false;
    });
  }
}

function bind(el) {
  el.querySelectorAll(".check-chip").forEach((chip) => {
    const input = chip.querySelector("input");
    chip.addEventListener("click", (event) => {
      event.preventDefault();
      input.checked = !input.checked;
      chip.classList.toggle("checked", input.checked);
      refreshRaw();
    });
  });
  el.querySelectorAll("[data-config-field]").forEach((input) => {
    input.addEventListener("change", refreshRaw);
    if (input.tagName === "INPUT" && input.type !== "checkbox") input.addEventListener("input", refreshRaw);
  });
  document.getElementById("config-save-top")?.addEventListener("click", () => save(el, {}));
  document.getElementById("config-save-bottom")?.addEventListener("click", () => save(el, {}));
  document.getElementById("config-reload")?.addEventListener("click", async () => {
    await loadAndRender(el, {});
    toast("已重新读取 config.json", "success");
  });
  document.getElementById("config-copy")?.addEventListener("click", async () => {
    const text = JSON.stringify(collectConfig(), null, 2);
    try {
      await navigator.clipboard.writeText(text);
      toast("配置 JSON 已复制到剪贴板", "success");
    } catch (error) {
      const pre = document.getElementById("raw-json");
      if (pre) {
        const range = document.createRange();
        range.selectNodeContents(pre);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        toast("已选中 JSON，请按 Ctrl+C 复制", "info");
      }
    }
  });
  document.querySelectorAll(".switch input").forEach((input) => {
    input.addEventListener("change", refreshRaw);
  });
}

async function loadAndRender(el, params) {
  el.innerHTML = loadingBlock("读取 config.json…");
  const data = await api.config();
  state.config = data.config;
  state.schema = data.schema;
  state.updatedAt = data.updated_at;
  state.appLabels = data.app_labels || {};
  state.sourceTypeLabels = data.source_type_labels || {};
  render(el, params);
}

export async function renderConfig(el, params) {
  try {
    await loadAndRender(el, params);
  } catch (error) {
    el.innerHTML = renderInlineError(error, "重新读取");
    el.querySelector("[data-retry]")?.addEventListener("click", () => renderConfig(el, params));
  }
}

export function onConfigEvent() {
  /* 配置页不需要实时事件 */
}
