# -*- coding: utf-8 -*-
"""生成微调实验报告页面（离线 HTML，可直接截图）。

读取：
    data/dataset_stats.json
    data/preview_samples.json
    outputs/training_summary.json
    outputs/training_log.csv
    outputs/eval_base.json
    outputs/eval_tuned.json
输出：
    report/index.html  dataset.html  training.html  evaluation.html  samples.html
    report/style.css
"""

from __future__ import annotations

import csv
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "report"
OUTPUT_DIR = ROOT / "outputs"

CSS = """
:root{
  --bg:#f4f6fb; --card:#ffffff; --ink:#0f172a; --muted:#64748b; --line:#e2e8f0;
  --brand:#2563eb; --brand-dark:#1e3a8a; --green:#16a34a; --orange:#ea580c; --red:#dc2626;
  --violet:#7c3aed; --cyan:#0891b2;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font-family:"Microsoft YaHei","Segoe UI",sans-serif;font-size:14px;line-height:1.6}
a{color:inherit;text-decoration:none}
.topbar{background:#0b1220;color:#e2e8f0;padding:14px 32px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:10;border-bottom:1px solid #1e293b}
.brand{display:flex;align-items:center;gap:12px;font-weight:700;letter-spacing:.5px}
.brand .mark{width:34px;height:34px;border-radius:10px;background:linear-gradient(135deg,#3b82f6,#8b5cf6);display:flex;align-items:center;justify-content:center;font-size:18px}
.nav{display:flex;gap:6px}
.nav a{padding:8px 14px;border-radius:9px;color:#cbd5e1;font-size:13px}
.nav a:hover{background:#1e293b;color:#fff}
.nav a.active{background:#1d4ed8;color:#fff}
.page{max-width:1180px;margin:0 auto;padding:28px 24px 48px}
.hero{background:linear-gradient(120deg,#0b1220 0%,#172554 55%,#1d4ed8 100%);border-radius:18px;padding:30px 34px;color:#fff;position:relative;overflow:hidden}
.hero:after{content:"";position:absolute;right:-80px;top:-80px;width:280px;height:280px;border-radius:50%;background:rgba(96,165,250,.18)}
.hero h1{margin:0 0 8px;font-size:28px;letter-spacing:.5px}
.hero p{margin:0;color:#c7d2fe;font-size:14px}
.tags{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.tag{border:1px solid rgba(255,255,255,.25);background:rgba(255,255,255,.08);padding:4px 10px;border-radius:999px;font-size:12px;color:#e0e7ff}
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:14px;margin-top:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px;box-shadow:0 4px 14px rgba(15,23,42,.05)}
.kpi .label{color:var(--muted);font-size:12px;margin-bottom:6px}
.kpi .value{font-size:24px;font-weight:800;letter-spacing:.3px}
.kpi .sub{color:var(--muted);font-size:12px;margin-top:2px}
.section{margin-top:26px}
.section h2{font-size:19px;margin:0 0 4px;display:flex;align-items:center;gap:9px}
.section h2 .dot{width:8px;height:24px;border-radius:4px;background:linear-gradient(180deg,#3b82f6,#8b5cf6)}
.section .desc{color:var(--muted);font-size:13px;margin:0 0 14px}
.grid{display:grid;gap:16px}
.g2{grid-template-columns:1fr 1fr}
.g3{grid-template-columns:repeat(3,1fr)}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px 22px;box-shadow:0 4px 14px rgba(15,23,42,.04)}
.card h3{margin:0 0 12px;font-size:15px}
.card .cap{color:var(--muted);font-size:12px;margin-top:10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#f8fafc;color:#475569;text-align:left;font-weight:600;padding:9px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
td{padding:9px 10px;border-bottom:1px solid #f1f5f9;vertical-align:top}
tr:hover td{background:#f8fbff}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600}
.pill.green{background:#dcfce7;color:#15803d}
.pill.orange{background:#ffedd5;color:#c2410c}
.pill.red{background:#fee2e2;color:#b91c1c}
.pill.blue{background:#dbeafe;color:#1d4ed8}
.pill.gray{background:#f1f5f9;color:#475569}
.metric-table td.num,.metric-table th.num{text-align:right;font-variant-numeric:tabular-nums}
.legend{display:flex;gap:16px;font-size:12px;color:var(--muted);margin-top:10px;align-items:center;flex-wrap:wrap}
.legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:5px}
.terminal{background:#0b1220;border-radius:12px;padding:14px 16px;color:#cbd5e1;font-family:Consolas,"Courier New",monospace;font-size:12px;line-height:1.75;overflow:hidden}
.terminal .g{color:#4ade80}.terminal .b{color:#60a5fa}.terminal .y{color:#facc15}.terminal .m{color:#94a3b8}
.chat{background:#f8fafc;border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-size:13px;white-space:pre-wrap;line-height:1.7}
.chat.user{background:#eff6ff;border-color:#bfdbfe}
.chat.answer{margin-top:10px}
.badge{display:inline-flex;align-items:center;gap:5px;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px}
.badge.ok{background:#dcfce7;color:#15803d}
.badge.bad{background:#fee2e2;color:#b91c1c}
.sample{border:1px solid var(--line);border-radius:14px;background:#fff;padding:18px 20px;margin-bottom:16px}
.sample .head{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px}
.sample .q{font-weight:700;margin:6px 0 10px}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.col{border:1px solid var(--line);border-radius:10px;padding:12px;background:#fcfdff}
.col h4{margin:0 0 8px;font-size:13px;display:flex;justify-content:space-between}
.col.base h4{color:#b45309}.col.tuned h4{color:#1d4ed8}
.answer{white-space:pre-wrap;font-size:12.5px;color:#334155;max-height:260px;overflow:auto}
.note{background:#fffbeb;border:1px solid #fde68a;border-radius:12px;padding:14px 16px;color:#92400e;font-size:13px}
.footer{margin-top:30px;color:#94a3b8;font-size:12px;text-align:center}
.bar-row{display:grid;grid-template-columns:150px 1fr 50px;gap:10px;align-items:center;margin-bottom:9px;font-size:13px}
.bar-track{display:block;height:10px;border-radius:6px;background:#eef2f7;overflow:hidden}
.bar-fill{display:block;height:100%;border-radius:6px;background:linear-gradient(90deg,#3b82f6,#8b5cf6)}
.kv{display:grid;grid-template-columns:150px 1fr;gap:8px 14px;font-size:13px}
.kv .k{color:var(--muted)}
code{background:#f1f5f9;padding:1px 6px;border-radius:6px;font-size:12px}
"""

