# -*- coding: utf-8 -*-
"""生成知识库问答微调数据集（train / validation / test）。

数据覆盖 5 个能力维度：
1. term_format  行业术语与回答格式适配
2. faithful     检索内容忠实回答（含干扰片段）
3. multi_snippet 多片段信息整合
4. citation     证据引用与出处标注
5. refusal      资料不足 / 资料冲突时的拒答

运行：
    python scripts/generate_dataset.py
输出：
    data/train.jsonl  data/validation.jsonl  data/test.jsonl
    data/knowledge_base.json  data/knowledge/*.md  data/dataset_stats.json
"""

from __future__ import annotations

import json
import random
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from kb_data import CLAUSES, CLAUSE_MAP, DOCS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
KNOWLEDGE_DIR = DATA_DIR / "knowledge"

SYSTEM_PROMPT = (
    "你是「知行学堂」在线教育平台的知识库问答助手。"
    "你只能依据用户提供的【资料】回答问题，并在答案中标注依据条款编号（格式如 [KB-EDU-002-2.3]）；"
    "当资料不足、资料无关或资料互相冲突时，必须明确说明无法回答并指出缺失信息，不得编造资料中没有的事实、数字和政策。"
)

CAPABILITIES = ["term_format", "faithful", "multi_snippet", "citation", "refusal"]
CAP_NAMES = {
    "term_format": "行业术语与格式适配",
    "faithful": "检索内容忠实回答",
    "multi_snippet": "多片段信息整合",
    "citation": "证据引用与出处标注",
    "refusal": "资料不足拒答",
}

# 多片段整合使用的业务相关条款对
RELATED_PAIRS = [
    ("KB-EDU-001-1.3", "KB-EDU-002-2.1"),
    ("KB-EDU-002-2.2", "KB-EDU-002-2.3"),
    ("KB-EDU-002-2.4", "KB-EDU-002-2.5"),
    ("KB-EDU-003-3.2", "KB-EDU-004-4.2"),
    ("KB-EDU-003-3.3", "KB-EDU-005-5.1"),
    ("KB-EDU-004-4.3", "KB-EDU-005-5.1"),
    ("KB-EDU-005-5.2", "KB-EDU-006-6.2"),
    ("KB-EDU-001-1.2", "KB-EDU-004-4.2"),
    ("KB-EDU-002-2.6", "KB-EDU-002-2.5"),
    ("KB-EDU-003-3.4", "KB-EDU-003-3.5"),
    ("KB-EDU-005-5.5", "KB-EDU-005-5.3"),
    ("KB-EDU-006-6.5", "KB-EDU-002-2.4"),
    ("KB-EDU-001-1.5", "KB-EDU-002-2.1"),
    ("KB-EDU-004-4.6", "KB-EDU-003-3.2"),
    ("KB-EDU-006-6.6", "KB-EDU-006-6.1"),
    ("KB-EDU-001-1.4", "KB-EDU-001-1.6"),
    ("KB-EDU-002-2.7", "KB-EDU-005-5.5"),
    ("KB-EDU-003-3.6", "KB-EDU-002-2.7"),
    ("KB-EDU-003-3.1", "KB-EDU-003-3.5"),
    ("KB-EDU-004-4.1", "KB-EDU-004-4.4"),
    ("KB-EDU-004-4.5", "KB-EDU-006-6.4"),
    ("KB-EDU-005-5.4", "KB-EDU-005-5.2"),
    ("KB-EDU-006-6.3", "KB-EDU-002-2.4"),
    ("KB-EDU-001-1.6", "KB-EDU-004-4.3"),
]

