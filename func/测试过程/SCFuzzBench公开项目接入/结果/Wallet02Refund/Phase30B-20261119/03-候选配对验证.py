#!/usr/bin/env python3
"""在统一 100 ETH 环境下回放 P0/P1 候选并进行 Echidna seed-only 检查。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from AgentB import to_echidna_sequence
from 属性种子上下文 import PROJECTS, load_project_context
from 种子验证 import AnvilSession, run_echidna, replay_seed


PHASE_ROOT = Path(__file__).resolve().parent
OLD_RESULT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/06-agent-v2/逐属性Agent种子流程.json"
NEW_RESULT = PHASE_ROOT / "02-新规划Anvil结果.json"
OUTPUT = PHASE_ROOT / "03-P0-P1配对验证结果.json"


def main() -> None:
    if OUTPUT.exists():
        raise FileExistsError(f"拒绝覆盖配对验证结果：{OUTPUT}")
    for candidate_path in (OLD_RESULT, NEW_RESULT):
        if not candidate_path.is_file():
            raise FileNotFoundError(candidate_path)

    old = json.loads(OLD_RESULT.read_text(encoding="utf-8"))
    new = json.loads(NEW_RESULT.read_text(encoding="utf-8"))
    old_row = old["property_results"][0]["candidate_results"][0]
    new_row = new["property_results"][0]["candidate_results"][0]
    context = load_project_context("Wallet02Refund", ["8e75f62866f6d582a033"])
    prop = context["properties"][0]
    candidate_context = {**context, "property": prop["property"]}

    candidates = [
        {"name": "P0-old-planner-AgentB-raw", "origin": str(OLD_RESULT.relative_to(ROOT)),
         "candidate_id": old_row["candidate_id"], "steps": old_row["plan"],
         "seed": old_row["raw_concrete_seed"]},
        {"name": "P0-old-planner-AgentB-feedback", "origin": str(OLD_RESULT.relative_to(ROOT)),
         "candidate_id": old_row["candidate_id"], "steps": old_row["plan"],
         "seed": old_row["concrete_seed"]},
        {"name": "P1-source-context-planner", "origin": str(NEW_RESULT.relative_to(ROOT)),
         "candidate_id": new_row["candidate_id"], "steps": new_row["plan"],
         "seed": new_row["concrete_seed"]},
    ]
    candidate_results = []
    with AnvilSession(project="Wallet02Refund") as session:
        for item in candidates:
            candidate = {"property_id": "8e75f62866f6d582a033",
                         "candidate_id": item["candidate_id"],
                         "steps": item["steps"],
                         "context": candidate_context,
                         "property": prop["property"]}
            replay = replay_seed("Wallet02Refund", candidate,
                                 item["seed"]["transactions"],
                                 session=session,
                                 dependency_hints=item["seed"].get("data_dependencies"),
                                 runtime_constraints=False)
            item_result = {"name": item["name"], "origin": item["origin"],
                           "candidate_id": item["candidate_id"], "plan": item["steps"],
                           "resolved_transactions": replay.get("resolved_transactions", []),
                           "anvil_replay": replay,
                           "target_reached": bool(replay.get("target_property_state", {}).get(
                               "counterexample_state_established")),
                           "echidna_seed_only": None}
            if replay.get("replay_status") == "executable":
                corpus_root = PHASE_ROOT / "seed-only" / item["name"] / "corpus"
                coverage = corpus_root / "coverage"
                if coverage.exists():
                    raise FileExistsError(f"拒绝复用语料目录：{coverage}")
                coverage.mkdir(parents=True)
                sequence = to_echidna_sequence(
                    candidate, replay["resolved_transactions"], candidate_context,
                    contract_address=PROJECTS["Wallet02Refund"]["deployment"]["contract_address"])
                seed_path = coverage / "candidate.txt"
                seed_path.write_text(json.dumps(sequence, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
                echidna = run_echidna(
                    "Wallet02Refund", corpus_root,
                    property_name="WalletHarness.echidna_wallet_accounting_respected()",
                    test_limit=1, timeout=60, seed=20261125, seq_len=8,
                    stop_on_fail=False, disable_slither=True)
                item_result["echidna_seed_only"] = {**echidna,
                    "corpus_seed_path": str(seed_path.relative_to(ROOT)),
                    "purpose": "single Echidna corpus replay/test-limit-1 probe; not fuzz comparison"}
            candidate_results.append(item_result)

    result = {
        "status": "completed",
        "comparison_scope": "P0 is the Phase30A plan under two historical Agent B parameterizations; P1 is the single Phase30B plan. No manual oracle path was loaded.",
        "uniform_initial_balance_wei": "100000000000000000000",
        "property_id": "8e75f62866f6d582a033",
        "max_sequence_length": 8,
        "candidates": candidate_results,
        "fuzz_gate": {
            "passed": any(item["target_reached"] and item["echidna_seed_only"] and
                           item["echidna_seed_only"].get("property_failures")
                           for item in candidate_results if item["name"].startswith("P1")),
            "groups_run": [],
            "reason": "G0/G1/G2 are conditional on the new planner reaching the frozen target in Anvil and the same candidate being falsified by Echidna.",
        },
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "candidates": [{"name": item["name"],
                                      "anvil": item["anvil_replay"].get("replay_status"),
                                      "target_reached": item["target_reached"],
                                      "echidna_exit": (item["echidna_seed_only"] or {}).get("exit_code"),
                                      "property_failures": (item["echidna_seed_only"] or {}).get("property_failures"),
                                      "loaded": (item["echidna_seed_only"] or {}).get("loaded_seed_count"),
                                      "replayed": (item["echidna_seed_only"] or {}).get("replayed_sequence_count"),
                                      "mutation_evidence": (item["echidna_seed_only"] or {}).get("mutation_evidence")}
                                     for item in candidate_results],
                      "fuzz_gate": result["fuzz_gate"],
                      "result": str(OUTPUT.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