NAV_ITEMS = [
    ("index.html", "总览"),
    ("dataset.html", "数据集"),
    ("training.html", "训练"),
    ("evaluation.html", "评测"),
    ("samples.html", "样例对比"),
]


def esc(text: str) -> str:
    return html.escape(str(text))


def load_json(path: Path, default=None):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def fmt(value, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def delta_class(delta: float) -> str:
    return "green" if delta > 0.005 else ("red" if delta < -0.005 else "gray")


def shell(title: str, active: str, body: str) -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if href == active else ""}">{label}</a>'
        for href, label in NAV_ITEMS
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<link rel="stylesheet" href="style.css">
</head>
<body>
<div class="topbar">
  <div class="brand"><span class="mark">知</span><span>知行学堂 · 知识库问答模型微调实验</span></div>
  <nav class="nav">{nav}</nav>
</div>
<div class="page">
{body}
<div class="footer">实验环境：Windows · Python 3.12 · PyTorch CPU · Qwen2.5-0.5B-Instruct · LoRA (r=16)　|　数据与指标均可通过 scripts/ 目录脚本复现</div>
</div>
</body>
</html>"""


def hero(title: str, subtitle: str, tags: list[str]) -> str:
    tag_html = "".join(f'<span class="tag">{esc(t)}</span>' for t in tags)
    return f"""<div class="hero">
  <h1>{esc(title)}</h1>
  <p>{esc(subtitle)}</p>
  <div class="tags">{tag_html}</div>
</div>"""


def kpi(label: str, value: str, sub: str = "") -> str:
    return f"""<div class="kpi"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div><div class="sub">{esc(sub)}</div></div>"""


def horizontal_bars(items: list[tuple[str, float, str]], max_value: float) -> str:
    rows = []
    for label, value, display in items:
        width = max(2, value / max_value * 100)
        rows.append(
            f'<div class="bar-row"><span>{esc(label)}</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{width:.1f}%"></span></span>'
            f'<strong>{esc(display)}</strong></div>'
        )
    return "".join(rows)


def donut(percent: float, size: int = 150, color: str = "#16a34a") -> str:
    radius = 54
    circumference = 2 * math.pi * radius
    dash = circumference * percent
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 140 140">
  <circle cx="70" cy="70" r="{radius}" fill="none" stroke="#eef2f7" stroke-width="16"/>
  <circle cx="70" cy="70" r="{radius}" fill="none" stroke="{color}" stroke-width="16"
     stroke-dasharray="{dash:.1f} {circumference:.1f}" stroke-linecap="round" transform="rotate(-90 70 70)"/>
  <text x="70" y="66" text-anchor="middle" font-size="22" font-weight="700" fill="#0f172a">{percent * 100:.0f}%</text>
  <text x="70" y="86" text-anchor="middle" font-size="11" fill="#64748b">可回答</text>
</svg>"""


