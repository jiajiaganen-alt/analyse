import { api } from "../api.js";
import { esc, fmtNumber, fmtTime, icon, loadingBlock, renderInlineError, statusBadge, toast } from "../ui.js";

const TYPE_LABELS = {
  topic: "主题",
  brand: "品牌/产品",
  event: "事件",
  person: "人物",
  org: "机构",
  media: "媒体",
  source: "来源",
};
const TYPE_COLORS = {
  topic: "#1d4ed8",
  brand: "#db2777",
  event: "#f59e0b",
  person: "#7c3aed",
  org: "#0d9488",
  media: "#0891b2",
  source: "#64748b",
};
const SOURCE_TYPE_LABELS = {
  news: "新闻",
  image: "图片",
  video: "视频",
  forum_post: "论坛",
  internal_data: "内部",
};

const state = {
  data: null,
  allData: null,
  reportId: "",
  reports: [],
  selectedId: null,
  focusMode: false,
  layout: "force",
  transform: { x: 0, y: 0, k: 1 },
  queryActive: false,
  dragging: null,
  resizeTimer: null,
};

function truncate(text, max = 16) {
  const value = String(text || "");
  return value.length > max ? value.slice(0, max - 1) + "…" : value;
}

function shellHTML() {
  return `
    <div class="graph-page-head">
      <div>
        <h1 class="page-title">图谱查看</h1>
        <p class="page-sub">从报告来源、事件与实体构建的关系图谱。点击节点高亮其关系，支持按节点类型、关键词、关系与来源编号查询。</p>
      </div>
      <div class="graph-toolbar">
        <select class="select" id="report-select" style="max-width:330px" title="选择报告"><option>加载中…</option></select>
        <button class="btn btn-sm active" id="layout-force" data-layout="force">${icon("activity")} 力导向</button>
        <button class="btn btn-sm" id="layout-layered" data-layout="layered">${icon("layers")} 分层</button>
        <button class="btn btn-sm" id="graph-reload">${icon("refresh")} 刷新</button>
      </div>
    </div>

    <div class="card" style="padding:10px 13px;margin-bottom:12px">
      <form id="graph-query-form" class="graph-toolbar" autocomplete="off">
        <span class="tiny muted" style="font-weight:600">条件查询</span>
        <select class="select" id="q-node-type">
          <option value="">全部节点类型</option>
          ${Object.entries(TYPE_LABELS)
            .map(([key, label]) => `<option value="${key}">${label}</option>`)
            .join("")}
        </select>
        <input class="input" id="q-keyword" placeholder="节点关键词，如：教育 / 家长" style="width:190px">
        <select class="select" id="q-relation"><option value="">全部关系</option></select>
        <input class="input" id="q-source-ref" placeholder="来源编号 S01" style="width:118px">
        <button class="btn btn-sm btn-primary" type="submit">${icon("filter")} 查询</button>
        <button class="btn btn-sm" type="button" id="q-reset">${icon("reset")} 重置</button>
        <span class="query-result" id="query-result"></span>
      </form>
    </div>

    <div class="graph-layout">
      <div class="graph-canvas-card">
        <div class="graph-canvas-head">
          <span class="g-title">关系图谱</span>
          <span class="g-sub" id="graph-sub">加载中…</span>
          <div class="g-tools">
            <button class="icon-btn" id="g-zoom-in" title="放大">${icon("zoomIn")}</button>
            <button class="icon-btn" id="g-zoom-out" title="缩小">${icon("zoomOut")}</button>
            <button class="icon-btn" id="g-zoom-reset" title="重置视图">${icon("reset")}</button>
          </div>
        </div>
        <div class="graph-stage" id="graph-stage">
          <svg class="graph-svg" id="graph-svg" xmlns="http://www.w3.org/2000/svg"></svg>
          <div class="graph-note">点击节点查看详情 · 拖拽画布平移 · 滚轮缩放</div>
          <div class="graph-legend">
            ${Object.entries(TYPE_LABELS)
              .map(
                ([key, label]) =>
                  `<span><i style="background:${TYPE_COLORS[key]}"></i>${label}</span>`
              )
              .join("")}
          </div>
        </div>
      </div>

      <aside class="graph-side">
        <div class="side-card" id="node-detail">
          <h3>节点详情 <span>Node Detail</span></h3>
          <div class="gd-empty">点击图谱中的节点查看属性、关系与来源引用。</div>
        </div>
        <div class="side-card" id="graph-stats">
          <h3>图谱统计 <span>Graph</span></h3>
          <div class="gd-empty">加载中…</div>
        </div>
      </aside>
    </div>
  `;
}