# 资料不足的拒答问题种子（问题不在知识库覆盖范围内）
REFUSAL_SEEDS = [
    {"q": "学费可以分期免息吗？", "missing": "分期免息政策、合作机构与利率说明", "next": "咨询课程顾问确认当期分期活动"},
    {"q": "课程可以转让给其他人学习吗？", "missing": "课程转让与账号共享规则", "next": "联系班主任说明受让方信息"},
    {"q": "退款可以退到支付宝余额吗？", "missing": "退款账户类型与变更规则", "next": "以支付页展示的原路退回规则为准"},
    {"q": "报名后可以更换主讲老师吗？", "missing": "更换主讲老师的申请条件与流程", "next": "向班主任提交更换讲师诉求"},
    {"q": "课程视频可以下载到本地吗？", "missing": "视频下载权限与离线缓存说明", "next": "使用客户端离线缓存功能并查看权限说明"},
    {"q": "平台提供就业推荐服务吗？", "missing": "就业推荐服务协议与合作企业名单", "next": "咨询就业服务专员了解当期服务"},
    {"q": "海外学员可以报名吗？", "missing": "海外报名资格、支付方式与开票规则", "next": "联系国际业务客服确认所在地区支持情况"},
    {"q": "结业后可以开具实习证明吗？", "missing": "实习证明开具条件与办理流程", "next": "向班主任提交实习证明申请"},
    {"q": "课程支持投屏到电视上观看吗？", "missing": "投屏兼容范围与设备要求", "next": "查看客户端帮助中心的投屏说明"},
    {"q": "老学员复购课程有优惠吗？", "missing": "复购优惠政策与优惠券适用范围", "next": "关注个人中心优惠券中心的活动通知"},
    {"q": "学习数据可以导出成 Excel 吗？", "missing": "学习数据导出范围与导出格式", "next": "向班主任提交数据导出需求"},
    {"q": "班级可以更换固定的上课时间吗？", "missing": "学员申请调整班级上课时间的规则", "next": "与班主任沟通是否可调整到其他班次"},
    {"q": "平台支持微信支付吗？", "missing": "支持的支付渠道清单", "next": "在支付页面查看可选支付方式"},
    {"q": "报名课程需要什么学历？", "missing": "课程报名资格与学历要求", "next": "查看课程详情页的报名条件"},
    {"q": "证书可以邮寄到国外吗？", "missing": "国际邮寄范围、费用与时效", "next": "联系客服确认国际邮寄可行性"},
    {"q": "平台有线下校区吗？", "missing": "线下校区地址与开放时间", "next": "咨询课程顾问了解线下教学点"},
    {"q": "课程有配套的实体教材吗？", "missing": "教材清单、版本与配送范围", "next": "在课程资料页查看教材说明"},
    {"q": "可以申请助学贷款吗？", "missing": "助学贷款合作机构与申请条件", "next": "咨询课程顾问了解教育分期方案"},
    {"q": "上课迟到了可以补签到吗？", "missing": "迟到补签与出勤修正规则", "next": "联系班主任说明迟到原因"},
    {"q": "课程可以暂停一段时间再学吗？", "missing": "课程冻结与延期学习规则", "next": "向班主任提交课程延期申请"},
    {"q": "平台会提供学习平板吗？", "missing": "学习设备赠送或租赁政策", "next": "查看课程权益说明中的设备清单"},
    {"q": "可以只购买课程中的某几节课吗？", "missing": "课程拆分购买与单节售卖规则", "next": "咨询课程顾问是否支持按模块购买"},
    {"q": "退费后优惠券会退回吗？", "missing": "优惠券退回与有效期恢复规则", "next": "联系客服查询该订单优惠券状态"},
    {"q": "直播间可以发送文件吗？", "missing": "直播间文件传输与权限说明", "next": "通过班级群向班主任索取资料"},
    {"q": "学员可以申请成为助教吗？", "missing": "助教招募条件与申请流程", "next": "关注平台助教招募公告"},
    {"q": "课程支持试听后再付款吗？", "missing": "先试听后付款的信用支付规则", "next": "咨询课程顾问了解试听与付款顺序"},
    {"q": "更换手机号后学习记录还在吗？", "missing": "账号换绑与学习记录迁移规则", "next": "在账号安全页提交手机号换绑申请"},
    {"q": "平台提供住宿安排吗？", "missing": "线下集训住宿标准与费用", "next": "咨询集训营班主任了解住宿安排"},
    {"q": "课程可以开具学时证明吗？", "missing": "学时证明开具条件与格式", "next": "向班主任提交学时证明申请"},
    {"q": "考试没通过可以退部分学费吗？", "missing": "考试未通过的部分退费规则", "next": "查看课程协议中的重学与退费条款"},
]

