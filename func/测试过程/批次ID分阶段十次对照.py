#!/usr/bin/env python3
"""不调用 API，按固定 80/500 测试预算做 BeeStorage 三臂十次配对。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "func/测试过程"))
from 批次ID修复三臂对照 import _run

SOURCE = ROOT / "deepseek/结果/逐属性原生对照实验/BeeStorage批次ID修复三臂-20261116"
OUTPUT = ROOT / "deepseek/结果/逐属性原生对照实验/BeeStorage批次ID分阶段十次-20261116"
SEEDS = [20261118 + 10 * index for index in range(10)]
ARMS = ("native", "old", "fixed")
STAMP = "sol/真实项目/BeeStorage/src/PostageStamp.sol"
HARNESS = "sol/真实项目/BeeStorage/src/echidna/EchidnaSystemHarness.sol"
TARGET_REGIONS = {
    "property_check": (HARNESS, 289, 293),
    "batch_create": (STAMP, 189, 239),
    "topup": (STAMP, 337, 368),
    "topup_success": (STAMP, 357, 368),
    "expire_and_pot": (STAMP, 446, 530),
    "payment_and_balance": (STAMP, 562, 586),
}


def _target_metrics(run: dict) -> dict:
    hit = set(run["hit_source_lines"])
    return {name: {"hit_line_count": len(lines := [f"{path}:{line}" for line in range(start, end + 1)
                                              if f"{path}:{line}" in hit]),
                   "hit_lines": lines}
            for name, (path, start, end) in TARGET_REGIONS.items()}


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"拒绝覆盖既有运行：{OUTPUT}")
    source = json.loads((SOURCE / "三臂对照结果.json").read_text(encoding="utf-8"))
    source_plan = json.loads((SOURCE / "实验方案.json").read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True)
    input_dir = OUTPUT / "输入种子"
    input_dir.mkdir()
    inputs = {"native": None}
    for arm in ("old", "fixed"):
        original = ROOT / source_plan[f"{arm}_seed"]
        copy = input_dir / original.name
        shutil.copy2(original, copy)
        inputs[arm] = copy
    plan = {"api_calls": 0, "property_id": source_plan["property_id"],
            "random_seeds": SEEDS, "treatments": list(ARMS),
            "early_test_limit": 80, "final_test_limit": 500,
            "early_measurement": "separate 80-test campaign, same random seed and settings",
            "final_measurement": "separate 500-test campaign, same random seed and settings",
            "reused_early_pairs": source_plan["random_seeds"],
            "other_settings": source_plan["same_settings"],
            "target_regions": {name: {"file": path, "first_line": start, "last_line": end}
                               for name, (path, start, end) in TARGET_REGIONS.items()},
            "source_three_pair_result": str((SOURCE / "三臂对照结果.json").relative_to(ROOT)),
            "input_seeds": {arm: str(path.relative_to(ROOT)) if path else None
                            for arm, path in inputs.items()}}
    (OUTPUT / "实验方案.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    pairs = {}
    for old_pair in source["pairs"]:
        seed = old_pair["random_seed"]
        if seed not in SEEDS:
            raise RuntimeError(f"历史随机种子未在预设十次内：{seed}")
        pairs[seed] = {"random_seed": seed, "early_80": old_pair["arms"],
                       "final_500": {}, "early_reused_from_source": True}
    for seed in SEEDS:
        if seed not in pairs:
            pairs[seed] = {"random_seed": seed, "early_80": {},
                           "final_500": {}, "early_reused_from_source": False}
        for budget, field in ((80, "early_80"), (500, "final_500")):
            if budget == 80 and pairs[seed]["early_reused_from_source"]:
                continue
            for arm in ARMS:
                run = _run(OUTPUT / "配对" / str(seed) / str(budget) / arm,
                           seed, arm, inputs[arm], budget)
                pairs[seed][field][arm] = run
                print(seed, budget, arm, run["unique_instructions"], flush=True)
        # 每组结束即保存检查点，不覆盖已有实验运行目录。
        checkpoint = {"api_calls": 0, "plan": plan,
                      "pairs": [pairs[item] for item in SEEDS if item in pairs]}
        (OUTPUT / "运行检查点.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for seed in SEEDS:
        pair = pairs[seed]
        for field in ("early_80", "final_500"):
            for arm in ARMS:
                pair[field][arm]["target_path_metrics"] = _target_metrics(pair[field][arm])
        rows.append(pair)
    result = {"api_calls": 0, "plan": plan, "pairs": rows}
    (OUTPUT / "分阶段十次结果.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print((OUTPUT / "分阶段十次结果.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
