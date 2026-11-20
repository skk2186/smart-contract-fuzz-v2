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
from web3._utils.events import event_abi_to_log_topic, get_event_data

from AgentB import HARNESS_ADDRESS, PROPERTY_SENDER, SENDERS, to_echidna_sequence
from 跨交易状态约束 import (infer_object_argument, matching_event_values,
                           propose_numeric_repair, slither_guard_evidence)
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
    fuzzing_counts = [(int(txs), int(cases)) for txs, cases in
                      re.findall(r"fuzzing\s*:\s*(\d+)\s*/\s*(\d+)",
                                 output, re.IGNORECASE)]
    tests_counts = [(int(done), int(total)) for done, total in
                    re.findall(r"\btests\s*:\s*(\d+)\s*/\s*(\d+)",
                               output, re.IGNORECASE)]
    worker_crashes = [line.strip() for line in output.splitlines()
                      if re.search(r"\bCrashed:\s*", line, re.IGNORECASE)]
    # fuzzing 的第一个数字是调用/交易进度，第二个数字不是可靠的实际 case
    # 数；tests 是属性通过/失败状态计数。两者都不能单独证明产生了新序列。
    property_failure = any(re.search(r"\b(?:falsified|failed)\b", line, re.IGNORECASE)
                          and re.search(r"\b(?:Test|property)\b", line, re.IGNORECASE)
                          for line in output.splitlines())
    instruction_counts = [int(match.replace(",", "")) for match in
                          re.findall(r"unique instructions\s*:\s*([\d,]+)", output, re.IGNORECASE)]
    coverage_snapshots = [int(match.replace(",", "")) for match in
                          re.findall(r"\bcov:\s*([\d,]+)", output, re.IGNORECASE)]
    return {"loaded_seed_count": count,
            "loaded_seed_evidence": count > 0,
            "replayed_sequence_count": len(replayed),
            "replay_evidence": bool(replayed),
            "replayed_lines": replayed,
            "mutation_evidence": False,
            "mutation_evidence_status": "not_inferable_without_input_output_coverage_or_sequence_diff",
            "fuzzing_activity_evidence": any(txs > 0 for txs, _ in fuzzing_counts),
            "fuzzing_transactions": max((txs for txs, _ in fuzzing_counts), default=0),
            "fuzzing_cases": None,
            "fuzzing_case_count_status": "not_inferable_from_text_progress_denominator",
            "fuzzing_progress_count": max((txs for txs, _ in fuzzing_counts), default=0),
            "fuzzing_progress_limit": max((cases for _, cases in fuzzing_counts), default=0),
            "tests_status_snapshots": [{"completed": done, "total": total}
                                        for done, total in tests_counts],
            "tests_status_semantics": "Echidna text-mode property status (failed/total), not executed test-case count",
            "property_failure_reported": property_failure,
            "worker_crashes": worker_crashes,
            "unique_instructions": max(instruction_counts or coverage_snapshots, default=None),
            "coverage_source": ("final_unique_instructions" if instruction_counts else
                                "last_status_cov_snapshot" if coverage_snapshots else None)}


class AnvilSession:
    def __init__(self, port: int | None = None, project: str | None = None):
        if not ANVIL_BIN.is_file():
            raise FileNotFoundError(f"找不到项目内 Anvil：{ANVIL_BIN}")
        self.port = port or self._free_port()
        self.project = project
        project_config = PROJECTS.get(project, {}) if project else {}
        execution = project_config.get("execution", {})
        self.chain_id = int(execution.get("chain_id", CHAIN_ID))
        self.initial_block_number = int(execution.get(
            "deployment_block_number", INITIAL_BLOCK_NUMBER))
        self.initial_timestamp = int(execution.get(
            "deployment_timestamp", INITIAL_TIMESTAMP))
        self.base_fee = int(execution.get("base_fee_per_gas", 0))
        self.gas_price = int(execution.get("gas_price", 0))
        self.gas_limit = int(execution.get("block_gas_limit", 100_000_000))
        self.hardfork = str(execution.get("hardfork", "shanghai"))
        deployment = project_config.get("deployment", {})
        self.deployer = str(deployment.get("deployer", execution.get("deployer", DEPLOYER)))
        self.property_sender = str(project_config.get("property", {}).get(
            "sender", PROPERTY_SENDER))
        self.senders = list(project_config.get("senders") or SENDERS)
        self.initial_balance = int(execution.get("initial_balance", INITIAL_BALANCE))
        self.max_transaction_gas = int(execution.get("max_transaction_gas", MAX_TX_GAS))
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
             "--chain-id", str(self.chain_id), "--number", str(self.initial_block_number - 1),
             "--timestamp", str(self.initial_timestamp - 1), "--block-base-fee-per-gas",
             str(self.base_fee), "--gas-price", str(self.gas_price), "--gas-limit",
             str(self.gas_limit), "--hardfork", self.hardfork,
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
                    for address in [self.deployer, *self.senders]:
                        self.rpc("anvil_setBalance", [address, hex(self.initial_balance)])
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


def _decode_revert_reason(data: Any) -> str | None:
    """解码 Solidity Error(string) 与 Panic(uint256) 返回数据。"""
    if not isinstance(data, str) or not data.startswith("0x") or len(data) < 10:
        return None
    try:
        payload = bytes.fromhex(data[2:])
        selector, encoded = payload[:4], payload[4:]
        if selector == bytes.fromhex("08c379a0"):
            from eth_abi import decode
            return str(decode(["string"], encoded)[0])
        if selector == bytes.fromhex("4e487b71") and len(encoded) >= 32:
            code = int.from_bytes(encoded[:32], "big")
            return f"Panic(0x{code:x})"
        return None
    except Exception:
        return None


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


