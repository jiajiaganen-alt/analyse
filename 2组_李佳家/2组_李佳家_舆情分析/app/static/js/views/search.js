import { api } from "../api.js";
import {
  cite,
  clamp,
  esc,
  fmtNumber,
  fmtTime,
  icon,
  renderInlineError,
  statusBadge,
  toast,
} from "../ui.js";

const TYPE_LABELS = {
  news: "新闻媒体",
  image: "图片素材",
  video: "视频内容",
  forum_post: "论坛帖子",
  internal_data: "内部数据",
};
const TYPE_COLORS = {
  news: "#2563eb",
  image: "#db2777",
  video: "#7c3aed",
  forum_post: "#f59e0b",
  internal_data: "#0d9488",
};
const STEPS = [
  { key: "collect", title: "多来源检索", desc: "主题匹配与来源召回" },
  { key: "multimedia", title: "多媒体解析", desc: "OCR / ASR 文本抽取" },
  { key: "insight", title: "洞察分析", desc: "观点、情绪与风险" },
  { key: "report", title: "报告生成", desc: "8 部分结构化汇总" },
  { key: "graph", title: "图谱构建", desc: "实体关系与引用" },
];

const state = {
  topics: [],
  selectedTypes: new Set(Object.keys(TYPE_LABELS)),
  result: null,
  busy: false,
  stepTimer: null,
  demoQuery: "预制菜进校园",
};

function shellHTML() {
  return `
    <div class="page-head">
      <div>
        <h1 class="page-title">主题检索</h1>
        <p class="page-sub">输入主题词，Agent 流水线将并行检索五类来源，抽取观点、情绪与风险，生成可追溯的结构化报告。</p>
      </div>
      <div class="page-actions">
        <a class="btn btn-sm" href="#/graph">${icon("graph")} 查看图谱</a>
        <a class="btn btn-sm" href="/docs" target="_blank" rel="noopener">${icon("file")} 接口文档</a>
      </div>
    </div>

    <section class="card search-panel">
      <div class="search-row">
        <div class="search-input">
          ${icon("search")}
          <input id="search-query" type="text" placeholder="输入主题词或关键词，例如：预制菜进校园" value="预制菜进校园" autocomplete="off" spellcheck="false">
        </div>
        <button class="btn btn-primary" id="search-btn">${icon("spark")} 开始分析</button>
      </div>
      <div class="search-filters">
        <span class="filter-label">来源类型</span>
        ${Object.entries(TYPE_LABELS)
          .map(
            ([key, label]) => `
            <label class="check-chip checked" data-type="${key}">
              <input type="checkbox" checked value="${key}">
              <span class="box">${icon("check")}</span>
              <span>${label}</span>
            </label>`
          )
          .join("")}
        <div class="quick-topics" id="quick-topics">
          <span>快捷主题</span>
          <button class="quick-topic" data-topic="预制菜进校园">预制菜进校园</button>
          <button class="quick-topic" data-topic="新能源车电池召回">新能源车电池召回</button>
        </div>
      </div>
    </section>

    <div id="pipeline-root"></div>
    <div id="report-root"></div>
  `;
}

function pipelineLoading(query) {
  return `
    <div class="agent-steps">
      <div class="agent-steps-head">
        <h3><span class="ai">AGENT PIPELINE</span> 正在分析「${esc(query)}」</h3>
        <span class="total">多来源检索 → 观点 / 情绪 / 风险抽取 → 洞察汇总 → 报告 → 图谱</span>
      </div>
      <div class="steps-track">
        ${STEPS.map(
          (step, index) => `
          <div class="step ${index === 0 ? "running" : "pending"}" data-step="${index}">
            <div class="step-index">${index === 0 ? '<span class="spin-mini"></span>' : String(index + 1).padStart(2, "0")}</div>
            <div class="step-main">
              <div class="step-title">${esc(step.title)} ${index === 0 ? '<span class="dur">执行中</span>' : ""}</div>
              <div class="step-sub">${esc(step.desc)}</div>
            </div>
          </div>`
        ).join("")}
      </div>
    </div>
  `;
}

