#!/usr/bin/env python3
"""ABI 校验、Anvil 原生逐交易回放、Echidna 语料落盘及加载/变异验证。"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import time
import argparse
import uuid
from pathlib import Path
from typing import Any

from web3 import HTTPProvider, Web3

from AgentB import HARNESS_ADDRESS, PROPERTY_SENDER, SENDERS, to_echidna_sequence
from 属性种子上下文 import PROJECTS, ROOT, read_json


DEPLOYER = "0x0000000000000000000000000000000000030000"
CHAIN_ID = 1
INITIAL_TIMESTAMP = 1524785992
INITIAL_BLOCK_NUMBER = 4370000
INITIAL_BALANCE = 0xffffffff
ANVIL_BIN = ROOT / ".tools/foundry/bin/anvil"
ECHIDNA_BIN = shutil.which("echidna") or "/usr/local/bin/echidna"
MAX_TX_GAS = 12_500_000


def echidna_corpus_evidence(output: str) -> dict[str, Any]:
    """从 Echidna 日志区分外部 coverage 语料、实际回放与后续变异。"""
    loaded_counts = []
    for line in output.splitlines():
        match = re.search(r"Loaded\s+(\d+)\s+transaction sequences from\s+(.+)", line)
        if match and Path(match.group(2).strip()).name == "coverage":
            loaded_counts.append(int(match.group(1)))
    replayed = [line.strip() for line in output.splitlines()
                if "Sequence replayed from corpus file" in line]
    count = max(loaded_counts, default=0)
    mutation = "fuzzing:" in output.lower() and "unique instructions" in output.lower()
    return {"loaded_seed_count": count,
            "loaded_seed_evidence": count > 0,
            "replayed_sequence_count": len(replayed),
            "replay_evidence": bool(replayed),
            "replayed_lines": replayed,
            "mutation_evidence": mutation}


class AnvilSession:
    def __init__(self, port: int | None = None):
        if not ANVIL_BIN.is_file():
            raise FileNotFoundError(f"找不到项目内 Anvil：{ANVIL_BIN}")
        self.port = port or self._free_port()
        self.process: subprocess.Popen | None = None
        self.web3: Web3 | None = None

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def __enter__(self):
        self.process = subprocess.Popen(
            [str(ANVIL_BIN), "--host", "127.0.0.1", "--port", str(self.port),
             "--chain-id", str(CHAIN_ID), "--number", str(INITIAL_BLOCK_NUMBER - 1),
             "--timestamp", str(INITIAL_TIMESTAMP - 1), "--block-base-fee-per-gas", "0",
             "--gas-price", "0", "--gas-limit", "100000000", "--hardfork", "shanghai",
             "--auto-impersonate",
             "--disable-code-size-limit", "--silent"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        provider = HTTPProvider(f"http://127.0.0.1:{self.port}", request_kwargs={"timeout": 3})
        self.web3 = Web3(provider)
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError(f"Anvil 异常退出，exit={self.process.returncode}")
            try:
                if self.web3.is_connected():
                    for address in [DEPLOYER, *SENDERS]:
                        self.rpc("anvil_setBalance", [address, hex(INITIAL_BALANCE)])
                    return self
            except Exception:
                pass
            time.sleep(0.15)
        raise TimeoutError("Anvil 在 20 秒内未启动")

    def __exit__(self, exc_type, exc, tb):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def rpc(self, method: str, params: list[Any]):
        response = self.web3.provider.make_request(method, params)
        if "error" in response:
            raise RuntimeError(f"{method}: {response['error']}")
        return response.get("result")


def _checksum(address: str) -> str:
    return Web3.to_checksum_address(address)


def _to_rpc_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_to_rpc_value(item) for item in value]
    if isinstance(value, bytes):
        return "0x" + value.hex()
    if hasattr(value, "hex") and not isinstance(value, (str, int)):
        try:
            return "0x" + value.hex()
        except Exception:
            pass
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    return str(value)


def _state_view_snapshot(web3: Web3, contract, contract_abis: dict[str, Any]) -> dict[str, Any]:
    """跟随 Harness 内部合约地址 getter，观测最多三层公开 view 状态。"""
    observations = {}
    visited: set[tuple[str, str]] = set()
    discovered: set[str] = set()

    def observe(current, contract_name: str, depth: int) -> None:
        key = (current.address.lower(), contract_name)
        if key in visited or depth > 3 or len(visited) >= 32:
            return
        visited.add(key)
        discovered.add(contract_name)
        for entry in current.abi:
            if (entry.get("type") != "function" or entry.get("inputs") or
                    entry.get("stateMutability") != "view"):
                continue
            signature = entry["name"] + "()"
            observation_key = f"{current.address.lower()}:{signature}"
            try:
                value = current.get_function_by_signature(signature)().call({"from": DEPLOYER})
                observations[observation_key] = _to_rpc_value(value)
            except Exception as exc:
                observations[observation_key] = {"error": type(exc).__name__}
                continue
            outputs = entry.get("outputs", [])
            values = value if isinstance(value, (list, tuple)) else [value]
            for output, item in zip(outputs, values):
                internal_type = output.get("internalType", "")
                if output.get("type") != "address" or not internal_type.startswith("contract "):
                    continue
                nested_name = internal_type.split()[-1]
                nested_abi = contract_abis.get(nested_name)
                if (nested_abi and isinstance(item, str) and item.lower() != "0x" + "0" * 40):
                    try:
                        nested = web3.eth.contract(address=Web3.to_checksum_address(item), abi=nested_abi)
                        observe(nested, nested_name, depth + 1)
                    except Exception:
                        continue

    root_name = "Harness"
    observe(contract, root_name, 0)
    encoded = json.dumps(observations, sort_keys=True, separators=(",", ":"))
    return {"fingerprint": Web3.keccak(text=encoded).hex(),
            "observed_view_count": len(observations),
            "tracked_contract_count": len(visited),
            "tracked_contract_types": sorted(discovered),
            "view_values": observations}


def _observed_effect_status(context: dict[str, Any], property_id: str,
                            signature: str, before: dict[str, Any],
                            after: dict[str, Any]) -> dict[str, Any]:
    """用 Slither 写状态证据和可观测 getter 判断一次调用是否产生可见效果。"""
    prop = next((item for item in context.get("properties", [])
                 if item.get("property_id") == property_id), {})
    action = next((item for item in prop.get("candidate_actions", [])
                   if item.get("abi_signature") == signature), {})
    expected_states = list(dict.fromkeys(
        evidence.get("state") for evidence in action.get("effect_evidence", [])
        if isinstance(evidence, dict) and isinstance(evidence.get("state"), str)
    ))
    if not expected_states:
        return {"status": "unknown", "expected_states": [],
                "observed_states": [], "changed_states": []}

    before_values = before.get("view_values", {})
    after_values = after.get("view_values", {})
    observed_states: list[str] = []
    changed_states: list[str] = []
    missing_states: list[str] = []
    for state in expected_states:
        getter = state.rsplit(".", 1)[-1] + "()"
        keys = [key for key in before_values.keys() & after_values.keys()
                if key.endswith(":" + getter)]
        if not keys:
            missing_states.append(state)
            continue
        observed_states.append(state)
        if any(before_values[key] != after_values[key] for key in keys):
            changed_states.append(state)

    if changed_states:
        status = "changed"
    elif missing_states:
        status = "unknown"
    else:
        status = "not_observed"
    return {"status": status, "expected_states": expected_states,
            "observed_states": observed_states, "changed_states": changed_states,
            "missing_states": missing_states}


def _deploy(session: AnvilSession, project: str):
    web3 = session.web3
    artifact = read_json(PROJECTS[project]["artifact"])
    factory = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    session.rpc("evm_setNextBlockTimestamp", [INITIAL_TIMESTAMP])
    tx_hash = factory.constructor().transact({"from": _checksum(DEPLOYER),
                                               "gas": 100_000_000,
                                               "gasPrice": 0})
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1 or not receipt.contractAddress:
        raise RuntimeError("Harness 部署失败")
    block = web3.eth.get_block(receipt.blockNumber)
    environment = {"chain_id": web3.eth.chain_id,
                   "deployment_block_number": int(block["number"]),
                   "deployment_timestamp": int(block["timestamp"]),
                   "contract_address": receipt.contractAddress.lower(),
                   "base_fee_per_gas": int(block.get("baseFeePerGas") or 0)}
    expected = {"chain_id": CHAIN_ID,
                "deployment_block_number": INITIAL_BLOCK_NUMBER,
                "deployment_timestamp": INITIAL_TIMESTAMP,
                "contract_address": HARNESS_ADDRESS.lower(),
                "base_fee_per_gas": 0}
    if environment != expected:
        raise RuntimeError(f"Anvil/Echidna 环境未对齐：actual={environment}, expected={expected}")
    return web3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"]), receipt


def replay_seed(project: str, candidate: dict[str, Any], transactions: list[dict[str, Any]],
                *, session: AnvilSession | None = None) -> dict[str, Any]:
    """每个种子从相同创世状态重放；属性调用使用 Echidna 的 psender。"""
    owned = session is None
    session = session or AnvilSession().__enter__()
    deployment_snapshot = None
    try:
        deployment_snapshot = session.rpc("evm_snapshot", [])
        contract, deploy_receipt = _deploy(session, project)
        deployment_block = session.web3.eth.get_block(deploy_receipt.blockNumber)
        artifact = read_json(PROJECTS[project]["artifact"])
        contract_abis = artifact.get("contract_abis", {})
        initial_state = _state_view_snapshot(session.web3, contract, contract_abis)
        property_name = candidate.get("property", "")
        if not property_name:
            property_context = next(p for p in candidate["context"]["properties"]
                                    if p["property_id"] == candidate["property_id"])
            property_name = property_context["property_abi"]
        property_signature = property_name.rsplit(".", 1)[-1]
        property_signatures = [entry["name"] + "()" for entry in contract.abi
                               if entry.get("type") == "function" and not entry.get("inputs")
                               and entry["name"].startswith("echidna_")
                               and any(output.get("type") == "bool" for output in entry.get("outputs", []))]
        initial_property_values: dict[str, bool | None] = {}
        initial_property_errors: dict[str, str] = {}
        for tested_property in property_signatures:
            try:
                prop_fn = contract.get_function_by_signature(tested_property)()
                initial_property_values[tested_property] = bool(
                    prop_fn.call({"from": _checksum(PROPERTY_SENDER)}))
            except Exception as exc:
                initial_property_values[tested_property] = None
                initial_property_errors[tested_property] = f"{type(exc).__name__}: {str(exc)[:200]}"
        records = []
        valid = bool(transactions)
        violation = None
        initial_violations = sorted(name for name, value in initial_property_values.items()
                                    if value is False)
        if initial_property_values.get(property_signature) is False:
            violation = {"transaction_index": 0, "property": property_signature,
                         "initial_state": True}
        last_state = initial_state
        for index, tx in enumerate(transactions, start=1):
            sender = _checksum(tx["sender"])
            delay_seconds = int(tx.get("delay_seconds", 0))
            delay_blocks = int(tx.get("delay_blocks", 0))
            for _ in range(delay_blocks):
                latest_timestamp = int(session.web3.eth.get_block("latest")["timestamp"])
                session.rpc("evm_setNextBlockTimestamp", [latest_timestamp + 1])
                session.rpc("evm_mine", [])
            latest_timestamp = int(session.web3.eth.get_block("latest")["timestamp"])
            session.rpc("evm_setNextBlockTimestamp",
                        [latest_timestamp + max(1, delay_seconds)])
            signature = tx["function"]
            fn = contract.get_function_by_signature(signature)(*tx["arguments"])
            call_data = fn._encode_transaction_data()
            rpc_tx = {"from": sender, "to": contract.address, "data": call_data,
                      "value": hex(int(tx["value_wei"])), "gas": hex(MAX_TX_GAS),
                      "gasPrice": "0x0"}
            try:
                tx_hash = session.web3.eth.send_transaction(rpc_tx)
                receipt = session.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            except Exception as exc:
                valid = False
                records.append({"index": index, "function": signature, "sender": sender,
                                "status": "rpc_error", "error": str(exc)[:500]})
                break
            state_after = _state_view_snapshot(session.web3, contract, contract_abis)
            effect = _observed_effect_status(
                candidate.get("context", {}), candidate.get("property_id", ""),
                signature, last_state, state_after)
            prop_result: bool | None = None
            prop_error = None
            property_values: dict[str, bool | None] = {}
            property_errors: dict[str, str] = {}
            if receipt.status == 1:
                for tested_property in property_signatures:
                    try:
                        prop_fn = contract.get_function_by_signature(tested_property)()
                        property_values[tested_property] = bool(
                            prop_fn.call({"from": _checksum(PROPERTY_SENDER)}))
                    except Exception as exc:
                        property_values[tested_property] = None
                        property_errors[tested_property] = f"{type(exc).__name__}: {str(exc)[:200]}"
                prop_result = property_values.get(property_signature)
                prop_error = property_errors.get(property_signature)
            if receipt.status != 1:
                valid = False
                try:
                    session.web3.eth.call(rpc_tx)
                except Exception as exc:
                    prop_error = f"tx_revert: {type(exc).__name__}: {str(exc)[:300]}"
            elif effect["status"] == "not_observed":
                # The target function has Slither-backed writes whose public getter
                # is observed, but none changed. This catches wrappers that swallow
                # an internal revert while returning success to the outer caller.
                valid = False
            if prop_result is False and violation is None:
                violation = {"transaction_index": index, "property": property_signature}
            other_violations = sorted(name for name, value in property_values.items()
                                      if value is False and name != property_signature)
            records.append({
                "index": index, "function": signature, "arguments": tx["arguments"],
                "sender": sender, "value_wei": tx["value_wei"],
                "delay_seconds": tx.get("delay_seconds", 0),
                "delay_blocks": tx.get("delay_blocks", 0),
                "tx_hash": tx_hash.hex(), "block_number": receipt.blockNumber,
                "status": "success" if receipt.status == 1 else "reverted",
                "gas_used": receipt.gasUsed,
                "observed_view_state_changed": last_state["fingerprint"] != state_after["fingerprint"],
                "observed_view_count": state_after["observed_view_count"],
                "tracked_contract_count": state_after["tracked_contract_count"],
                "tracked_contract_types": state_after["tracked_contract_types"],
                "observed_effect_status": effect["status"],
                "expected_effect_states": effect["expected_states"],
                "observed_effect_states": effect["observed_states"],
                "changed_effect_states": effect["changed_states"],
                "unobserved_effect_states": effect.get("missing_states", []),
                "execution_effect_error": ("expected Slither-backed write was not observed"
                                           if effect["status"] == "not_observed" else None),
                "state_fingerprint_before": last_state["fingerprint"],
                "state_fingerprint_after": state_after["fingerprint"],
                "target_property": prop_result,
                "property_error": prop_error,
                "all_property_values": property_values,
                "all_property_errors": property_errors,
                "other_property_violations_during_prevalidation": other_violations,
            })
            last_state = state_after
            if receipt.status != 1:
                break
        session.rpc("evm_revert", [deployment_snapshot])
        deployment_snapshot = None
        return {"project": project, "contract_address": contract.address,
                "deployment_status": "success" if deploy_receipt.status == 1 else "failed",
                "candidate_id": candidate["candidate_id"],
                "replay_status": "executable" if valid else "replay_failed",
                "target_property_violation": violation,
                "initial_property_values": initial_property_values,
                "initial_property_errors": initial_property_errors,
                "initial_property_violations": initial_violations,
                "environment": {"chain_id": CHAIN_ID,
                                "initial_timestamp": INITIAL_TIMESTAMP,
                                "initial_block_number": INITIAL_BLOCK_NUMBER,
                                "deployment_timestamp": int(deployment_block["timestamp"]),
                                "deployment_block_number": int(deployment_block["number"]),
                                "deployer": DEPLOYER.lower(),
                                "property_sender": PROPERTY_SENDER.lower(),
                                "sender_pool": [item.lower() for item in SENDERS],
                                "gas_price_wei": 0,
                "evm_revision": "shanghai",
                                "gas_limit_per_transaction": MAX_TX_GAS,
                                "contract_address": contract.address.lower()},
                "transactions": records}
    finally:
        if deployment_snapshot is not None:
            try:
                session.rpc("evm_revert", [deployment_snapshot])
            except Exception:
                pass
        if owned:
            session.__exit__(None, None, None)


def new_seed_id() -> str:
    return "seed-" + uuid.uuid4().hex


def write_corpus(project: str, candidate: dict[str, Any], transactions: list[dict[str, Any]],
                 context: dict[str, Any], corpus_root: Path, *,
                 replay: dict[str, Any], seed_id: str) -> Path:
    if replay.get("replay_status") != "executable":
        raise ValueError("只有逐笔回放成功的种子可以写入 Echidna 语料")
    if not seed_id or not re.fullmatch(r"seed-[0-9a-f]{32}", seed_id):
        raise ValueError("seed_id 必须是 UUID 格式的全局唯一种子标识")
    global_corpus_roots = [ROOT / "deepseek/结果", ROOT / "seeds",
                           ROOT / ".tools/results", corpus_root.parent]
    scanned_roots: set[Path] = set()
    for root in global_corpus_roots:
        root = root.resolve()
        if root in scanned_roots or not root.is_dir():
            continue
        scanned_roots.add(root)
        collision = next(root.rglob(seed_id + ".txt"), None)
        if collision is not None:
            raise FileExistsError(f"种子 ID 已在工作区语料中使用：{collision}")
    sequence = to_echidna_sequence(candidate, transactions, context,
                                   contract_address=HARNESS_ADDRESS)
    path = corpus_root / "coverage" / (seed_id + ".txt")
    if path.exists():
        raise FileExistsError(f"种子 ID 重复：{seed_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sequence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Re-open and validate the generated shape before Echidna is invoked.
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or len(parsed) != len(transactions):
        raise ValueError("生成的 Echidna 语料长度校验失败")
    return path


def run_echidna(project: str, corpus_root: Path, *, property_name: str,
                test_limit: int = 80, timeout: int = 45,
                seed: int = 20261113,
                campaign_deadline: float | None = None) -> dict[str, Any]:
    if not Path(ECHIDNA_BIN).is_file() and shutil.which(ECHIDNA_BIN) is None:
        raise FileNotFoundError(f"找不到 Echidna 2.3.2：{ECHIDNA_BIN}")
    conf = PROJECTS[project]
    project_data = {"Request": {
        "target": "sol/真实项目/Request/src/contracts/test/EchidnaERC20CommerceEscrowWrapper.sol",
        "contract": "EchidnaERC20CommerceEscrowWrapper",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/"},
        "Immutable": {
        "target": "sol/真实项目/Immutable/test/token/erc721/fuzz/ERC721PsiV2.Echidna.sol",
        "contract": "ERC721PsiV2Echidna",
        "remaps": ("openzeppelin-contracts-4/=sol/真实项目/依赖/OpenZeppelin4/contracts/ "
                   "openzeppelin-contracts-5/=sol/真实项目/依赖/OpenZeppelin561/contracts/")},
        "Hokusai": {
        "target": "sol/真实项目/Hokusai/contracts/echidna/EchidnaHokusaiToken.sol",
        "contract": "EchidnaHokusaiToken",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/"}}
    spec = project_data[project]
    compiler_config = corpus_root.parent / f"{project}-{corpus_root.name}-crytic-compile.json"
    compiler_config.write_text(json.dumps({
        "solc": "/home/skk/miniconda3/envs/contract-fuzz/bin/solc",
        "solc_remaps": spec["remaps"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    echidna_config = corpus_root.parent / f"{project}-{corpus_root.name}-echidna.yaml"
    echidna_config.write_text("\n".join([
        f'prefix: "{property_name}"', "workers: 1",
        f'corpusDir: "{corpus_root}"',
        f'contractAddr: "{HARNESS_ADDRESS.lower()}"',
        f'deployer: "{DEPLOYER.lower()}"',
        f'psender: "{PROPERTY_SENDER.lower()}"',
        "sender: [" + ", ".join(f'"{item.lower()}"' for item in SENDERS) + "]",
        f"balanceAddr: {INITIAL_BALANCE}", "balanceContract: 0",
        f"testMaxGas: {MAX_TX_GAS}", f"propMaxGas: {MAX_TX_GAS}",
        "maxGasprice: 0", "maxTimeDelay: 86400", "maxBlockDelay: 86400",
        "coverage: true", "stopOnFail: false", "",]), encoding="utf-8")
    command = [ECHIDNA_BIN, spec["target"], "--contract", spec["contract"],
               "--crytic-args", f"--config-file {compiler_config.relative_to(ROOT)}",
               "--config", str(echidna_config.relative_to(ROOT)),
               "--test-limit", str(test_limit), "--seq-len", "8",
               "--seed", str(seed), "--workers", "1", "--disable-slither", "--format", "text",
               "--deployer", DEPLOYER, "--contract-addr", HARNESS_ADDRESS,
               *sum((["--sender", item] for item in SENDERS), [])]
    corpus_root.mkdir(parents=True, exist_ok=True)
    run_marker = corpus_root / ".echidna-run-started"
    if run_marker.exists():
        raise RuntimeError(f"语料目录已经执行过 Echidna，拒绝复用：{corpus_root}")
    run_marker.write_text(json.dumps({"property_name": property_name,
                                     "seed": seed, "started_at": time.time()},
                                    ensure_ascii=False), encoding="utf-8")
    started = time.monotonic()
    remaining = None if campaign_deadline is None else max(0, int(campaign_deadline - time.monotonic()))
    if remaining == 0:
        raise TimeoutError("本条件 Echidna 墙钟预算已耗尽")
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            timeout=min(timeout, remaining) if remaining is not None else timeout,
            env={**os.environ, "SOLC_VERSION": "0.8.20",
                 "PATH": "/home/skk/miniconda3/envs/contract-fuzz/bin:" + os.environ.get("PATH", "")})
    elapsed = round(time.monotonic() - started, 3)
    output = result.stdout[-18000:]
    result_prefix = property_name if property_name.endswith("_") else property_name + ":"
    property_results = [line.strip() for line in output.splitlines()
                        if line.strip().startswith(result_prefix)]
    property_failures = [line for line in property_results if ": failed" in line.lower()]
    return {"project": project, "property_name": property_name,
            "command": command, "exit_code": result.returncode,
            "elapsed_seconds": elapsed, **echidna_corpus_evidence(output),
            "target_property_results": property_results,
            "property_failures": property_failures,
            "initial_state_failures": [line for line in property_failures
                                        if "no transactions made" in line.lower()],
            "output": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=list(PROJECTS))
    parser.add_argument("corpus_root", type=Path)
    parser.add_argument("--property", required=True,
                        help="要单独评价的 echidna_* 属性函数名")
    parser.add_argument("--test-limit", type=int, default=80)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--seed", type=int, default=20261113)
    args = parser.parse_args()
    corpus_root = args.corpus_root if args.corpus_root.is_absolute() else ROOT / args.corpus_root
    result = run_echidna(args.project, corpus_root, property_name=args.property,
                         test_limit=args.test_limit,
                         timeout=args.timeout, seed=args.seed)
    output = ROOT / f"deepseek/结果/{args.project}-Echidna语料验证.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in
                      ("project", "property_name", "exit_code", "elapsed_seconds", "loaded_seed_evidence",
                       "replay_evidence", "mutation_evidence", "target_property_results")}, ensure_ascii=False))
    print(f"详情：{output}", flush=True)


if __name__ == "__main__":
    main()

