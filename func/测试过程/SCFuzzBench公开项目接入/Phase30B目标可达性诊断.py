#!/usr/bin/env python3
"""Run the isolated Phase30B manual reachability oracle for Wallet02Refund.

The generated Echidna corpus file is diagnostic-only and is never placed in
the V2 candidate corpus, Agent input, or shared seed directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
RESULTS = (ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund"
           / "Phase30B-20261119")
DIAGNOSTIC = RESULTS / "diagnostic-oracle"
PROJECT = "Wallet02Refund"
PROPERTY_ID = "8e75f62866f6d582a033"
ACCOUNT_COUNT = 5
MAPPING_SLOT = 1  # Wallet.creator is slot 0; Wallet.balances is slot 1.
WEI_PER_ETH = 10**18

sys.path.insert(0, str(ROOT / "deepseek"))
sys.path.insert(0, str(ROOT / "func/功能"))

from eth_abi import encode  # noqa: E402
from web3 import Web3  # noqa: E402

from AgentB import to_echidna_sequence  # noqa: E402
from 属性种子上下文 import PROJECTS, load_project_context, read_json  # noqa: E402
from 种子验证 import ANVIL_BIN, ECHIDNA_BIN, AnvilSession, _deploy  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk_calls(node: dict[str, Any]):
    yield node
    for child in node.get("calls", []) if isinstance(node.get("calls"), list) else []:
        if isinstance(child, dict):
            yield from _walk_calls(child)


def _eth(wei: int) -> str:
    return format(Decimal(wei) / Decimal(WEI_PER_ETH), "f")


def _wallet_mapping_value(web3, wallet_address: str, account_address: str) -> int:
    storage_key = Web3.keccak(encode(
        ["address", "uint256"], [Web3.to_checksum_address(account_address), MAPPING_SLOT]))
    raw = web3.eth.get_storage_at(Web3.to_checksum_address(wallet_address), storage_key)
    return int.from_bytes(raw, "big")


def _snapshot(session, contract, wallet_address: str,
              account_addresses: list[str]) -> dict[str, Any]:
    web3 = session.web3
    ledger = []
    for index, address in enumerate(account_addresses):
        deposits = int(contract.functions.cumulativeDeposits(index).call())
        payout = int(contract.functions.cumulativePayout(index).call())
        wallet_credit = _wallet_mapping_value(web3, wallet_address, address)
        ledger.append({
            "actor": index,
            "proxy_address": address,
            "wallet_internal_credit_wei": str(wallet_credit),
            "wallet_internal_credit_eth": _eth(wallet_credit),
            "cumulative_deposits_wei": str(deposits),
            "cumulative_deposits_eth": _eth(deposits),
            "cumulative_payout_wei": str(payout),
            "cumulative_payout_eth": _eth(payout),
            "accounting_holds": payout <= deposits,
        })
    wallet_balance = int(web3.eth.get_balance(Web3.to_checksum_address(wallet_address)))
    return {
        "wallet_balance_wei": str(wallet_balance),
        "wallet_balance_eth": _eth(wallet_balance),
        "ledger": ledger,
        "property_value": bool(contract.functions.echidna_wallet_accounting_respected().call(
            {"from": Web3.to_checksum_address(session.property_sender)})),
    }


def main() -> int:
    if DIAGNOSTIC.exists():
        raise FileExistsError(f"Refusing to overwrite diagnostic output: {DIAGNOSTIC}")
    DIAGNOSTIC.mkdir(parents=True)
    corpus_dir = DIAGNOSTIC / "echidna-corpus"
    coverage_dir = corpus_dir / "coverage"
    coverage_dir.mkdir(parents=True)

    config = PROJECTS[PROJECT]
    wallet_source = ROOT / "sol/单合约测试/wallet_02_refund_nosub/test/Wallet.sol"
    harness_artifact = read_json(config["artifact"])
    context = load_project_context(PROJECT, [PROPERTY_ID])
    property_context = next(item for item in context["properties"]
                            if item["property_id"] == PROPERTY_ID)

    # This is an intentionally researcher-written oracle sequence. It is not
    # supplied to either Agent and is written only in this diagnostic directory.
    transactions = [
        {"function": "deposit(uint8)", "arguments": [1], "sender": None,
         "value_wei": str(WEI_PER_ETH), "delay_seconds": 0, "delay_blocks": 0,
         "expected_outcome": "state_change"},
        {"function": "deposit(uint8)", "arguments": [0], "sender": None,
         "value_wei": str(WEI_PER_ETH), "delay_seconds": 0, "delay_blocks": 0,
         "expected_outcome": "state_change"},
        {"function": "refund(uint8)", "arguments": [1], "sender": None,
         "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0,
         "expected_outcome": "state_change"},
        {"function": "refund(uint8)", "arguments": [1], "sender": None,
         "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0,
         "expected_outcome": "state_change"},
    ]

    anvil_rows = []
    with AnvilSession(project=PROJECT) as session:
        contract, deployment_receipt = _deploy(session, PROJECT)
        deployment_trace = session.rpc("debug_traceTransaction", [
            deployment_receipt.transactionHash.hex(), {"tracer": "callTracer"}])
        created = [node["to"] for node in _walk_calls(deployment_trace)
                   if str(node.get("type", "")).upper() in {"CREATE", "CREATE2"}
                   and node.get("to")
                   and str(node["to"]).lower() != str(deployment_receipt.contractAddress).lower()]
        if len(created) < ACCOUNT_COUNT + 1:
            raise RuntimeError(
                "Deployment call trace did not expose Wallet and five WalletUser addresses: "
                + json.dumps(deployment_trace, sort_keys=True))
        wallet_address = Web3.to_checksum_address(created[0])
        account_addresses = [Web3.to_checksum_address(item)
                             for item in created[1:ACCOUNT_COUNT + 1]]
        transactions[0]["sender"] = session.senders[1]
        transactions[1]["sender"] = session.senders[0]
        transactions[2]["sender"] = session.senders[1]
        transactions[3]["sender"] = session.senders[1]

        before = _snapshot(session, contract, wallet_address, account_addresses)
        for index, tx in enumerate(transactions, start=1):
            actor = int(tx["arguments"][0]) % ACCOUNT_COUNT
            tx_hash = contract.get_function_by_signature(tx["function"])(
                *tx["arguments"]).transact({
                    "from": Web3.to_checksum_address(tx["sender"]),
                    "value": int(tx["value_wei"]),
                    "gas": session.max_transaction_gas,
                    "gasPrice": 0,
                })
            receipt = session.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            trace = session.rpc("debug_traceTransaction", [
                tx_hash.hex(), {"tracer": "callTracer"}])
            after = _snapshot(session, contract, wallet_address, account_addresses)
            anvil_rows.append({
                "transaction_index": index,
                "function": tx["function"],
                "account_argument": actor,
                "sender": tx["sender"],
                "value_wei": tx["value_wei"],
                "value_eth": _eth(int(tx["value_wei"])),
                "status": "success" if int(receipt.status) == 1 else "reverted",
                "receipt_status": int(receipt.status),
                "transaction_hash": tx_hash.hex(),
                "block_number": int(receipt.blockNumber),
                "gas_used": int(receipt.gasUsed),
                "wallet_balance_before_wei": before["wallet_balance_wei"],
                "wallet_balance_after_wei": after["wallet_balance_wei"],
                "wallet_internal_credit_before_wei": before["ledger"][actor][
                    "wallet_internal_credit_wei"],
                "wallet_internal_credit_after_wei": after["ledger"][actor][
                    "wallet_internal_credit_wei"],
                "account_cumulative_deposits_before_wei": before["ledger"][actor][
                    "cumulative_deposits_wei"],
                "account_cumulative_deposits_after_wei": after["ledger"][actor][
                    "cumulative_deposits_wei"],
                "account_cumulative_payout_before_wei": before["ledger"][actor][
                    "cumulative_payout_wei"],
                "account_cumulative_payout_after_wei": after["ledger"][actor][
                    "cumulative_payout_wei"],
                "property_before": before["property_value"],
                "property_after": after["property_value"],
                "all_actor_ledgers_after": after["ledger"],
                "call_trace": trace,
            })
            if int(receipt.status) != 1:
                break
            before = after

        property_reached = anvil_rows[-1]["property_after"] is False
        anvil_result = {
            "purpose": "manual_diagnostic_oracle_only",
            "input_freeze_revision": 2,
            "contract_address": contract.address,
            "wallet_address": wallet_address,
            "account_proxy_addresses": account_addresses,
            "deployment": {
                "status": int(deployment_receipt.status),
                "contract_address": deployment_receipt.contractAddress,
                "block_number": int(deployment_receipt.blockNumber),
                "gas_used": int(deployment_receipt.gasUsed),
                "created_contract_addresses": created,
                "call_trace": deployment_trace,
            },
            "manual_transactions": transactions,
            "transaction_rows": anvil_rows,
            "target_state_reached": property_reached,
            "final_property_value": anvil_rows[-1]["property_after"],
        }

    candidate = {"property_id": PROPERTY_ID}
    sequence = to_echidna_sequence(
        candidate, transactions, context,
        contract_address=config["deployment"]["contract_address"])
    seed_path = coverage_dir / "manual-diagnostic-oracle.txt"
    seed_path.write_text(json.dumps(sequence, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")

    base_config = (ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund"
                   / "06b-funded-replay/raw/Wallet02Refund-corpus-echidna.yaml")
    crytic_config = (ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund"
                     / "06b-funded-replay/raw/Wallet02Refund-corpus-crytic-compile.json")
    yaml = base_config.read_text(encoding="utf-8")
    yaml = re.sub(r'(?m)^corpusDir:.*$', f'corpusDir: "{corpus_dir}"', yaml)
    echidna_config = DIAGNOSTIC / "Wallet02Refund-diagnostic-echidna.yaml"
    echidna_config.write_text(yaml, encoding="utf-8")

    harness_path = ROOT / "sol/单合约测试/wallet_02_refund_nosub/test/WalletHarness.sol"
    command = [
        str(ECHIDNA_BIN), str(harness_path), "--contract", "WalletHarness",
        "--crytic-args", f"--config-file {crytic_config}",
        "--config", str(echidna_config), "--test-limit", "1", "--seq-len", "8",
        "--shrink-limit", "1", "--seed", "20261125", "--workers", "1",
        "--format", "text", "--deployer", PROJECTS[PROJECT]["deployment"]["deployer"],
        "--contract-addr", PROJECTS[PROJECT]["deployment"]["contract_address"],
    ]
    for sender in PROJECTS[PROJECT]["senders"]:
        command.extend(["--sender", sender])
    command.append("--disable-slither")
    import time
    echidna_started = time.monotonic()
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join([
        str(ROOT / ".tools/olympia-venv/bin"),
        str(ROOT / ".tools/foundry/bin"),
        env.get("PATH", ""),
    ])
    completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True,
                               timeout=90, check=False)
    echidna_elapsed = round(time.monotonic() - echidna_started, 6)
    (DIAGNOSTIC / "echidna.log").write_text(completed.stdout, encoding="utf-8")
    (DIAGNOSTIC / "echidna.stderr.log").write_text(completed.stderr, encoding="utf-8")
    replay_lines = [line.strip() for line in completed.stdout.splitlines()
                    if "Sequence replayed from corpus file" in line]
    property_lines = [line.strip() for line in completed.stdout.splitlines()
                      if "echidna_wallet_accounting_respected" in line.lower()
                      or "reproducer" in line.lower() or "falsif" in line.lower()]
    echidna_result = {
        "purpose": "manual_diagnostic_oracle_only",
        "command": command,
        "exit_code": completed.returncode,
        "timed_out": False,
        "elapsed_seconds": echidna_elapsed,
        "seed_path": str(seed_path.relative_to(ROOT)),
        "seed_sha256": _sha256(seed_path),
        "loaded_sequence_replay_lines": replay_lines,
        "property_or_reproducer_lines": property_lines,
        "test_zero_lines": [line.strip() for line in completed.stdout.splitlines()
                            if re.search(r"tests:\s*0/", line)],
        "stdout_log": str((DIAGNOSTIC / "echidna.log").relative_to(ROOT)),
        "stderr_log": str((DIAGNOSTIC / "echidna.stderr.log").relative_to(ROOT)),
    }

    result = {
        "schema_version": 1,
        "phase": "30B",
        "sample": PROJECT,
        "diagnostic_class": "manual_oracle_not_v2_discovery",
        "diagnostic_isolated_from_agent_inputs": True,
        "diagnostic_isolated_from_v2_candidate_seeds": True,
        "diagnostic_isolated_from_shared_seed_directory": True,
        "property_id": PROPERTY_ID,
        "target_property": property_context["property"],
        "source_sha256": _sha256(wallet_source),
        "harness_sha256": _sha256(harness_path),
        "source_file_sha256": {str(wallet_source.relative_to(ROOT)): _sha256(wallet_source),
                               str(harness_path.relative_to(ROOT)): _sha256(harness_path)},
        "anvil_version": subprocess.run([str(ANVIL_BIN), "--version"], capture_output=True,
                                        text=True, check=False).stdout.strip(),
        "echidna_version": subprocess.run([str(ECHIDNA_BIN), "--version"], capture_output=True,
                                          text=True, check=False).stdout.strip(),
        "anvil": anvil_result,
        "echidna": echidna_result,
        "same_counterexample": {
            "anvil_sequence": transactions,
            "echidna_sequence_sha256": _sha256(seed_path),
            "transaction_count": len(transactions),
        },
    }
    output_path = DIAGNOSTIC / "manual-oracle-result.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({
        "result": str(output_path.relative_to(ROOT)),
        "anvil_target_reached": property_reached,
        "anvil_transaction_count": len(anvil_rows),
        "echidna_exit_code": completed.returncode,
        "echidna_replay_lines": replay_lines,
        "echidna_property_lines": property_lines,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
