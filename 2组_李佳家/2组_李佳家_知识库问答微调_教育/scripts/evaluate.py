# -*- coding: utf-8 -*-
"""知识库问答模型评测脚本。

评测指标（全部可解释、可复算）：
- citation_f1      引用准确率：引用编号是否存在、是否覆盖标准依据（P/R/F1）
- key_point_cov    要点覆盖率：标准答案要点在生成答案中的字符 3-gram 覆盖比例
- number_grounding 数字忠实度：答案中的数字是否都能在检索资料中找到出处
- format_ok        格式合规：是否包含结论/依据/分点等要求的结构
- term_hit         术语准确率：标准条款术语在答案中的命中比例
- refusal_ok       拒答正确性：资料不足时是否拒答，可回答时是否避免误拒答

用法：
    python scripts/evaluate.py --model_path <base> --tag base --limit 4
    python scripts/evaluate.py --model_path <base> --adapter outputs/lora_adapter --tag tuned --limit 4
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = Path(r"D:\ai_models\modelscope_cache\models\Qwen\Qwen2___5-0___5B-Instruct")

CITATION_RE = re.compile(r"\[(KB-EDU-\d{3}-\d+\.\d+)\]")
NUMBER_RE = re.compile(r"\d{1,2}:\d{2}|\d+(?:\.\d+)?%?")
REFUSAL_MARKERS = ("无法", "冲突", "不能确定", "无法确认", "资料不足", "没有相关")


def significant_numbers(text: str) -> list[str]:
    numbers = NUMBER_RE.findall(text)
    return [
        n
        for n in numbers
        if len(re.sub(r"\D", "", n)) >= 2 or "%" in n or ":" in n or "." in n
    ]


def char_ngrams(text: str, n: int = 3) -> set[str]:
    clean = re.sub(r"[\s，。；：、（）()“”\"'\[\]【】|,.;:]", "", text)
    return {clean[i : i + n] for i in range(max(0, len(clean) - n + 1))}


def point_coverage(points: list[str], answer: str) -> float:
    if not points:
        return 0.0
    answer_grams = char_ngrams(answer)
    covered = 0
    for point in points:
        grams = char_ngrams(point)
        if not grams:
            continue
        ratio = len(grams & answer_grams) / len(grams)
        if ratio >= 0.35:
            covered += 1
    return covered / len(points)


def format_ok(capability: str, answer: str) -> bool:
    if capability == "refusal":
        return ("无法" in answer or "冲突" in answer) and ("缺少" in answer or "建议" in answer)
    if capability == "term_format":
        return "依据" in answer and ("1." in answer or "步骤" in answer)
    if capability == "faithful":
        return "依据" in answer and ("结论" in answer or "要点" in answer)
    if capability == "multi_snippet":
        return "依据" in answer and len(CITATION_RE.findall(answer)) >= 2 and "1." in answer and "2." in answer
    if capability == "citation":
        return "依据" in answer and ("原文" in answer or "摘录" in answer or "引用" in answer)
    return True


def build_prompt(tokenizer, row: dict) -> tuple[str, str]:
    messages = row["messages"]
    prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True)
    return prompt, messages[2]["content"]


def score_sample(row: dict, answer: str, context: str) -> dict:
    capability = row["capability"]
    meta = row["meta"]
    answerable = meta["answerable"]
    context_refs = set(meta["context_refs"])
    gold_refs = set(meta["gold_refs"])
    citations = CITATION_RE.findall(answer)
    cited = set(citations)

    valid_citations = cited & context_refs
    precision = len(valid_citations) / len(cited) if cited else (1.0 if not answerable else 0.0)
    if gold_refs:
        recall = len(cited & gold_refs) / len(gold_refs)
    else:
        recall = 1.0 if not cited else 0.0
    citation_f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    coverage = point_coverage(meta.get("key_points", []), answer) if answerable else 0.0

    numbers = significant_numbers(answer)
    unsupported = [n for n in numbers if n not in context]
    if answerable:
        grounding = 1.0 if not numbers else 1 - len(unsupported) / len(numbers)
    else:
        # 拒答样本的正确性由 refusal_ok 衡量，不评估数字忠实度
        grounding = 1.0

    fmt = 1.0 if format_ok(capability, answer) else 0.0

    terms = meta.get("terms", [])
    term_hit = (sum(1 for t in terms if t in answer) / len(terms)) if terms else (1.0 if not answerable else 0.0)

    refused = any(marker in answer for marker in REFUSAL_MARKERS)
    refusal_ok = (refused if not answerable else not refused)
    refusal_ok = 1.0 if refusal_ok else 0.0

    if answerable:
        overall = (
            0.25 * citation_f1
            + 0.25 * coverage
            + 0.20 * grounding
            + 0.15 * fmt
            + 0.15 * term_hit
        )
    else:
        overall = 0.7 * refusal_ok + 0.3 * fmt

    return {
        "citation_precision": round(precision, 4),
        "citation_recall": round(recall, 4),
        "citation_f1": round(citation_f1, 4),
        "key_point_coverage": round(coverage, 4),
        "number_grounding": round(grounding, 4),
        "format_ok": fmt,
        "term_hit": round(term_hit, 4),
        "refusal_ok": refusal_ok,
        "overall": round(overall, 4),
        "unsupported_numbers": unsupported,
        "citations": citations,
    }


def load_samples(limit: int) -> list[dict]:
    path = ROOT / "data" / "test.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["capability"], []).append(row)
    selected: list[dict] = []
    for capability in ["term_format", "faithful", "multi_snippet", "citation", "refusal"]:
        if capability == "refusal":
            rows = grouped[capability]
            conflicts = [r for r in rows if r["meta"].get("refusal_type") == "conflict"]
            missing = [r for r in rows if r["meta"].get("refusal_type") != "conflict"]
            selected.extend(conflicts[:2])
            selected.extend(missing[: max(0, limit - 2)])
        else:
            selected.extend(grouped[capability][:limit])
    return selected


def summarize_results(results: list[dict]) -> tuple[dict, list[dict]]:
    """按能力维度与总体汇总指标，供评测与离线重算共用。

    拒答维度不使用引用、要点覆盖、数字忠实度和术语指标（表中显示为 -），
    总体指标中这几项也只对可回答样本求平均，避免用“不适用”的 0 分拉低结果。
    """
    metric_keys = [
        "citation_f1",
        "citation_precision",
        "citation_recall",
        "key_point_coverage",
        "number_grounding",
        "format_ok",
        "term_hit",
        "refusal_ok",
        "overall",
    ]
    retrieval_keys = [
        "citation_f1",
        "citation_precision",
        "citation_recall",
        "key_point_coverage",
        "number_grounding",
        "term_hit",
    ]
    by_capability = []
    for capability in ["term_format", "faithful", "multi_snippet", "citation", "refusal"]:
        rows = [r for r in results if r["capability"] == capability]
        row_summary: dict = {
            "capability": capability,
            "capability_name": rows[0]["capability_name"],
            "count": len(rows),
        }
        for key in metric_keys:
            if capability == "refusal" and key in retrieval_keys:
                row_summary[key] = None
            else:
                row_summary[key] = round(sum(r[key] for r in rows) / len(rows), 4)
        by_capability.append(row_summary)

    answerable = [r for r in results if r["answerable"]]
    aggregate = {
        key: round(sum(r[key] for r in answerable) / len(answerable), 4)
        for key in retrieval_keys
    }
    aggregate["format_ok"] = round(sum(r["format_ok"] for r in results) / len(results), 4)
    aggregate["refusal_ok"] = round(sum(r["refusal_ok"] for r in results) / len(results), 4)
    aggregate["overall"] = round(sum(r["overall"] for r in results) / len(results), 4)
    aggregate["answerable_count"] = len(answerable)
    aggregate["avg_latency_sec"] = round(
        sum(r.get("latency_sec", 0) for r in results) / len(results), 2
    )
    return aggregate, by_capability


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model_path", default=str(DEFAULT_MODEL))
    parser.add_argument("--adapter", default="")
    parser.add_argument("--tag", default="base")
    parser.add_argument("--limit", type=int, default=4, help="每个能力维度评测条数")
    parser.add_argument("--max_new_tokens", type=int, default=180)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--output_dir", default=str(ROOT / "outputs"))
    args = parser.parse_args()

    torch.set_num_threads(max(1, torch.get_num_threads()))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    tokenizer = AutoTokenizer.from_pretrained(args.model_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    print(f"加载模型：{args.model_path}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model_path,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )
    if args.adapter:
        from peft import PeftModel

        print(f"加载 LoRA 适配器：{args.adapter}")
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    samples = load_samples(args.limit)
    print(f"评测样本：{len(samples)} 条（每维度 {args.limit} 条）")

    results: list[dict] = []
    started = time.time()
    for start in range(0, len(samples), args.batch_size):
        batch_rows = samples[start : start + args.batch_size]
        prompts = [build_prompt(tokenizer, row)[0] for row in batch_rows]
        encoded = tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=1024)
        input_len = encoded["input_ids"].shape[1]
        batch_started = time.time()
        with torch.no_grad():
            outputs = model.generate(
                **encoded,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                num_beams=1,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        latency = (time.time() - batch_started) / len(batch_rows)
        decoded = tokenizer.batch_decode(outputs[:, input_len:], skip_special_tokens=True)

        for row, answer in zip(batch_rows, decoded):
            answer = answer.strip()
            user_content = row["messages"][1]["content"]
            context = user_content.split("【问题】")[0]
            metrics = score_sample(row, answer, context)
            metrics["latency_sec"] = round(latency, 2)
            results.append(
                {
                    "id": row["id"],
                    "capability": row["capability"],
                    "capability_name": row["meta"]["capability_name"],
                    "answerable": row["meta"]["answerable"],
                    "question": user_content.split("【问题】")[-1].strip(),
                    "context": context,
                    "gold_answer": row["messages"][2]["content"],
                    "prediction": answer,
                    "gold_refs": row["meta"]["gold_refs"],
                    **metrics,
                }
            )
        print(f"  已生成 {min(start + args.batch_size, len(samples))}/{len(samples)}")

    aggregate, by_capability = summarize_results(results)

    report = {
        "tag": args.tag,
        "model_path": args.model_path,
        "adapter": args.adapter,
        "evaluated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sample_count": len(results),
        "duration_seconds": round(time.time() - started, 1),
        "aggregate": aggregate,
        "by_capability": by_capability,
        "samples": results,
    }
    output_path = output_dir / f"eval_{args.tag}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def cell(value) -> str:
        return f"{value:>8.3f}" if value is not None else f"{'—':>8}"

    print("\n" + "=" * 78)
    print(f"{'能力维度':<22}{'引用F1':>8}{'要点覆盖':>10}{'数字忠实':>10}{'格式':>8}{'术语':>8}{'拒答':>8}{'综合':>8}")
    for row in by_capability:
        print(
            f"{row['capability_name']:<22}{cell(row['citation_f1'])}{cell(row['key_point_coverage']):>10}"
            f"{cell(row['number_grounding']):>10}{row['format_ok']:>8.3f}{cell(row['term_hit'])}"
            f"{row['refusal_ok']:>8.3f}{row['overall']:>8.3f}"
        )
    print("-" * 78)
    print(
        f"{'总体':<22}{aggregate['citation_f1']:>8.3f}{aggregate['key_point_coverage']:>10.3f}"
        f"{aggregate['number_grounding']:>10.3f}{aggregate['format_ok']:>8.3f}"
        f"{aggregate['term_hit']:>8.3f}{aggregate['refusal_ok']:>8.3f}{aggregate['overall']:>8.3f}"
    )
    print(f"平均单条生成耗时：{aggregate['avg_latency_sec']} 秒")
    print(f"评测结果已保存：{output_path}")


if __name__ == "__main__":
    main()
