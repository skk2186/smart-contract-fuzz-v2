#!/usr/bin/env python3
"""对预登记的 OpenNFTs 原生属性运行一次隔离的原生 Echidna 基线。"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "func/功能"))
sys.path.insert(0, str(ROOT / "deepseek"))
from 种子验证 import run_echidna

OUT = ROOT / "deepseek/结果/通用依赖泛化验证"
PROPERTIES = ("echidna_owner", "echidna_balance")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT,
                        help="使用新目录复跑，避免覆盖已有 campaign")
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    if not output_dir.is_relative_to(ROOT):
        parser.error("输出目录必须位于本仓库内")
    rows = []
    for index, name in enumerate(PROPERTIES):
        corpus = output_dir / "原生基线" / name
        corpus.parent.mkdir(parents=True, exist_ok=True)
        row = run_echidna("OpenNFTs", corpus, property_name=name,
                          test_limit=80, timeout=45, seed=20261116 + index,
                          seq_len=8, shrink_limit=1, stop_on_fail=False,
                          disable_slither=True)
        rows.append(row)
        (output_dir / "原生基线.json").write_text(
            json.dumps({"properties": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(json.dumps({"property": name, "status": row["status"],
                          "results": row["target_property_results"],
                          "log": row["full_log_path"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