CONFLICT_CASES = [
    {
        "cid": "KB-EDU-002-2.3",
        "fake_cid": "KB-EDU-099-9.1",
        "fake_text": "退费到账时间：退费申请审核通过后，款项将在 7 个工作日内按原支付渠道退回。",
        "fake_heading": "退费到账时间（历史版本）",
        "point": "退费到账时间存在 7 个工作日与 15 个工作日两种说法",
        "question": "退费审核通过后多久能到账？",
    },
    {
        "cid": "KB-EDU-002-2.5",
        "fake_cid": "KB-EDU-099-9.2",
        "fake_text": "退费手续费：开课后退费不收取任何手续费，全额退还剩余金额。",
        "fake_heading": "退费手续费（历史版本）",
        "point": "退费手续费存在「收取 5%」与「不收取」两种说法",
        "question": "开课后退费要收手续费吗？",
    },
    {
        "cid": "KB-EDU-005-5.3",
        "fake_cid": "KB-EDU-099-9.3",
        "fake_text": "证书发放时间：电子证书在结业审核通过后 30 个工作日内发放。",
        "fake_heading": "证书发放时间（历史版本）",
        "point": "电子证书发放时间存在 3 个工作日与 30 个工作日两种说法",
        "question": "电子证书一般多久能发下来？",
    },
    {
        "cid": "KB-EDU-001-1.2",
        "fake_cid": "KB-EDU-099-9.4",
        "fake_text": "课程有效期：录播课自开通之日起 180 天内有效。",
        "fake_heading": "课程有效期（历史版本）",
        "point": "录播课有效期存在 365 天与 180 天两种说法",
        "question": "录播课的有效期是一年吗？",
    },
    {
        "cid": "KB-EDU-005-5.1",
        "fake_cid": "KB-EDU-099-9.5",
        "fake_text": "结业条件：完成课程进度的 60% 即可结业，无需参加结业考试。",
        "fake_heading": "结业条件（历史版本）",
        "point": "结业条件存在「进度 80% 且考试 60 分」与「进度 60% 且免考」两种说法",
        "question": "结业需要满足哪些条件？",
    },
    {
        "cid": "KB-EDU-006-6.2",
        "fake_cid": "KB-EDU-099-9.6",
        "fake_text": "开票时间：付款成功后 30 个工作日内开具发票。",
        "fake_heading": "开票时间（历史版本）",
        "point": "开票时间存在 7 个工作日与 30 个工作日两种说法",
        "question": "付款后多久可以开发票？",
    },
    {
        "cid": "KB-EDU-002-2.1",
        "fake_cid": "KB-EDU-099-9.7",
        "fake_text": "退费申请时限：开课后 15 个自然日内均可提交退费申请，按未消耗课时折算退费。",
        "fake_heading": "退费申请时限（历史版本）",
        "point": "开课后退费时限存在 7 个自然日与 15 个自然日两种说法",
        "question": "开课后还能申请退费吗？",
    },
    {
        "cid": "KB-EDU-003-3.2",
        "fake_cid": "KB-EDU-099-9.8",
        "fake_text": "请假与补课：直播课请假需提前 48 小时向班主任报备，补课在 7 个自然日内安排。",
        "fake_heading": "请假与补课（历史版本）",
        "point": "请假提前时间存在 24 小时与 48 小时两种说法",
        "question": "直播课请假需要提前多久报备？",
    },
    {
        "cid": "KB-EDU-004-4.2",
        "fake_cid": "KB-EDU-099-9.9",
        "fake_text": "回放上线与有效期：直播课回放保留 30 天，支持 1.25 倍和 1.5 倍速播放。",
        "fake_heading": "回放有效期（历史版本）",
        "point": "直播回放保留期存在 90 天与 30 天两种说法",
        "question": "直播回放能保留多久？",
    },
    {
        "cid": "KB-EDU-005-5.1",
        "fake_cid": "KB-EDU-099-9.10",
        "fake_text": "结业条件：作业平均分不低于 70 分、结业考试成绩不低于 60 分即可结业。",
        "fake_heading": "结业作业分数线（历史版本）",
        "point": "作业平均分要求存在 60 分与 70 分两种说法",
        "question": "作业平均分最低要多少才能结业？",
    },
    {
        "cid": "KB-EDU-002-2.4",
        "fake_cid": "KB-EDU-099-9.11",
        "fake_text": "不可退费情形：开课后 7 个自然日内可申请全额退费，已消耗课时不扣除费用。",
        "fake_heading": "退费限制（历史版本）",
        "point": "开课后退费规则存在「按未消耗课时折算」与「可全额退费」两种说法",
        "question": "开课后还能全额退费吗？",
    },
    {
        "cid": "KB-EDU-006-6.6",
        "fake_cid": "KB-EDU-099-9.12",
        "fake_text": "企业采购与团报：企业一次性采购 5 人及以上课程可享受课程原价 8 折优惠。",
        "fake_heading": "企业团报折扣（历史版本）",
        "point": "企业团报折扣存在 9 折与 8 折两种说法",
        "question": "企业团报可以打几折？",
    },
]