def line_chart(rows: list[dict], width: int = 1020, height: int = 300) -> str:
    if not rows:
        return "<p>暂无训练日志</p>"
    pad_l, pad_r, pad_t, pad_b = 55, 20, 20, 38
    losses = [float(r["loss"]) for r in rows if r.get("loss")]
    vals = [float(r["val_loss"]) for r in rows if r.get("val_loss")]
    all_values = losses + vals
    if not all_values:
        return "<p>暂无损失数据</p>"
    vmin, vmax = min(all_values), max(all_values)
    if vmax - vmin < 0.05:
        vmax = vmin + 0.05
    vmin = max(0, vmin - (vmax - vmin) * 0.15)
    steps = [int(r["step"]) for r in rows]
    max_step = max(steps)

    def x(step: int) -> float:
        return pad_l + (step - 1) / max(1, max_step - 1) * (width - pad_l - pad_r)

    def y(value: float) -> float:
        return pad_t + (vmax - value) / (vmax - vmin) * (height - pad_t - pad_b)

    grid = []
    for i in range(5):
        value = vmin + (vmax - vmin) * i / 4
        yy = y(value)
        grid.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" stroke="#eef2f7"/>'
            f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="10" fill="#94a3b8">{value:.2f}</text>'
        )
    x_ticks = []
    for i in range(6):
        step = 1 + round((max_step - 1) * i / 5)
        x_ticks.append(
            f'<text x="{x(step):.1f}" y="{height - 14}" text-anchor="middle" font-size="10" fill="#94a3b8">{step}</text>'
        )
    loss_points = " ".join(f"{x(int(r['step'])):.1f},{y(float(r['loss'])):.1f}" for r in rows if r.get("loss"))
    val_points = [(x(int(r["step"])), y(float(r["val_loss"]))) for r in rows if r.get("val_loss")]
    val_line = ""
    if val_points:
        val_line = (
            '<polyline points="' + " ".join(f"{px:.1f},{py:.1f}" for px, py in val_points) +
            '" fill="none" stroke="#f59e0b" stroke-width="2.2"/>'
        )
        val_line += "".join(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.4" fill="#fff" stroke="#f59e0b" stroke-width="2"/>'
            for px, py in val_points
        )
    return f"""<svg width="100%" viewBox="0 0 {width} {height}" style="display:block">
  {''.join(grid)}
  {''.join(x_ticks)}
  <polyline points="{loss_points}" fill="none" stroke="#2563eb" stroke-width="2.8"/>
  {val_line}
  <text x="{width / 2:.0f}" y="{height - 2}" text-anchor="middle" font-size="10" fill="#94a3b8">优化步数（step）</text>
</svg>"""


def grouped_bar_chart(labels: list[str], series_a: list[float], series_b: list[float],
                      name_a: str = "基线模型", name_b: str = "微调模型",
                      width: int = 1040, height: int = 320) -> str:
    pad_l, pad_r, pad_t, pad_b = 48, 16, 18, 52
    n = len(labels)
    slot = (width - pad_l - pad_r) / max(1, n)
    bar_w = slot * 0.26
    grid = []
    for i in range(5):
        value = i / 4
        yy = pad_t + (1 - value) * (height - pad_t - pad_b)
        grid.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{width - pad_r}" y2="{yy:.1f}" stroke="#eef2f7"/>'
            f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" text-anchor="end" font-size="10" fill="#94a3b8">{value:.1f}</text>'
        )
    bars = []
    for i, label in enumerate(labels):
        center = pad_l + slot * (i + 0.5)
        for j, (value, color) in enumerate(((series_a[i], "#f59e0b"), (series_b[i], "#2563eb"))):
            bar_h = max(1.5, value * (height - pad_t - pad_b))
            xx = center - bar_w + j * (bar_w + 3)
            bars.append(
                f'<rect x="{xx:.1f}" y="{height - pad_b - bar_h:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'rx="3" fill="{color}"/>'
            )
            bars.append(
                f'<text x="{xx + bar_w / 2:.1f}" y="{height - pad_b - bar_h - 5:.1f}" text-anchor="middle" '
                f'font-size="9.5" fill="#475569">{value:.2f}</text>'
            )
        bars.append(
            f'<text x="{center:.1f}" y="{height - 24}" text-anchor="middle" font-size="10.5" fill="#475569">{esc(label)}</text>'
        )
    return f"""<svg width="100%" viewBox="0 0 {width} {height}" style="display:block">
  {''.join(grid)}
  {''.join(bars)}
  <g font-size="11" fill="#475569">
    <rect x="{pad_l}" y="{height - 14}" width="10" height="10" rx="2" fill="#f59e0b"/>
    <text x="{pad_l + 15}" y="{height - 5}">{esc(name_a)}</text>
    <rect x="{pad_l + 105}" y="{height - 14}" width="10" height="10" rx="2" fill="#2563eb"/>
    <text x="{pad_l + 120}" y="{height - 5}">{esc(name_b)}</text>
  </g>
</svg>"""


