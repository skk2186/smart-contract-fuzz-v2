#!/usr/bin/env python3
"""Phase30B 通用上下文、属性观察器与非 Wallet 历史种子回归。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[6]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek")]

from 属性种子上下文 import load_project_context
from 种子验证 import AnvilSession, echidna_corpus_evidence, replay_seed


def main() -> None:
    output_path = Path(__file__).with_name("01-通用实现回归结果.json")
    if output_path.exists():
        raise FileExistsError(f"拒绝覆盖已有回归结果：{output_path}")

    wallet_context = load_project_context("Wallet02Refund")
    wallet_property = wallet_context["properties"][0]
    wallet_actions = wallet_property["candidate_actions"]
    wallet_action_evidence = []
    for action in wallet_actions:
        chain = action.get("source_call_chain", [])
        wallet_action_evidence.append({
            "function": action.get("abi_signature"),
            "source_excerpt_first_line": (action.get("source_excerpt") or "").splitlines()[:1],
            "call_chain": [{"contract": item["contract"], "function": item["function"],
                            "called_from": item.get("called_from"),
                            "contract_typed_variables": item.get("contract_typed_variables"),
                            "constructor_source": item.get("constructor_source")}
                           for item in chain],
        })
    if not all(item["source_excerpt_first_line"] for item in wallet_action_evidence):
        raise AssertionError("WalletHarness 动作源码仍缺失")
    if not all({"WalletHarness", "WalletUser", "Wallet"}.issubset(
            {row["contract"] for row in action["call_chain"]})
            for action in wallet_action_evidence):
        raise AssertionError("Wallet 声明类型明确的调用链没有到达底层 Wallet")

    prior_path = ROOT / "deepseek/结果/Agent种子语料/Request/58e77e98bfd646b9844f6819b3f00947/逐属性Agent种子流程.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8"))
    prior_property = prior["property_results"][0]
    prior_candidate = next(row for row in prior_property["candidate_results"]
                           if row.get("status") == "executable")
    request_context = load_project_context("Request", [prior_property["property_id"]])
    candidate = {"property_id": prior_property["property_id"],
                 "candidate_id": prior_candidate["candidate_id"],
                 "steps": prior_candidate["plan"],
                 "context": request_context}
    concrete = prior_candidate["concrete_seed"]
    with AnvilSession(project="Request") as session:
        replay = replay_seed("Request", candidate, concrete["transactions"],
                             session=session,
                             dependency_hints=concrete.get("data_dependencies"),
                             runtime_constraints=False)
    if replay.get("replay_status") != "executable":
        raise AssertionError("Request 历史有效种子在 Phase30B 通用实现下未能回放")

    phase30a_log = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/06b-funded-replay/raw/corpus/echidna.log"
    diagnostic_log = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/Phase30B-20261119/diagnostic-oracle/echidna-retry.log"
    parser_checks = {
        "phase30a_tests_0_of_1": echidna_corpus_evidence(
            phase30a_log.read_text(encoding="utf-8")),
        "manual_oracle_property_failure": echidna_corpus_evidence(
            diagnostic_log.read_text(encoding="utf-8")),
    }
    result = {
        "status": "passed",
        "wallet_exact_contract_and_call_chain": wallet_action_evidence,
        "non_wallet_regression": {
            "project": "Request",
            "historical_run": str(prior_path.relative_to(ROOT)),
            "candidate_id": prior_candidate["candidate_id"],
            "replay_status": replay.get("replay_status"),
            "transaction_count": len(replay.get("transactions", [])),
            "target_property_violation": replay.get("target_property_violation"),
            "target_property_state": replay.get("target_property_state"),
            "predicate_getters_initial": replay.get("initial_predicate_getters", []),
            "first_transaction_predicate_getters": (
                replay.get("transactions", [{}])[0].get("predicate_getter_values", [])),
        },
        "corpus_counter_parser_checks": parser_checks,
    }
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": result["status"],
                      "wallet_chain_contracts": sorted({row["contract"]
                          for item in wallet_action_evidence for row in item["call_chain"]}),
                      "request_replay_status": replay.get("replay_status"),
                      "request_transaction_count": len(replay.get("transactions", [])),
                      "request_getter_count": len(replay.get("initial_predicate_getters", [])),
                      "result": str(output_path.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
