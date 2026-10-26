# -*- coding: utf-8 -*-
"""把基线与微调的逐条评测结果导出为 CSV，便于用 Excel 查看。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"

COLUMNS = [
    "tag",
    "id",
    "capability",
    "capability_name",
    "answerable",
    "question",
    "citation_f1",
    "key_point_coverage",
    "number_grounding",
    "format_ok",
    "term_hit",
    "refusal_ok",
    "overall",
    "citations",
    "prediction",
]


def main() -> None:
    rows: list[dict] = []
    for tag in ("base", "tuned"):
        path = OUTPUT_DIR / f"eval_{tag}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for sample in data["samples"]:
            rows.append(
                {
                    "tag": tag,
                    **{key: sample.get(key, "") for key in COLUMNS if key != "tag"},
                    "citations": "|".join(sample.get("citations", [])),
                }
            )
    output = OUTPUT_DIR / "eval_details.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"导出 {len(rows)} 条明细 -> {output}")


if __name__ == "__main__":
    main()