function pipelineResult(steps, durationMs) {
  return `
    <div class="agent-steps">
      <div class="agent-steps-head">
        <h3><span class="ai">AGENT PIPELINE</span> 执行完成 <span style="color:#0f9d76;font-weight:500">5 / 5</span></h3>
        <span class="total">总耗时 ${fmtNumber(durationMs)} ms · 每段耗时由服务端实测</span>
      </div>
      <div class="steps-track">
        ${steps
          .map(
            (step, index) => `
          <div class="step ${step.status === "success" ? "success" : "failed"}" data-step="${index}">
            <div class="step-index">${step.status === "success" ? icon("check") : icon("alert")}</div>
            <div class="step-main">
              <div class="step-title">${esc(step.title)} <span class="dur">${fmtNumber(step.duration_ms)} ms</span></div>
              <div class="step-sub" title="${esc(step.summary)}">${esc(step.summary)}</div>
            </div>
          </div>`
          )
          .join("")}
      </div>
    </div>
  `;
}

function reportHeader(data) {
  const report = data.report;
  const sentiment = report.sentiment;
  const risk = report.risk_summary;
  return `
    <div class="report-top" id="report-top">
      <div class="report-top-main">
        <div>
          <div class="report-kicker"><span>STRUCTURED REPORT</span><span style="color:#cdd6e3">·</span><span>8 SECTIONS</span><span style="color:#cdd6e3">·</span><span>${esc(
            report.category || "舆情分析"
          )}</span></div>
          <h2>${esc(report.topic)}</h2>
          <div class="report-meta">
            <span>报告编号 <code>${esc(report.report_id)}</code></span>
            <span>${icon("clock")} ${esc(report.generated_label)}</span>
            <span>来源 <b>${report.source_count}</b> 条</span>
            <span>耗时 <b>${fmtNumber(data.duration_ms)}</b> ms</span>
          </div>
        </div>
        <div class="report-actions">
          <a class="btn btn-primary btn-sm" href="#/graph?report=${encodeURIComponent(report.report_id)}">${icon("graph")} 查看图谱</a>
          <a class="btn btn-sm" href="/api/report/${encodeURIComponent(report.report_id)}/markdown">${icon("download")} 导出 Markdown</a>
          <a class="btn btn-sm" href="/api/report/${encodeURIComponent(report.report_id)}" target="_blank" rel="noopener">${icon("file")} JSON</a>
        </div>
      </div>
      <div class="report-stats">
        <div class="report-stat"><div class="v">${report.source_count}<small>条</small></div><div class="k">来源总数</div></div>
        <div class="report-stat"><div class="v">${report.channels.length}<small>类</small></div><div class="k">传播渠道</div></div>
        <div class="report-stat"><div class="v">${sentiment.ratios.negative}<small>%</small></div><div class="k">负面占比</div></div>
        <div class="report-stat"><div class="v">${esc(risk.level_label)}<small>${risk.score}</small></div><div class="k">综合风险</div></div>
        <div class="report-stat"><div class="v">${Math.round(report.conclusion.confidence * 100)}<small>%</small></div><div class="k">结论置信度</div></div>
      </div>
    </div>
  `;
}

const NAV = [
  ["overview", "概述"],
  ["timeline", "时间线"],
  ["channels", "传播渠道"],
  ["opinions", "主要观点"],
  ["sentiment", "情绪倾向"],
  ["risks", "风险判断"],
  ["evidence", "重点证据"],
  ["conclusion", "结论摘要"],
  ["sources", "来源清单"],
];

function sectionHead(no, title, sub) {
  return `<div class="section-head"><span class="section-no">${no}</span><h3>${esc(title)}</h3><span class="sub">${esc(
    sub
  )}</span></div>`;
}