TERM_TEMPLATES = [
    "「{heading}」是怎么规定的？",
    "请说明平台关于「{heading}」的具体要求。",
    "我想了解「{heading}」，需要满足哪些条件？",
    "关于「{heading}」，制度里是怎么写的？",
    "请解释「{heading}」的规则。",
]
STEP_TEMPLATES = [
    "如何办理「{heading}」？请按步骤说明。",
    "「{heading}」的操作流程是什么？",
    "请说明「{heading}」的办理步骤和注意事项。",
]
CITATION_TEMPLATES = [
    "请依据资料回答「{heading}」的规定，并标注依据条款编号。",
    "引用知识库条款说明「{heading}」，并给出出处。",
    "请回答「{heading}」相关问题，答案中必须标注引用来源。",
    "请说明「{heading}」的制度要求，并为结论附上依据。",
]
FAITHFUL_TEMPLATES = [
    "「{heading}」中涉及的时间限制和金额标准分别是什么？",
    "「{heading}」具体有哪些数量或期限要求？",
    "请准确说明「{heading}」中的数字和时限。",
    "「{heading}」提到的期限、费用分别是多少？",
]
MULTI_TEMPLATES = [
    "同时涉及「{h1}」和「{h2}」时应该怎么处理？",
    "如果既遇到「{h1}」又涉及「{h2}」，平台规则是什么？",
    "请综合说明「{h1}」与「{h2}」的规定。",
    "我需要先处理「{h1}」再处理「{h2}」吗？请说明相关规则。",
    "关于「{h1}」和「{h2}」，我该如何安排办理顺序？",
]
REFUSAL_TEMPLATES = [
    "{q}",
    "请问{q}",
    "我想确认一下：{q}",
    "{q}麻烦说明一下。",
]


def snippet(clause: dict) -> str:
    return f"[{clause['cid']}] {clause['heading']}：{clause['text']}"


def render_context(clauses: list[dict]) -> str:
    lines = ["【资料】"]
    for idx, clause in enumerate(clauses, start=1):
        lines.append(f"【资料{idx}】{snippet(clause)}")
    return "\n".join(lines)


def explain_answer(clause: dict) -> str:
    points = "\n".join(f"{i}. {p}" for i, p in enumerate(clause["points"], start=1))
    return (
        f"结论：{clause['summary']}。\n"
        f"关键要点：\n{points}\n"
        f"依据：[{clause['cid']}]\n"
        f"办理建议：{clause['advice']}。"
    )


def steps_answer(clause: dict) -> str:
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(clause["process"], start=1))
    return (
        f"办理步骤：\n{steps}\n"
        f"依据：[{clause['cid']}]\n"
        f"注意事项：{clause['advice']}。"
    )


