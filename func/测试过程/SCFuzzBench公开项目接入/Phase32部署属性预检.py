#!/usr/bin/env python3
"""对 Phase32 冻结候选做 Anvil 部署与目标属性初始状态检查。"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek")]

from 属性种子上下文 import PROJECTS, find_property, load_project_context  # noqa: E402
from 种子验证 import AnvilSession, _call_assertion_target, _deploy  # noqa: E402


RESULTS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120"
TASKS = {
    "Phase32PigfoxRWADemo": ["supply_equals_sum_of_balances",
                              "redemption_ledger_consistent"],
    "Phase32ReconVaultExample": ["property_share_solvency",
                                 "property_total_supply_solvency"],
}


def main() -> None:
    rows = []
    for project, names in TASKS.items():
        ids = [find_property(project, name) for name in names]
        context = load_project_context(project, ids)
        with AnvilSession(project=project) as session:
            snapshot = session.rpc("evm_snapshot", [])
            contract, receipt = _deploy(session, project)
            artifact = json.loads(Path(PROJECTS[project]["artifact"]).read_text(encoding="utf-8"))
            for prop in context["properties"]:
                descriptor = {
                    "project": project,
                    "property_id": prop["property_id"],
                    "property": prop["property"],
                    "property_kind": prop["property_kind"],
                    "property_test_mode": ("assertion" if prop["property_kind"] == "assertion_test"
                                            else "property"),
                    "property_source": prop["property_source"],
                    "assertion_sites": prop["assertion_sites"],
                    "read_states": prop["read_states"],
                    "candidate_actions": [item["abi_signature"] for item in
                                          prop["candidate_actions"] if item["seed_compatible"]],
                    "deployment_status": "success" if receipt.status == 1 else "failed",
                    "contract_address": contract.address.lower(),
                    "expected_contract_address": PROJECTS[project]["deployment"]["contract_address"],
                    "deployment_block": receipt.blockNumber,
                    "deployment_timestamp": int(session.web3.eth.get_block(receipt.blockNumber)["timestamp"]),
                }
                if prop["property_kind"] == "assertion_test" and prop.get("assertion_trigger"):
                    descriptor["assertion_call_initial"] = _call_assertion_target(
                        session, contract, prop["assertion_trigger"]["abi_signature"])
                    descriptor["target_abi"] = next(item for item in artifact["abi"]
                                                     if item.get("type") == "function" and
                                                     item["name"] == prop["assertion_trigger"]["abi_signature"].split("(")[0])
                else:
                    function = contract.get_function_by_signature(prop["property_abi"])()
                    descriptor["property_call_initial"] = bool(
                        function.call({"from": PROJECTS[project]["property"]["sender"]}))
                rows.append(descriptor)
            session.rpc("evm_revert", [snapshot])
    destination = RESULTS / "部署与属性初始状态.json"
    destination.write_text(json.dumps({"schema_version": 1, "tasks": rows},
                                      ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tasks": len(rows), "status": "completed",
                      "result": str(destination.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