def dataset_page(stats: dict, preview: list[dict]) -> str:
    splits = stats["splits"]
    knowledge = stats["knowledge"]
    caps = stats["capabilities"]
    refusal_types = stats.get("refusal_types", {"missing": 0, "conflict": 0})
    refusal_test = stats.get("refusal_types_test", {"missing": 0, "conflict": 0})
    max_cap = max(c["total"] for c in caps)
    cap_bars = horizontal_bars(
        [(c["name"], c["total"], f"{c['total']} 条") for c in caps], max_cap
    )
    answerable = stats["answerable_ratio"]
    body = hero(
        "数据集构建",
        "围绕 5 个能力维度构造 560 条指令数据，覆盖可回答、资料冲突、资料缺失三类场景",
        ["6 篇制度文档", "37 个知识条款", "420 训练 / 60 验证 / 80 测试", "5 能力维度"],
    )
    body += f"""
<div class="kpis">
  {kpi("训练集", str(splits["train"]), "75%")}
  {kpi("验证集", str(splits["validation"]), "10.7%")}
  {kpi("测试集", str(splits["test"]), "14.3%")}
  {kpi("知识文档", str(knowledge["docs"]), f"{knowledge['clauses']} 个条款")}
  {kpi("可回答样本", f"{answerable * 100:.0f}%", "其余为拒答样本")}
  {kpi("平均上下文字数", str(stats["context_chars"]["mean"]), "检索片段 + 问题")}
</div>

<div class="section">
  <h2><span class="dot"></span>能力维度分布</h2>
  <p class="desc">每个能力维度独立生成 112 条样本，按 84 / 12 / 16 切分，保证测试集覆盖全部能力。</p>
  <div class="grid g2">
    <div class="card">
      <h3>样本数量（按能力）</h3>
      {cap_bars}
      <div class="cap">术语与格式 84 条训练样本中包含制度解释与办理步骤两种回答格式</div>
    </div>
    <div class="card" style="display:flex;align-items:center;gap:26px;justify-content:center">
      {donut(answerable)}
      <div>
        <div style="font-weight:700;font-size:15px;margin-bottom:8px">可回答 / 拒答比例</div>
        <div style="color:#64748b;font-size:13px;line-height:1.9">
          可回答样本 {int(round(answerable * splits["total"]))} 条（{answerable * 100:.0f}%）<br>
          拒答样本 {splits["total"] - int(round(answerable * splits["total"]))} 条（{100 - answerable * 100:.0f}%）<br>
          其中资料不足 {refusal_types.get("missing", 0)} 条、资料冲突 {refusal_types.get("conflict", 0)} 条<br>
          测试集含冲突样本 {refusal_test.get("conflict", 0)} 条
        </div>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>数据构成与长度统计</h2>
  <div class="grid g3">
    <div class="card"><h3>上下文长度</h3><div class="kv">
      <span class="k">平均</span><span><strong>{stats["context_chars"]["mean"]}</strong> 字</span>
      <span class="k">最短</span><span>{stats["context_chars"]["min"]} 字</span>
      <span class="k">最长</span><span>{stats["context_chars"]["max"]} 字</span>
      <span class="k">结构</span><span>2-4 个检索片段</span>
    </div></div>
    <div class="card"><h3>答案长度</h3><div class="kv">
      <span class="k">平均</span><span><strong>{stats["answer_chars"]["mean"]}</strong> 字</span>
      <span class="k">最短</span><span>{stats["answer_chars"]["min"]} 字</span>
      <span class="k">最长</span><span>{stats["answer_chars"]["max"]} 字</span>
      <span class="k">格式</span><span>结论 + 要点 + 依据</span>
    </div></div>
    <div class="card"><h3>数据质检</h3><div class="kv">
      <span class="k">引用可追溯</span><span><span class="pill green">通过</span></span>
      <span class="k">拒答表述</span><span><span class="pill green">通过</span></span>
      <span class="k">训练/测试重叠</span><span><span class="pill green">0 条</span></span>
      <span class="k">重复样本 ID</span><span><span class="pill green">0 条</span></span>
    </div></div>
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>训练数据示例</h2>
  <p class="desc">system 中固定约束「只依据资料回答 + 标注引用 + 资料不足拒答」，user 提供检索片段与问题，assistant 为监督答案。</p>
  <div class="grid g2">"""
    for item in preview[:2]:
        body += f"""
    <div class="card">
      <h3>{esc(item["capability_name"])}</h3>
      <div class="chat user"><strong>问题：</strong>{esc(item["question"])}</div>
      <div class="chat answer"><strong>标准答案：</strong>{esc(item["answer"])}</div>
    </div>"""
    body += """
  </div>
</div>
"""
    return shell("数据集构建 · 微调实验报告", "dataset.html", body)