def citation_answer(clause: dict) -> str:
    points = "\n".join(f"{i}. {p}" for i, p in enumerate(clause["points"], start=1))
    excerpt = clause["text"][:46].rstrip("。") + "……"
    return (
        f"根据资料，{clause['summary']}。\n"
        f"关键要点：\n{points}\n"
        f"原文摘录：“{excerpt}”\n"
        f"依据：[{clause['cid']}]"
    )


def multi_answer(c1: dict, c2: dict) -> str:
    return (
        f"综合说明：\n"
        f"1. {c1['summary']}（依据：[{c1['cid']}]）\n"
        f"2. {c2['summary']}（依据：[{c2['cid']}]）\n"
        f"处理建议：两项规定需同时满足，请先按「{c1['heading']}」核对适用条件，"
        f"再按「{c2['heading']}」确认后续办理要求；任一条件不具备时应先补齐材料或联系班主任确认。"
    )


def refusal_answer(seed: dict) -> str:
    return (
        f"无法依据现有资料确认该问题。\n"
        f"缺少信息：{seed['missing']}。\n"
        f"建议：{seed['next']}；也可以联系人工客服 400-800-1234 进一步核实。"
    )


def conflict_answer(case: dict, clause: dict) -> str:
    return (
        f"资料之间存在冲突，无法给出确定结论。\n"
        f"冲突点：{case['point']}。\n"
        f"建议：以平台最新发布的《{clause['doc_title']}》为准，并向班主任或财务确认后再办理。"
    )


def pick_distractors(gold: list[dict], rng: random.Random, count: int, avoid_numbers: set[str] | None = None) -> list[dict]:
    gold_ids = {c["cid"] for c in gold}
    pool = [c for c in CLAUSES if c["cid"] not in gold_ids]
    rng.shuffle(pool)
    chosen: list[dict] = []
    for clause in pool:
        if avoid_numbers:
            numbers = set(extract_numbers(clause["text"]))
            if numbers & avoid_numbers:
                continue
        chosen.append(clause)
        if len(chosen) >= count:
            break
    return chosen


def extract_numbers(text: str) -> list[str]:
    return re.findall(r"\d{1,2}:\d{2}|\d+(?:\.\d+)?%?", text)


def make_sample(
    idx: int,
    capability: str,
    question: str,
    context_clauses: list[dict],
    answer: str,
    gold_refs: list[str],
    answerable: bool,
    extra_meta: dict | None = None,
) -> dict:
    meta = {
        "capability": capability,
        "capability_name": CAP_NAMES[capability],
        "answerable": answerable,
        "gold_refs": gold_refs,
        "context_refs": [c["cid"] for c in context_clauses],
    }
    if extra_meta:
        meta.update(extra_meta)
    return {
        "id": f"edu-{capability}-{idx:04d}",
        "capability": capability,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{render_context(context_clauses)}\n\n【问题】{question}"},
            {"role": "assistant", "content": answer},
        ],
        "meta": meta,
    }


def build_term_format(rng: random.Random, count: int) -> list[dict]:
    samples: list[dict] = []
    used: set[str] = set()
    clauses = [c for c in CLAUSES]
    guard = 0
    while len(samples) < count and guard < count * 40:
        guard += 1
        clause = rng.choice(clauses)
        if clause.get("process") and rng.random() < 0.45:
            question = rng.choice(STEP_TEMPLATES).format(heading=clause["heading"])
            answer = steps_answer(clause)
        else:
            question = rng.choice(TERM_TEMPLATES).format(heading=clause["heading"])
            answer = explain_answer(clause)
        key = question + "|" + clause["cid"]
        if key in used:
            continue
        used.add(key)
        distractors = pick_distractors([clause], rng, rng.randint(1, 2))
        context = [clause] + distractors
        rng.shuffle(context)
        samples.append(
            make_sample(
                len(samples),
                "term_format",
                question,
                context,
                answer,
                [clause["cid"]],
                True,
                {
                    "terms": clause["terms"],
                    "key_points": clause["points"],
                    "style": "steps" if answer.startswith("办理步骤") else "explain",
                    "doc_title": clause["doc_title"],
                },
            )
        )
    return samples