function reportHTML(data) {
  const report = data.report;
  const overview = report.event_overview;
  const stats = report.stats;
  const sentiment = report.sentiment;
  const risk = report.risk_summary;
  const conclusion = report.conclusion;

  const overviewHTML = `
    <section class="section-card" id="sec-overview">
      ${sectionHead("01", "事件概述", "背景、范围与来源结构")}
      <div class="section-body">
        <div class="overview-text">${overview.paragraphs.map((p) => `<p>${esc(p)}</p>`).join("")}</div>
        <div class="chips" style="margin-top:8px">${cite(overview.refs)} <span class="tiny muted" style="margin-left:4px">结论引用来源</span></div>
        <div class="overview-stats">
          <div class="overview-stat"><div class="k">来源总数</div><div class="v">${stats.source_count} <small>条</small></div></div>
          <div class="overview-stat"><div class="k">渠道覆盖</div><div class="v">${stats.type_coverage} <small>/ 5 类</small></div></div>
          <div class="overview-stat"><div class="k">时间跨度</div><div class="v">${stats.span_days} <small>天</small></div></div>
          <div class="overview-stat"><div class="k">平均可信度</div><div class="v">${stats.avg_credibility} <small>/ 1.0</small></div></div>
        </div>
        <div class="chips" style="margin-top:10px">${report.keywords
          .slice(0, 8)
          .map((item) => `<span class="chip blue">${esc(item.keyword)} <b style="font-weight:600">${item.count}</b></span>`)
          .join("")}</div>
      </div>
    </section>`;

  const timelineHTML = `
    <section class="section-card" id="sec-timeline">
      ${sectionHead("02", "时间线", "按时间顺序 · 点击可查看来源")}
      <div class="timeline-wrap" id="timeline-wrap"></div>
    </section>`;

  const channelsHTML = `
    <section class="section-card" id="sec-channels">
      ${sectionHead("03", "传播渠道", "按来源类型统计传播分布")}
      <div class="section-body">
        <div class="channel-legend">
          <span><i class="legend-dot" style="background:#2563eb"></i>条形长度 = 来源数量</span>
          <span><i class="legend-dot" style="background:#f26d6d"></i>右侧数值 = 该渠道负面占比</span>
          <span class="muted">共 ${report.channels.reduce((sum, item) => sum + item.count, 0)} 条来源</span>
        </div>
        <div id="channel-wrap"></div>
      </div>
    </section>`;

  const opinionsHTML = `
    <section class="section-card" id="sec-opinions">
      ${sectionHead("04", "主要观点", "按来源与角色聚类")}
      <div class="section-body">
        <div class="opinion-grid">
          ${report.opinions
            .map(
              (opinion) => `
            <article class="opinion-card">
              <div class="opinion-head">
                <span class="opinion-role">${esc(opinion.role)}</span>
                <span class="badge ${
                  opinion.tone === "negative" ? "badge-negative" : opinion.tone === "positive" ? "badge-positive" : "badge-neutral"
                }">${esc(opinion.stance)}</span>
                <span class="opinion-count">${opinion.count} 条 · 负面 ${opinion.sentiment_ratios.negative}%</span>
              </div>
              <p class="opinion-summary">${esc(opinion.summary)}</p>
              ${opinion.highlights
                .slice(0, 2)
                .map(
                  (item) =>
                    `<div class="opinion-quote">“${esc(item.text)}” <span class="ref">[${esc(item.ref)}]</span><span class="tiny muted"> · ${esc(
                      item.position
                    )}</span></div>`
                )
                .join("")}
              <div class="chips" style="margin-top:7px">${cite(opinion.refs)}</div>
            </article>`
            )
            .join("")}
        </div>
      </div>
    </section>`;

  const sentimentHTML = `
    <section class="section-card" id="sec-sentiment">
      ${sectionHead("05", "情绪倾向", "正向 / 中性 / 负向整体判断")}
      <div class="section-body">
        <div class="sentiment-wrap">
          <div>
            <div class="sent-stack">
              ${["positive", "neutral", "negative"]
                .map((key) => {
                  const ratio = sentiment.ratios[key];
                  if (ratio <= 0) return "";
                  return `<div class="sent-seg ${key.slice(0, 3)}" style="width:${ratio}%">${
                    ratio >= 8 ? ratio + "%" : ""
                  }</div>`;
                })
                .join("")}
            </div>
            <div class="sent-legend">
              <span><i class="legend-dot" style="background:#10b981"></i>正向 <b class="num">${sentiment.counts.positive}</b> 条 · ${sentiment.ratios.positive}%</span>
              <span><i class="legend-dot" style="background:#b3bfd0"></i>中性 <b class="num">${sentiment.counts.neutral}</b> 条 · ${sentiment.ratios.neutral}%</span>
              <span><i class="legend-dot" style="background:#ef4444"></i>负向 <b class="num">${sentiment.counts.negative}</b> 条 · ${sentiment.ratios.negative}%</span>
            </div>
            <div class="sentiment-trend">
              <span class="trend-icon trend-${esc(sentiment.trend_direction)}">${
                sentiment.trend_direction === "up" ? "↑" : sentiment.trend_direction === "down" ? "↓" : "→"
              }</span>
              <span>${esc(sentiment.trend)}</span>
            </div>
            <div class="chips" style="margin-top:8px">${cite(sentiment.refs)}</div>
          </div>
          <div class="sentiment-judge">
            <div class="tag">整体判断 · ${esc(sentiment.label)}</div>
            <p>${esc(sentiment.judgement)}</p>
          </div>
        </div>
      </div>
    </section>`;

  const risksHTML = `
    <section class="section-card" id="sec-risks">
      ${sectionHead("06", "风险判断", "高风险点与关注事项")}
      <div class="section-body">
        <div class="risk-grid">
          ${report.risks
            .map(
              (item) => `
            <article class="risk-card ${esc(item.level)}">
              <div class="risk-head">
                <span class="badge ${
                  item.level === "high" ? "badge-high" : item.level === "medium" ? "badge-medium" : "badge-low"
                }">${esc(item.level_label)}</span>
                <h4>${esc(item.title)}</h4>
              </div>
              <p class="risk-desc">${esc(item.description)}</p>
              <div class="risk-indicators">${item.indicators
                .map((indicator) => `<span class="risk-indicator">${esc(indicator)}</span>`)
                .join("")}</div>
              <div class="risk-foot"><span>关联来源 ${item.related_count} 条</span><span>${cite(item.refs)}</span></div>
            </article>`
            )
            .join("")}
        </div>
        <div class="risk-summary-bar">
          <span>综合风险 <b>${esc(risk.level_label)}</b>（${risk.score} / 100）</span>
          <span class="muted">${risk.basis.map((item) => esc(item)).join(" · ")}</span>
          <span class="risk-score"><span class="meter"><i style="width:${clamp(risk.score, 0, 100)}%"></i></span>${risk.score}</span>
        </div>
      </div>
    </section>`;

  const evidenceHTML = `
    <section class="section-card" id="sec-evidence">
      ${sectionHead("07", "重点证据", "标题 / 链接 / 摘要 / 引用位置")}
      <div class="section-body" style="padding-top:6px">
        <div class="table-wrap">
          <table class="table evidence-table">
            <thead><tr><th style="width:44px">编号</th><th>来源证据</th><th style="width:80px">类型</th><th style="width:100px">发布时间</th><th style="width:210px">引用位置</th><th style="width:56px">情绪</th></tr></thead>
            <tbody>
              ${report.evidence
                .map(
                  (item) => `
                <tr>
                  <td><span class="cite">${esc(item.ref)}</span></td>
                  <td class="evidence-title">
                    <a href="${esc(item.url)}" target="_blank" rel="noopener">${esc(item.title)}</a>
                    <div class="evidence-summary">${esc(item.summary)}</div>
                    <div class="tiny muted" style="margin-top:2px">${esc(item.source)} · ${esc(item.author_role)}</div>
                  </td>
                  <td><span class="chip">${esc(item.source_type_label)}</span></td>
                  <td class="muted nowrap">${fmtTime(item.published_at, "short")}</td>
                  <td>
                    <div class="evidence-quote">“${esc(item.quote)}”<div class="pos">${esc(item.quote_position)}</div></div>
                  </td>
                  <td><span class="sent-dot ${esc(item.sentiment)}"><i></i>${esc(item.sentiment_label)}</span></td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    </section>`;

  const conclusionHTML = `
    <section class="section-card conclusion-card" id="sec-conclusion">
      ${sectionHead("08", "结论摘要", "最终结论、建议与置信度")}
      <div class="conclusion-body">
        <p class="conclusion-summary">${esc(conclusion.summary)}</p>
        <div class="conclusion-recs" style="grid-template-columns:repeat(${Math.min(
          3,
          conclusion.recommendations.length
        )},minmax(0,1fr))">
          ${conclusion.recommendations
            .map(
              (item, index) => `
            <div class="rec-item">
              <span class="idx">${String(index + 1).padStart(2, "0")}</span>
              <h5>${esc(item.title)}</h5>
              <p>${esc(item.text)} ${cite(item.refs)}</p>
            </div>`
            )
            .join("")}
        </div>
        <div class="conclusion-foot">
          <span>结论可追溯至来源编号与图谱节点</span>
          <span class="confidence">置信度 ${Math.round(conclusion.confidence * 100)}%
            <span class="bar"><i style="width:${clamp(conclusion.confidence * 100, 0, 100)}%"></i></span>
          </span>
        </div>
      </div>
    </section>`;

  const sourcesHTML = `
    <section class="section-card" id="sec-sources">
      ${sectionHead("09", "来源清单", "全部来源与引用编号对照")}
      <div class="section-body">
        <div class="sources-toolbar">
          <div class="sources-search">${icon("search")}<input id="source-filter" placeholder="筛选来源标题、媒体或关键词"></div>
          <span class="sources-count" id="source-count">共 ${report.sources.length} 条来源</span>
          <span class="muted tiny" style="margin-left:auto">编号 [S01] 用于报告引用与图谱回溯</span>
        </div>
        <div class="sources-table-wrap">
          <table class="table sources-table">
            <thead><tr><th style="width:48px">编号</th><th style="width:72px">类型</th><th>标题</th><th style="width:120px">来源</th><th style="width:94px">发布时间</th><th style="width:58px">情绪</th><th style="width:44px">链接</th></tr></thead>
            <tbody id="source-rows">
              ${report.sources
                .map(
                  (source) => `
                <tr data-search="${esc(
                  `${source.ref} ${source.title} ${source.source} ${(source.keywords || []).join(" ")}`.toLowerCase()
                )}">
                  <td><span class="cite">${esc(source.ref)}</span></td>
                  <td><span class="tiny">${esc(source.source_type_label)}</span></td>
                  <td class="t-title">${esc(source.title)}</td>
                  <td class="muted">${esc(source.source)}</td>
                  <td class="muted nowrap">${fmtTime(source.published_at, "short")}</td>
                  <td><span class="sent-dot ${esc(source.sentiment)}"><i></i>${esc(source.sentiment_label)}</span></td>
                  <td><a class="source-link" href="${esc(source.url)}" target="_blank" rel="noopener">${icon("external")}</a></td>
                </tr>`
                )
                .join("")}
            </tbody>
          </table>
        </div>
      </div>
    </section>`;

  return `
    ${reportHeader(data)}
    <nav class="report-nav" aria-label="报告章节">
      ${NAV.map(([key, label]) => `<button data-scroll="sec-${key}">${label}</button>`).join("")}
    </nav>
    ${overviewHTML}
    ${timelineHTML}
    ${channelsHTML}
    ${opinionsHTML}
    ${sentimentHTML}
    ${risksHTML}
    ${evidenceHTML}
    ${conclusionHTML}
    ${sourcesHTML}
  `;
}

/* ------------------------------------------------------------ 时间线 SVG */
function wrapText(text, perLine, maxLines) {
  const value = String(text || "");
  const lines = [];
  for (let index = 0; index < value.length && lines.length < maxLines; index += perLine) {
    lines.push(value.slice(index, index + perLine));
  }
  if (lines.length === maxLines && value.length > perLine * maxLines) {
    lines[maxLines - 1] = lines[maxLines - 1].slice(0, perLine - 1) + "…";
  }
  return lines;
}

function drawTimeline(container, events) {
  if (!container) return;
  if (!events || !events.length) {
    container.innerHTML = `<div class="empty">暂无时间线数据</div>`;
    return;
  }
  const W = 1120;
  const H = 306;
  const axisY = 168;
  const padX = 58;
  const count = events.length;
  const spacing = count > 1 ? (W - padX * 2) / (count - 1) : 0;
  const cardW = 120;
  const cardH = 104;
  const parts = [];
  parts.push(`<line x1="${padX - 20}" y1="${axisY}" x2="${W - padX + 20}" y2="${axisY}" class="tl-axis"/>`);
  events.forEach((event, index) => {
    const x = padX + index * spacing;
    const above = index % 2 === 0;
    const cardY = above ? axisY - 22 - cardH : axisY + 22;
    const cardX = clamp(x - cardW / 2, 8, W - cardW - 8);
    const stemEnd = above ? cardY + cardH : cardY;
    parts.push(`<line x1="${x.toFixed(1)}" y1="${axisY}" x2="${x.toFixed(1)}" y2="${stemEnd}" class="tl-stem"/>`);
    parts.push(
      `<circle cx="${x.toFixed(1)}" cy="${axisY}" r="${event.importance === "high" ? 5 : 3.8}" class="tl-dot ${
        event.importance === "high" ? "high" : ""
      }"><title>${esc(event.description)}</title></circle>`
    );
    parts.push(
      `<rect x="${cardX.toFixed(1)}" y="${cardY}" width="${cardW}" height="${cardH}" rx="8" class="tl-card ${
        event.importance === "high" ? "high" : ""
      }"><title>${esc(event.description)}</title></rect>`
    );
    parts.push(
      `<text x="${(cardX + 10).toFixed(1)}" y="${cardY + 16}" class="tl-date">${esc(event.date_label)} ${esc(
        event.time_label
      )}</text>`
    );
    const lines = wrapText(event.title, 10, 3);
    lines.forEach((line, lineIndex) => {
      parts.push(
        `<text x="${(cardX + 10).toFixed(1)}" y="${cardY + 34 + lineIndex * 13}" class="tl-title">${esc(line)}</text>`
      );
    });
    parts.push(
      `<text x="${(cardX + 10).toFixed(1)}" y="${cardY + cardH - 10}" class="tl-ref">${event.refs
        .slice(0, 3)
        .map((ref) => `[${ref}]`)
        .join(" ")}</text>`
    );
  });
  container.innerHTML = `<svg class="timeline-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="舆情时间线">${parts.join(
    ""
  )}</svg>`;
}

