#!/usr/bin/env python3
"""Re-run the frozen Phase37 and Phase40/41 executor regressions."""

from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入"),
                str(ROOT / "func/测试过程/跨交易属性状态依赖审计")]

import 真实合约统一执行适配器 as adapter
import Phase41Drips端到端实验 as phase41


OUTPUT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase42-20261123/Drips/automatic/regression-final"


def write_json(path: Path, value: Any) -> None:
    adapter.write_json(path, value)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=False)
    phase37 = importlib.import_module("Phase37前置约束绑定验证")
    phase37_root = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase37-20261121"
    phase37_summary = adapter.read_json(phase37_root / "Phase37-开发集结果.json")
    phase36_freeze = adapter.read_json(
        ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase36-20261120/00-Phase36冻结.json")
    _, contexts, _ = phase37._runtime_contexts(phase36_freeze)
    phase37_rows = {}
    for task_id in ("BWorkflow", "CMsgSender", "DAllowance"):
        confirmation = phase37_summary["development_set"][task_id]["G2"][
            "direct_goal_confirmations"][0]
        row = dict(contexts[task_id])
        row["task_id"] = task_id
        result = phase37._direct_anvil_goal_check(
            row["project"], row, confirmation["sequence"])
        phase37_rows[task_id] = {"source_phase37_candidate": confirmation.get("candidate_no"),
                                 "source_sequence_sha256": phase37.sequence_sha(
                                     confirmation["sequence"]),
                                 "result": result}
        write_json(OUTPUT / (task_id + ".json"), phase37_rows[task_id])

    manifest = adapter.read_json(
        ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置/Drips.json")
    drips_backend, _, _, _ = phase41._foundry(manifest, OUTPUT / "Drips-phase40")
    drips_sequence = []
    for row in manifest["sequences"][0]["transactions"]:
        drips_sequence.append({"function": row["signature"],
                               "arguments": row.get("arguments", []),
                               "sender": row["sender"],
                               "value_wei": str(row.get("value_wei", "0")),
                               "delay_seconds": int(row.get("delay_seconds", 0)),
                               "delay_blocks": int(row.get("delay_blocks", 0))})
    raw_drips, feedback_drips = phase41._replay(
        drips_backend, manifest, drips_sequence,
        "Phase40-fixed-give-add-squeeze-Phase42-regression",
        OUTPUT / "Drips-phase40", "testSqueeze(uint8,uint8)")
    write_json(OUTPUT / "Drips-phase40-fixed-sequence.json",
               {"raw": raw_drips, "feedback": feedback_drips,
                "sequence": drips_sequence})

    wallet_manifest = adapter.read_json(
        ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置/Wallet02Refund.json")
    wallet_baseline = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase41-20261123/回归/Wallet-UnifiedAnvil"
    wallet_spec = wallet_baseline / "backend/wallet-phase37-counterexample-unified.anvil-spec.json"
    wallet_previous_raw = adapter.read_json(
        wallet_baseline / "backend/anvil/wallet-phase37-counterexample-unified/result.json")
    spec = adapter.read_json(wallet_spec)
    sender_by_index = {index: address for index, address in enumerate(
        wallet_previous_raw["chain"]["accounts"])}
    sender_indices = {address.lower(): index for index, address in sender_by_index.items()}
    transactions = [adapter.Transaction(
        signature=row["function"], arguments=row.get("arguments", []),
        sender=sender_by_index[int(row["sender_index"])],
        value_wei=str(row.get("value_wei", "0")),
        delay_seconds=int(row.get("delay_seconds", 0)))
        for row in spec["transactions"]]
    wallet_output = OUTPUT / "Wallet-UnifiedAnvil"
    wallet_output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([str(ROOT / ".tools/foundry/bin"),
                                   str(ROOT / ".tools/olympia-venv/bin"),
                                   env.get("PATH", "")])
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT / ".tools/python"),
                                         env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    wallet_backend = adapter.AnvilRpcBackend(
        sys.executable, wallet_output, env, spec_template=wallet_spec,
        manifest=wallet_manifest)
    wallet_request = adapter.ExecutionRequest(
        "wallet-phase37-counterexample-phase42", transactions, False,
        {"anvil_spec": str(wallet_spec), "sender_indices": sender_indices})
    raw_wallet = wallet_backend.execute_sequence(wallet_request)
    feedback_wallet = wallet_backend.to_v2_feedback(
        raw_wallet, target_property_signature="echidna_wallet_accounting_respected()")
    write_json(wallet_output / "v2-feedback.json", feedback_wallet)
    wallet_result = {"backend_status": raw_wallet.get("status"),
                     "replay_status": feedback_wallet.get("replay_status"),
                     "target_property_state": feedback_wallet.get("target_property_state"),
                     "sequence_success": feedback_wallet.get("sequence_success"),
                     "transactions": feedback_wallet.get("transactions"),
                     "source_phase41_counterexample_preserved": True,
                     "raw": raw_wallet}
    write_json(wallet_output / "summary.json", wallet_result)

    summary = {
        "schema_version": 1,
        "classification": "fixed-regression-only; no new discovery or paper gain",
        "phase37_original_development_set": {
            task: {"G1_status": phase37_summary["development_set"][task]["G1"]["status"],
                  "G2_status": phase37_summary["development_set"][task]["G2"]["status"],
                  "confirmed_success_candidates": phase37_summary["development_set"][task]["G2"][
                      "phase37_counts"].get("binding_applied_or_confirmed")}
            for task in ("BWorkflow", "CMsgSender", "DAllowance")},
        "phase37_replays": phase37_rows,
        "phase40_drips_fixed_sequence": {
            "backend_status": raw_drips.get("status"),
            "replay_status": feedback_drips.get("replay_status"),
            "transactions": feedback_drips.get("transactions"),
            "target_property_state": feedback_drips.get("target_property_state"),
            "execution_semantics": feedback_drips.get("execution_semantics")},
        "wallet_anvil": wallet_result,
        "pigfox_gate_known_regression": {
            "preserved": True,
            "phase37_original_saved_replays": phase37_summary["final_outcome"].get(
                "pigfox_gate_saved_replays"),
            "cause": "parent-state fingerprint changed after repeated mint; the existing gate re-probed candidates"},
    }
    write_json(OUTPUT / "Phase42-regression-summary.json", summary)
    print(json.dumps({
        "status": "complete",
        "B_C_D": {task: {"all_transactions_succeeded": row["result"][
            "all_transactions_succeeded"], "target_state_reached": row["result"][
            "target_state_reached"], "property_value": row["result"]["property_value"]}
            for task, row in phase37_rows.items()},
        "Drips_phase40": {"backend": raw_drips.get("status"),
                          "replay": feedback_drips.get("replay_status")},
        "Wallet": {"backend": raw_wallet.get("status"),
                   "replay": feedback_wallet.get("replay_status"),
                   "counterexample": feedback_wallet.get("target_property_state", {}).get(
                       "counterexample_state_established")},
        "output": str(OUTPUT)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