def build_faithful(rng: random.Random, count: int) -> list[dict]:
    samples: list[dict] = []
    used: set[str] = set()
    numeric_clauses = [c for c in CLAUSES if extract_numbers(c["text"])]
    guard = 0
    while len(samples) < count and guard < count * 60:
        guard += 1
        clause = rng.choice(numeric_clauses)
        question = rng.choice(FAITHFUL_TEMPLATES).format(heading=clause["heading"])
        key = question + "|" + clause["cid"]
        if key in used:
            continue
        used.add(key)
        answer = explain_answer(clause)
        gold_numbers = set(extract_numbers(clause["text"])) | set(clause.get("numbers", []))
        distractors = pick_distractors([clause], rng, 2, avoid_numbers={n.rstrip("%") for n in gold_numbers})
        if len(distractors) < 2:
            continue
        context = [clause] + distractors
        rng.shuffle(context)
        samples.append(
            make_sample(
                len(samples),
                "faithful",
                question,
                context,
                answer,
                [clause["cid"]],
                True,
                {
                    "terms": clause["terms"],
                    "key_points": clause["points"],
                    "gold_numbers": sorted(gold_numbers),
                    "distractor_numbers": sorted(
                        {n for d in distractors for n in extract_numbers(d["text"])}
                    ),
                    "doc_title": clause["doc_title"],
                },
            )
        )
    return samples


def build_multi_snippet(rng: random.Random, count: int) -> list[dict]:
    samples: list[dict] = []
    used: set[str] = set()
    guard = 0
    pairs = list(RELATED_PAIRS)
    while len(samples) < count and guard < count * 60:
        guard += 1
        cid1, cid2 = rng.choice(pairs)
        c1, c2 = CLAUSE_MAP[cid1], CLAUSE_MAP[cid2]
        question = rng.choice(MULTI_TEMPLATES).format(h1=c1["heading"], h2=c2["heading"])
        key = question + "|" + cid1 + "|" + cid2
        if key in used:
            continue
        used.add(key)
        answer = multi_answer(c1, c2)
        distractors = pick_distractors([c1, c2], rng, 1)
        context = [c1, c2] + distractors
        rng.shuffle(context)
        samples.append(
            make_sample(
                len(samples),
                "multi_snippet",
                question,
                context,
                answer,
                [c1["cid"], c2["cid"]],
                True,
                {
                    "terms": sorted(set(c1["terms"] + c2["terms"])),
                    "key_points": [c1["summary"], c2["summary"]],
                    "doc_title": f"{c1['doc_title']} / {c2['doc_title']}",
                },
            )
        )
    return samples


def build_citation(rng: random.Random, count: int) -> list[dict]:
    samples: list[dict] = []
    used: set[str] = set()
    guard = 0
    while len(samples) < count and guard < count * 40:
        guard += 1
        clause = rng.choice(CLAUSES)
        question = rng.choice(CITATION_TEMPLATES).format(heading=clause["heading"])
        key = question + "|" + clause["cid"]
        if key in used:
            continue
        used.add(key)
        answer = citation_answer(clause)
        distractors = pick_distractors([clause], rng, rng.randint(1, 2))
        context = [clause] + distractors
        rng.shuffle(context)
        samples.append(
            make_sample(
                len(samples),
                "citation",
                question,
                context,
                answer,
                [clause["cid"]],
                True,
                {
                    "terms": clause["terms"],
                    "key_points": clause["points"],
                    "doc_title": clause["doc_title"],
                },
            )
        )
    return samples