function graphStatsHTML() {
  const data = state.data;
  if (!data) return "";
  const stats = data.stats || {};
  const typeCounts = {};
  (data.nodes || []).forEach((node) => {
    typeCounts[node.type] = (typeCounts[node.type] || 0) + 1;
  });
  const relationCounts = {};
  (data.edges || []).forEach((edge) => {
    relationCounts[edge.label || edge.relation] = (relationCounts[edge.label || edge.relation] || 0) + 1;
  });
  const relations = Object.entries(relationCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  return `
    <div class="kv-row"><span class="k">报告编号</span><span class="v mono" style="font-size:9px">${esc(state.reportId)}</span></div>
    <div class="kv-row"><span class="k">当前节点 / 关系</span><span class="v">${fmtNumber(
      (data.nodes || []).length
    )} / ${fmtNumber((data.edges || []).length)}</span></div>
    <div class="kv-row"><span class="k">报告主题</span><span class="v">${esc(data.topic || "—")}</span></div>
    <div class="kv-row"><span class="k">生成时间</span><span class="v">${fmtTime(data.created_at, "short")}</span></div>
    <div class="gd-section">
      <h5>节点类型（点击筛选）</h5>
      <div class="node-type-legend">
        ${Object.entries(TYPE_LABELS)
          .map(
            ([key, label]) => `
          <span class="type-chip" data-filter-type="${key}">
            <i style="background:${TYPE_COLORS[key]}"></i>${label}<b style="color:#98a2b3;font-weight:400">${
              typeCounts[key] || 0
            }</b>
          </span>`
          )
          .join("")}
      </div>
    </div>
    <div class="gd-section">
      <h5>主要关系</h5>
      <div class="gd-relations">
        ${relations
          .map(
            ([label, count]) =>
              `<div class="gd-rel"><span class="rel-label">${esc(label)}</span><span class="rel-node" style="margin-left:auto">${count} 条</span></div>`
          )
          .join("")}
      </div>
    </div>
    <div class="gd-section">
      <h5>图谱文件</h5>
      <div class="tiny mono" style="color:#98a2b3;word-break:break-all">graphs/${esc(state.reportId)}/graph.json</div>
    </div>
  `;
}

function layoutPositions(nodes, edges, width, height) {
  const marginX = 46;
  const marginY = 48;
  if (state.layout === "layered") {
    const columns = {
      topic: 0.12,
      event: 0.34,
      org: 0.55,
      person: 0.55,
      brand: 0.55,
      media: 0.73,
      source: 0.91,
    };
    const groups = {};
    nodes.forEach((node) => {
      const key = ["org", "person", "brand"].includes(node.type) ? "org" : node.type;
      if (!groups[key]) groups[key] = [];
      groups[key].push(node);
    });
    Object.values(groups).forEach((group) => group.sort((a, b) => (b.degree || 0) - (a.degree || 0)));
    const positions = {};
    Object.entries(groups).forEach(([key, group]) => {
      const xRatio = columns[key] || 0.5;
      const x = marginX + (width - marginX * 2) * xRatio;
      group.forEach((node, index) => {
        const usable = height - marginY * 2;
        const y = marginY + (usable * (index + 0.5)) / Math.max(1, group.length);
        let dx = 0;
        if (key === "org") dx = node.type === "person" ? -26 : node.type === "brand" ? 26 : 0;
        positions[node.id] = { x: Math.min(width - 30, Math.max(30, x + dx)), y };
      });
    });
    return positions;
  }

  // 力导向布局：确定性初始位置 + 斥力/弹簧/类型锚点
  const n = nodes.length || 1;
  const positions = {};
  const typeCounts = {};
  nodes.forEach((node) => {
    typeCounts[node.type] = (typeCounts[node.type] || 0) + 1;
  });
  const typeIndex = {};
  const anchors = {};
  nodes.forEach((node, index) => {
    const seed = Array.from(node.id).reduce((sum, char) => sum + char.charCodeAt(0), 0);
    const angle = (index / n) * Math.PI * 2 + (seed % 17) / 17;
    const radius = Math.min(width, height) * (0.16 + ((index % 4) / 4) * 0.16);
    positions[node.id] = {
      x: width / 2 + Math.cos(angle) * radius,
      y: height / 2 + Math.sin(angle) * radius,
      vx: 0,
      vy: 0,
    };
    const current = typeIndex[node.type] || 0;
    typeIndex[node.type] = current + 1;
    const total = Math.max(1, typeCounts[node.type] || 1);
    const ratio = total > 1 ? current / (total - 1) : 0.5;
    if (node.type === "topic") {
      anchors[node.id] = { x: width * 0.47, y: height * 0.5 };
    } else if (node.type === "event") {
      anchors[node.id] = { x: width * 0.3, y: height * (0.16 + ratio * 0.68) };
    } else if (node.type === "source") {
      anchors[node.id] = { x: width * 0.95, y: height * (0.08 + ratio * 0.84) };
    } else if (node.type === "media") {
      anchors[node.id] = { x: width * 0.82, y: height * (0.12 + ratio * 0.36) };
    } else if (node.type === "person") {
      anchors[node.id] = { x: width * 0.69, y: height * (0.28 + ratio * 0.52) };
    } else if (node.type === "brand") {
      anchors[node.id] = { x: width * 0.74, y: height * (0.32 + ratio * 0.36) };
    } else {
      anchors[node.id] = { x: width * 0.6, y: height * (0.1 + ratio * 0.8) };
    }
  });
  const charge = Math.sqrt((width * height) / n) * 1.35;
  const iterations = 200;
  for (let iteration = 0; iteration < iterations; iteration += 1) {
    const alpha = 1 - iteration / iterations;
    for (let i = 0; i < nodes.length; i += 1) {
      const a = positions[nodes[i].id];
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = positions[nodes[j].id];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distance = Math.sqrt(dx * dx + dy * dy);
        if (distance < 0.8) {
          dx = 0.8 + (i % 3) * 0.2;
          dy = 0.6 + (j % 3) * 0.2;
          distance = Math.sqrt(dx * dx + dy * dy);
        }
        const force = (charge * charge) / distance;
        const fx = (dx / distance) * force * 0.5;
        const fy = (dy / distance) * force * 0.5;
        a.vx -= fx;
        a.vy -= fy;
        b.vx += fx;
        b.vy += fy;
      }
    }
    edges.forEach((edge) => {
      const a = positions[edge.source];
      const b = positions[edge.target];
      if (!a || !b) return;
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const distance = Math.max(0.5, Math.sqrt(dx * dx + dy * dy));
      const desired = 78;
      const force = (distance - desired) * 0.026;
      const fx = (dx / distance) * force;
      const fy = (dy / distance) * force;
      a.vx += fx;
      a.vy += fy;
      b.vx -= fx;
      b.vy -= fy;
    });
    nodes.forEach((node) => {
      const position = positions[node.id];
      const anchor = anchors[node.id] || { x: width / 2, y: height / 2 };
      position.vx += (anchor.x - position.x) * 0.018;
      position.vy += (anchor.y - position.y) * 0.018;
      position.vx += (width / 2 - position.x) * 0.0015;
      position.vy += (height / 2 - position.y) * 0.0015;
      position.x += position.vx * 0.35 * alpha;
      position.y += position.vy * 0.35 * alpha;
      position.vx *= 0.72;
      position.vy *= 0.72;
    });
  }
  // 归一化到画布范围
  const values = Object.values(positions);
  const minX = Math.min(...values.map((item) => item.x));
  const maxX = Math.max(...values.map((item) => item.x));
  const minY = Math.min(...values.map((item) => item.y));
  const maxY = Math.max(...values.map((item) => item.y));
  const spanX = Math.max(1, maxX - minX);
  const spanY = Math.max(1, maxY - minY);
  const scaleX = (width - marginX * 2) / spanX;
  const scaleY = (height - marginY * 2) / spanY;
  const scale = Math.min(scaleX, scaleY, 1.25);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;
  Object.keys(positions).forEach((id) => {
    positions[id].x = (positions[id].x - minX) * scale + offsetX;
    positions[id].y = (positions[id].y - minY) * scale + offsetY;
  });
  return positions;
}