/* ------------------------------------------------------------ 渠道条形图 */
function drawChannels(container, channels) {
  if (!container) return;
  const W = 1120;
  const rowH = 38;
  const top = 20;
  const H = top + channels.length * rowH + 16;
  const labelW = 92;
  const maxBar = 700;
  const maxCount = Math.max(...channels.map((item) => item.count), 1);
  const parts = [];
  channels.forEach((channel, index) => {
    const y = top + index * rowH;
    const barW = Math.max(6, (channel.count / maxCount) * maxBar);
    const color = TYPE_COLORS[channel.source_type] || "#2563eb";
    parts.push(
      `<text x="0" y="${y + 12}" class="ch-label">${esc(channel.label)}</text>`,
      `<rect x="${labelW}" y="${y + 1}" width="${maxBar}" height="15" rx="7.5" class="ch-track"/>`,
      `<rect x="${labelW}" y="${y + 1}" width="${barW.toFixed(1)}" height="15" rx="7.5" fill="${color}" opacity="0.92"/>`,
      `<text x="${labelW + barW + 10}" y="${y + 13}" class="ch-count">${channel.count} 条</text>`,
      `<text x="${labelW + barW + 58}" y="${y + 13}" class="ch-pct">${channel.ratio}%</text>`,
      `<text x="${W - 8}" y="${y + 13}" text-anchor="end" class="ch-pct" style="fill:${
        channel.negative_ratio >= 40 ? "#dc2626" : "#98a2b3"
      }">负面 ${channel.negative_ratio}%</text>`,
      `<text x="${W - 112}" y="${y + 13}" text-anchor="end" class="ch-pct">${esc(
        channel.top_sources.slice(0, 1).join("")
      )}</text>`
    );
  });
  container.innerHTML = `<svg class="channel-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="传播渠道条形图">${parts.join(
    ""
  )}</svg>`;
}

