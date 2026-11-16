#!/usr/bin/env python3
"""补全 Request 属性的 Agent B 预算预检失败，并复用原配对基线。"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/功能")]

from 属性种子上下文 import load_project_context
from 种子验证 import run_echidna
from 运行Agent种子流程 import run_project

PROPERTY_ID = "c451c42790194538cf50"
PROPERTY_NAME = "echidna_token_conservation"
RANDOM_SEEDS = [20261218, 20261228, 20261238]
OUTPUT = ROOT / "deepseek/结果/跨合约深层状态引导-20261116"
RETRY_ROOT = OUTPUT / "种子生成/Request/c451c42790194538cf50-retry-40000"


def main() -> None:
    if RETRY_ROOT.exists():
        raise FileExistsError(f"拒绝覆盖既有补跑：{RETRY_ROOT}")
    result_path = OUTPUT / "跨合约对照结果.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    sample = next(item for item in result["samples"]
                  if item["sample"]["project"] == "Request")
    if sample["generated_seed"]:
        raise RuntimeError("Request 已经有有效种子，无需预算补跑")
    amendment = {"reason": "首轮 Agent B 在 API 请求前被 30000 Token 属性预算预检拦截；未发出模型请求。为完成已固定样本的完整 Agent A/B 流程，只调整该属性的本地预算上限。",
                 "original_token_budget": 30000, "retry_token_budget": 40000,
                 "property_id": PROPERTY_ID, "random_seeds": RANDOM_SEEDS,
                 "selection_or_evaluation_rule_changed": False}
    (OUTPUT / "Request预算补充方案.json").write_text(
        json.dumps(amendment, ensure_ascii=False, indent=2), encoding="utf-8")
    generation = run_project(
        "Request", [PROPERTY_ID], max_candidates=1, max_steps=8,
        repairs=1, planning_repairs=1, echidna_limit=80, echidna_timeout=60,
        echidna_seed=RANDOM_SEEDS[0], token_budget=40000, wall_budget=240,
        run_fuzzer=False, run_root=RETRY_ROOT,
        api_log_path=RETRY_ROOT / "API调用.jsonl")
    (RETRY_ROOT / "逐属性Agent种子流程.json").write_text(
        json.dumps(generation, ensure_ascii=False, indent=2), encoding="utf-8")
    row = generation["property_results"][0]
    candidate = next((item for item in row.get("candidate_results", [])
                      if item.get("status") == "executable" and item.get("corpus_file")), None)
    seed_path = ROOT / candidate["corpus_file"] if candidate else None
    v2_runs = []
    if seed_path:
        context = load_project_context("Request", [PROPERTY_ID])
        prop = context["properties"][0]
        for seed in RANDOM_SEEDS:
            root = OUTPUT / "Echidna" / "Request" / PROPERTY_ID / str(seed) / "v2-retry-40000"
            root.mkdir(parents=True, exist_ok=False)
            corpus = root / "coverage"
            corpus.mkdir()
            shutil.copy2(seed_path, corpus / seed_path.name)
            run = run_echidna("Request", root, property_name=PROPERTY_NAME,
                              test_limit=80, timeout=60, seed=seed, seq_len=8,
                              shrink_limit=1, stop_on_fail=False,
                              disable_slither=True)
            replayed = any(seed_path.name in line for line in run["replayed_lines"])
            if run["status"] != "completed" or run["exit_code"] != 0 or not replayed:
                raise RuntimeError(f"Request 补跑 Echidna 失败或未回放种子：{seed}")
            lcov = next(root.glob("covered.*.lcov"))
            lines = set()
            source = ""
            for line in lcov.read_text(encoding="utf-8").splitlines():
                if line.startswith("SF:"):
                    source = str(Path(line[3:]).relative_to(ROOT))
                elif line.startswith("DA:"):
                    number, hits, *_ = line[3:].split(",")
                    if int(hits) > 0:
                        lines.add(f"{source}:{int(number)}")
            baseline = next(item for item in sample["pairs"] if item["random_seed"] == seed)["native"]
            v2_runs.append({"random_seed": seed, "native": baseline,
                            "v2": {"unique_instructions": run["unique_instructions"],
                                   "hit_source_line_count": len(lines),
                                   "hit_source_lines": sorted(lines),
                                   "target_property_results": run["target_property_results"],
                                   "property_failures": run["property_failures"],
                                   "initial_state_failures": run["initial_state_failures"],
                                   "loaded_seed_count": run["loaded_seed_count"],
                                   "replayed_sequence_count": run["replayed_sequence_count"],
                                   "external_seed_replayed": replayed,
                                   "fuzzing_cases": run["fuzzing_cases"],
                                   "elapsed_seconds": run["elapsed_seconds"],
                                   "log_path": run["full_log_path"],
                                   "lcov_path": str(lcov.relative_to(ROOT))},
                            "coverage_delta_unique_instructions":
                                run["unique_instructions"] - baseline["unique_instructions"],
                            "coverage_delta_source_lines": len(lines) - baseline["hit_source_line_count"]})
    supplement = {"amendment": amendment, "generation": generation,
                  "generated_seed": ({"seed_id": candidate["seed_id"],
                                      "seed_class": candidate["seed_class"],
                                      "corpus_file": candidate["corpus_file"],
                                      "transaction_count": len(candidate["concrete_seed"]["transactions"]),
                                      "replay_attempts": candidate["replay_attempts"]}
                                     if candidate else None),
                  "pairs": v2_runs}
    (OUTPUT / "Request预算补跑结果.json").write_text(
        json.dumps(supplement, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Request", row["status"],
          candidate["seed_id"] if candidate else "no-valid-seed",
          "pairs", len(v2_runs), flush=True)


if __name__ == "__main__":
    main()