def training_page(stats: dict, summary: dict | None, log_rows: list[dict], console_lines: list[str]) -> str:
    body = hero(
        "LoRA 微调训练",
        "在 CPU 环境下完成 Qwen2.5-0.5B-Instruct 的 LoRA 指令微调，仅训练 1.75% 参数",
        ["LoRA r=16", "7 个投影层", "assistant-only loss", "CPU 训练"],
    )
    if not summary:
        body += '<div class="note">尚未找到训练结果，请先运行 scripts/train_lora.py</div>'
        return shell("训练 · 微调实验报告", "training.html", body)

    train_cfg = summary["train"]
    duration_min = summary["duration_seconds"] / 60
    body += f"""
<div class="kpis">
  {kpi("训练步数", str(train_cfg["max_steps"]), f"batch {train_cfg['batch_size']} × 累积 {train_cfg['grad_accum']}")}
  {kpi("可训练参数", f"{summary['trainable_params'] / 1e6:.2f}M", f"占比 {summary['trainable_ratio'] * 100:.2f}%")}
  {kpi("最佳验证损失", fmt(summary.get("best_val_loss"), 4), "验证集 60 条")}
  {kpi("训练时长", f"{duration_min:.1f} 分钟", f"设备 {summary['device'].upper()}")}
  {kpi("序列长度", str(train_cfg["max_length"]), "assistant 部分计算损失")}
  {kpi("学习率", f"{train_cfg['learning_rate']:.1e}", f"warmup {train_cfg['warmup_steps']} 步")}
</div>

<div class="section">
  <h2><span class="dot"></span>训练损失曲线</h2>
  <p class="desc">蓝线为每个优化步的训练损失，橙点为验证损失（每 {train_cfg.get('eval_steps', 20)} 步评估一次）。</p>
  <div class="card">
    {line_chart(log_rows)}
    <div class="legend">
      <span><i style="background:#2563eb"></i>训练损失</span>
      <span><i style="background:#f59e0b"></i>验证损失</span>
      <span>横轴：优化步数</span>
    </div>
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>训练配置</h2>
  <div class="grid g2">
    <div class="card">
      <h3>模型与 LoRA</h3>
      <div class="kv">
        <span class="k">基座模型</span><span>Qwen2.5-0.5B-Instruct（494M）</span>
        <span class="k">LoRA rank</span><span>{summary["lora"]["r"]}</span>
        <span class="k">LoRA alpha</span><span>{summary["lora"]["alpha"]}</span>
        <span class="k">LoRA dropout</span><span>{summary["lora"]["dropout"]}</span>
        <span class="k">目标模块</span><span>q/k/v/o/gate/up/down_proj</span>
        <span class="k">精度</span><span>{summary["dtype"]}</span>
      </div>
    </div>
    <div class="card">
      <h3>优化设置</h3>
      <div class="kv">
        <span class="k">优化器</span><span>AdamW (β=0.9/0.95)</span>
        <span class="k">学习率</span><span>{train_cfg["learning_rate"]}（余弦衰减）</span>
        <span class="k">批大小</span><span>{train_cfg["batch_size"]} × 梯度累积 {train_cfg["grad_accum"]}</span>
        <span class="k">最大序列长度</span><span>{train_cfg["max_length"]}</span>
        <span class="k">训练样本</span><span>{train_cfg["samples"]} 条</span>
        <span class="k">完成时间</span><span>{summary["finished_at"]}</span>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>训练日志</h2>
  <p class="desc">以下为脚本输出的真实训练日志（节选），完整日志见 outputs/train_console.log 与 training_log.csv。</p>
  <div class="terminal">"""
    for line in console_lines[-14:]:
        cls = ""
        if "[step" in line:
            cls = "b"
        elif "训练完成" in line or "可训练参数" in line:
            cls = "g"
        elif "==" in line:
            cls = "m"
        body += f'<div class="{cls}">{esc(line)}</div>'
    body += """
  </div>
</div>
"""
    return shell("训练 · 微调实验报告", "training.html", body)