def build_refusal(rng: random.Random, count: int) -> list[dict]:
    """构造拒答样本：12 条资料冲突 + 其余为资料不足。

    冲突样本使用每个案例独立的提问方式，保证问题在训练/测试之间不重复；
    资料不足样本从 30 个知识库外问题 × 4 种问法中不重复抽取。
    """
    samples: list[dict] = []

    for case in CONFLICT_CASES:
        clause = CLAUSE_MAP[case["cid"]]
        question = case["question"]
        fake = {
            "cid": case["fake_cid"],
            "heading": case["fake_heading"],
            "text": case["fake_text"],
        }
        contexts = [clause, fake] + pick_distractors([clause], rng, 1)
        rng.shuffle(contexts)
        samples.append(
            make_sample(
                len(samples),
                "refusal",
                question,
                contexts,
                conflict_answer(case, clause),
                [],
                False,
                {
                    "refusal_type": "conflict",
                    "missing": case["point"],
                    "terms": clause["terms"],
                    "key_points": [],
                    "doc_title": clause["doc_title"],
                },
            )
        )

    used_questions = {s["messages"][1]["content"].split("【问题】")[-1].strip() for s in samples}
    guard = 0
    while len(samples) < count and guard < count * 80:
        guard += 1
        seed = rng.choice(REFUSAL_SEEDS)
        question = rng.choice(REFUSAL_TEMPLATES).format(q=seed["q"])
        if question in used_questions:
            continue
        used_questions.add(question)
        distractors = pick_distractors([], rng, rng.randint(2, 3))
        samples.append(
            make_sample(
                len(samples),
                "refusal",
                question,
                distractors,
                refusal_answer(seed),
                [],
                False,
                {
                    "refusal_type": "missing",
                    "missing": seed["missing"],
                    "terms": [],
                    "key_points": [],
                    "doc_title": "",
                },
            )
        )
    if len(samples) < count:
        raise RuntimeError(f"拒答样本不足：{len(samples)} < {count}")
    rng.shuffle(samples)
    return samples


def split_capability(samples: list[dict], rng: random.Random) -> tuple[list, list, list]:
    rng.shuffle(samples)
    n_train = 84
    n_val = 12
    train = samples[:n_train]
    val = samples[n_train : n_train + n_val]
    test = samples[n_train + n_val : n_train + n_val + 16]
    return train, val, test


