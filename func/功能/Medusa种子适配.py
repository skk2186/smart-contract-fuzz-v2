#!/usr/bin/env python3
"""把冻结的 V2 有效交易序列编码为 Medusa 1.5.1 原生 corpus。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

try:
    from eth_abi import encode as abi_encode
    from eth_utils import keccak, to_checksum_address
except ImportError as exc:  # pragma: no cover - depends on the selected runtime
    raise SystemExit("缺少 eth-abi / eth-utils；请使用项目已固定的 Python 环境。") from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_type(item: dict[str, Any]) -> str:
    raw = item["type"]
    if not raw.startswith("tuple"):
        return raw
    suffix = raw[len("tuple") :]
    components = item.get("components")
    if not isinstance(components, list):
        raise ValueError("ABI tuple 缺少 components")
    return "(" + ",".join(_canonical_type(part) for part in components) + ")" + suffix


def _abi_value(item: dict[str, Any], value: Any) -> Any:
    """把 JSON 中的可审计字面量转成 ABI 编码器要求的字节/元组类型。"""
    raw_type = item["type"]
    array_match = __import__("re").fullmatch(r"(.*)(\[[0-9]*\])", raw_type)
    if array_match:
        if not isinstance(value, (list, tuple)):
            raise ValueError(f"ABI 数组参数 {raw_type} 必须是列表")
        subtype = array_match.group(1)
        element = dict(item, type=subtype)
        return [_abi_value(element, part) for part in value]
    if raw_type.startswith("tuple"):
        components = item.get("components", [])
        if isinstance(value, dict):
            value = [value.get(component.get("name")) for component in components]
        if not isinstance(value, (list, tuple)) or len(value) != len(components):
            raise ValueError("ABI tuple 参数与 components 结构不一致")
        return tuple(_abi_value(component, part) for component, part in zip(components, value))
    if raw_type == "bytes" or __import__("re").fullmatch(r"bytes[0-9]+", raw_type):
        if isinstance(value, str) and value.startswith("0x"):
            try:
                return bytes.fromhex(value[2:])
            except ValueError as exc:
                raise ValueError(f"非法十六进制 ABI bytes 值：{value}") from exc
        if isinstance(value, (bytes, bytearray)):
            return bytes(value)
        raise ValueError(f"ABI {raw_type} 值必须是 0x 十六进制字符串")
    return value


def _method_abi(abi: list[dict[str, Any]], signature: str) -> dict[str, Any]:
    matches = []
    for entry in abi:
        if entry.get("type") != "function":
            continue
        canonical = f"{entry.get('name')}({','.join(_canonical_type(x) for x in entry.get('inputs', []))})"
        if canonical == signature:
            matches.append(entry)
    if len(matches) != 1:
        raise ValueError(f"ABI 中未能唯一匹配函数签名：{signature}")
    return matches[0]


def _parse_wei(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("value_wei 不能为 bool")
    if isinstance(value, int):
        amount = value
    elif isinstance(value, str):
        amount = int(value, 16) if value.lower().startswith("0x") else int(value, 10)
    else:
        raise ValueError(f"不支持的 value_wei 类型：{type(value).__name__}")
    if amount < 0:
        raise ValueError("value_wei 不能为负数")
    return amount


def _norm_address(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} 必须是地址字符串")
    try:
        return to_checksum_address(value).lower()
    except ValueError as exc:
        raise ValueError(f"{field} 不是有效以太坊地址：{value}") from exc


def convert_seed(
    seed_path: Path,
    abi_path: Path,
    deployment_map_path: Path,
    output_directory: Path,
    gas_limit: int | None = None,
) -> dict[str, Any]:
    """转换单个冻结种子；不能可靠转换时只写 unsupported 清单，不写语料。"""
    original_bytes = seed_path.read_bytes()
    seed = json.loads(original_bytes)
    artifact_bytes = abi_path.read_bytes()
    artifact = json.loads(artifact_bytes)
    deployment_bytes = deployment_map_path.read_bytes()
    deployment = json.loads(deployment_bytes)
    abi = artifact.get("abi")
    if not isinstance(abi, list):
        raise ValueError("ABI artifact 缺少 abi 数组")
    if seed.get("replay_status") != "executable":
        raise ValueError("冻结种子 replay_status 不是 executable")
    environment = seed.get("environment")
    if not isinstance(environment, dict):
        raise ValueError("冻结种子缺少部署环境元数据")
    if gas_limit is None:
        gas_limit = int(environment.get("gas_limit_per_transaction", 0))
    if gas_limit <= 0:
        raise ValueError("缺少有效的 gas_limit_per_transaction")
    gas_price = _parse_wei(environment.get("gas_price_wei", 0))

    source_address = _norm_address(seed.get("contract_address"), "contract_address")
    source_to_medusa = {
        _norm_address(source, "source_to_medusa key"): _norm_address(target, "source_to_medusa value")
        for source, target in deployment.get("source_to_medusa", {}).items()
    }
    target_address = source_to_medusa.get(source_address)
    if target_address is None:
        raise ValueError(f"部署映射中没有冻结种子合约地址：{source_address}")

    allowed_senders = {
        _norm_address(item, "sender_addresses") for item in deployment.get("sender_addresses", [])
    }
    if not allowed_senders:
        raise ValueError("部署元数据未提供允许的 sender_addresses")

    resolved = seed.get("resolved_transactions")
    if not isinstance(resolved, list) or not resolved:
        raise ValueError("冻结种子缺少 resolved_transactions")
    observed = seed.get("transactions", [])
    observed_by_position = {i + 1: tx for i, tx in enumerate(observed) if isinstance(tx, dict)}
    corpus_sequence: list[dict[str, Any]] = []
    transaction_records: list[dict[str, Any]] = []
    sender_nonces: dict[str, int] = {}
    unsupported: list[dict[str, Any]] = []

    for position, tx in enumerate(resolved, start=1):
        try:
            signature = tx.get("function")
            arguments = tx.get("arguments")
            if not isinstance(signature, str) or not isinstance(arguments, list):
                raise ValueError("缺少 function 或 arguments")
            method = _method_abi(abi, signature)
            inputs = method.get("inputs", [])
            if len(inputs) != len(arguments):
                raise ValueError(f"ABI 参数个数 {len(inputs)} 与种子参数个数 {len(arguments)} 不一致")
            if observed_by_position.get(position, {}).get("status") != "success":
                raise ValueError("Phase 25 原始回放中该交易没有明确的 success 记录")
            types = [_canonical_type(item) for item in inputs]
            encoded_arguments = [_abi_value(item, value) for item, value in zip(inputs, arguments)]
            call_data = keccak(text=signature)[:4] + abi_encode(types, encoded_arguments)

            sender = _norm_address(tx.get("sender"), "sender")
            if sender not in allowed_senders:
                raise ValueError(f"sender 未列入部署元数据的 sender_addresses：{sender}")
            requested_to = tx.get("to", seed.get("contract_address"))
            source_to = _norm_address(requested_to, "transaction.to")
            mapped_to = source_to_medusa.get(source_to)
            if mapped_to is None:
                raise ValueError(f"未知目标地址没有部署映射：{source_to}")
            nonce = sender_nonces.get(sender, 0)
            sender_nonces[sender] = nonce + 1
            value_wei = _parse_wei(tx.get("value_wei", 0))
            block_delay = tx.get("delay_blocks", 0)
            timestamp_delay = tx.get("delay_seconds", 0)
            if not isinstance(block_delay, int) or block_delay < 0:
                raise ValueError("delay_blocks 必须是非负整数")
            if not isinstance(timestamp_delay, int) or timestamp_delay < 0:
                raise ValueError("delay_seconds 必须是非负整数")
            observed_tx = observed_by_position.get(position, {})
            observed_input = observed_tx.get("internal_call_trace", {}).get("input")
            if observed_input and "0x" + call_data.hex() != observed_input.lower():
                raise ValueError("ABI 编码结果与 Phase 25 原始交易 calldata 不一致")

            corpus_sequence.append(
                {
                    "call": {
                        "from": sender,
                        "to": mapped_to,
                        "nonce": nonce,
                        "value": hex(value_wei),
                        "gasLimit": gas_limit,
                        "gasPrice": hex(gas_price),
                        "gasFeeCap": "0x0",
                        "gasTipCap": "0x0",
                        "data": "0x" + call_data.hex(),
                    },
                    "blockNumberDelay": block_delay,
                    "blockTimestampDelay": timestamp_delay,
                }
            )
            transaction_records.append(
                {
                    "position": position,
                    "function": signature,
                    "arguments": arguments,
                    "resolved_argument_bindings": observed_tx.get("argument_bindings", []),
                    "source_target": source_to,
                    "medusa_target": mapped_to,
                    "sender": sender,
                    "nonce_assigned_for_fresh_chain": nonce,
                    "value_wei": str(value_wei),
                    "blockNumberDelay": block_delay,
                    "blockTimestampDelay": timestamp_delay,
                    "calldata": "0x" + call_data.hex(),
                    "calldata_sha256": hashlib.sha256(call_data).hexdigest(),
                    "original_observation_status": observed_tx.get("status"),
                    "original_internal_errors": observed_tx.get("internal_errors", []),
                }
            )
        except Exception as exc:  # preserve a reviewable failure reason per element
            unsupported.append({"position": position, "reason": str(exc)})

    manifest: dict[str, Any] = {
        "format": "medusa-1.5.1-call-sequence",
        "status": "supported" if not unsupported else "unsupported",
        "source_seed": str(seed_path),
        "source_seed_sha256": hashlib.sha256(original_bytes).hexdigest(),
        "abi_artifact": str(abi_path),
        "abi_artifact_sha256": hashlib.sha256(artifact_bytes).hexdigest(),
        "abi_sha256_canonical_json": hashlib.sha256(
            json.dumps(abi, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "deployment_metadata": str(deployment_map_path),
        "deployment_metadata_sha256": hashlib.sha256(deployment_bytes).hexdigest(),
        "deployment_mapping": deployment,
        "source_contract_address": source_address,
        "medusa_contract_address": target_address,
        "contract_name": artifact.get("contract"),
        "compiler_version": artifact.get("compiler"),
        "source_environment": environment,
        "execution_context_warnings": [
            "Medusa 1.5.1 的原生序列可保留每笔交易的区块/时间增量，但该版本没有配置绝对起始区块号和时间戳的选项；"
            "源环境已记录在清单，需结合目标语义判断是否影响本案例。"
        ] if environment.get("initial_block_number") or environment.get("initial_timestamp") else [],
        "original_transaction_count": len(resolved),
        "converted_transaction_count": len(corpus_sequence),
        "transactions": transaction_records,
        "unsupported": unsupported,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    sequences_directory = output_directory / "call_sequences"
    metadata_directory = output_directory / "metadata"
    metadata_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = metadata_directory / "seed_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not unsupported:
        sequences_directory.mkdir(parents=True, exist_ok=True)
        corpus_path = sequences_directory / "v2_seed.json"
        corpus_path.write_text(json.dumps(corpus_sequence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest["corpus_file"] = str(corpus_path)
        manifest["corpus_file_sha256"] = sha256_file(corpus_path)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif sequences_directory.exists():
        for old in sequences_directory.glob("*.json"):
            old.unlink()
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, required=True)
    parser.add_argument("--abi", type=Path, required=True)
    parser.add_argument("--deployment-map", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="corpusDirectory 根目录")
    parser.add_argument("--gas-limit", type=int, default=12_500_000)
    args = parser.parse_args(argv)
    try:
        result = convert_seed(args.seed, args.abi, args.deployment_map, args.out, args.gas_limit)
    except Exception as exc:
        print(json.dumps({"status": "unsupported", "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "manifest": str(args.out / "metadata/seed_manifest.json")}, ensure_ascii=False))
    return 0 if result["status"] == "supported" else 2


if __name__ == "__main__":
    raise SystemExit(main())
