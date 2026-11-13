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
from pathlib import Path
from typing import Any

from web3 import HTTPProvider, Web3

from AgentB import SENDERS, to_echidna_sequence
from 属性种子上下文 import PROJECTS, ROOT, read_json


DEPLOYER = "0x0000000000000000000000000000000000030000"
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
             "--chain-id", "31337", "--auto-impersonate", "--disable-code-size-limit", "--silent"],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        provider = HTTPProvider(f"http://127.0.0.1:{self.port}", request_kwargs={"timeout": 3})
        self.web3 = Web3(provider)
        end = time.monotonic() + 20
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise RuntimeError(f"Anvil 异常退出，exit={self.process.returncode}")
            try:
                if self.web3.is_connected():
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
            "tracked_contract_types": sorted(discovered)}


def _deploy(session: AnvilSession, project: str):
    web3 = session.web3
    artifact = read_json(PROJECTS[project]["artifact"])
    web3.provider.make_request("anvil_setBalance", [DEPLOYER, hex(10**23)])
    factory = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    tx_hash = factory.constructor().transact({"from": _checksum(DEPLOYER),
                                               "gas": 30_000_000,
                                               "gasPrice": max(web3.eth.gas_price, 1_000_000_000)})
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1 or not receipt.contractAddress:
        raise RuntimeError("Harness 部署失败")
    return web3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"]), receipt


def replay_seed(project: str, candidate: dict[str, Any], transactions: list[dict[str, Any]],
                *, session: AnvilSession | None = None) -> dict[str, Any]:
    """每个种子从同一个构造后 snapshot 重放；返回逐笔 receipt 和属性值。"""
    owned = session is None
    session = session or AnvilSession().__enter__()
    try:
        contract, deploy_receipt = _deploy(session, project)
        artifact = read_json(PROJECTS[project]["artifact"])
        contract_abis = artifact.get("contract_abis", {})
        baseline_snapshot = session.rpc("evm_snapshot", [])
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
        records = []
        valid = True
        violation = None
        last_state = initial_state
        for index, tx in enumerate(transactions, start=1):
            sender = _checksum(tx["sender"])
            session.rpc("anvil_setBalance", [sender, hex(10**22)])
            signature = tx["function"]
            fn = contract.get_function_by_signature(signature)(*tx["arguments"])
            call_data = fn._encode_transaction_data()
            rpc_tx = {"from": sender, "to": contract.address, "data": call_data,
                      "value": hex(int(tx["value_wei"])), "gas": hex(MAX_TX_GAS),
                      "gasPrice": hex(max(session.web3.eth.gas_price, 1_000_000_000))}
            try:
                tx_hash = session.web3.eth.send_transaction(rpc_tx)
                receipt = session.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            except Exception as exc:
                valid = False
                records.append({"index": index, "function": signature, "sender": sender,
                                "status": "rpc_error", "error": str(exc)[:500]})
                break
            state_after = _state_view_snapshot(session.web3, contract, contract_abis)
            prop_result: bool | None = None
            prop_error = None
            property_values: dict[str, bool | None] = {}
            property_errors: dict[str, str] = {}
            if receipt.status == 1:
                for tested_property in property_signatures:
                    try:
                        prop_fn = contract.get_function_by_signature(tested_property)()
                        property_values[tested_property] = bool(prop_fn.call({"from": sender}))
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
        session.rpc("evm_revert", [baseline_snapshot])
        return {"project": project, "contract_address": contract.address,
                "deployment_status": "success" if deploy_receipt.status == 1 else "failed",
                "candidate_id": candidate["candidate_id"],
                "replay_status": "executable" if valid else "replay_failed",
                "target_property_violation": violation,
                "transactions": records}
    finally:
        if owned:
            session.__exit__(None, None, None)


def write_corpus(project: str, candidate: dict[str, Any], transactions: list[dict[str, Any]],
                 context: dict[str, Any], corpus_root: Path) -> Path:
    sequence = to_echidna_sequence(candidate, transactions, context)
    path = corpus_root / "coverage" / (candidate["candidate_id"].replace("/", "_") + ".txt")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sequence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Re-open and validate the generated shape before Echidna is invoked.
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or len(parsed) != len(transactions):
        raise ValueError("生成的 Echidna 语料长度校验失败")
    return path


def run_echidna(project: str, corpus_root: Path, *, property_name: str,
                test_limit: int = 80, timeout: int = 45,
                seed: int = 20261113) -> dict[str, Any]:
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
    compiler_config = corpus_root.parent / f"{project}-crytic-compile.json"
    compiler_config.write_text(json.dumps({
        "solc": "/home/skk/miniconda3/envs/contract-fuzz/bin/solc",
        "solc_remaps": spec["remaps"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    echidna_config = corpus_root.parent / f"{project}-{property_name}-echidna.yaml"
    echidna_config.write_text(
        f'prefix: "{property_name}"\nworkers: 1\ncorpusDir: "{corpus_root}"\n',
        encoding="utf-8")
    command = [ECHIDNA_BIN, spec["target"], "--contract", spec["contract"],
               "--crytic-args", f"--config-file {compiler_config.relative_to(ROOT)}",
               "--config", str(echidna_config.relative_to(ROOT)),
               "--test-limit", str(test_limit), "--seq-len", "8",
               "--seed", str(seed), "--workers", "1", "--disable-slither", "--format", "text"]
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout + 90,
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