def split_refusal(samples: list[dict], rng: random.Random) -> tuple[list, list, list]:
    """拒答样本分层切分：保证测试集同时包含资料冲突与资料不足样本。"""
    conflicts = [s for s in samples if s["meta"]["refusal_type"] == "conflict"]
    missing = [s for s in samples if s["meta"]["refusal_type"] == "missing"]
    rng.shuffle(conflicts)
    rng.shuffle(missing)
    train = conflicts[:6] + missing[:78]
    val = conflicts[6:9] + missing[78:87]
    test = conflicts[9:12] + missing[87:100]
    for part in (train, val, test):
        rng.shuffle(part)
    return train, val, test


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def export_knowledge() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"docs": DOCS, "total_docs": len(DOCS), "total_clauses": len(CLAUSES)}
    (DATA_DIR / "knowledge_base.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for doc in DOCS:
        lines = [f"# {doc['title']}", "", f"- 文档编号：{doc['doc_id']}", f"- 分类：{doc['category']}", ""]
        for clause in doc["clauses"]:
            lines.append(f"## {clause['heading']}（{clause['cid']}）")
            lines.append("")
            lines.append(clause["text"])
            lines.append("")
            lines.append("**要点**")
            lines.append("")
            for point in clause["points"]:
                lines.append(f"- {point}")
            lines.append("")
            if clause.get("process"):
                lines.append("**办理流程**")
                lines.append("")
                for i, step in enumerate(clause["process"], start=1):
                    lines.append(f"{i}. {step}")
                lines.append("")
            lines.append(f"**办理建议**：{clause['advice']}")
            lines.append("")
        (KNOWLEDGE_DIR / f"{doc['doc_id']}_{doc['title']}.md").write_text(
            "\n".join(lines), encoding="utf-8"
        )


def main() -> None:
    rng = random.Random(20260515)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    export_knowledge()

    builders = {
        "term_format": build_term_format,
        "faithful": build_faithful,
        "multi_snippet": build_multi_snippet,
        "citation": build_citation,
        "refusal": build_refusal,
    }
    per_cap_total = 112
    train_all: list[dict] = []
    val_all: list[dict] = []
    test_all: list[dict] = []

    for capability, builder in builders.items():
        samples = builder(rng, per_cap_total)
        if len(samples) < per_cap_total:
            raise RuntimeError(f"{capability} 样本不足：{len(samples)} < {per_cap_total}")
        if capability == "refusal":
            train, val, test = split_refusal(samples, rng)
        else:
            train, val, test = split_capability(samples, rng)
        for split_name, subset in (("train", train), ("validation", val), ("test", test)):
            for sample in subset:
                sample["meta"]["split"] = split_name
        train_all.extend(train)
        val_all.extend(val)
        test_all.extend(test)
        print(
            f"{capability:14s} total={len(samples):3d} train={len(train):3d} "
            f"val={len(val):2d} test={len(test):2d}"
        )

    rng.shuffle(train_all)
    rng.shuffle(val_all)
    rng.shuffle(test_all)

    write_jsonl(DATA_DIR / "train.jsonl", train_all)
    write_jsonl(DATA_DIR / "validation.jsonl", val_all)
    write_jsonl(DATA_DIR / "test.jsonl", test_all)

    all_samples = train_all + val_all + test_all
    lengths = [len(s["messages"][1]["content"]) + len(s["messages"][2]["content"]) for s in all_samples]
    stats = {
        "generated_at": "2026-10-24",
        "seed": 20260515,
        "system_prompt": SYSTEM_PROMPT,
        "knowledge": {"docs": len(DOCS), "clauses": len(CLAUSES)},
        "splits": {
            "train": len(train_all),
            "validation": len(val_all),
            "test": len(test_all),
            "total": len(all_samples),
        },
        "capabilities": [],
        "answerable_ratio": round(sum(1 for s in all_samples if s["meta"]["answerable"]) / len(all_samples), 4),
        "context_chars": {
            "mean": round(statistics.mean(lengths), 1),
            "max": max(lengths),
            "min": min(lengths),
        },
        "answer_chars": {
            "mean": round(statistics.mean(len(s["messages"][2]["content"]) for s in all_samples), 1),
            "max": max(len(s["messages"][2]["content"]) for s in all_samples),
            "min": min(len(s["messages"][2]["content"]) for s in all_samples),
        },
    }
    for capability in CAPABILITIES:
        rows = [s for s in all_samples if s["capability"] == capability]
        stats["capabilities"].append(
            {
                "key": capability,
                "name": CAP_NAMES[capability],
                "train": sum(1 for s in rows if s["meta"]["split"] == "train"),
                "validation": sum(1 for s in rows if s["meta"]["split"] == "validation"),
                "test": sum(1 for s in rows if s["meta"]["split"] == "test"),
                "total": len(rows),
            }
        )
    refusal_rows = [s for s in all_samples if s["capability"] == "refusal"]
    stats["refusal_types"] = {
        kind: sum(1 for s in refusal_rows if s["meta"]["refusal_type"] == kind)
        for kind in ("missing", "conflict")
    }
    test_refusal = [s for s in test_all if s["capability"] == "refusal"]
    stats["refusal_types_test"] = {
        kind: sum(1 for s in test_refusal if s["meta"]["refusal_type"] == kind)
        for kind in ("missing", "conflict")
    }
    (DATA_DIR / "dataset_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 数据样例（供报告展示）
    preview = []
    for capability in CAPABILITIES:
        sample = next(s for s in train_all if s["capability"] == capability)
        preview.append(
            {
                "capability": capability,
                "capability_name": CAP_NAMES[capability],
                "question": sample["messages"][1]["content"].split("【问题】")[-1].strip(),
                "answer": sample["messages"][2]["content"],
            }
        )
    (DATA_DIR / "preview_samples.json").write_text(
        json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"总计：train={len(train_all)} validation={len(val_all)} test={len(test_all)}")
    print(f"输出目录：{DATA_DIR}")


if __name__ == "__main__":
    main()