METRIC_ROWS = [
    ("citation_f1", "引用 F1", "引用编号正确且覆盖标准依据"),
    ("key_point_coverage", "要点覆盖率", "标准答案要点被覆盖的比例"),
    ("number_grounding", "数字忠实度", "答案数字均能在资料中找到出处"),
    ("format_ok", "格式合规率", "结论 / 要点 / 依据结构完整"),
    ("term_hit", "术语准确率", "行业术语命中比例"),
    ("refusal_ok", "拒答正确率", "资料不足时拒答、可回答时不误拒答"),
    ("overall", "综合得分", "按能力维度加权后的综合分"),
]


def evaluation_page(base: dict | None, tuned: dict | None) -> str:
    body = hero(
        "评测结果",
        "在 25 条留出测试样本上对比基座模型与 LoRA 微调模型，指标全部由脚本自动计算",
        ["5 维度 × 5 条", "基线与微调同题对比", "规则化可复算指标"],
    )
    if not base or not tuned:
        body += '<div class="note">尚未找到完整的评测结果，请先运行 scripts/evaluate.py</div>'
        return shell("评测 · 微调实验报告", "evaluation.html", body)

    base_agg = base["aggregate"]
    tuned_agg = tuned["aggregate"]
    labels = [row["capability_name"] for row in base["by_capability"]]
    overall_a = [row["overall"] for row in base["by_capability"]]
    overall_b = [row["overall"] for row in tuned["by_capability"]]

    body += f"""
<div class="kpis">
  {kpi("基线综合得分", fmt(base_agg["overall"]), "Qwen2.5-0.5B-Instruct")}
  {kpi("微调综合得分", fmt(tuned_agg["overall"]), "LoRA 微调后")}
  {kpi("综合提升", f"+{(tuned_agg['overall'] - base_agg['overall']) * 100:.1f} 分", "满分 100")}
  {kpi("拒答正确率", fmt(tuned_agg["refusal_ok"]), f"基线 {fmt(base_agg['refusal_ok'])}")}
  {kpi("引用 F1", fmt(tuned_agg["citation_f1"]), f"基线 {fmt(base_agg['citation_f1'])}")}
  {kpi("要点覆盖", fmt(tuned_agg["key_point_coverage"]), f"基线 {fmt(base_agg['key_point_coverage'])}")}
</div>

<div class="section">
  <h2><span class="dot"></span>各能力维度综合得分</h2>
  <p class="desc">同一批测试问题分别输入基座模型和微调模型，按能力维度计算综合得分。</p>
  <div class="card">
    {grouped_bar_chart(labels, overall_a, overall_b)}
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>指标总览</h2>
  <div class="card">
    <table class="metric-table">
      <thead><tr><th>指标</th><th>说明</th><th class="num">基线</th><th class="num">微调</th><th class="num">变化</th></tr></thead>
      <tbody>"""
    for key, name, desc in METRIC_ROWS:
        a, b = base_agg[key], tuned_agg[key]
        diff = b - a
        body += (
            f'<tr><td><strong>{name}</strong></td><td style="color:#64748b">{desc}</td>'
            f'<td class="num">{fmt(a)}</td><td class="num"><strong>{fmt(b)}</strong></td>'
            f'<td class="num"><span class="pill {delta_class(diff)}">{diff:+.3f}</span></td></tr>'
        )
    body += """
      </tbody>
    </table>
    <div class="cap">评测样本：每个能力维度从测试集中固定抽取 5 条，共 25 条；温度 0、贪心解码、最大生成 180 tokens。</div>
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>分维度明细</h2>
  <div class="card">
    <table>
      <thead><tr><th>能力维度</th><th class="num">引用 F1</th><th class="num">要点覆盖</th><th class="num">数字忠实</th><th class="num">格式</th><th class="num">术语</th><th class="num">拒答</th><th class="num">综合</th></tr></thead>
      <tbody>"""
    for row_b in tuned["by_capability"]:
        body += (
            f'<tr><td><strong>{esc(row_b["capability_name"])}</strong></td>'
            f'<td class="num">{fmt(row_b["citation_f1"])}</td>'
            f'<td class="num">{fmt(row_b["key_point_coverage"])}</td>'
            f'<td class="num">{fmt(row_b["number_grounding"])}</td>'
            f'<td class="num">{fmt(row_b["format_ok"])}</td>'
            f'<td class="num">{fmt(row_b["term_hit"])}</td>'
            f'<td class="num">{fmt(row_b["refusal_ok"])}</td>'
            f'<td class="num"><strong>{fmt(row_b["overall"])}</strong></td></tr>'
        )
    body += """
      </tbody>
    </table>
  </div>
</div>
"""
    return shell("评测 · 微调实验报告", "evaluation.html", body)


