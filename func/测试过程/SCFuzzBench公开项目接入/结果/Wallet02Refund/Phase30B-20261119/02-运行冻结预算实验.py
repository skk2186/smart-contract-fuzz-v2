#!/usr/bin/env python3
"""按 Phase30B 冻结预算执行唯一一轮新规划及 Anvil 反馈回放。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/功能")]

from 运行Agent种子流程 import run_project


def main() -> None:
    phase_root = Path(__file__).resolve().parent
    run_root = phase_root / "agent-run"
    result_path = phase_root / "02-新规划Anvil结果.json"
    api_path = run_root / "API调用.jsonl"
    if result_path.exists() or api_path.exists():
        raise FileExistsError("Phase30B 新规划已有输出；拒绝覆盖或追加第二轮 Agent 调用")

    result = run_project(
        "Wallet02Refund", ["8e75f62866f6d582a033"],
        max_candidates=1,
        max_steps=8,
        repairs=1,
        planning_repairs=0,
        execution_replans=0,
        schema_repairs=0,
        echidna_limit=500,
        echidna_timeout=60,
        echidna_seed=20261125,
        token_budget=400_000,
        wall_budget=600,
        run_fuzzer=False,
        runtime_constraints=True,
        run_root=run_root,
    )
    result["phase30b_execution"] = {
        "plan": "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/Phase30B-20261119/00-实验方案修订.json",
        "agent_calls_allowed": {"agent_a": 1, "agent_b_generation": 1,
                                "agent_b_execution_feedback_repair": 1},
        "echidna_fuzzing_deferred_until_target_gate": True,
        "candidate_outputs_are_phase30b_isolated": True,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    row = result["property_results"][0]
    print(json.dumps({"status": row.get("status"),
                      "candidate_count": len(row.get("candidate_results", [])),
                      "candidates": [{"candidate_id": candidate.get("candidate_id"),
                                      "status": candidate.get("status"),
                                      "plan": candidate.get("plan"),
                                      "target_property_state": candidate.get("replay_attempts", [{}])[-1].get(
                                          "target_property_state"),
                                      "agent_b_calls": candidate.get("agent_b", {}).get("logical_calls")}
                                     for candidate in row.get("candidate_results", [])],
                      "api_usage": result.get("api_usage"),
                      "elapsed_seconds": result.get("total_elapsed_seconds"),
                      "result": str(result_path.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
