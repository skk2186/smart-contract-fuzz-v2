#!/usr/bin/env python3
"""不调用 API，逐条重放已保存的阶段 A 种子并核验新执行分类。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from 属性种子上下文 import load_project_context
from 种子验证 import replay_seed


def main() -> None:
    audit_root = ROOT / "deepseek/结果/逐属性原生对照实验/种子效用核验-20261115"
    source = json.loads((audit_root / "种子效用核验.json").read_text(encoding="utf-8"))
    records = []
    for old in source["records"]:
        report = json.loads((ROOT / old["source_report"]).read_text(encoding="utf-8"))
        prop = next(item for item in report["properties"]
                    if item["property_id"] == old["property_id"])
        candidate = next(item for item in prop["seed_generation"]["candidate_results"]
                         if item.get("seed_id") == old["seed_id"])
        concrete = candidate["concrete_seed"]
        plan = {"candidate_id": candidate["candidate_id"],
                "property_id": old["property_id"], "property": old["property"],
                "steps": candidate["plan"],
                "context": load_project_context(old["project"], [old["property_id"]])}
        original = replay_seed(old["project"], plan, concrete["transactions"])
        rebound = replay_seed(old["project"], plan, concrete["transactions"],
                              dependency_hints=concrete.get("data_dependencies"))
        declared_rejection = None
        if (len(concrete["transactions"]) == 1 and
                original["transactions"][0].get("execution_class") == "unexpected_internal_revert"):
            # 仅作显式声明机制的反事实核验；不改写保存的历史种子。
            annotated = [{**concrete["transactions"][0], "expected_outcome": "rejection"}]
            declared_rejection = replay_seed(old["project"], plan, annotated)
        def compact(run):
            return {"replay_status": run["replay_status"],
                    "resolved_transactions": run["resolved_transactions"],
                    "transactions": [{key: tx.get(key) for key in
                                      ("index", "function", "status", "execution_class",
                                       "expected_outcome", "changed_storage_slot_count",
                                       "internal_errors", "argument_bindings",
                                       "dependency_errors", "execution_effect_error", "events")}
                                     for tx in run["transactions"]]}
        records.append({"project": old["project"], "property_id": old["property_id"],
                        "seed_id": old["seed_id"], "original": compact(original),
                        "with_historical_dependency_hints": compact(rebound),
                        "with_declared_rejection_counterfactual": (
                            compact(declared_rejection) if declared_rejection else None)})
        print(old["project"], old["property_id"], original["replay_status"],
              rebound["replay_status"], flush=True)
    destination = audit_root / "状态依赖回归.json"
    destination.write_text(json.dumps({"api_calls": 0, "input_seed_count": len(records),
                                       "records": records}, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(destination.relative_to(ROOT))


if __name__ == "__main__":
    main()