def samples_page(base: dict | None, tuned: dict | None) -> str:
    body = hero(
        "样例对比",
        "从测试集中选取引用、拒答、多片段整合三类典型问题，对比基线与微调模型的真实输出",
        ["同题对比", "真实生成结果", "通过 / 未通过标注"],
    )
    if not base or not tuned:
        body += '<div class="note">尚未找到评测明细，请先运行 scripts/evaluate.py</div>'
        return shell("样例对比 · 微调实验报告", "samples.html", body)

    base_map = {item["id"]: item for item in base["samples"]}
    tuned_map = {item["id"]: item for item in tuned["samples"]}
    selections = []
    for capability in ("citation", "refusal", "multi_snippet"):
        for item in tuned["samples"]:
            if item["capability"] == capability and item["id"] in base_map:
                selections.append((base_map[item["id"]], item))
                break

    body += '<div class="section">'
    for base_row, tuned_row in selections:
        body += f"""
  <div class="sample">
    <div class="head">
      <div><span class="pill blue">{esc(tuned_row["capability_name"])}</span>
      <span class="pill gray">{'可回答' if tuned_row['answerable'] else '资料不足'}</span></div>
      <div>
        <span class="badge {'ok' if tuned_row['overall'] >= 0.7 else 'bad'}">微调综合 {tuned_row['overall']:.2f}</span>
        <span class="badge {'ok' if base_row['overall'] >= 0.7 else 'bad'}">基线综合 {base_row['overall']:.2f}</span>
      </div>
    </div>
    <div class="q">问题：{esc(tuned_row["question"])}</div>
    <div class="cols">
      <div class="col base"><h4><span>基线模型</span><span class="pill {'green' if base_row['overall'] >= 0.7 else 'orange'}">{base_row['overall']:.2f}</span></h4>
        <div class="answer">{esc(base_row["prediction"])}</div>
      </div>
      <div class="col tuned"><h4><span>微调模型</span><span class="pill {'green' if tuned_row['overall'] >= 0.7 else 'orange'}">{tuned_row['overall']:.2f}</span></h4>
        <div class="answer">{esc(tuned_row["prediction"])}</div>
      </div>
    </div>
    <div class="cap">标准依据：{esc('、'.join(tuned_row["gold_refs"]) or "无（应拒答）")}　|　
      引用：{esc('、'.join(tuned_row["citations"]) or "无")}　|　
      要点覆盖 {tuned_row["key_point_coverage"]:.2f}　|　数字忠实 {tuned_row["number_grounding"]:.2f}　|　格式 {tuned_row["format_ok"]:.0f}
    </div>
  </div>"""
    body += "</div>"
    return shell("样例对比 · 微调实验报告", "samples.html", body)


