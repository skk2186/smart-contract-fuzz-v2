#!/usr/bin/env python3
"""跨合约验证完整 Agent A/B 深层状态种子与原生 Echidna。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/功能")]

from 属性种子上下文 import PROJECTS, load_project_context
from 种子验证 import run_echidna
from 运行Agent种子流程 import run_project

SAMPLES = [
    {"project": "Hokusai", "property_id": "40b35ad5dc128d8aff62",
     "category": "两步 mint/burn 供应量会计状态依赖",
     "source": "deepseek/结果/逐属性原生对照实验/9abf66b9161b4f67b48de4a561e41a2f/逐属性原生对照实验.json"},
    {"project": "Kink", "property_id": "28d4a5495cb06ab375a1",
     "category": "两步流动性注入/移除及 LP 余额依赖",
     "source": "deepseek/结果/逐属性原生对照实验/9abf66b9161b4f67b48de4a561e41a2f/逐属性原生对照实验.json"},
    {"project": "Request", "property_id": "c451c42790194538cf50",
     "category": "三步支付授权/扣款/退款及 paymentRef 状态依赖",
     "source": "deepseek/结果/逐属性原生对照实验/2253a6ce251e4d44aea57f6be6378ff3/逐属性原生对照实验.json"},
]
RANDOM_SEEDS = [20261218, 20261228, 20261238]
TEST_LIMIT = 80
TOKEN_BUDGET_PER_PROPERTY = 30000
WALL_BUDGET_PER_PROPERTY = 240
OUTPUT = ROOT / "deepseek/结果/跨合约深层状态引导-20261116"


def _lcov(campaign_root: Path) -> set[str]:
    files = list(campaign_root.glob("covered.*.lcov"))
    if len(files) != 1:
        raise RuntimeError(f"期望一个 LCOV 文件：{campaign_root}，实际 {len(files)}")
    source = ""
    lines = set()
    for row in files[0].read_text(encoding="utf-8").splitlines():
        if row.startswith("SF:"):
            source = str(Path(row[3:]).relative_to(ROOT))
        elif row.startswith("DA:"):
            number, hits, *_ = row[3:].split(",")
            if int(hits) > 0:
                lines.add(f"{source}:{int(number)}")
    return lines


def _campaign(project: str, property_row: dict[str, Any], prop_context: dict[str, Any],
              root: Path, treatment: str, random_seed: int,
              external_seed: Path | None) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=False)
    coverage = root / "coverage"
    coverage.mkdir()
    if external_seed:
        shutil.copy2(external_seed, coverage / external_seed.name)
    property_name = property_row["property"].rsplit(".", 1)[-1].split("(", 1)[0]
    result = run_echidna(
        project, root, property_name=property_name, test_limit=TEST_LIMIT,
        timeout=60, seed=random_seed, seq_len=8, shrink_limit=1,
        stop_on_fail=False, disable_slither=True)
    if result["status"] != "completed" or result["exit_code"] != 0:
        raise RuntimeError(f"Echidna campaign 失败：{result['status']} / {result['exit_code']}")
    if external_seed:
        replayed = any(external_seed.name in line for line in result["replayed_lines"])
        if result["loaded_seed_count"] < 1 or not replayed:
            raise RuntimeError(f"外部种子未加载回放：{external_seed}")
    else:
        replayed = False
        if result["loaded_seed_count"] != 0:
            raise RuntimeError("原生基线的空语料目录意外加载了种子")
    return {"treatment": treatment, "property_id": property_row["property_id"],
            "random_seed": random_seed, "test_limit": TEST_LIMIT,
            "unique_instructions": result["unique_instructions"],
            "hit_source_line_count": len(lines := _lcov(root)),
            "hit_source_lines": sorted(lines),
            "target_property_results": result["target_property_results"],
            "property_failures": result["property_failures"],
            "initial_state_failures": result["initial_state_failures"],
            "loaded_seed_count": result["loaded_seed_count"],
            "replayed_sequence_count": result["replayed_sequence_count"],
            "external_seed_replayed": replayed,
            "fuzzing_cases": result["fuzzing_cases"],
            "elapsed_seconds": result["elapsed_seconds"],
            "log_path": result["full_log_path"],
            "lcov_path": str(next(root.glob("covered.*.lcov")).relative_to(ROOT))}


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"拒绝覆盖已有实验目录：{OUTPUT}")
    OUTPUT.mkdir(parents=True)
    plan = {"experiment": "跨合约深层状态引导验证",
            "api_calls": "计划内每属性完整 Agent A 与 Agent B 流程；仅在执行时发生",
            "selection_rule": "预先选择非 BeeStorage 的真实项目属性；已有 Slither/源码证据或历史 Agent A 计划证明至少两笔状态操作存在跨交易依赖；三个合约各取一种不同业务流程；失败属性保留并仍运行 V2 空语料组",
            "samples": SAMPLES, "treatments": ["native_echidna_empty_corpus", "current_A_B_seeded"],
            "test_limit_per_campaign": TEST_LIMIT, "random_seeds_per_pair": RANDOM_SEEDS,
            "settings": {"seq_len": 8, "shrink_limit": 1, "workers": 1,
                         "stop_on_fail": False, "disable_slither": True,
                         "exact_property_prefix": True},
            "generation": {"max_candidates": 1, "max_steps": 8,
                           "planning_repairs": 1, "execution_feedback_repairs": 1,
                           "token_budget_per_property": TOKEN_BUDGET_PER_PROPERTY,
                           "wall_budget_seconds_per_property": WALL_BUDGET_PER_PROPERTY}}
    (OUTPUT / "实验方案.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    reports = []
    for sample_index, sample in enumerate(SAMPLES):
        project, property_id = sample["project"], sample["property_id"]
        context = load_project_context(project, [property_id])
        prop = context["properties"][0]
        generation_root = OUTPUT / "种子生成" / project / property_id
        generation_root.mkdir(parents=True)
        generation = run_project(
            project, [property_id], max_candidates=1, max_steps=8,
            repairs=1, planning_repairs=1, echidna_limit=TEST_LIMIT,
            echidna_timeout=60, echidna_seed=RANDOM_SEEDS[0],
            token_budget=TOKEN_BUDGET_PER_PROPERTY,
            wall_budget=WALL_BUDGET_PER_PROPERTY,
            run_fuzzer=False, run_root=generation_root,
            api_log_path=generation_root / "API调用.jsonl")
        generation_path = generation_root / "逐属性Agent种子流程.json"
        generation_path.write_text(json.dumps(generation, ensure_ascii=False, indent=2), encoding="utf-8")
        generated_row = generation["property_results"][0]
        candidate = next((item for item in generated_row.get("candidate_results", [])
                          if item.get("status") == "executable" and item.get("corpus_file")), None)
        seed_path = ROOT / candidate["corpus_file"] if candidate else None
        pairs = []
        for pair_index, random_seed in enumerate(RANDOM_SEEDS):
            baseline = _campaign(project, prop, prop, OUTPUT / "Echidna" / project / property_id /
                                 str(random_seed) / "native", "native_echidna", random_seed, None)
            v2 = _campaign(project, prop, prop, OUTPUT / "Echidna" / project / property_id /
                           str(random_seed) / "v2",
                           "current_A_B_seeded" if seed_path else "current_A_B_failed_empty",
                           random_seed, seed_path)
            pairs.append({"random_seed": random_seed, "native": baseline, "v2": v2,
                          "coverage_delta_unique_instructions":
                              v2["unique_instructions"] - baseline["unique_instructions"],
                          "coverage_delta_source_lines":
                              v2["hit_source_line_count"] - baseline["hit_source_line_count"]})
            print(project, property_id, random_seed,
                  "seed" if seed_path else "no-valid-seed",
                  baseline["unique_instructions"], v2["unique_instructions"], flush=True)
        records = {"sample": sample, "generation": generation,
                   "generated_seed": ({"seed_id": candidate["seed_id"],
                                      "seed_class": candidate["seed_class"],
                                      "corpus_file": candidate["corpus_file"],
                                      "transaction_count": len(candidate["concrete_seed"]["transactions"]),
                                      "replay_attempts": candidate["replay_attempts"]}
                                     if candidate else None),
                   "pairs": pairs}
        reports.append(records)
        checkpoint = {"plan": plan, "completed_samples": reports}
        (OUTPUT / "运行检查点.json").write_text(
            json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
    final = {"plan": plan, "samples": reports,
             "summary": {"api_calls": sum(
                 item["generation"].get("api_usage", {}).get("request_attempts", 0)
                 for item in reports),
                 "api_total_tokens": sum(
                     item["generation"].get("api_usage", {}).get("total_tokens", 0)
                     for item in reports),
                 "estimated_cost_usd_offpeak": str(sum(
                     float(item["generation"].get("api_usage", {}).get(
                         "estimated_cost_usd_offpeak", 0)) for item in reports)),
                 "estimated_cost_usd_peak": str(sum(
                     float(item["generation"].get("api_usage", {}).get(
                         "estimated_cost_usd_peak", 0)) for item in reports))}}
    (OUTPUT / "跨合约对照结果.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    print((OUTPUT / "跨合约对照结果.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