def _receipt_events(web3: Web3, receipt: Any, contract_abis: dict[str, Any],
                    harness_abi: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按编译产物 ABI 解码真实 receipt；同名事件保留地址以便消歧。"""
    by_topic: dict[bytes, list[dict[str, Any]]] = {}
    for abi in [harness_abi, *contract_abis.values()]:
        if not isinstance(abi, list):
            continue
        for entry in abi:
            if entry.get("type") == "event" and not entry.get("anonymous"):
                by_topic.setdefault(bytes(event_abi_to_log_topic(entry)), []).append(entry)
    events = []
    for log in receipt.logs:
        if not log["topics"]:
            continue
        for entry in by_topic.get(bytes(log["topics"][0]), []):
            try:
                decoded = get_event_data(web3.codec, entry, log)
            except Exception:
                continue
            item = {"name": entry["name"], "address": log["address"].lower(),
                    "fields": {key: _to_rpc_value(value)
                               for key, value in decoded["args"].items()}}
            if item not in events:
                events.append(item)
            break
    return events


def _trace_effects(session: AnvilSession, tx_hash: Any) -> dict[str, Any]:
    """区分外层收据成功与内部调用回滚，并计数持久存储槽变化。"""
    call = session.rpc("debug_traceTransaction", [tx_hash.hex(), {"tracer": "callTracer"}])
    errors = []
    def visit(node: dict[str, Any], depth: int) -> None:
        if depth and node.get("error"):
            errors.append({"depth": depth, "type": node.get("type"),
                           "address": node.get("to"), "error": node["error"],
                           "output": node.get("output")})
        for child in node.get("calls", []):
            visit(child, depth + 1)
    visit(call, 0)
    trace_nodes = 0
    def compact(node: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        nonlocal trace_nodes
        trace_nodes += 1
        result = {key: node.get(key) for key in ("type", "from", "to", "input",
                                                  "output", "error", "value") if key in node}
        if depth < 12 and trace_nodes < 128:
            result["calls"] = [compact(child, depth + 1)
                               for child in node.get("calls", [])[:32]]
        elif node.get("calls"):
            result["calls_truncated"] = True
        return result
    call_tree = compact(call)
    diff = session.rpc("debug_traceTransaction", [tx_hash.hex(),
                       {"tracer": "prestateTracer", "tracerConfig": {"diffMode": True}}])
    before, after = diff.get("pre", {}), diff.get("post", {})
    slots = sum(len(set(before.get(addr, {}).get("storage", {})) |
                        set(after.get(addr, {}).get("storage", {})))
                for addr in set(before) | set(after))
    balance_changes = []
    for address in sorted(set(before) | set(after)):
        old = before.get(address, {}).get("balance")
        new = after.get(address, {}).get("balance")
        if old is None or new is None:
            continue
        try:
            old_wei = int(old, 16) if isinstance(old, str) else int(old)
            new_wei = int(new, 16) if isinstance(new, str) else int(new)
        except (TypeError, ValueError):
            continue
        if old_wei != new_wei:
            balance_changes.append({"address": address.lower(),
                                    "before_wei": old_wei,
                                    "after_wei": new_wei,
                                    "delta_wei": new_wei - old_wei})
    return {"internal_errors": errors, "internal_call_trace": call_tree,
            "changed_storage_slot_count": slots,
            "balance_changes": balance_changes,
            "top_level_trace_error": call.get("error"),
            "top_level_output": call.get("output")}


def _call_assertion_target(session: AnvilSession, contract: Any,
                           signature: str) -> dict[str, Any]:
    """在当前状态只读执行选定 assertion 函数，并识别 Solidity assert 的 Panic(0x01)。"""
    function = contract.get_function_by_signature(signature)()
    transaction = {"from": _checksum(session.property_sender),
                   "to": contract.address,
                   "data": function._encode_transaction_data(),
                   "gas": hex(session.max_transaction_gas),
                   "gasPrice": "0x0"}
    response = session.web3.provider.make_request("eth_call", [transaction, "latest"])
    if "result" in response:
        return {"status": "passed", "result": True}
    error = response.get("error") or {}
    data = error.get("data")
    if isinstance(data, dict):
        data = data.get("data") or data.get("result")
    if not isinstance(data, str):
        data = None
    reason = _decode_revert_reason(data)
    if reason == "Panic(0x1)":
        return {"status": "target_assertion_failed", "result": False,
                "revert_reason": reason, "revert_data": data}
    return {"status": "assertion_call_error", "result": None,
            "revert_reason": reason,
            "error": str(error)[:500], "revert_data": data}


def _resolve_event_arguments(tx: dict[str, Any], action: dict[str, Any],
                             prior_events: list[list[dict[str, Any]]],
                             dependency_hints: list[dict[str, Any]],
                             prior_inputs: list[dict[str, Any]], *,
                             infer_object_ids: bool = False) -> tuple[list[Any], list[dict[str, Any]], list[str]]:
    """仅从已执行交易的唯一事件字段绑定参数，不从 nonce 等输入猜对象 ID。"""
    from AgentB import normalize_argument
    resolved = list(tx["arguments"])
    bindings, errors = [], []
    tx_index = len(prior_events)  # zero-based index of current transaction
    for arg_index, param in enumerate(action.get("abi_inputs", [])):
        raw = resolved[arg_index]
        explicit = raw if isinstance(raw, dict) else None
        hint = next((h for h in dependency_hints
                     if h.get("transaction_index") == tx_index and
                     h.get("field") == param.get("name")), None)
        hinted = hint is not None
        if not explicit and not hinted:
            if infer_object_ids:
                inferred, rows = infer_object_argument(
                    [raw], [param], prior_events, transaction_index=tx_index + 1)
                if rows:
                    resolved[arg_index] = inferred[0]
                    binding = rows[0]
                    bindings.append({"argument_index": arg_index,
                                     "argument_name": param["name"],
                                     "from_transaction": binding["sources"][-1]["from_transaction"],
                                     "event": binding["sources"][-1]["event"],
                                     "event_address": binding["sources"][-1]["event_address"],
                                     "field": binding["sources"][-1]["field"],
                                     "original": raw, "resolved": inferred[0],
                                     "binding_mode": binding["binding_mode"],
                                     "sources": binding["sources"]})
            continue
        if explicit:
            source_index = explicit.get("from_transaction")
            event_name = explicit.get("event")
            field = explicit.get("field")
            if (not isinstance(source_index, int) or isinstance(source_index, bool) or
                    source_index < 1 or source_index > len(prior_events) or
                    not isinstance(event_name, str) or not isinstance(field, str)):
                errors.append(f"参数 {param['name']} 的事件引用无效；需指定已执行交易序号、event、field")
                continue
            indexed_events = [(source_index, event) for event in prior_events[source_index - 1]
                              if event["name"] == event_name and field in event["fields"]]
        else:
            field = param["name"]
            source = hint.get("depends_on_index", hint.get("depends_on_transaction_index"))
            source = source if type(source) is int and 0 <= source < tx_index else None
            indexed_events = [(index + 1, event)
                              for index, events in enumerate(prior_events)
                              for event in events if (source is None or source == index) and
                              field in event["fields"]]
            previous = [item[field] for index, item in enumerate(prior_inputs)
                        if field in item and (source is None or source == index)]
            if not indexed_events and previous:
                # 相同身份等输入可直接复用；它不是前序交易新产生的对象 ID。
                if raw not in previous:
                    errors.append(f"参数 {field} 未复用前序交易输入：{previous[-1]}")
                continue
        try:
            values = {(index, event["address"], str(normalize_argument(
                param["type"], event["fields"][field]))): event["fields"][field]
                      for index, event in indexed_events}
        except ValueError:
            values = {}
        if len(values) != 1:
            source = f"{event_name}.{field}" if explicit else field
            errors.append(f"参数 {param['name']} 未找到唯一的前序事件字段 {source}；候选数={len(values)}")
            continue
        (source_index, address, _), value = next(iter(values.items()))
        resolved[arg_index] = normalize_argument(param["type"], value)
        bindings.append({"argument_index": arg_index, "argument_name": param["name"],
                         "from_transaction": source_index, "event": event_name if explicit else None,
                         "event_address": address, "field": field,
                         "original": raw, "resolved": resolved[arg_index]})
    return resolved, bindings, errors


def _state_view_snapshot(web3: Web3, contract, contract_abis: dict[str, Any], *,
                         sender: str = DEPLOYER) -> dict[str, Any]:
    """跟随 Harness 内部合约地址 getter，观测最多三层公开 view 状态。"""
    observations = {}
    visited: set[tuple[str, str]] = set()
    discovered: set[str] = set()
    instances: list[dict[str, str]] = []

    def observe(current, contract_name: str, depth: int) -> None:
        key = (current.address.lower(), contract_name)
        if key in visited or depth > 3 or len(visited) >= 32:
            return
        visited.add(key)
        discovered.add(contract_name)
        instances.append({"name": contract_name, "address": current.address.lower()})
        for entry in current.abi:
            if (entry.get("type") != "function" or entry.get("inputs") or
                    entry.get("stateMutability") != "view"):
                continue
            signature = entry["name"] + "()"
            observation_key = f"{current.address.lower()}:{signature}"
            try:
                value = current.get_function_by_signature(signature)().call({"from": sender})
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
            "contract_instances": instances,
            "view_values": observations}


def _flatten_named_outputs(outputs: list[dict[str, Any]], value: Any) -> list[dict[str, Any]]:
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    flattened = []
    for output, item in zip(outputs, values):
        if output.get("type") == "tuple" and output.get("components"):
            nested = _flatten_named_outputs(output["components"], item)
            parent = str(output.get("name") or "")
            for row in nested:
                flattened.append({**row, "name": f"{parent}.{row['name']}" if parent else row["name"]})
        elif output.get("type", "").endswith("[]"):
            continue
        else:
            flattened.append({"name": output.get("name") or "",
                              "type": output.get("type", ""),
                              "value": _to_rpc_value(item)})
    return flattened


def _parameterized_getter_observations(web3: Web3, state: dict[str, Any],
                                       contract_abis: dict[str, Any],
                                       prior_events: list[list[dict[str, Any]]], *,
                                       transaction_index: int,
                                       sender: str = DEPLOYER) -> list[dict[str, Any]]:
    """用已成功事件中的对象键调用匹配的单参数公开 view getter。"""
    observations = []
    seen: set[tuple[str, str, str]] = set()
    for instance in state.get("contract_instances", []):
        contract_name = instance.get("name")
        abi = contract_abis.get(contract_name)
        if not isinstance(abi, list):
            continue
        try:
            target = web3.eth.contract(address=_checksum(instance["address"]), abi=abi)
        except Exception:
            continue
        for entry in abi:
            if (entry.get("type") != "function" or
                    entry.get("stateMutability") != "view" or
                    len(entry.get("inputs", [])) != 1):
                continue
            param = entry["inputs"][0]
            name, kind = str(param.get("name") or ""), str(param.get("type") or "")
            if not name:
                continue
            matches = matching_event_values(name, kind, prior_events,
                                            transaction_index=transaction_index)
            distinct = {repr(row["value"]): row["value"] for row in matches}
            if not distinct:
                continue
            signature = entry["name"] + "(" + kind + ")"
            for argument_key, argument in distinct.items():
                key = (instance["address"].lower(), signature, argument_key)
                if key in seen or len(seen) >= 64:
                    continue
                seen.add(key)
                sources = [row["source"] for row in matches
                           if repr(row["value"]) == argument_key]
                try:
                    value = target.get_function_by_signature(signature)(argument).call(
                        {"from": sender})
                    outputs = _flatten_named_outputs(entry.get("outputs", []), value)
                    observations.append({"contract": contract_name,
                                         "address": instance["address"].lower(),
                                         "function": signature,
                                         "input": {"name": name, "type": kind, "value": argument},
                                         "input_sources": sources,
                                         "status": "returned", "outputs": outputs})
                except Exception as exc:
                    observations.append({"contract": contract_name,
                                         "address": instance["address"].lower(),
                                         "function": signature,
                                         "input": {"name": name, "type": kind, "value": argument},
                                         "input_sources": sources,
                                         "status": "error",
                                         "error": f"{type(exc).__name__}: {str(exc)[:240]}"})
    return observations


def _view_state_delta(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    old_values = before.get("view_values", {})
    new_values = after.get("view_values", {})
    return [{"getter": key, "before": old_values.get(key), "after": new_values.get(key)}
            for key in sorted(set(old_values) | set(new_values))
            if old_values.get(key) != new_values.get(key)]


def _solidity_error_texts(trace: dict[str, Any], property_error: str | None) -> list[str]:
    texts = [property_error] if property_error else []
    for row in trace.get("internal_errors", []):
        output = row.get("output")
        if not isinstance(output, str):
            continue
        try:
            raw = bytes.fromhex(output[2:] if output.startswith("0x") else output)
            if len(raw) < 68 or raw[:4] != bytes.fromhex("08c379a0"):
                continue
            args = raw[4:]
            offset = int.from_bytes(args[:32], "big")
            length = int.from_bytes(args[offset:offset + 32], "big")
            start = offset + 32
            if start + length <= len(args):
                texts.append(args[start:start + length].decode("utf-8", errors="replace"))
        except (ValueError, IndexError, OverflowError):
            continue
    return texts


def _split_solidity_arguments(arguments: str) -> list[str]:
    parts, start, depth = [], 0, 0
    for index, char in enumerate(arguments):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            parts.append(arguments[start:index].strip())
            start = index + 1
    tail = arguments[start:].strip()
    if tail or parts:
        parts.append(tail)
    return parts


def _property_calls(expression: str) -> list[tuple[str | None, str, list[str]]]:
    calls = []
    pattern = r"(?:(?P<receiver>[A-Za-z_][A-Za-z0-9_]*)\s*\.\s*)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\("
    for match in re.finditer(pattern, expression):
        opening = expression.find("(", match.start())
        depth = 0
        for index in range(opening, len(expression)):
            if expression[index] == "(":
                depth += 1
            elif expression[index] == ")":
                depth -= 1
                if depth == 0:
                    args = _split_solidity_arguments(expression[opening + 1:index])
                    calls.append((match.group("receiver"), match.group("name"), args))
                    break
    return calls


def _resolve_property_argument(expression: str, abi_type: str, declarations: str,
                                property_sender: str, contract=None,
                                seen: set[str] | None = None) -> Any:
    expression = expression.strip()
    seen = set(seen or ())
    if expression == "this" and contract is not None:
        value: Any = contract.address
    elif expression == "msg.sender":
        value: Any = property_sender
    elif expression in {"true", "false"}:
        value = expression == "true"
    else:
        cast = re.fullmatch(r"(?:address|bool|u?int[0-9]*|bytes[0-9]*)\s*\((.*)\)", expression)
        if cast:
            value = _resolve_property_argument(cast.group(1), abi_type, declarations,
                                               property_sender, contract, seen)
        elif contract is not None and re.fullmatch(
                r"[A-Za-z_][A-Za-z0-9_]*\s*\[\s*[^\]]+\s*\]", expression):
            access = re.fullmatch(
                r"(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\[\s*(?P<index>[^\]]+)\s*\]",
                expression)
            assert access is not None
            name, index_expression = access.group("name"), access.group("index").strip()
            getters = [item for item in contract.abi
                       if item.get("type") == "function" and item.get("name") == name and
                       len(item.get("inputs", [])) == 1 and
                       item.get("stateMutability") in {"view", "pure"}]
            if len(getters) != 1:
                raise ValueError("索引属性参数没有唯一匹配的公开 view getter")
            getter = getters[0]
            index_type = getter["inputs"][0]["type"]
            index = _resolve_property_argument(index_expression, index_type, declarations,
                                               property_sender, contract, seen)
            signature = name + "(" + index_type + ")"
            value = contract.get_function_by_signature(signature)(index).call(
                {"from": _checksum(property_sender)})
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", expression):
            if expression in seen:
                raise ValueError("循环常量引用")
            seen.add(expression)
            getter_signature = expression + "()"
            getter_abi = next((item for item in (contract.abi if contract else [])
                               if item.get("type") == "function" and
                               item.get("name") == expression and not item.get("inputs") and
                               item.get("stateMutability") in {"view", "pure"}), None)
            if getter_abi is not None:
                value = contract.get_function_by_signature(getter_signature)().call(
                    {"from": _checksum(property_sender)})
            else:
                initializers = re.findall(r"\b" + re.escape(expression) +
                                          r"\s*=\s*([^;]+);", declarations)
                if not initializers:
                    raise ValueError("属性参数不是可解析的字面量/局部常量")
                value = _resolve_property_argument(initializers[0], abi_type,
                                                   declarations, property_sender,
                                                   contract, seen)
        elif re.fullmatch(r"0x[0-9a-fA-F]+|[0-9][0-9_]*", expression):
            value = int(expression.replace("_", ""), 0 if expression.startswith("0x") else 10)
        elif len(expression) >= 2 and expression[0] == expression[-1] == '"':
            value = bytes(expression[1:-1], "utf-8").decode("unicode_escape")
        else:
            raise ValueError("暂不支持该属性参数表达式")

    if abi_type == "address":
        if isinstance(value, str) and Web3.is_address(value):
            return Web3.to_checksum_address(value)
        if isinstance(value, int) and 0 <= value < 2 ** 160:
            return Web3.to_checksum_address("0x" + value.to_bytes(20, "big").hex())
        raise ValueError("address 参数无法解析")
    if abi_type == "bool":
        if isinstance(value, bool):
            return value
        raise ValueError("bool 参数无法解析")
    if abi_type.startswith(("uint", "int")):
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        raise ValueError("数值参数无法解析")
    if abi_type == "string" and isinstance(value, str):
        return value
    if abi_type.startswith("bytes") and isinstance(value, str) and value.startswith("0x"):
        return bytes.fromhex(value[2:])
    raise ValueError("ABI 参数类型不在轻量观察器支持范围")


def _property_getter_specs(property_context: dict[str, Any], contract,
                           contract_abis: dict[str, Any], *,
                           project: str | None = None,
                           property_sender: str = PROPERTY_SENDER) -> list[dict[str, Any]]:
    """解析属性直接调用及有界索引状态的公开 view getter 观察点。"""
    reference = property_context.get("property_source", "")
    source_reference = str(reference).split("#", 1)[0]
    source_path = ROOT / source_reference
    if not source_path.is_file() and project in PROJECTS:
        source_path = ROOT / PROJECTS[project].get("source_root", "") / source_reference
    if not source_path.is_file():
        return [{"status": "unresolved", "reason":
                 f"属性源码引用无法在仓库根目录或项目源码目录解析：{source_reference}"}]
    source = source_path.read_text(encoding="utf-8", errors="replace")
    line_match = re.search(r"#(\d+)", str(reference))
    if line_match:
        declarations = "\n".join(source.splitlines()[:max(0, int(line_match.group(1)) - 1)])
    else:
        declarations = source
    predicate = "\n".join(re.sub(r"^\s*\d+:\s?", "", line)
                             for line in (property_context.get("property_predicate") or "").splitlines())
    abi = [item for item in contract.abi
           if item.get("type") == "function" and
           item.get("stateMutability") in {"view", "pure"}]
    target_name = property_context.get("property_abi", "").split("(", 1)[0].rsplit(".", 1)[-1]
    specs = []

    def add_spec(spec: dict[str, Any]) -> None:
        key = (spec.get("signature"), spec.get("receiver"),
               json.dumps(spec.get("arguments", []), sort_keys=True), spec.get("status"))
        if not any((row.get("signature"), row.get("receiver"),
                    json.dumps(row.get("arguments", []), sort_keys=True), row.get("status")) == key
                   for row in specs):
            specs.append(spec)

    # Resolve statically bounded loops before resolving call arguments. This lets
    # calls such as TOKEN.balanceOf(holders[i]) expand into one getter read per
    # public array element instead of silently disappearing as unsupported.
    loop_ranges: dict[str, list[int] | None] = {}
    loop_pattern = re.compile(
        r"\bfor\s*\(\s*(?:u?int(?:[0-9]+)?)\s+(?P<name>[A-Za-z_]\w*)\s*=\s*"
        r"(?P<start>[^;]+);\s*(?P=name)\s*<\s*(?P<end>[^;]+);", re.MULTILINE)
    for loop in loop_pattern.finditer(predicate):
        variable = loop.group("name")
        try:
            start = _resolve_property_argument(loop.group("start"), "uint256", declarations,
                                               property_sender, contract)
            end = _resolve_property_argument(loop.group("end"), "uint256", declarations,
                                             property_sender, contract)
            if not isinstance(start, int) or not isinstance(end, int) or end < start or end - start > 256:
                loop_ranges[variable] = None
            else:
                loop_ranges[variable] = list(range(start, end))
        except (ValueError, TypeError):
            loop_ranges[variable] = None

    def expand_arguments(arguments: list[str]) -> list[list[str]]:
        variants: list[list[str]] = [[]]
        for expression in arguments:
            variables = [name for name in loop_ranges
                         if re.search(r"\b" + re.escape(name) + r"\b", expression)]
            options = [expression]
            for variable in variables:
                values = loop_ranges[variable]
                if values is None:
                    raise ValueError("属性参数引用了无法静态界定的循环变量")
                options = [re.sub(r"\b" + re.escape(variable) + r"\b", str(value), option)
                           for option in options for value in values]
                if len(options) > 256:
                    raise ValueError("属性参数循环展开超过 256 个有界值")
            variants = [prefix + [option] for prefix in variants for option in options]
            if len(variants) > 256:
                raise ValueError("属性参数组合展开超过 256 个有界值")
        return variants

    for receiver, name, arguments in _property_calls(predicate):
        if name == target_name:
            continue
        target_type = None
        if receiver:
            receiver_getter = next((item for item in abi
                                    if item.get("name") == receiver and not item.get("inputs")
                                    and item.get("stateMutability") in {"view", "pure"}
                                    and any(output.get("type") == "address"
                                            for output in item.get("outputs", []))), None)
            if receiver_getter is None:
                add_spec({"function": name, "expressions": arguments,
                          "receiver": receiver, "status": "unresolved",
                          "reason": f"跨合约引用 {receiver} 未通过 Harness 公共 ABI 暴露地址"})
                continue
            internal_type = next((output.get("internalType", "")
                                  for output in receiver_getter.get("outputs", [])
                                  if output.get("type") == "address"), "")
            target_type = internal_type.replace("contract ", "").strip() or None
            target_abi = contract_abis.get(target_type) if target_type else None
            if not isinstance(target_abi, list):
                add_spec({"function": name, "expressions": arguments,
                          "receiver": receiver, "receiver_type": target_type,
                          "status": "unresolved",
                          "reason": f"缺少 {target_type or receiver} 的合约 ABI"})
                continue
        else:
            target_abi = abi
        matches = [entry for entry in target_abi if entry.get("type") == "function" and
                   entry.get("name") == name and
                   entry.get("stateMutability") in {"view", "pure"} and
                   len(entry.get("inputs", [])) == len(arguments)]
        if not matches:
            if receiver:
                add_spec({"function": name, "expressions": arguments,
                          "receiver": receiver, "receiver_type": target_type,
                          "status": "unresolved",
                          "reason": "跨合约公开 ABI 中没有唯一匹配的 view getter"})
            continue
        try:
            argument_variants = expand_arguments(arguments)
        except (ValueError, TypeError) as exc:
            add_spec({"function": name, "expressions": arguments,
                      "receiver": receiver, "receiver_type": target_type,
                      "status": "unresolved", "reason": str(exc)})
            continue
        resolved_count = 0
        errors = []
        for entry in matches:
            signature = entry["name"] + "(" + ",".join(
                item["type"] for item in entry.get("inputs", [])) + ")"
            for argument_set in argument_variants:
                try:
                    values = [_resolve_property_argument(expression, parameter["type"],
                                                         declarations, property_sender,
                                                         contract)
                              for expression, parameter in zip(argument_set, entry.get("inputs", []))]
                    add_spec({"signature": signature, "expressions": argument_set,
                              "source_expressions": arguments, "arguments": values,
                              "receiver": receiver,
                              "receiver_getter": receiver + "()" if receiver else None,
                              "receiver_type": target_type,
                              "loop_expansion": argument_set != arguments})
                    resolved_count += 1
                except (ValueError, TypeError) as exc:
                    errors.append(str(exc))
        if resolved_count == 0:
            add_spec({"function": name, "expressions": arguments,
                      "receiver": receiver, "receiver_type": target_type,
                      "status": "unresolved",
                      "reason": errors[0] if errors else "ABI 参数未匹配"})

    # Public mapping/array getters are functions with one ABI index argument. Resolve
    # statically bounded for-loop indices so per-transaction feedback observes the
    # actual operands of quantified predicates rather than only the final bool.
    mapping_pattern = re.compile(r"\b(?P<name>[A-Za-z_]\w*)\s*\[\s*(?P<index>[^\]]+)\s*\]")
    for access in mapping_pattern.finditer(predicate):
        name, index_expression = access.group("name"), access.group("index").strip()
        if name == target_name:
            continue
        entries = [item for item in abi if item.get("type") == "function" and
                   item.get("name") == name and len(item.get("inputs", [])) == 1 and
                   item.get("stateMutability") in {"view", "pure"}]
        if len(entries) != 1:
            add_spec({"function": name, "expressions": [index_expression],
                      "status": "unresolved", "reason": "索引状态没有唯一匹配的单参数公开 view getter"})
            continue
        entry = entries[0]
        parameter_type = entry["inputs"][0]["type"]
        values: list[int] | None = None
        if index_expression in loop_ranges:
            values = loop_ranges[index_expression]
        else:
            try:
                value = _resolve_property_argument(index_expression, parameter_type,
                                                   declarations, property_sender, contract)
                values = [value] if isinstance(value, int) else None
            except (ValueError, TypeError):
                values = None
        signature = entry["name"] + "(" + ",".join(item["type"] for item in entry["inputs"]) + ")"
        if values is None:
            add_spec({"function": name, "expressions": [index_expression],
                      "status": "unresolved", "reason": "属性索引不是可解析且有界的整数/循环变量"})
            continue
        for value in values:
            add_spec({"signature": signature, "expressions": [index_expression],
                      "arguments": [value], "receiver": None,
                      "receiver_getter": None, "receiver_type": None,
                      "index_source": "statically_bounded_property_loop"
                      if index_expression in loop_ranges else "property_index_literal"})
    observed_signatures = {item.get("signature") for item in specs}
    for identifier in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", predicate):
        entry = next((item for item in abi if item.get("name") == identifier and
                      not item.get("inputs") and
                      item.get("stateMutability") in {"view", "pure"}), None)
        signature = identifier + "()"
        if (entry and identifier != target_name and signature not in observed_signatures):
            add_spec({"signature": signature, "expressions": [identifier],
                      "arguments": [], "receiver": None,
                      "receiver_getter": None, "receiver_type": None})
            observed_signatures.add(signature)
    return specs


def _observe_property_getters(web3: Web3, contract, contract_abis: dict[str, Any],
                              specs: list[dict[str, Any]], *,
                              property_sender: str = PROPERTY_SENDER) -> list[dict[str, Any]]:
    observations = []
    for spec in specs:
        if spec.get("status") == "unresolved":
            observations.append(spec)
            continue
        try:
            target = contract
            receiver_address = None
            if spec.get("receiver_getter"):
                receiver_address = contract.get_function_by_signature(
                    spec["receiver_getter"])().call({"from": _checksum(property_sender)})
                target_abi = contract_abis.get(spec.get("receiver_type"))
                if not isinstance(target_abi, list):
                    raise ValueError("缺少属性 getter 接收合约 ABI")
                target = web3.eth.contract(address=Web3.to_checksum_address(receiver_address),
                                           abi=target_abi)
            value = target.get_function_by_signature(spec["signature"])(
                *spec["arguments"]).call({"from": _checksum(property_sender)})
            observations.append({**spec, "status": "observed",
                                 "receiver_address": (_to_rpc_value(receiver_address)
                                                      if receiver_address else None),
                                 "value": _to_rpc_value(value)})
        except Exception as exc:
            observations.append({**spec, "status": "call_error",
                                 "error": f"{type(exc).__name__}: {str(exc)[:200]}"})
    return observations


def _target_property_state(property_signature: str,
                           initial_values: dict[str, Any],
                           initial_getters: list[dict[str, Any]],
                           records: list[dict[str, Any]]) -> dict[str, Any]:
    initial = initial_values.get(property_signature)
    trajectory = [{"transaction_index": 0, "value": initial,
                   "predicate_getters": initial_getters}]
    trajectory.extend({"transaction_index": row.get("index"),
                       "value": row.get("target_property"),
                       "predicate_getters": row.get("predicate_getter_values", [])}
                      for row in records)

    def getter_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        return (str(item.get("signature")), str(item.get("receiver")),
                json.dumps(item.get("receiver_address"), sort_keys=True),
                json.dumps(item.get("arguments", []), sort_keys=True))

    prior_values: dict[tuple[str, str, str, str], Any] = {}
    first_change = None
    for row in trajectory:
        changed = []
        for getter in row.get("predicate_getters", []):
            if getter.get("status") != "observed" or "value" not in getter:
                continue
            key = getter_key(getter)
            value = getter["value"]
            if key in prior_values and prior_values[key] != value:
                changed.append({"signature": getter.get("signature"),
                                "receiver": getter.get("receiver"),
                                "receiver_address": getter.get("receiver_address"),
                                "arguments": getter.get("arguments", []),
                                "before": prior_values[key], "after": value})
            prior_values[key] = value
        row["changed_predicate_getters"] = changed
        if changed and first_change is None:
            first_change = row

    first_false = next((item for item in trajectory if item.get("value") is False), None)
    getter_observation_incomplete = any(
        getter.get("status") in {"unresolved", "call_error"}
        for row in trajectory for getter in row.get("predicate_getters", []))
    observed_values = [item.get("value") for item in trajectory
                       if isinstance(item.get("value"), bool)]
    if first_false:
        status = "counterexample_state_established"
    elif first_change:
        status = "property_related_state_changed_property_holds"
    elif getter_observation_incomplete:
        status = "property_state_unobservable"
    elif observed_values and len(observed_values) == len(trajectory):
        status = "no_observed_property_related_state_change"
    else:
        status = "property_state_unobservable"
    return {"property": property_signature,
            "semantics": "属性布尔反例与属性谓词操作数 getter 变化分别判定",
            "status": status,
            "target_property_state_established": bool(first_false or first_change),
            "counterexample_state_established": first_false is not None,
            "property_related_state_changed": first_change is not None,
            "first_established_transaction_index": (
                first_false.get("transaction_index") if first_false else
                first_change.get("transaction_index") if first_change else None),
            "first_property_related_change_transaction_index": (
                first_change.get("transaction_index") if first_change else None),
            "first_counterexample_transaction_index": (
                first_false.get("transaction_index") if first_false else None),
            "trajectory": trajectory}


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
    config = PROJECTS[project]
    deployment = config.get("deployment", {})
    constructor_args = deployment.get("constructor_args",
                                     config.get("constructor_args", []))
    deployer = deployment.get("deployer", session.deployer)
    expected_address = deployment.get("contract_address", _project_runtime(project)["contract_address"])
    artifact = read_json(config["artifact"])
    factory = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bytecode"])
    session.rpc("evm_setNextBlockTimestamp", [session.initial_timestamp])
    tx_hash = factory.constructor(*constructor_args).transact({"from": _checksum(deployer),
                                               "gas": session.gas_limit,
                                               "gasPrice": 0})
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    if receipt.status != 1 or not receipt.contractAddress:
        trace_error = None
        revert_data = None
        revert_reason = None
        trace_summary = None
        try:
            trace = session.rpc("debug_traceTransaction", [
                tx_hash.hex(), {"tracer": "callTracer"}])
            trace_error = trace.get("error")
            revert_data = trace.get("output")
            revert_reason = _decode_revert_reason(revert_data)

            def compact_trace(node: dict[str, Any], depth: int = 0) -> dict[str, Any]:
                summary = {key: node.get(key) for key in
                           ("type", "from", "to", "error", "output", "input")
                           if key in node}
                for field, limit in (("input", 256), ("output", 1024)):
                    value = summary.get(field)
                    if isinstance(value, str) and len(value) > limit:
                        summary[field] = value[:limit]
                        summary[field + "_truncated"] = True
                if depth < 8:
                    summary["calls"] = [compact_trace(child, depth + 1)
                                         for child in node.get("calls", [])[:32]]
                elif node.get("calls"):
                    summary["calls_truncated"] = True
                return summary

            trace_summary = compact_trace(trace)
        except Exception as exc:
            trace_error = f"{type(exc).__name__}: {str(exc)[:300]}"
        raise RuntimeError(
            "Harness 部署失败："
            + json.dumps({"receipt_status": receipt.status,
                          "transaction_hash": tx_hash.hex(),
                          "trace_error": trace_error,
                          "revert_reason": revert_reason,
                          "revert_data": (revert_data[:1024] if isinstance(revert_data, str) else None),
                          "call_trace": trace_summary},
                         ensure_ascii=False))
    block = web3.eth.get_block(receipt.blockNumber)
    environment = {"chain_id": web3.eth.chain_id,
                   "deployment_block_number": int(block["number"]),
                   "deployment_timestamp": int(block["timestamp"]),
                   "contract_address": receipt.contractAddress.lower(),
                   "base_fee_per_gas": int(block.get("baseFeePerGas") or 0)}
    expected = {"chain_id": session.chain_id,
                "deployment_block_number": session.initial_block_number,
                "deployment_timestamp": session.initial_timestamp,
                "contract_address": expected_address.lower(),
                "base_fee_per_gas": session.base_fee}
    if environment != expected:
        raise RuntimeError(f"Anvil/Echidna 环境未对齐：actual={environment}, expected={expected}")
    return web3.eth.contract(address=receipt.contractAddress, abi=artifact["abi"]), receipt


def inspect_initial_state(project: str, property_context: dict[str, Any], *,
                          session: AnvilSession) -> dict[str, Any]:
    """部署未经交易的 Harness，记录可读状态及守卫相关 getter 的初始值。"""
    snapshot = session.rpc("evm_snapshot", [])
    try:
        contract, receipt = _deploy(session, project)
        artifact = read_json(PROJECTS[project]["artifact"])
        views = _state_view_snapshot(session.web3, contract,
                                     artifact.get("contract_abis", {}), sender=session.deployer)
        signatures = set()
        for action in property_context.get("candidate_actions", []):
            for effect in action.get("effect_evidence", []):
                for guard in effect.get("guards", []):
                    signatures.update(item for item in guard.get("predicate_calls", [])
                                      if isinstance(item, str) and "(" in item)
        abi = {entry["name"] + "(" + ",".join(x["type"] for x in entry.get("inputs", [])) + ")": entry
               for entry in contract.abi if entry.get("type") == "function"}
        probes = []
        for signature in sorted(signatures):
            abi_signature = signature.rsplit(".", 1)[-1]
            entry = abi.get(abi_signature)
            if entry is None or len(entry.get("inputs", [])) != 1 or entry.get("stateMutability") not in {"view", "pure"}:
                continue
            kind = entry["inputs"][0]["type"]
            values = ([0, 1] if kind.startswith(("uint", "int")) else
                      [session.property_sender] if kind == "address" else
                      [False, True] if kind == "bool" else [])
            for value in values:
                try:
                    result = contract.get_function_by_signature(abi_signature)(value).call(
                        {"from": _checksum(session.property_sender)})
                    probes.append({"function": abi_signature, "argument": value,
                                   "status": "returned", "value": _to_rpc_value(result)})
                except Exception as exc:
                    message = str(exc)[:240]
                    lower = message.lower()
                    category = ("object_missing" if any(term in lower for term in
                                ("invalid token id", "does not exist", "not found", "unknown id"))
                                else "guard_rejected" if "revert" in lower else "call_error")
                    probes.append({"function": abi_signature, "argument": value,
                                   "status": category, "error": message})
        property_values = {}
        for entry in contract.abi:
            if (entry.get("type") != "function" or entry.get("inputs") or
                    not entry["name"].startswith("echidna_") or
                    not any(out.get("type") == "bool" for out in entry.get("outputs", []))):
                continue
            try:
                property_values[entry["name"] + "()"] = bool(
                    contract.get_function_by_signature(entry["name"] + "()")().call(
                        {"from": _checksum(session.property_sender)}))
            except Exception as exc:
                property_values[entry["name"] + "()"] = {"error": str(exc)[:200]}
        role_addresses = []
        for key, value in views["view_values"].items():
            signature = key.rsplit(":", 1)[-1]
            if (re.fullmatch(r"(?:owner|admin|governor|controller|operator|manager|guardian)\(\)",
                             signature, re.IGNORECASE) and
                    isinstance(value, str) and Web3.is_address(value) and
                    int(value, 16) != 0):
                role_addresses.append({"getter": signature, "address": value.lower()})
        return {"status": "observed", "deployment_block": int(receipt.blockNumber),
                "view_values": views["view_values"], "view_count": views["observed_view_count"],
                "tracked_contract_types": views["tracked_contract_types"],
                "role_addresses": role_addresses,
                "guard_predicate_probes": probes,
                "initial_properties": property_values,
                "limitations": "private state is not read directly; constructor and Slither evidence remain static inference"}
    finally:
        session.rpc("evm_revert", [snapshot])


def replay_seed(project: str, candidate: dict[str, Any], transactions: list[dict[str, Any]],
                *, session: AnvilSession | None = None,
                dependency_hints: list[dict[str, Any]] | None = None,
                runtime_constraints: bool = False) -> dict[str, Any]:
    """每个种子从相同创世状态重放；属性调用使用 Echidna 的 psender。"""
    owned = session is None
    session = session or AnvilSession(project=project).__enter__()
    deployment_snapshot = None
    try:
        deployment_snapshot = session.rpc("evm_snapshot", [])
        contract, deploy_receipt = _deploy(session, project)
        deployment_block = session.web3.eth.get_block(deploy_receipt.blockNumber)
        artifact = read_json(PROJECTS[project]["artifact"])
        contract_abis = artifact.get("contract_abis", {})
        initial_state = _state_view_snapshot(session.web3, contract, contract_abis,
                                             sender=session.deployer)
        property_name = candidate.get("property", "")
        if not property_name:
            property_context = next(p for p in candidate["context"]["properties"]
                                    if p["property_id"] == candidate["property_id"])
            property_name = property_context["property_abi"]
        property_signature = property_name.rsplit(".", 1)[-1]
        if not property_signature.endswith("()"):
            property_signature += "()"
        property_context = next((item for item in candidate.get("context", {}).get("properties", [])
                                 if item.get("property_id") == candidate.get("property_id")), {})
        assertion_trigger = (candidate.get("assertion_trigger") or
                              property_context.get("assertion_trigger"))
        assertion_signature = (
            assertion_trigger.get("abi_signature")
            if property_context.get("property_kind") == "assertion_test" and
            assertion_trigger and assertion_trigger.get("seed_compatible") else None)
        predicate_getter_specs = _property_getter_specs(
            property_context, contract, contract_abis,
            project=project,
            property_sender=session.property_sender)
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
                    prop_fn.call({"from": _checksum(session.property_sender)}))
            except Exception as exc:
                initial_property_values[tested_property] = None
                initial_property_errors[tested_property] = f"{type(exc).__name__}: {str(exc)[:200]}"
        if assertion_signature:
            assertion_initial = _call_assertion_target(session, contract, assertion_signature)
            initial_property_values[property_signature] = assertion_initial.get("result")
            if assertion_initial["status"] == "assertion_call_error":
                initial_property_errors[property_signature] = json.dumps(
                    assertion_initial, ensure_ascii=False)
        initial_predicate_getters = _observe_property_getters(
            session.web3, contract, contract_abis, predicate_getter_specs,
            property_sender=session.property_sender)
        records = []
        resolved_transactions: list[dict[str, Any]] = []
        prior_events: list[list[dict[str, Any]]] = []
        actions = {item["abi_signature"]: item for item in property_context.get("candidate_actions", [])
                   if item.get("abi_signature")}
        valid = bool(transactions)
        violation = None
        initial_violations = sorted(name for name, value in initial_property_values.items()
                                    if value is False)
        if initial_property_values.get(property_signature) is False:
            violation = {"transaction_index": 0, "property": property_signature,
                         "initial_state": True}
        last_state = initial_state
        for index, tx in enumerate(transactions, start=1):
            action = actions.get(tx["function"], {})
            static_guards = slither_guard_evidence(action)
            args, bindings, binding_errors = _resolve_event_arguments(
                tx, action, prior_events, dependency_hints or [],
                [{item.get("name"): value for item, value in zip(
                    actions.get(previous["function"], {}).get("abi_inputs", []),
                    previous["arguments"])} for previous in resolved_transactions],
                infer_object_ids=runtime_constraints)
            if binding_errors:
                valid = False
                records.append({"index": index, "function": tx["function"],
                                "status": "dependency_unresolved", "dependency_errors": binding_errors,
                                "prior_events": prior_events[-2:]})
                break
            effective_tx = {**tx, "arguments": args}
            resolved_transactions.append(effective_tx)
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
            fn = contract.get_function_by_signature(signature)(*args)
            call_data = fn._encode_transaction_data()
            rpc_tx = {"from": sender, "to": contract.address, "data": call_data,
                      "value": hex(int(tx["value_wei"])),
                      "gas": hex(session.max_transaction_gas),
                      "gasPrice": "0x0"}
            try:
                tx_hash = session.web3.eth.send_transaction(rpc_tx)
                receipt = session.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            except Exception as exc:
                valid = False
                records.append({"index": index, "function": signature, "sender": sender,
                                "status": "rpc_error", "error": str(exc)[:500]})
                break
            try:
                trace = _trace_effects(session, tx_hash)
                events = _receipt_events(session.web3, receipt, contract_abis, contract.abi)
            except Exception as exc:
                trace = {"internal_errors": [], "changed_storage_slot_count": None,
                         "balance_changes": [],
                         "trace_error": f"{type(exc).__name__}: {str(exc)[:300]}",
                         "top_level_output": None}
                events = []
                valid = False
            # 只有没有内部回滚的交易事件才可作为后续对象绑定/状态查询的来源。
            prior_events.append(events if receipt.status == 1 and not trace["internal_errors"] else [])
            state_after = _state_view_snapshot(session.web3, contract, contract_abis,
                                               sender=session.deployer)
            effect = _observed_effect_status(
                candidate.get("context", {}), candidate.get("property_id", ""),
                signature, last_state, state_after)
            prop_result: bool | None = None
            prop_error = None
            property_values: dict[str, bool | None] = {}
            property_errors: dict[str, str] = {}
            target_assertion_failure = bool(
                assertion_signature == signature and receipt.status != 1 and
                _decode_revert_reason(trace.get("top_level_output")) == "Panic(0x1)")
            if receipt.status == 1:
                for tested_property in property_signatures:
                    try:
                        prop_fn = contract.get_function_by_signature(tested_property)()
                        property_values[tested_property] = bool(
                            prop_fn.call({"from": _checksum(session.property_sender)}))
                    except Exception as exc:
                        property_values[tested_property] = None
                        property_errors[tested_property] = f"{type(exc).__name__}: {str(exc)[:200]}"
                if assertion_signature:
                    assertion_result = ("target_assertion_failed" if target_assertion_failure else
                                        _call_assertion_target(session, contract, assertion_signature))
                    if isinstance(assertion_result, dict):
                        property_values[property_signature] = assertion_result.get("result")
                        if assertion_result["status"] == "assertion_call_error":
                            property_errors[property_signature] = json.dumps(
                                assertion_result, ensure_ascii=False)
                    else:
                        property_values[property_signature] = False
                        property_errors[property_signature] = "Panic(0x1): selected target assertion failed"
                prop_result = property_values.get(property_signature)
                prop_error = property_errors.get(property_signature)
                predicate_getter_values = _observe_property_getters(
                    session.web3, contract, contract_abis, predicate_getter_specs,
                    property_sender=session.property_sender)
            else:
                if target_assertion_failure:
                    property_values[property_signature] = False
                    property_errors[property_signature] = "Panic(0x1): selected target assertion failed"
                    prop_result = False
                    prop_error = property_errors[property_signature]
                predicate_getter_values = []
            if receipt.status != 1 and not target_assertion_failure:
                valid = False
                try:
                    session.web3.eth.call(rpc_tx)
                except Exception as exc:
                    prop_error = f"tx_revert: {type(exc).__name__}: {str(exc)[:300]}"
            expected_outcome = tx.get("expected_outcome")
            internal_revert = bool(trace["internal_errors"])
            if internal_revert and expected_outcome != "rejection" and not target_assertion_failure:
                valid = False
            if expected_outcome == "rejection" and not internal_revert and not target_assertion_failure:
                valid = False
            if (expected_outcome == "state_change" and trace["changed_storage_slot_count"] == 0
                    and not target_assertion_failure):
                valid = False
            if (receipt.status == 1 and not internal_revert and
                    effect["status"] == "not_observed" and
                    signature != assertion_signature):
                # The target function has Slither-backed writes whose public getter
                # is observed, but none changed. This catches wrappers that swallow
                # an internal revert while returning success to the outer caller.
                valid = False
            execution_class = ("target_assertion_failure" if target_assertion_failure else
                               "trace_unavailable" if trace.get("trace_error") else
                               "outer_revert" if receipt.status != 1 else
                               "expected_rejection" if internal_revert and expected_outcome == "rejection" else
                               "unexpected_internal_revert" if internal_revert else
                               "state_established" if trace["changed_storage_slot_count"] else
                               "no_persistent_state_change")
            runtime_observations: list[dict[str, Any]] = []
            repair_proposal = None
            if (runtime_constraints and execution_class in {
                    "outer_revert", "unexpected_internal_revert", "trace_unavailable"}):
                runtime_observations = _parameterized_getter_observations(
                    session.web3, state_after, contract_abis, prior_events[:-1],
                    transaction_index=index, sender=session.deployer)
                repair_proposal = propose_numeric_repair(
                    action.get("abi_inputs", []), args, runtime_observations,
                    _solidity_error_texts(trace, prop_error),
                    static_guards=static_guards,
                    source_excerpt=str(action.get("source_excerpt") or ""))
                if repair_proposal:
                    repair_proposal["transaction_index"] = index
            if prop_result is False and violation is None:
                violation = {"transaction_index": index, "property": property_signature}
            other_violations = sorted(name for name, value in property_values.items()
                                      if value is False and name != property_signature)
            records.append({
                "index": index, "function": signature, "arguments": args,
                "argument_bindings": bindings,
                "slither_preconditions": static_guards,
                "slither_source_excerpt": action.get("source_excerpt"),
                "sender": sender, "value_wei": tx["value_wei"],
                "delay_seconds": tx.get("delay_seconds", 0),
                "delay_blocks": tx.get("delay_blocks", 0),
                "tx_hash": tx_hash.hex(), "block_number": receipt.blockNumber,
                "status": "success" if receipt.status == 1 else "reverted",
                "gas_used": receipt.gasUsed,
                "execution_class": execution_class,
                "expected_outcome": expected_outcome,
                "internal_errors": trace["internal_errors"],
                "internal_call_trace": trace.get("internal_call_trace"),
                "changed_storage_slot_count": trace["changed_storage_slot_count"],
                "balance_changes": trace.get("balance_changes", []),
                "trace_error": trace.get("trace_error"),
                "events": events,
                "observed_view_state_changed": last_state["fingerprint"] != state_after["fingerprint"],
                "view_state_changes": _view_state_delta(last_state, state_after),
                "observed_view_count": state_after["observed_view_count"],
                "tracked_contract_count": state_after["tracked_contract_count"],
                "tracked_contract_types": state_after["tracked_contract_types"],
                "observed_effect_status": effect["status"],
                "expected_effect_states": effect["expected_states"],
                "observed_effect_states": effect["observed_states"],
                "changed_effect_states": effect["changed_states"],
                "unobserved_effect_states": effect.get("missing_states", []),
                "execution_effect_error": (
                    "internal call reverted without an explicit rejection expectation"
                    if execution_class == "unexpected_internal_revert" else
                    "expected rejection did not occur" if expected_outcome == "rejection" and not internal_revert else
                    "expected state change was not observed" if expected_outcome == "state_change" and
                    trace["changed_storage_slot_count"] == 0 else
                    "expected Slither-backed write was not observed"
                    if effect["status"] == "not_observed" and not internal_revert else None),
                "state_fingerprint_before": last_state["fingerprint"],
                "state_fingerprint_after": state_after["fingerprint"],
                "target_property": prop_result,
                "assertion_check": (property_values.get(property_signature)
                                    if assertion_signature else None),
                "assertion_failure_scope": (
                    "selected_target_function" if target_assertion_failure else
                    "not_target_assertion" if assertion_signature and receipt.status != 1 else None),
                "property_error": prop_error,
                "predicate_getter_values": predicate_getter_values,
                "runtime_constraint_observations": runtime_observations,
                "constraint_repair_proposal": repair_proposal,
                "all_property_values": property_values,
                "all_property_errors": property_errors,
                "other_property_violations_during_prevalidation": other_violations,
            })
            last_state = state_after
            if receipt.status != 1 and not target_assertion_failure:
                break
        session.rpc("evm_revert", [deployment_snapshot])
        deployment_snapshot = None
        target_state = _target_property_state(
            property_signature, initial_property_values,
            initial_predicate_getters, records)
        trajectory_by_index = {int(row.get("transaction_index", 0)): row
                               for row in target_state.get("trajectory", [])}
        for tx_record in records:
            trajectory = trajectory_by_index.get(int(tx_record.get("index", -1)), {})
            tx_record["changed_predicate_getters"] = trajectory.get(
                "changed_predicate_getters", [])
            tx_record["property_related_state_changed"] = bool(
                tx_record["changed_predicate_getters"])
        return {"project": project, "contract_address": contract.address,
                "deployment_status": "success" if deploy_receipt.status == 1 else "failed",
                "candidate_id": candidate["candidate_id"],
                "target_property_test_mode": "assertion" if assertion_signature else "boolean_property",
                "replay_status": "executable" if valid else "replay_failed",
                "target_property_violation": violation,
                "initial_property_values": initial_property_values,
                "initial_property_errors": initial_property_errors,
                "initial_property_violations": initial_violations,
                "initial_predicate_getters": initial_predicate_getters,
                "target_property_state": target_state,
                "environment": {"chain_id": session.chain_id,
                                "initial_timestamp": session.initial_timestamp,
                                "initial_block_number": session.initial_block_number,
                                "deployment_timestamp": int(deployment_block["timestamp"]),
                                "deployment_block_number": int(deployment_block["number"]),
                                "deployer": session.deployer.lower(),
                                "property_sender": session.property_sender.lower(),
                                "sender_pool": [item.lower() for item in session.senders],
                                "gas_price_wei": 0,
                "evm_revision": "shanghai",
                                "gas_limit_per_transaction": session.max_transaction_gas,
                                "contract_address": contract.address.lower()},
                "transactions": records, "resolved_transactions": resolved_transactions}
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


def _project_runtime(project: str) -> dict[str, Any]:
    config = PROJECTS.get(project, {})
    deployment = config.get("deployment", {})
    execution = config.get("execution", {})
    return {
        "deployer": deployment.get("deployer", execution.get("deployer", DEPLOYER)),
        "contract_address": deployment.get(
            "contract_address", execution.get("contract_address", HARNESS_ADDRESS)),
        "property_sender": config.get("property", {}).get("sender", PROPERTY_SENDER),
        "senders": config.get("senders") or SENDERS,
        "chain_id": int(execution.get("chain_id", CHAIN_ID)),
        "timestamp": int(execution.get("deployment_timestamp", INITIAL_TIMESTAMP)),
        "block_number": int(execution.get("deployment_block_number", INITIAL_BLOCK_NUMBER)),
        "balance": int(execution.get("initial_balance", INITIAL_BALANCE)),
        "max_gas": int(execution.get("max_transaction_gas", MAX_TX_GAS)),
    }


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
    sequence = to_echidna_sequence(
        candidate, transactions, context,
        contract_address=_project_runtime(project)["contract_address"])
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
                campaign_deadline: float | None = None,
                test_mode: str = "property",
                property_prefix: str | None = None,
                filter_functions: list[str] | None = None,
                seq_len: int = 8,
                shrink_limit: int = 1,
                stop_on_fail: bool = False,
                disable_slither: bool = True,
                sender_pool: list[str] | None = None,
                working_directory: Path | None = None) -> dict[str, Any]:
    if not Path(ECHIDNA_BIN).is_file() and shutil.which(ECHIDNA_BIN) is None:
        raise FileNotFoundError(f"找不到 Echidna 2.3.2：{ECHIDNA_BIN}")
    conf = PROJECTS[project]
    project_data = {"Request": {
        "target": "sol/真实项目/Request/src/contracts/test/EchidnaERC20CommerceEscrowWrapper.sol",
        "contract": "EchidnaERC20CommerceEscrowWrapper",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/"},
        "OpenNFTs": {
        "target": "sol/真实项目/OpenNFTs/tests/echidna/OpenAutoMarketEx.e.sol",
        "contract": "OpenAutoMarketExFuzz",
        "remaps": "OpenNFTs/=sol/真实项目/OpenNFTs/"},
        "Immutable": {
        "target": "sol/真实项目/Immutable/test/token/erc721/fuzz/ERC721PsiV2.Echidna.sol",
        "contract": "ERC721PsiV2Echidna",
        "remaps": ("openzeppelin-contracts-4/=sol/真实项目/依赖/OpenZeppelin4/contracts/ "
                   "openzeppelin-contracts-5/=sol/真实项目/依赖/OpenZeppelin561/contracts/")},
        "Hokusai": {
        "target": "sol/真实项目/Hokusai/contracts/echidna/EchidnaHokusaiToken.sol",
        "contract": "EchidnaHokusaiToken",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin4/contracts/"},
        "BeeStorage": {
        "target": "sol/真实项目/BeeStorage/src/echidna/EchidnaSystemHarness.sol",
        "contract": "EchidnaSystemHarness",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin482/contracts/"},
        "Kink": {
        "target": "sol/真实项目/Kink/echidna/KinkPoolEchidna.sol",
        "contract": "KinkPoolEchidna",
        "remaps": "@openzeppelin/contracts/=sol/真实项目/依赖/OpenZeppelin550/contracts/",
        "solc_args": "--optimize --via-ir"},
        "Drips": {
        "target": "sol/真实项目/DripsSCFuzzBench",
        "contract": "Echidna",
        "remaps": None,
        "foundry": True}}
    dynamic_target = conf.get("fuzzer_target")
    if dynamic_target:
        spec = {"target": dynamic_target, "contract": conf["contract"],
                "remaps": conf.get("remaps"), "solc_args": conf.get("solc_args"),
                "foundry": conf.get("foundry", False)}
    else:
        spec = project_data[project]
    compiler_config = corpus_root.parent / f"{project}-{corpus_root.name}-crytic-compile.json"
    configured_solc_version = str(conf.get("solc_version", "0.8.20"))
    solc_candidates = [conf.get("solc"), os.environ.get("SOLC_BIN"),
                       str(Path.home() / f".solc-select/artifacts/solc-{configured_solc_version}/solc-{configured_solc_version}"),
                       str(Path.home() / ".solc-select/artifacts/solc-0.8.20/solc-0.8.20"),
                       shutil.which("solc"), "solc"]
    solc = next((item for item in solc_candidates
                 if item and (item == "solc" or Path(item).is_file())), "solc")
    compiler_config_data = {"solc": solc}
    if spec.get("remaps"):
        compiler_config_data["solc_remaps"] = spec["remaps"]
    if spec.get("solc_args"):
        compiler_config_data["solc_args"] = spec["solc_args"]
    compiler_config.write_text(json.dumps(compiler_config_data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
    echidna_config = corpus_root.parent / f"{project}-{corpus_root.name}-echidna.yaml"
    runtime = _project_runtime(project)
    profile_echidna = conf.get("echidna", {})
    if filter_functions is None and profile_echidna.get("filter_functions") is not None:
        filter_functions = profile_echidna["filter_functions"]
    if filter_functions is None and profile_echidna.get("exclude_functions"):
        abi = read_json(conf["artifact"]).get("abi", [])
        excluded = set(profile_echidna["exclude_functions"])
        filter_functions = []
        for entry in abi:
            if entry.get("type") != "function":
                continue
            signature = entry["name"] + "(" + ",".join(
                item["type"] for item in entry.get("inputs", [])) + ")"
            qualified = f"{conf['contract']}.{signature}"
            if qualified not in excluded and signature not in excluded:
                filter_functions.append(qualified)
    active_senders = list(dict.fromkeys(item.lower() for item in
                                        (sender_pool or runtime["senders"])))
    property_sender = runtime["property_sender"].lower()
    config_lines = [
        f'prefix: "{property_prefix or profile_echidna.get("prefix") or property_name}"', "workers: 1",
        f'testMode: "{test_mode}"',
        f'corpusDir: "{corpus_root}"',
        f'contractAddr: "{runtime["contract_address"].lower()}"',
        f'deployer: "{runtime["deployer"].lower()}"',
        f'psender: "{property_sender}"',
        "sender: [" + ", ".join(f'"{item}"' for item in active_senders) + "]",
        f"balanceAddr: {runtime['balance']}", "balanceContract: 0",
        f"testMaxGas: {runtime['max_gas']}", f"propMaxGas: {runtime['max_gas']}",
        "maxGasprice: 0", "maxTimeDelay: 86400", "maxBlockDelay: 86400",
        "coverage: true", f"stopOnFail: {'true' if stop_on_fail else 'false'}"]
    if filter_functions is not None:
        config_lines.append("filterBlacklist: false")
        config_lines.append("filterFunctions: [" + ", ".join(
            json.dumps(item, ensure_ascii=False) for item in filter_functions) + "]")
    config_lines.append("")
    echidna_config.write_text("\n".join(config_lines), encoding="utf-8")
    crytic_args = ("--foundry-compile-all " if spec.get("foundry") else "") + \
        f"--config-file {compiler_config.resolve()}"
    command_target = spec["target"]
    if spec.get("foundry") and working_directory is not None:
        # CryticCompile/Fuzz runs for Foundry projects from the project root.
        # Keep the target relative (`.`) as Foundry smoke runs do; an absolute
        # path makes CryticCompile mis-resolve generated `foundry-pp` units.
        command_target = "."
    command = [ECHIDNA_BIN, command_target, "--contract", spec["contract"],
               "--crytic-args", crytic_args,
               "--config", str(echidna_config.resolve()),
               "--test-limit", str(test_limit), "--seq-len", str(seq_len),
               "--shrink-limit", str(shrink_limit),
               "--seed", str(seed), "--workers", "1", "--format", "text",
               "--deployer", runtime["deployer"], "--contract-addr", runtime["contract_address"],
               *sum((["--sender", item] for item in active_senders), [])]
    if disable_slither:
        command.append("--disable-slither")
    corpus_root.mkdir(parents=True, exist_ok=True)
    initial_corpus_files = sorted(path.name for path in
                                  (corpus_root / "coverage").glob("*.txt"))
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
    environment = {**os.environ,
                   "SOLC_VERSION": configured_solc_version,
                   "PATH": str(ROOT / ".tools/foundry/bin") + os.pathsep +
                           "/home/skk/miniconda3/envs/contract-fuzz/bin:" +
                           os.environ.get("PATH", "")}
    if spec.get("foundry"):
        build_root = corpus_root.parent / "foundry-build"
        environment["FOUNDRY_OUT"] = str(build_root / "out")
        environment["FOUNDRY_CACHE_PATH"] = str(build_root / "cache")
    try:
        if working_directory is not None:
            run_cwd = Path(working_directory).resolve()
        elif spec.get("foundry") and conf.get("source_root"):
            # Foundry projects with generated or relative import units must be
            # compiled from their project root, as Foundry smoke invocations do.
            run_cwd = (ROOT / conf["source_root"]).resolve()
        else:
            run_cwd = ROOT
        if not run_cwd.is_dir():
            raise FileNotFoundError(f"Echidna 工作目录不存在：{run_cwd}")
        result = subprocess.run(command, cwd=run_cwd, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                timeout=min(timeout, remaining) if remaining is not None else timeout,
                                env=environment)
        exit_code = result.returncode
        full_output = result.stdout
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        exit_code = None
        timed_out = True
        partial = exc.stdout or ""
        full_output = partial.decode("utf-8", errors="replace") if isinstance(partial, bytes) else partial
    elapsed = round(time.monotonic() - started, 3)
    full_log_path = (corpus_root / "echidna.log").resolve()
    full_log_path.write_text(full_output, encoding="utf-8")
    output = full_output[-18000:]
    result_prefix = property_name if property_name.endswith("_") else property_name + ":"
    property_results = [line.strip() for line in full_output.splitlines()
                        if line.strip().startswith(result_prefix)]
    if test_mode == "assertion":
        target_name = property_name.split("(", 1)[0].rsplit(".", 1)[-1]
        property_results = [line.strip() for line in full_output.splitlines()
                            if target_name in line and ":" in line and
                            any(token in line.lower() for token in
                                ("passing", "failed", "falsified", "💥"))]
        property_failures = [line for line in property_results
                             if "passing" not in line.lower() and
                             any(token in line.lower() for token in
                                 ("failed", "falsified", "💥"))]
    else:
        target_falsifications = [line.strip() for line in full_output.splitlines()
                                 if re.search(r"\bTest\s+" + re.escape(property_name) +
                                              r"\s+falsified\b", line, re.IGNORECASE)]
        property_results = list(dict.fromkeys(target_falsifications + property_results))
        property_failures = [line for line in property_results
                             if any(token in line.lower() for token in
                                    (": failed", "falsified", "💥"))]
    return {"project": project, "property_name": property_name,
            "test_mode": test_mode,
            "command": command, "exit_code": exit_code,
            "status": "timeout" if timed_out else "completed",
            "timed_out": timed_out,
            "seed": seed, "test_limit": test_limit,
            "seq_len": seq_len, "shrink_limit": shrink_limit,
            "elapsed_seconds": elapsed, **echidna_corpus_evidence(full_output),
            "initial_corpus_file_count": len(initial_corpus_files),
            "initial_corpus_files": initial_corpus_files,
             "full_log_path": str(full_log_path.relative_to(ROOT)),
            "stop_on_fail": stop_on_fail,
            "target_property_results": property_results,
            "property_failures": property_failures,
            "first_property_failure_observed_seconds": elapsed if property_failures else None,
            "property_failure_time_is_upper_bound": bool(property_failures and not stop_on_fail),
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

