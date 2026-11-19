#!/usr/bin/env python3
"""Isolated regression fixture for the generic bounded extension module.

PaperExample is a non-Wallet, source-available sample. The explicit fixture
actions in this file are used only to check the extension API and Anvil replay;
they are not sent to the Wallet planner, agent, Echidna Wallet corpus, or scored
as automatic discovery evidence.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func" / "功能"))
sys.path.insert(0, str(ROOT / "deepseek"))

from 状态反馈序列扩展 import propose_extensions
from 种子验证 import AnvilSession


SOURCE = ROOT / "sol/单合约测试/PaperExample/PaperExample.sol"
SOLC = Path.home() / ".solc-select/artifacts/solc-0.8.20/solc-0.8.20"
OUT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase31-20261119/非Wallet回归"
SENDER = "0x0000000000000000000000000000000000010000"


def _abi_map(abi: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {entry["name"] + "(" + ",".join(row["type"] for row in entry.get("inputs", [])) + ")": entry
            for entry in abi if entry.get("type") == "function"}


def main() -> None:
    started = time.monotonic()
    if not SOLC.is_file():
        raise FileNotFoundError(SOLC)
    compilation = subprocess.run([str(SOLC), "--combined-json", "abi,bin", str(SOURCE)],
                                 check=True, capture_output=True, text=True)
    compiled = json.loads(compilation.stdout)
    contract_data = next(value for key, value in compiled["contracts"].items()
                         if key.endswith(":TEST"))
    abi = (json.loads(contract_data["abi"]) if isinstance(contract_data["abi"], str)
           else contract_data["abi"])
    abi_by_signature = _abi_map(abi)
    target_signature = "set1(int256)"
    base = [{"function": "set0(int256)", "arguments": [23], "sender": SENDER,
             "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0}]
    template = {"function": target_signature, "arguments": [5], "sender": SENDER,
                "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0,
                "sequence_extension_evidence": {"matched_states": ["flag1"],
                                                 "read_states": ["flag0"],
                                                 "write_states": ["flag1"],
                                                 "evidence_origin": "isolated source-review regression fixture"}}
    evidence = {target_signature: {"matched_states": ["flag1"],
                                   "read_states": ["flag0"],
                                   "write_states": ["flag1"]}}
    proposals = propose_extensions(
        base, [template], evidence, abi_by_signature, mode="static",
        target_states={"flag1"}, senders=[SENDER], max_sequence_length=8,
        max_proposals=24)
    candidate = next((row for row in proposals
                      if [tx["function"] for tx in row["sequence"]] ==
                      ["set0(int256)", "set1(int256)"]), None)
    if candidate is None:
        raise AssertionError("generic static extension did not preserve the base prefix")

    trace = []
    with AnvilSession() as session:
        web3 = session.web3
        deployer = session.deployer
        factory = web3.eth.contract(abi=abi, bytecode="0x" + contract_data["bin"])
        tx_hash = factory.constructor().transact(
            {"from": web3.to_checksum_address(deployer), "gas": session.gas_limit,
             "gasPrice": 0})
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        if receipt.status != 1 or not receipt.contractAddress:
            raise RuntimeError("PaperExample deployment failed")
        contract = web3.eth.contract(address=receipt.contractAddress, abi=abi)
        for index, tx in enumerate(candidate["sequence"]):
            before = {name: bool(getattr(contract.functions, name)().call())
                      for name in ("flag0", "flag1")}
            method, _ = tx["function"].split("(", 1)
            sent = getattr(contract.functions, method)(*tx["arguments"]).transact(
                {"from": web3.to_checksum_address(tx["sender"]), "value": int(tx["value_wei"]),
                 "gas": session.max_transaction_gas, "gasPrice": 0})
            tx_receipt = web3.eth.wait_for_transaction_receipt(sent, timeout=30)
            after = {name: bool(getattr(contract.functions, name)().call())
                     for name in ("flag0", "flag1")}
            prop = bool(contract.functions.echidna_flag().call())
            trace.append({"index": index + 1, "function": tx["function"],
                          "arguments": tx["arguments"], "sender": tx["sender"],
                          "receipt_status": int(tx_receipt.status),
                          "state_before": before, "state_after": after,
                          "property_value": prop})
            if tx_receipt.status != 1:
                raise RuntimeError(f"transaction {index + 1} failed")

    result = {"phase": 31, "sample": "PaperExample",
              "fixture_classification": "manual non-Wallet regression fixture; excluded from automatic discovery metrics",
              "source": str(SOURCE.relative_to(ROOT)),
              "compiler": str(SOLC), "contract": "TEST",
              "property": "echidna_flag()", "extension_mode": "static",
              "source_relation": {"set0": {"writes": ["flag0"]},
                                  "set1": {"reads": ["flag0"], "writes": ["flag1"]},
                                  "property": {"reads": ["flag1"]}},
              "base_sequence": base, "proposal_count": len(proposals),
              "proposal": candidate, "transactions": trace,
              "target_counterexample_reached": trace[-1]["property_value"] is False,
              "elapsed_seconds": round(time.monotonic() - started, 6),
              "compiler_stderr": compilation.stderr}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "PaperExample-通用扩展回归.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("sample", "fixture_classification", "proposal_count",
                       "target_counterexample_reached", "elapsed_seconds")},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
