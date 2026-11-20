#!/usr/bin/env python3
"""按 Phase32 冻结预算调用现有 Agent A/B，生成独立样本的初始种子。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]
DRIVER = ROOT / "deepseek/实验过程/运行Agent种子流程.py"
RESULTS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120/AgentAB"
TASKS = {
    "Phase32PigfoxRWADemo": ["2e998090c7de1e70f195", "eaf144ea41a1f5bc076d"],
    "Phase32ReconVaultExample": ["be946ac20a91ff2f9904", "76606be646ce1a2dbd78"],
}


def main() -> None:
    spec = importlib.util.spec_from_file_location("generic_agent_seed_pipeline", DRIVER)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法导入既有逐属性 Agent A/B 流程")
    pipeline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pipeline)
    for project, property_ids in TASKS.items():
        output = RESULTS / project
        output.mkdir(parents=True, exist_ok=True)
        result = pipeline.run_project(
            project, property_ids,
            max_candidates=1, max_steps=8,
            repairs=0, planning_repairs=0, execution_replans=0,
            schema_repairs=0, echidna_limit=500, echidna_timeout=180,
            echidna_seed=20261125, token_budget=400000, wall_budget=600,
            run_fuzzer=False, runtime_constraints=True,
            run_root=output / "pipeline",
            api_log_path=output / "API调用.jsonl")
        destination = output / "Agent种子流程.json"
        destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                               encoding="utf-8")
        print(json.dumps({"project": project,
                          "property_status": {row["property_id"]: row["status"]
                                              for row in result["property_results"]},
                          "valid_evm_seeds": sum(row.get("valid_evm_seed_count", 0)
                                                  for row in result["property_results"]),
                          "api_usage": result["api_usage"],
                          "result": str(destination.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
