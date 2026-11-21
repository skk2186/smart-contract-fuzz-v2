#!/usr/bin/env python3
"""在不改动目标项目的前提下运行 Echidna 与 Anvil 原生 harness 检查。

支持两种独立入口：
  echidna：调用目标项目原生属性/断言 harness，并记录真实日志和预算统计。
  anvil：按 JSON 清单部署编译 artifact、发送完整交易序列并读取指定状态。

本驱动只负责实验执行和证据收集，不生成种子、不修改属性，也不实现 V2 算法。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".tools/python"))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def resolve_path(value: str | Path, base: Path = ROOT) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (base / path).resolve()


def experiment_env() -> dict[str, str]:
    env = os.environ.copy()
    prefixes = [str(ROOT / ".tools/olympia-venv/bin"), str(ROOT / ".tools/foundry/bin")]
    env["PATH"] = os.pathsep.join(prefixes + [env.get("PATH", "")])
    python_path = [str(ROOT / ".tools/python")]
    if env.get("PYTHONPATH"):
        python_path.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(python_path)
    return env


def extract_echidna_stats(log: str) -> dict[str, Any]:
    stats: dict[str, Any] = {}
    patterns = {
        "tests": r"tests:\s*([0-9]+/[0-9]+)",
        "fuzzing": r"fuzzing:\s*([0-9]+/[0-9]+)",
        "coverage": r"\bcov:\s*([0-9]+)",
        "corpus": r"\bcorpus:\s*([0-9]+)",
    }
    for key, pattern in patterns.items():
        matches = re.findall(pattern, log)
        if matches:
            stats[key] = matches[-1]
    stats["loaded_sequences"] = [int(v) for v in re.findall(r"Loaded ([0-9]+) transaction sequences", log)]
    stats["passing_properties"] = re.findall(r"^([^\n:]+): passing$", log, flags=re.MULTILINE)
    stats["failing_properties"] = re.findall(r"^([^\n:]+): (?:failing|failed)$", log, flags=re.MULTILINE)
    return stats


def run_echidna(args: argparse.Namespace) -> int:
    project = resolve_path(args.project)
    config = resolve_path(args.config, project)
    output = resolve_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    binary = str(resolve_path(args.binary)) if "/" in args.binary else args.binary
    command = [binary, str(project), "--contract", args.contract, "--config", str(config),
               "--test-mode", args.mode, "--test-limit", str(args.test_limit),
               "--seq-len", str(args.seq_len), "--seed", str(args.seed),
               "--workers", str(args.workers), "--timeout", str(args.timeout),
               "--corpus-dir", str(output / "corpus"), "--format", "text"]
    log_path = output / "echidna.log"
    started = time.monotonic()
    start_utc = utc_now()
    with log_path.open("w", encoding="utf-8") as log:
        try:
            completed = subprocess.run(command, cwd=project, env=experiment_env(),
                                       stdout=log, stderr=subprocess.STDOUT,
                                       timeout=args.timeout + 60, check=False)
            returncode = completed.returncode
            timeout_hit = False
        except subprocess.TimeoutExpired:
            returncode = 124
            timeout_hit = True
    elapsed = time.monotonic() - started
    text = log_path.read_text(encoding="utf-8", errors="replace")
    result = {
        "kind": "native_echidna",
        "started_at_utc": start_utc,
        "ended_at_utc": utc_now(),
        "project": str(project),
        "contract": args.contract,
        "mode": args.mode,
        "config": str(config),
        "command": command,
        "test_limit": args.test_limit,
        "sequence_length": args.seq_len,
        "seed": args.seed,
        "workers": args.workers,
        "timeout_seconds": args.timeout,
        "elapsed_seconds": round(elapsed, 6),
        "returncode": returncode,
        "timeout_hit": timeout_hit,
        "log": str(log_path),
        "log_sha256": sha256(log_path),
        "statistics": extract_echidna_stats(text),
    }
    write_json(output / "summary.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return returncode


def _anvil_args(config: dict[str, Any]) -> list[str]:
    binary = str(resolve_path(config.get("binary", ROOT / ".tools/foundry/bin/anvil")))
    command = [binary, "--host", str(config.get("host", "127.0.0.1")),
               "--port", str(config.get("port", 18549)),
               "--chain-id", str(config.get("chain_id", 31337)),
               "--accounts", str(config.get("accounts", 10)),
               "--balance", str(config.get("balance_eth", 10000)),
               "--gas-limit", str(config.get("block_gas_limit", 100000000))]
    if config.get("disable_code_size_limit", False):
        command.append("--disable-code-size-limit")
    if config.get("timestamp") is not None:
        command.extend(["--timestamp", str(config["timestamp"])])
    if config.get("silent", True):
        command.append("--silent")
    return command


def _read_calls(contract: Any, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in calls:
        row = {"label": item.get("label"), "function": item["function"],
               "arguments": item.get("arguments", [])}
        try:
            fn = contract.get_function_by_signature(item["function"])(*item.get("arguments", []))
            value = fn.call()
            row["value"] = value.hex() if isinstance(value, (bytes, bytearray)) else str(value)
            row["status"] = "success"
        except Exception as exc:  # Keep failed independent reads as evidence.
            row["status"] = "error"
            row["error"] = str(exc)
        rows.append(row)
    return rows


def run_anvil(args: argparse.Namespace) -> int:
    from web3 import Web3
    from web3.providers.rpc import HTTPProvider

    spec_path = resolve_path(args.spec)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    project = resolve_path(spec["project_root"])
    artifact_path = resolve_path(spec["artifact"], project)
    output = resolve_path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    anvil_config = spec.get("anvil", {})
    command = _anvil_args(anvil_config)
    host, port = anvil_config.get("host", "127.0.0.1"), int(anvil_config.get("port", 18549))
    rpc_url = f"http://{host}:{port}"
    anvil_log = output / "anvil.log"
    result: dict[str, Any] = {
        "kind": "anvil_deploy_and_replay",
        "spec": str(spec_path),
        "spec_sha256": sha256(spec_path),
        "started_at_utc": utc_now(),
        "project": str(project),
        "artifact": str(artifact_path),
        "artifact_sha256": sha256(artifact_path),
        "anvil_command": command,
        "rpc_url": rpc_url,
        "transactions": [],
    }
    process = None
    started = time.monotonic()
    try:
        with anvil_log.open("w", encoding="utf-8") as stream:
            process = subprocess.Popen(command, cwd=project, env=experiment_env(),
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        w3 = Web3(HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
        deadline = time.monotonic() + int(anvil_config.get("startup_timeout", 30))
        while time.monotonic() < deadline and not w3.is_connected():
            if process.poll() is not None:
                raise RuntimeError(f"Anvil exited early with status {process.returncode}")
            time.sleep(0.2)
        if not w3.is_connected():
            raise TimeoutError("Anvil RPC startup timed out")
        accounts = w3.eth.accounts
        result["chain"] = {
            "chain_id": w3.eth.chain_id,
            "accounts": accounts,
            "balances_wei": [str(w3.eth.get_balance(a)) for a in accounts],
            "block_number": w3.eth.block_number,
            "timestamp": w3.eth.get_block("latest")["timestamp"],
        }
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        bytecode = artifact["bytecode"]
        if isinstance(bytecode, dict):
            bytecode = bytecode["object"]
        if not bytecode.startswith("0x"):
            bytecode = "0x" + bytecode
        factory = w3.eth.contract(abi=artifact["abi"], bytecode=bytecode)
        deploy_cfg = spec.get("deployment", {})
        deployer = accounts[int(deploy_cfg.get("sender_index", 0))]
        tx_hash = factory.constructor(*deploy_cfg.get("arguments", [])).transact({
            "from": deployer, "gas": int(deploy_cfg.get("gas", 95_000_000))})
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=int(deploy_cfg.get("timeout", 90)))
        result["deployment"] = {
            "tx_hash": tx_hash.hex(), "status": int(receipt.status),
            "gas_used": int(receipt.gasUsed), "contract_address": receipt.contractAddress,
            "block_number": int(receipt.blockNumber), "sender": deployer,
        }
        if int(receipt.status) != 1:
            try:
                trace = w3.provider.make_request("debug_traceTransaction", [tx_hash.hex(), {}])
                detail = trace.get("result", {})
                result["deployment"]["trace"] = {
                    "error": detail.get("error"), "return_value": detail.get("returnValue"),
                    "struct_log_count": len(detail.get("structLogs", [])),
                }
            except Exception as exc:
                result["deployment"]["trace_error"] = str(exc)
            result["status"] = "deployment_failed"
        else:
            contract = w3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"])
            result["state_before"] = _read_calls(contract, spec.get("state_reads_before", []))
            for index, tx in enumerate(spec.get("transactions", []), start=1):
                delay = int(tx.get("delay_seconds", 0))
                if delay:
                    w3.provider.make_request("evm_increaseTime", [delay])
                    w3.provider.make_request("evm_mine", [])
                sender = accounts[int(tx.get("sender_index", 0))]
                record = {"index": index, "function": tx["function"],
                          "arguments": tx.get("arguments", []), "sender": sender,
                          "value_wei": str(tx.get("value_wei", "0")), "delay_seconds": delay}
                try:
                    fn = contract.get_function_by_signature(tx["function"])(*tx.get("arguments", []))
                    call_tx = {"from": sender, "gas": int(tx.get("gas", 20_000_000)),
                               "value": int(tx.get("value_wei", 0))}
                    tx_hash = fn.transact(call_tx)
                    r = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)
                    record.update({"tx_hash": tx_hash.hex(), "status": int(r.status),
                                   "gas_used": int(r.gasUsed), "block_number": int(r.blockNumber),
                                   "logs": [{"address": row["address"],
                                             "topics": [t.hex() for t in row["topics"]],
                                             "data": row["data"].hex()} for row in r.logs]})
                    if int(r.status) == 0:
                        try:
                            trace = w3.provider.make_request("debug_traceTransaction", [tx_hash.hex(), {}])
                            detail = trace.get("result", {})
                            record["trace"] = {"error": detail.get("error"),
                                                "return_value": detail.get("returnValue"),
                                                "struct_log_count": len(detail.get("structLogs", []))}
                        except Exception as exc:
                            record["trace_error"] = str(exc)
                except Exception as exc:
                    record.update({"status": "submission_error", "error": str(exc)})
                result["transactions"].append(record)
                if record.get("status") != 1 and not spec.get("continue_after_failure", False):
                    break
            result["state_after"] = _read_calls(contract, spec.get("state_reads_after", []))
            result["status"] = "replay_completed"
        result["ended_at_utc"] = utc_now()
        result["elapsed_seconds"] = round(time.monotonic() - started, 6)
        result["anvil_log"] = str(anvil_log)
        result["anvil_log_sha256"] = sha256(anvil_log)
        write_json(output / "result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        result.update({"status": "runner_error", "error": str(exc),
                       "ended_at_utc": utc_now(),
                       "elapsed_seconds": round(time.monotonic() - started, 6)})
        if anvil_log.exists():
            result["anvil_log"] = str(anvil_log)
            result["anvil_log_sha256"] = sha256(anvil_log)
        write_json(output / "result.json", result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    finally:
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode_command", required=True)
    ech = sub.add_parser("echidna", help="运行原生 Echidna 属性/断言 harness")
    ech.add_argument("--project", required=True)
    ech.add_argument("--contract", required=True)
    ech.add_argument("--config", required=True)
    ech.add_argument("--mode", choices=["property", "assertion", "foundry"], required=True)
    ech.add_argument("--output", required=True)
    ech.add_argument("--binary", default="/usr/local/bin/echidna")
    ech.add_argument("--test-limit", type=int, default=500)
    ech.add_argument("--seq-len", type=int, default=8)
    ech.add_argument("--seed", type=int, required=True)
    ech.add_argument("--workers", type=int, default=1)
    ech.add_argument("--timeout", type=int, default=600)
    ech.set_defaults(func=run_echidna)
    anv = sub.add_parser("anvil", help="按冻结交易清单部署并回放 Anvil 序列")
    anv.add_argument("--spec", required=True)
    anv.add_argument("--output", required=True)
    anv.set_defaults(func=run_anvil)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