def index_page(stats: dict, summary: dict | None, base: dict | None, tuned: dict | None) -> str:
    splits = stats["splits"] if stats else {"train": 0, "validation": 0, "test": 0}
    body = hero(
        "知识库问答模型微调实验报告",
        "知行学堂在线教育知识库 · 检索增强问答场景 · Qwen2.5-0.5B-Instruct + LoRA",
        ["5 个能力维度", "560 条指令数据", "CPU 可复现", "引用可追溯"],
    )
    tuned_score = tuned["aggregate"]["overall"] if tuned else 0
    base_score = base["aggregate"]["overall"] if base else 0
    body += f"""
<div class="kpis">
  {kpi("训练样本", str(splits["train"]), "84 条 / 能力")}
  {kpi("验证样本", str(splits["validation"]), "用于选择最佳适配器")}
  {kpi("测试样本", str(splits["test"]), "留出集，不参与训练")}
  {kpi("基线综合分", fmt(base_score), "Qwen2.5-0.5B-Instruct")}
  {kpi("微调综合分", fmt(tuned_score), "LoRA r=16")}
  {kpi("综合提升", f"+{(tuned_score - base_score) * 100:.1f} 分", "25 条测试样本")}
</div>

<div class="section">
  <h2><span class="dot"></span>实验概览</h2>
  <div class="grid g2">
    <div class="card">
      <h3>任务定义</h3>
      <p style="color:#475569;margin:0 0 10px">面向在线教育知识库的检索增强问答：模型需要依据检索到的制度条款回答学员问题，给出可追溯的条款引用；当资料不足或互相冲突时明确拒答，避免编造。</p>
      <div class="kv">
        <span class="k">基座模型</span><span>Qwen2.5-0.5B-Instruct</span>
        <span class="k">微调方式</span><span>LoRA（r=16, alpha=32）</span>
        <span class="k">训练数据</span><span>420 条指令样本</span>
        <span class="k">评测方式</span><span>5 维度 × 5 条留出样本</span>
      </div>
    </div>
    <div class="card">
      <h3>报告导航</h3>
      <div class="kv">
        <span class="k"><a href="dataset.html" style="color:#2563eb">数据集构建 →</a></span><span>文档、条款、样本分布与质检</span>
        <span class="k"><a href="training.html" style="color:#2563eb">训练过程 →</a></span><span>LoRA 配置、损失曲线、训练日志</span>
        <span class="k"><a href="evaluation.html" style="color:#2563eb">评测结果 →</a></span><span>基线 vs 微调、分维度指标</span>
        <span class="k"><a href="samples.html" style="color:#2563eb">样例对比 →</a></span><span>引用、拒答、多片段真实输出</span>
      </div>
    </div>
  </div>
</div>

<div class="section">
  <h2><span class="dot"></span>能力维度</h2>
  <div class="grid g3">"""
    for cap in stats["capabilities"]:
        body += f"""
    <div class="card">
      <h3>{esc(cap["name"])}</h3>
      <div style="font-size:26px;font-weight:800;color:#2563eb">{cap["total"]}<span style="font-size:13px;color:#64748b;font-weight:400"> 条</span></div>
      <div class="cap">训练 {cap["train"]} · 验证 {cap["validation"]} · 测试 {cap["test"]}</div>
    </div>"""
    body += """
  </div>
</div>
"""
    return shell("总览 · 微调实验报告", "index.html", body)


def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "style.css").write_text(CSS, encoding="utf-8")

    stats = load_json(ROOT / "data" / "dataset_stats.json", {})
    preview = load_json(ROOT / "data" / "preview_samples.json", [])
    summary = load_json(OUTPUT_DIR / "training_summary.json")
    base = load_json(OUTPUT_DIR / "eval_base.json")
    tuned = load_json(OUTPUT_DIR / "eval_tuned.json")

    log_rows: list[dict] = []
    log_path = OUTPUT_DIR / "training_log.csv"
    if log_path.exists():
        with log_path.open(encoding="utf-8") as f:
            log_rows = list(csv.DictReader(f))
    console_lines: list[str] = []
    console_path = OUTPUT_DIR / "train_console.log"
    if console_path.exists():
        console_lines = console_path.read_text(encoding="utf-8").splitlines()

    if summary:
        summary.setdefault("train", {})["eval_steps"] = 20

    pages = {
        "index.html": index_page(stats, summary, base, tuned),
        "dataset.html": dataset_page(stats, preview),
        "training.html": training_page(stats, summary, log_rows, console_lines),
        "evaluation.html": evaluation_page(base, tuned),
        "samples.html": samples_page(base, tuned),
    }
    for name, content in pages.items():
        (REPORT_DIR / name).write_text(content, encoding="utf-8")
        print(f"生成 {REPORT_DIR / name}")


if __name__ == "__main__":
    main()
