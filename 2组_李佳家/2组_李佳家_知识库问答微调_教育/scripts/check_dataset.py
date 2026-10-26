# -*- coding: utf-8 -*-
"""数据集质量检查脚本。

检查项：
1. 三个切分文件存在、行数符合预期（420 / 60 / 80）
2. 每条样本具备 system / user / assistant 三轮消息
3. 可回答样本的答案包含至少一个引用编号，且引用条款出现在上下文中
4. 不可回答样本的答案包含明确拒答表述
5. 训练集与测试集问题不重复（避免数据泄漏）
6. 输出能力维度分布、长度统计与示例

运行：python scripts/check_dataset.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CITATION_RE = re.compile(r"\[(KB-EDU-\d{3}-\d+\.\d+)\]")
REFUSAL_MARKERS = ("无法依据现有资料", "资料之间存在冲突")


def load_split(name: str) -> list[dict]:
    path = DATA_DIR / f"{name}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"缺少数据文件：{path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    splits = {name: load_split(name) for name in ("train", "validation", "test")}
    expected = {"train": 420, "validation": 60, "test": 80}
    errors: list[str] = []

    for name, rows in splits.items():
        print(f"[{name}] {len(rows)} 条（期望 {expected[name]}）")
        if len(rows) != expected[name]:
            errors.append(f"{name} 行数 {len(rows)} != {expected[name]}")

    all_ids: set[str] = set()
    for name, rows in splits.items():
        for row in rows:
            if row["id"] in all_ids:
                errors.append(f"重复 ID：{row['id']}")
            all_ids.add(row["id"])
            messages = row.get("messages", [])
            if [m.get("role") for m in messages] != ["system", "user", "assistant"]:
                errors.append(f"{row['id']} 消息角色不正确")
                continue
            user_text = messages[1]["content"]
            answer = messages[2]["content"]
            meta = row.get("meta", {})
            if meta.get("answerable"):
                citations = CITATION_RE.findall(answer)
                if not citations:
                    errors.append(f"{row['id']} 可回答样本缺少引用")
                for citation in citations:
                    if citation not in user_text:
                        errors.append(f"{row['id']} 引用了上下文之外的条款 {citation}")
                if not set(meta.get("gold_refs", [])) & set(citations):
                    errors.append(f"{row['id']} 未引用标准答案中的依据条款")
            else:
                if not any(marker in answer for marker in REFUSAL_MARKERS):
                    errors.append(f"{row['id']} 拒答样本缺少拒答表述")

    train_questions = {row["messages"][1]["content"].split("【问题】")[-1].strip() for row in splits["train"]}
    test_questions = {row["messages"][1]["content"].split("【问题】")[-1].strip() for row in splits["test"]}
    overlap = train_questions & test_questions
    if overlap:
        errors.append(f"训练集与测试集存在重复问题：{len(overlap)} 条")

    capability_counts = Counter(row["capability"] for row in splits["train"])
    print("\n能力维度分布（train）：")
    for capability, count in capability_counts.items():
        print(f"  {capability:14s} {count}")
    print(f"\n可回答样本占比：{sum(1 for r in splits['train'] if r['meta']['answerable']) / len(splits['train']):.2%}")
    print(f"训练集/测试集问题重叠：{len(overlap)}")

    if errors:
        print("\n检查未通过：")
        for error in errors[:20]:
            print(" -", error)
        raise SystemExit(1)
    print("\n数据集检查通过")


if __name__ == "__main__":
    main()
