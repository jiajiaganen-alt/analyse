# -*- coding: utf-8 -*-
"""使用最新测试集元数据重新计算已有评测结果（无需重新生成）。

用途：调整了多片段样本的要点口径、拒答样本的数字忠实度口径后，
直接对已保存的模型输出重新打分，避免重复跑 CPU 推理。

运行：python scripts/rescore_eval.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate import score_sample, summarize_results  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"


def main() -> None:
    test_rows = [
        json.loads(line)
        for line in (ROOT / "data" / "test.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    test_map = {row["id"]: row for row in test_rows}

    for tag in ("base", "tuned"):
        path = OUTPUT_DIR / f"eval_{tag}.json"
        if not path.exists():
            print(f"跳过：{path} 不存在")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for sample in data["samples"]:
            row = test_map[sample["id"]]
            metrics = score_sample(row, sample["prediction"], sample["context"])
            metrics["latency_sec"] = sample.get("latency_sec", 0)
            sample.update(metrics)
        aggregate, by_capability = summarize_results(data["samples"])
        data["aggregate"] = aggregate
        data["by_capability"] = by_capability
        data["rescored_at"] = "2026-10-24"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[{tag}] overall={aggregate['overall']:.4f} 引用F1={aggregate['citation_f1']:.4f} "
              f"要点={aggregate['key_point_coverage']:.4f} 拒答={aggregate['refusal_ok']:.4f}")


if __name__ == "__main__":
    main()