function nodeRadius(node) {
  if (node.type === "topic") return 19;
  if (node.type === "event") return 8.5;
  if (node.type === "org") return 9.5;
  if (node.type === "person") return 8.5;
  if (node.type === "brand") return 9;
  if (node.type === "media") return 8;
  return 5.2 + Math.min(2.6, (node.degree || 0) * 0.25);
}

function nodeShape(node) {
  const color = TYPE_COLORS[node.type] || "#64748b";
  if (node.type === "source") {
    return `<rect class="n-core" x="-5.6" y="-5.6" width="11.2" height="11.2" rx="2.4" fill="${color}"></rect>`;
  }
  if (node.type === "topic") {
    return `<circle class="n-core" r="19" fill="${color}"></circle>
      <circle r="25" fill="none" stroke="${color}" stroke-width="1" opacity=".22"></circle>`;
  }
  const radius = nodeRadius(node);
  return `<circle class="n-core" r="${radius}" fill="${color}"></circle>`;
}

function drawGraph() {
  const stage = document.getElementById("graph-stage");
  const svg = document.getElementById("graph-svg");
  if (!stage || !svg || !state.data) return;
  const width = Math.max(520, stage.clientWidth || 780);
  const height = Math.max(480, stage.clientHeight || 646);
  const nodes = state.data.nodes || [];
  const edges = state.data.edges || [];
  const positions = layoutPositions(nodes, edges, width, height);
  const selected = state.selectedId;
  const selectedNode = nodes.find((node) => node.id === selected);
  const nodesById = {};
  nodes.forEach((node) => {
    nodesById[node.id] = node;
  });
  const incident = new Set();
  const neighbors = new Set();
  if (selected) {
    edges.forEach((edge) => {
      if (edge.source === selected || edge.target === selected) {
        incident.add(edge.id);
        neighbors.add(edge.source === selected ? edge.target : edge.source);
      }
    });
  }
  const { x, y, k } = state.transform;
  const edgeParts = [];
  const labelCandidates = [];
  edges.forEach((edge) => {
    const a = positions[edge.source];
    const b = positions[edge.target];
    if (!a || !b) return;
    const other = nodesById[edge.source === selected ? edge.target : edge.source];
    const structural = other && other.type !== "source";
    const highlighted = incident.has(edge.id) && (selectedNode?.type === "source" || structural);
    const dim = state.focusMode && selected && !highlighted;
    edgeParts.push(
      `<line class="gedge ${highlighted ? "highlight" : ""} ${dim ? "dim" : ""}" x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(
        1
      )}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}"></line>`
    );
    if (highlighted) {
      labelCandidates.push({ edge, a, b, otherType: other ? other.type : "unknown" });
    }
  });
  const picked = [];
  const seenTypes = new Set();
  labelCandidates.forEach((item) => {
    if (picked.length >= 4) return;
    if (!seenTypes.has(item.otherType)) {
      picked.push(item);
      seenTypes.add(item.otherType);
    }
  });
  labelCandidates.forEach((item) => {
    if (picked.length < 4 && !picked.includes(item)) picked.push(item);
  });
  picked.forEach(({ edge, a, b }) => {
    const ratio = 0.62;
    const labelX = a.x + (b.x - a.x) * ratio;
    const labelY = a.y + (b.y - a.y) * ratio - 3;
    edgeParts.push(
      `<text class="gedge-label highlight" x="${labelX.toFixed(1)}" y="${labelY.toFixed(
        1
      )}" text-anchor="middle">${esc(edge.label || edge.relation)}</text>`
    );
  });
  const nodeParts = [];
  nodes.forEach((node) => {
    const position = positions[node.id];
    if (!position) return;
    const isSelected = node.id === selected;
    const isNeighbor = neighbors.has(node.id);
    const dim = state.focusMode && selected && !isSelected && !isNeighbor;
    const radius = nodeRadius(node);
    const labelY = node.type === "source" ? 3 : node.type === "topic" ? -radius - 12 : radius + 13;
    const labelX = node.type === "source" ? 10 : 0;
    const labelClass = node.type === "source" ? "n-label source-label" : "n-label";
    const labelWorthy =
      ["topic", "event", "media", "brand"].includes(node.type) || (node.degree || 0) >= 4;
    const showLabel =
      node.type === "source"
        ? isSelected || state.layout === "layered"
        : labelWorthy || isSelected;
    nodeParts.push(
      `<g class="gnode ${isSelected ? "selected" : ""} ${dim ? "dim" : ""}" data-node="${esc(node.id)}" transform="translate(${position.x.toFixed(
        1
      )} ${position.y.toFixed(1)})">
        ${isSelected ? '<circle class="halo" r="30"></circle>' : ""}
        ${nodeShape(node)}
        ${
          showLabel
            ? `<text class="${labelClass}" x="${labelX}" y="${labelY}" text-anchor="${
                node.type === "source" ? "start" : "middle"
              }">${esc(truncate(node.label, node.type === "source" ? 10 : node.type === "topic" ? 20 : 9))}</text>`
            : ""
        }
        <title>${esc(node.label)} · ${esc(TYPE_LABELS[node.type] || node.type)}</title>
      </g>`
    );
  });
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.innerHTML = `
    <g class="viewport" transform="translate(${x} ${y}) scale(${k})">
      <g class="edges">${edgeParts.join("")}</g>
      <g class="nodes">${nodeParts.join("")}</g>
    </g>
  `;
  bindGraphInteractions(svg, positions, width, height);
  renderSidebar();
  const sub = document.getElementById("graph-sub");
  if (sub) {
    sub.textContent = `${nodes.length} 节点 · ${edges.length} 关系 · ${state.layout === "force" ? "力导向" : "分层"}布局${
      state.queryActive ? " · 查询结果" : ""
    }`;
  }
  const statsEl = document.getElementById("graph-stats");
  if (statsEl) statsEl.innerHTML = `<h3>图谱统计 <span>Graph</span></h3>${graphStatsHTML()}`;
  bindStatChips();
}

function bindStatChips() {
  document.querySelectorAll("[data-filter-type]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const type = chip.dataset.filterType;
      const select = document.getElementById("q-node-type");
      if (select) select.value = type;
      const form = document.getElementById("graph-query-form");
      if (form) form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
    });
  });
}

function bindGraphInteractions(svg, positions, width, height) {
  const viewport = svg.querySelector(".viewport");
  const apply = () => {
    if (viewport)
      viewport.setAttribute(
        "transform",
        `translate(${state.transform.x} ${state.transform.y}) scale(${state.transform.k})`
      );
  };
  svg.querySelectorAll("[data-node]").forEach((group) => {
    group.addEventListener("click", (event) => {
      event.stopPropagation();
      if (state.dragging && state.dragging.moved) return;
      selectNode(group.dataset.node, true);
    });
    group.addEventListener("mouseenter", () => group.classList.add("hover"));
    group.addEventListener("mouseleave", () => group.classList.remove("hover"));
  });
  svg.onclick = (event) => {
    if (event.target.closest("[data-node]")) return;
    if (state.dragging && state.dragging.moved) return;
    state.selectedId = null;
    state.focusMode = false;
    drawGraph();
  };
  svg.onpointerdown = (event) => {
    if (event.button !== 0) return;
    if (event.target.closest("[data-node]")) return;
    state.dragging = {
      startX: event.clientX,
      startY: event.clientY,
      originX: state.transform.x,
      originY: state.transform.y,
      moved: false,
    };
    svg.classList.add("dragging");
    svg.setPointerCapture(event.pointerId);
  };
  svg.onpointermove = (event) => {
    if (!state.dragging) return;
    const dx = event.clientX - state.dragging.startX;
    const dy = event.clientY - state.dragging.startY;
    if (Math.abs(dx) + Math.abs(dy) > 3) state.dragging.moved = true;
    state.transform.x = state.dragging.originX + dx;
    state.transform.y = state.dragging.originY + dy;
    apply();
  };
  const endDrag = () => {
    if (!state.dragging) return;
    svg.classList.remove("dragging");
    state.dragging = null;
  };
  svg.onpointerup = endDrag;
  svg.onpointercancel = endDrag;
  svg.onwheel = (event) => {
    event.preventDefault();
    const rect = svg.getBoundingClientRect();
    const cursorX = event.clientX - rect.left;
    const cursorY = event.clientY - rect.top;
    const ratio = event.deltaY < 0 ? 1.12 : 0.89;
    const nextK = Math.max(0.45, Math.min(2.6, state.transform.k * ratio));
    const scale = nextK / state.transform.k;
    state.transform.x = cursorX - (cursorX - state.transform.x) * scale;
    state.transform.y = cursorY - (cursorY - state.transform.y) * scale;
    state.transform.k = nextK;
    apply();
  };
}

function selectNode(nodeId, focusMode) {
  state.selectedId = nodeId;
  state.focusMode = Boolean(focusMode);
  drawGraph();
}

function renderSidebar() {
  const panel = document.getElementById("node-detail");
  if (!panel || !state.data) return;
  const node = (state.data.nodes || []).find((item) => item.id === state.selectedId);
  if (!node) {
    panel.innerHTML = `<h3>节点详情 <span>Node Detail</span></h3>
      <div class="gd-empty">点击图谱中的节点查看属性、关系与来源引用。</div>
      <div class="gd-section"><h5>连接度最高的节点</h5><div class="chips">${(state.data.nodes || [])
        .slice()
        .sort((a, b) => (b.degree || 0) - (a.degree || 0))
        .slice(0, 6)
        .map((item) => `<button class="type-chip" data-jump-node="${esc(item.id)}"><i style="background:${
          TYPE_COLORS[item.type]
        }"></i>${esc(truncate(item.label, 12))}</button>`)
        .join("")}</div></div>`;
    panel.querySelectorAll("[data-jump-node]").forEach((button) =>
      button.addEventListener("click", () => selectNode(button.dataset.jumpNode, false))
    );
    return;
  }
  const edges = (state.data.edges || []).filter(
    (edge) => edge.source === node.id || edge.target === node.id
  );
  const nodesById = {};
  (state.data.nodes || []).forEach((item) => {
    nodesById[item.id] = item;
  });
  const refs = node.source_refs || [];
  const sourceNodes = (state.allData?.nodes || []).filter(
    (item) => item.type === "source" && refs.includes((item.source_refs || [])[0])
  );
  const meta = node.meta || {};
  panel.innerHTML = `
    <h3>节点详情 <span>Node Detail</span></h3>
    <div class="gnode-detail">
      <div class="gd-type">
        <span class="badge" style="color:${TYPE_COLORS[node.type]};background:${TYPE_COLORS[node.type]}14;border-color:${
    TYPE_COLORS[node.type]
  }33">${esc(node.type_label || TYPE_LABELS[node.type] || node.type)}</span>
        <span class="tiny muted">连接度 ${node.degree || 0}</span>
      </div>
      <h3 style="font-size:14px">${esc(node.label)}</h3>
      <div class="gd-id">${esc(node.id)}</div>
      <div class="gd-desc">${esc(node.description || "暂无描述")}</div>
      ${node.type === "source" ? sourceMetaHTML(meta) : ""}
      <div class="gd-section">
        <h5>来源引用（${refs.length}）</h5>
        <div class="chips">${refs.map((ref) => `<span class="cite">${esc(ref)}</span>`).join("") || '<span class="gd-empty">无</span>'}</div>
      </div>
      ${
        sourceNodes.length
          ? `<div class="gd-section"><h5>可回溯来源</h5><div class="gd-sources">
              ${sourceNodes
                .map(
                  (item) =>
                    `<a class="gd-source" href="${esc(item.meta?.url || "#")}" target="_blank" rel="noopener">
                      <span class="ref">${esc((item.source_refs || [])[0] || "")}</span>
                      <span style="flex:1">${esc(item.label)}</span>
                      ${icon("external")}
                    </a>`
                )
                .join("")}
            </div></div>`
          : ""
      }
      <div class="gd-section">
        <h5>关联关系（${edges.length}）</h5>
        <div class="gd-relations">
          ${edges
            .slice(0, 18)
            .map((edge) => {
              const outgoing = edge.source === node.id;
              const other = nodesById[outgoing ? edge.target : edge.source];
              return `<button class="gd-rel" data-jump-node="${esc(other ? other.id : "")}" style="border:1px solid #edf1f7;background:#f8fafd;cursor:pointer;text-align:left">
                <span class="rel-label">${esc(edge.label || edge.relation)}</span>
                <span style="color:#98a2b3">${outgoing ? "→" : "←"}</span>
                <span class="rel-node">${esc(other ? truncate(other.label, 16) : "未知节点")}</span>
              </button>`;
            })
            .join("") || '<span class="gd-empty">暂无关联关系</span>'}
        </div>
      </div>
    </div>
  `;
  panel.querySelectorAll("[data-jump-node]").forEach((button) => {
    button.addEventListener("click", () => {
      if (button.dataset.jumpNode) selectNode(button.dataset.jumpNode, true);
    });
  });
}

function sourceMetaHTML(meta) {
  return `<div class="gd-section">
    <h5>来源属性</h5>
    <div class="kv-row"><span class="k">来源媒体</span><span class="v">${esc(meta.source || "—")}</span></div>
    <div class="kv-row"><span class="k">来源类型</span><span class="v">${esc(
      SOURCE_TYPE_LABELS[meta.source_type] || meta.source_type_label || "—"
    )}</span></div>
    <div class="kv-row"><span class="k">发布时间</span><span class="v">${fmtTime(meta.published_at, "short")}</span></div>
    <div class="kv-row"><span class="k">情绪</span><span>${statusBadge(
      meta.sentiment === "negative" ? "failed" : meta.sentiment === "positive" ? "running" : "stopped",
      meta.sentiment === "negative" ? "负向" : meta.sentiment === "positive" ? "正向" : "中性"
    )}</span></div>
    ${meta.url ? `<a class="btn btn-sm" style="margin-top:8px" href="${esc(meta.url)}" target="_blank" rel="noopener">${icon(
      "external"
    )} 查看原文</a>` : ""}
  </div>`;
}

async function loadReports() {
  const data = await api.reports();
  state.reports = (data.reports || []).filter((item) => item.has_graph);
  return state.reports;
}

function fillReportSelect() {
  const select = document.getElementById("report-select");
  if (!select) return;
  if (!state.reports.length) {
    select.innerHTML = `<option>暂无报告图谱</option>`;
    return;
  }
  select.innerHTML = state.reports
    .map(
      (report) =>
        `<option value="${esc(report.report_id)}" ${report.report_id === state.reportId ? "selected" : ""}>${esc(
          report.topic
        )} · ${esc(report.report_id)}</option>`
    )
    .join("");
}

function fillRelations() {
  const select = document.getElementById("q-relation");
  if (!select || !state.allData) return;
  const labels = {};
  (state.allData.edges || []).forEach((edge) => {
    labels[edge.relation] = edge.label || edge.relation;
  });
  select.innerHTML = `<option value="">全部关系</option>${Object.entries(labels)
    .map(([relation, label]) => `<option value="${esc(relation)}">${esc(label)} (${esc(relation)})</option>`)
    .join("")}`;
}

function resetView() {
  state.transform = { x: 0, y: 0, k: 1 };
  drawGraph();
}

async function loadGraph(reportId) {
  let data;
  if (reportId && reportId !== "latest") {
    data = await api.graph(reportId);
  } else {
    data = await api.graphLatest();
  }
  state.data = data;
  state.allData = data;
  state.reportId = data.report_id;
  state.selectedId = (data.nodes || []).find((node) => node.type === "topic")?.id || null;
  state.focusMode = false;
  state.queryActive = false;
  state.transform = { x: 0, y: 0, k: 1 };
  fillRelations();
  drawGraph();
  const queryResult = document.getElementById("query-result");
  if (queryResult) queryResult.textContent = "";
  return data;
}

function emptyGraphHTML(message) {
  return `<div class="card" style="padding:44px 20px;text-align:center">
    <div style="width:46px;height:46px;border-radius:12px;background:#eef4ff;color:#1d4ed8;display:flex;align-items:center;justify-content:center;margin:0 auto 12px">${icon(
      "graph"
    )}</div>
    <div style="font-size:15px;font-weight:600;margin-bottom:4px">暂无图谱数据</div>
    <div class="muted" style="font-size:11.5px;margin-bottom:14px">${esc(message)}</div>
    <div style="display:flex;gap:8px;justify-content:center">
      <a class="btn btn-primary btn-sm" href="#/search?demo=1">${icon("search")} 发起主题检索</a>
      <button class="btn btn-sm" data-retry-graph>${icon("refresh")} 重新加载</button>
    </div>
  </div>`;
}

async function doQuery(form) {
  if (!state.allData) return;
  const nodeType = document.getElementById("q-node-type")?.value || "";
  const keyword = document.getElementById("q-keyword")?.value.trim() || "";
  const relation = document.getElementById("q-relation")?.value || "";
  const sourceRef = document.getElementById("q-source-ref")?.value.trim().toUpperCase() || "";
  const resultEl = document.getElementById("query-result");
  if (!nodeType && !keyword && !relation && !sourceRef) {
    resetQuery();
    return;
  }
  try {
    const result = await api.graphQuery({
      report_id: state.reportId,
      node_type: nodeType || null,
      keyword: keyword || null,
      relation: relation || null,
      source_ref: sourceRef || null,
      limit: 200,
    });
    state.data = {
      ...state.allData,
      nodes: result.nodes || [],
      edges: result.edges || [],
    };
    state.selectedId = (result.nodes || []).find((node) => node.type === "topic")?.id || null;
    state.focusMode = false;
    state.queryActive = true;
    state.transform = { x: 0, y: 0, k: 1 };
    drawGraph();
    if (resultEl) {
      resultEl.innerHTML = `命中 <b>${result.stats.node_count}</b> 节点 / <b>${result.stats.edge_count}</b> 关系`;
    }
    if (!result.stats.matched) toast("没有匹配的节点或关系", "warn");
  } catch (error) {
    toast(error.message || "查询失败", "error");
  }
}

function resetQuery() {
  if (!state.allData) return;
  state.data = state.allData;
  state.queryActive = false;
  state.selectedId = (state.allData.nodes || []).find((node) => node.type === "topic")?.id || null;
  state.focusMode = false;
  state.transform = { x: 0, y: 0, k: 1 };
  const form = document.getElementById("graph-query-form");
  if (form) form.reset();
  const resultEl = document.getElementById("query-result");
  if (resultEl) resultEl.textContent = "";
  drawGraph();
}

function bindShell(el, params) {
  const form = document.getElementById("graph-query-form");
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    doQuery(form);
  });
  document.getElementById("q-reset")?.addEventListener("click", resetQuery);
  document.getElementById("graph-reload")?.addEventListener("click", async () => {
    try {
      await loadReports();
      fillReportSelect();
      await loadGraph(state.reportId);
      toast("图谱已刷新", "success");
    } catch (error) {
      toast(error.message || "刷新失败", "error");
    }
  });
  document.getElementById("report-select")?.addEventListener("change", async (event) => {
    const reportId = event.target.value;
    if (!reportId) return;
    try {
      await loadGraph(reportId);
      const target = location.pathname.startsWith("/graph-viewer")
        ? `/graph-viewer/${encodeURIComponent(reportId)}`
        : `/#/graph?report=${encodeURIComponent(reportId)}`;
      history.replaceState(null, "", target);
    } catch (error) {
      toast(error.message || "图谱加载失败", "error");
    }
  });
  document.querySelectorAll("[data-layout]").forEach((button) => {
    button.addEventListener("click", () => {
      state.layout = button.dataset.layout;
      document.querySelectorAll("[data-layout]").forEach((item) => item.classList.toggle("active", item === button));
      resetView();
    });
  });
  document.getElementById("g-zoom-in")?.addEventListener("click", () => zoomBy(1.2));
  document.getElementById("g-zoom-out")?.addEventListener("click", () => zoomBy(0.84));
  document.getElementById("g-zoom-reset")?.addEventListener("click", resetView);
  window.addEventListener("resize", () => {
    if (state.resizeTimer) clearTimeout(state.resizeTimer);
    state.resizeTimer = setTimeout(() => {
      if (document.getElementById("graph-stage") && state.data) drawGraph();
    }, 220);
  });
}