/* ------------------------------------------------------------ 绑定 */
function bindReport(el, data, params) {
  const report = data.report;
  drawTimeline(document.getElementById("timeline-wrap"), report.timeline);
  drawChannels(document.getElementById("channel-wrap"), report.channels);

  el.querySelectorAll("[data-scroll]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.scroll);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });

  const filter = document.getElementById("source-filter");
  if (filter) {
    filter.addEventListener("input", () => {
      const keyword = filter.value.trim().toLowerCase();
      let visible = 0;
      document.querySelectorAll("#source-rows tr").forEach((row) => {
        const matched = !keyword || (row.dataset.search || "").includes(keyword);
        row.style.display = matched ? "" : "none";
        if (matched) visible += 1;
      });
      const countEl = document.getElementById("source-count");
      if (countEl) countEl.textContent = `显示 ${visible} / ${report.sources.length} 条来源`;
    });
  }

  if (params.focus) {
    document.body.classList.add("focus-mode");
    document.body.dataset.focusSection = params.focus;
  }
}

export function cleanupSearch() {
  document.body.classList.remove("has-report", "focus-mode");
  delete document.body.dataset.focusSection;
}

async function loadTopics() {
  try {
    const data = await api.topics();
    state.topics = data.topics || [];
    state.demoQuery = data.demo_query || state.demoQuery;
    const container = document.getElementById("quick-topics");
    if (container) {
      container.innerHTML = `<span>快捷主题</span>${state.topics
        .map(
          (topic) =>
            `<button class="quick-topic" data-topic="${esc(topic.topic)}" title="${esc(
              topic.topic
            )} · ${topic.source_count} 条来源">${esc(topic.topic)}</button>`
        )
        .join("")}`;
      bindQuickTopics();
    }
  } catch (error) {
    /* 快捷主题加载失败不阻断检索 */
  }
}

function bindQuickTopics() {
  document.querySelectorAll(".quick-topic").forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById("search-query");
      if (input) input.value = button.dataset.topic || "";
    });
  });
}

function searchErrorHTML(error) {
  const payload = error.payload || {};
  const detail = (payload.error && payload.error.detail) || payload.detail_data || {};
  const missing = detail.missing_apps || [];
  const available = (payload.error && payload.error.detail && payload.error.detail.available_topics) || [];
  const isOffline = /系统未上线|系统未启动/.test(error.message || "");
  let action = "";
  if (missing.length || isOffline) {
    action = `<button class="btn btn-primary btn-sm" data-prepare-retry>${icon("play")} 启动所需应用并重试</button>`;
  }
  return `<div class="card card-pad" style="border-color:#f3cccc;background:#fffafa;margin-bottom:12px">
    <div style="display:flex;gap:10px;align-items:flex-start">
      <span style="width:28px;height:28px;border-radius:8px;background:#fdeeee;color:#b42318;display:flex;align-items:center;justify-content:center;flex:0 0 28px">${icon(
        "alert"
      )}</span>
      <div style="flex:1">
        <div style="font-weight:600;margin-bottom:3px">检索未完成</div>
        <div class="muted" style="font-size:11.5px">${esc(error.message || "未知错误")}</div>
        ${
          missing.length
            ? `<div class="chips" style="margin-top:7px">${missing
                .map((name) => `<span class="chip red">${esc(name)} 未运行</span>`)
                .join("")}</div>`
            : ""
        }
        ${available.length ? `<div class="tiny muted" style="margin-top:6px">可用主题：${available.map(esc).join("、")}</div>` : ""}
      </div>
      <div style="display:flex;gap:7px">${action}<button class="btn btn-sm" data-retry-search>重试</button></div>
    </div>
  </div>`;
}

function bindErrorActions(el, query) {
  el.querySelectorAll("[data-retry-search]").forEach((button) =>
    button.addEventListener("click", () => runSearch(el, query))
  );
  el.querySelectorAll("[data-prepare-retry]").forEach((button) =>
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "正在启动…";
      try {
        const status = await api.getStatus();
        if (status.system.system_status !== "online") await api.systemStart();
        const required = ["topic_search", "multimedia_search", "insight_analysis", "report_writer"];
        await Promise.all(required.map((name) => api.startApp(name, true).catch(() => null)));
      } catch (error) {
        /* ignore */
      }
      await runSearch(el, query);
    })
  );
}

async function runSearch(el, query) {
  if (state.busy) return;
  const cleaned = String(query || "").trim();
  if (!cleaned) {
    toast("请输入检索主题", "warn");
    return;
  }
  const types = [...state.selectedTypes];
  if (!types.length) {
    toast("请至少选择一种来源类型", "warn");
    return;
  }
  state.busy = true;
  const button = document.getElementById("search-btn");
  const original = button ? button.innerHTML : "";
  if (button) {
    button.disabled = true;
    button.innerHTML = `<span class="spin-mini" style="border-color:#cfe0ff;border-top-color:#fff"></span> 分析中…`;
  }
  const pipelineRoot = document.getElementById("pipeline-root");
  const reportRoot = document.getElementById("report-root");
  if (pipelineRoot) pipelineRoot.innerHTML = pipelineLoading(cleaned);
  if (reportRoot) reportRoot.innerHTML = "";
  animateSteps();

  try {
    const data = await api.search({
      query: cleaned,
      source_types: types,
      auto_start: true,
    });
    if (state.stepTimer) clearInterval(state.stepTimer);
    state.stepTimer = null;
    state.result = data;
    document.body.classList.add("has-report");
    if (pipelineRoot) pipelineRoot.innerHTML = pipelineResult(data.agent_steps, data.duration_ms);
    if (reportRoot) {
      reportRoot.innerHTML = reportHTML(data);
      bindReport(el, data, currentParams);
      bindReportLinks(el, data);
    }
    toast(`报告 ${data.report_id} 生成完成，来源 ${data.source_count} 条`, "success");
  } catch (error) {
    if (state.stepTimer) clearInterval(state.stepTimer);
    state.stepTimer = null;
    if (pipelineRoot) {
      pipelineRoot.innerHTML = `<div class="agent-steps" style="border-color:#f3cccc"><div class="agent-steps-head"><h3><span class="ai" style="color:#b42318;background:#fdeeee;border-color:#f5d0cd">AGENT PIPELINE</span> 流水线中断</h3><span class="total">未生成报告</span></div><div style="padding:8px 4px;color:#667085;font-size:11px">${esc(
        error.message
      )}</div></div>`;
    }
    if (reportRoot) {
      reportRoot.innerHTML = searchErrorHTML(error);
      bindErrorActions(el, cleaned);
    }
    toast(error.message || "检索失败", "error", 5000);
  } finally {
    state.busy = false;
    if (button) {
      button.disabled = false;
      button.innerHTML = original;
    }
  }
}

function bindReportLinks(el, data) {
  /* 预留：报告内的复制/书签行为，当前使用原生链接 */
}

let currentParams = {};

function animateSteps() {
  if (state.stepTimer) clearInterval(state.stepTimer);
  let index = 0;
  state.stepTimer = setInterval(() => {
    const steps = document.querySelectorAll("#pipeline-root .step");
    if (!steps.length) return;
    index += 1;
    steps.forEach((step, stepIndex) => {
      step.classList.remove("running");
      if (stepIndex < index) step.classList.add("success");
      else if (stepIndex === index) step.classList.add("running");
      else step.classList.add("pending");
      const badge = step.querySelector(".step-index");
      if (badge) {
        if (stepIndex < index) badge.innerHTML = icon("check");
        else if (stepIndex === index) badge.innerHTML = '<span class="spin-mini"></span>';
        else badge.textContent = String(stepIndex + 1).padStart(2, "0");
      }
    });
    if (index >= steps.length - 1) {
      clearInterval(state.stepTimer);
      state.stepTimer = null;
    }
  }, 320);
}

function bindSearchControls(el) {
  el.querySelectorAll(".check-chip").forEach((chip) => {
    const input = chip.querySelector("input");
    chip.addEventListener("click", (event) => {
      event.preventDefault();
      input.checked = !input.checked;
      chip.classList.toggle("checked", input.checked);
      if (input.checked) state.selectedTypes.add(input.value);
      else state.selectedTypes.delete(input.value);
    });
  });
  bindQuickTopics();
  const button = document.getElementById("search-btn");
  const input = document.getElementById("search-query");
  if (button) {
    button.addEventListener("click", () => runSearch(el, input ? input.value : ""));
  }
  if (input) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") runSearch(el, input.value);
    });
  }
}

async function ensureAppsForDemo() {
  try {
    const status = await api.getStatus();
    if (status.system.system_status !== "online") {
      await api.systemStart();
    }
    const required = ["topic_search", "multimedia_search", "insight_analysis", "report_writer"];
    const todo = required.filter((name) => {
      const app = (status.apps || []).find((item) => item.app_name === name);
      return app && app.enabled && !["running", "starting"].includes(app.status);
    });
    await Promise.all(todo.map((name) => api.startApp(name, true).catch(() => null)));
  } catch (error) {
    /* demo 启动失败时让检索接口返回明确错误 */
  }
}

export async function renderSearch(el, params) {
  currentParams = params || {};
  state.result = null;
  state.busy = false;
  document.body.classList.remove("has-report", "focus-mode");
  delete document.body.dataset.focusSection;
  if (state.stepTimer) clearInterval(state.stepTimer);
  state.stepTimer = null;
  el.innerHTML = shellHTML();
  bindSearchControls(el);
  await loadTopics();
  const input = document.getElementById("search-query");
  if (input && params.q) input.value = params.q;
  if (params.demo === "1") {
    if (input) input.value = state.demoQuery || "预制菜进校园";
    await ensureAppsForDemo();
    await runSearch(el, input ? input.value : state.demoQuery);
  } else if (params.q) {
    await runSearch(el, params.q);
  }
}

export function onSearchEvent() {
  /* 检索页不依赖实时事件，保留接口 */
}
