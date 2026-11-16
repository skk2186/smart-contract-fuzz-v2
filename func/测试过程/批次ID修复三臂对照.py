#!/usr/bin/env python3
"""离线比较 BeeStorage 原生、历史种子与事件绑定修正种子。"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from AgentB import to_echidna_sequence
from 属性种子上下文 import load_project_context
from 种子验证 import run_echidna

PROPERTY_ID = "2c68514fc72b1303d6e8"
PROPERTY_NAME = "echidna_stamp_internal_pot_not_above_contract_balance"
RANDOM_SEEDS = [20261118, 20261128, 20261138]
TEST_LIMIT = 80
OUTPUT = ROOT / "deepseek/结果/逐属性原生对照实验/BeeStorage批次ID修复三臂-20261116"


def _lcov_lines(campaign: Path) -> set[tuple[str, int]]:
    files = list(campaign.glob("covered.*.lcov"))
    if len(files) != 1:
        raise RuntimeError(f"LCOV 文件数量不是 1：{campaign}: {len(files)}")
    source = ""
    hit: set[tuple[str, int]] = set()
    for line in files[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            source = str(Path(line[3:]).relative_to(ROOT))
        elif line.startswith("DA:"):
            number, count, *_ = line[3:].split(",")
            if int(count) > 0:
                hit.add((source, int(number)))
    return hit


def _run(root: Path, seed: int, treatment: str, input_seed: Path | None,
         test_limit: int) -> dict:
    root.mkdir(parents=True, exist_ok=False)
    corpus = root / "coverage"
    corpus.mkdir()
    if input_seed:
        shutil.copy2(input_seed, corpus / input_seed.name)
    result = run_echidna("BeeStorage", root, property_name=PROPERTY_NAME,
                         test_limit=test_limit, timeout=60, seed=seed,
                         seq_len=8, shrink_limit=1, stop_on_fail=False,
                         disable_slither=True)
    if result["status"] != "completed" or result["exit_code"] != 0:
        raise RuntimeError(f"Echidna 未正常完成：{root}, {result['status']}, {result['exit_code']}")
    replayed = any(input_seed.name in line for line in result["replayed_lines"]) if input_seed else False
    if input_seed and (result["loaded_seed_count"] < 1 or not replayed):
        raise RuntimeError(f"种子没有实际加载并回放：{root}")
    if not input_seed and result["loaded_seed_count"] != 0:
        raise RuntimeError(f"原生组出现外部语料：{root}")
    hit = _lcov_lines(root)
    return {"treatment": treatment, "random_seed": seed,
            "test_limit": test_limit, "unique_instructions": result["unique_instructions"],
            "hit_source_line_count": len(hit),
            "hit_source_lines": [f"{path}:{line}" for path, line in sorted(hit)],
            "target_property_results": result["target_property_results"],
            "property_failures": result["property_failures"],
            "initial_state_failures": result["initial_state_failures"],
            "loaded_seed_count": result["loaded_seed_count"],
            "replayed_sequence_count": result["replayed_sequence_count"],
            "specific_seed_replayed": replayed,
            "fuzzing_cases": result["fuzzing_cases"],
            "elapsed_seconds": result["elapsed_seconds"],
            "log_path": result["full_log_path"],
            "lcov_path": str(next(root.glob("covered.*.lcov")).relative_to(ROOT))}


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"拒绝覆盖已有运行：{OUTPUT}")
    audit = ROOT / "deepseek/结果/逐属性原生对照实验/种子效用核验-20261115"
    row = next(item for item in json.loads((audit / "种子效用核验.json").read_text())["records"]
               if item["property_id"] == PROPERTY_ID)
    regression = next(item for item in json.loads((audit / "状态依赖回归.json").read_text())["records"]
                      if item["property_id"] == PROPERTY_ID)
    if regression["with_historical_dependency_hints"]["replay_status"] != "executable":
        raise RuntimeError("修正种子未通过 Anvil 逐笔回放")
    source = json.loads((ROOT / row["source_report"]).read_text())
    prop = next(item for item in source["properties"] if item["property_id"] == PROPERTY_ID)
    candidate = next(item for item in prop["seed_generation"]["candidate_results"]
                     if item.get("seed_id") == row["seed_id"])
    old_path = ROOT / row["source_corpus"]
    old = json.loads(old_path.read_text())
    context = load_project_context("BeeStorage", [PROPERTY_ID])
    fixed = to_echidna_sequence(
        {"candidate_id": candidate["candidate_id"], "property_id": PROPERTY_ID,
         "steps": candidate["plan"]},
        regression["with_historical_dependency_hints"]["resolved_transactions"], context)
    if len(old) != len(fixed) or len(old) != 3:
        raise RuntimeError("新旧语料交易数不匹配")
    for tx_index, (before, after) in enumerate(zip(old, fixed)):
        expected = json.loads(json.dumps(before))
        if tx_index == 1:
            expected["call"]["contents"][1][1] = after["call"]["contents"][1][1]
        if expected != after:
            raise RuntimeError(f"第 {tx_index + 1} 笔出现 batchId 之外的语料变更")
    OUTPUT.mkdir(parents=True)
    seed_dir = OUTPUT / "输入种子"
    seed_dir.mkdir()
    old_copy = seed_dir / old_path.name
    shutil.copy2(old_path, old_copy)
    fixed_path = seed_dir / f"seed-fixed-{hashlib.sha256(json.dumps(fixed, sort_keys=True).encode()).hexdigest()[:24]}.txt"
    fixed_path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    plan = {"api_calls": 0, "project": "BeeStorage", "property_id": PROPERTY_ID,
            "property_name": PROPERTY_NAME, "test_limit": TEST_LIMIT,
            "random_seeds": RANDOM_SEEDS, "treatments": ["native", "old", "fixed"],
            "same_settings": {"seq_len": 8, "shrink_limit": 1, "workers": 1,
                              "stop_on_fail": False, "disable_slither": True},
            "old_seed": str(old_copy.relative_to(ROOT)),
            "fixed_seed": str(fixed_path.relative_to(ROOT)),
            "only_changed_corpus_field": "transaction 2 call argument 2 batchId",
            "old_seed_sha256": hashlib.sha256(old_copy.read_bytes()).hexdigest(),
            "fixed_seed_sha256": hashlib.sha256(fixed_path.read_bytes()).hexdigest()}
    (OUTPUT / "实验方案.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    seed_only = {}
    for treatment, seed_path in (("native", None), ("old", old_copy), ("fixed", fixed_path)):
        result = _run(OUTPUT / "纯回放" / treatment, RANDOM_SEEDS[0], treatment, seed_path, 0)
        seed_only[treatment] = result
        print("seed-only", treatment, result["unique_instructions"], flush=True)
    pairs = []
    for random_seed in RANDOM_SEEDS:
        arms = {}
        for treatment, seed_path in (("native", None), ("old", old_copy), ("fixed", fixed_path)):
            result = _run(OUTPUT / "配对" / str(random_seed) / treatment,
                          random_seed, treatment, seed_path, TEST_LIMIT)
            arms[treatment] = result
            print(random_seed, treatment, result["unique_instructions"],
                  result["target_property_results"], flush=True)
        pairs.append({"random_seed": random_seed, "arms": arms})
    fixed_lines = set(seed_only["fixed"]["hit_source_lines"])
    old_lines = set(seed_only["old"]["hit_source_lines"])
    result = {"api_calls": 0, "plan": plan, "seed_only": seed_only,
              "seed_only_fixed_only_lines": sorted(fixed_lines - old_lines),
              "seed_only_old_only_lines": sorted(old_lines - fixed_lines),
              "pairs": pairs}
    (OUTPUT / "三臂对照结果.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print((OUTPUT / "三臂对照结果.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