function zoomBy(ratio) {
  const stage = document.getElementById("graph-stage");
  const svg = document.getElementById("graph-svg");
  if (!stage || !svg) return;
  const rect = svg.getBoundingClientRect();
  const cursorX = rect.width / 2;
  const cursorY = rect.height / 2;
  const nextK = Math.max(0.45, Math.min(2.6, state.transform.k * ratio));
  const scale = nextK / state.transform.k;
  state.transform.x = cursorX - (cursorX - state.transform.x) * scale;
  state.transform.y = cursorY - (cursorY - state.transform.y) * scale;
  state.transform.k = nextK;
  const viewport = svg.querySelector(".viewport");
  if (viewport)
    viewport.setAttribute(
      "transform",
      `translate(${state.transform.x} ${state.transform.y}) scale(${state.transform.k})`
    );
}

export async function renderGraph(el, params) {
  state.data = null;
  state.allData = null;
  state.reports = [];
  state.queryActive = false;
  state.layout = params.layout === "layered" ? "layered" : "force";
  state.transform = { x: 0, y: 0, k: 1 };
  el.innerHTML = shellHTML();
  document.querySelectorAll("[data-layout]").forEach((button) => {
    button.classList.toggle("active", button.dataset.layout === state.layout);
  });
  bindShell(el, params);
  const preferred = params.report_id || params.report || "";
  try {
    await loadReports();
    fillReportSelect();
    if (state.reports.length) {
      const target = preferred && state.reports.some((item) => item.report_id === preferred)
        ? preferred
        : state.reports[0].report_id;
      await loadGraph(target);
      const select = document.getElementById("report-select");
      if (select) select.value = state.reportId;
    } else if (params.demo === "1") {
      // demo 模式：没有图谱时自动跑一次主主题检索
      const sub = document.getElementById("graph-sub");
      if (sub) sub.textContent = "正在生成演示图谱…";
      await api.search({ query: "预制菜进校园", auto_start: true });
      await loadReports();
      fillReportSelect();
      if (state.reports.length) await loadGraph(state.reports[0].report_id);
      else throw new Error("检索完成但未生成图谱");
    } else {
      el.innerHTML = emptyGraphHTML("需要先完成一次主题检索，系统会自动构建节点与关系。");
      el.querySelector("[data-retry-graph]")?.addEventListener("click", () => renderGraph(el, params));
    }
  } catch (error) {
    el.innerHTML = emptyGraphHTML(error.message || "图谱加载失败");
    el.querySelector("[data-retry-graph]")?.addEventListener("click", () => renderGraph(el, params));
  }
}

export function cleanupGraph() {
  if (state.resizeTimer) clearTimeout(state.resizeTimer);
  state.resizeTimer = null;
}
