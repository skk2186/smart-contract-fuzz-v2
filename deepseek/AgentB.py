#!/usr/bin/env python3
"""Agent B：将 Agent A 序列实例化为具有完整 ABI 参数与发送者的交易。"""

from __future__ import annotations

import json
import re
from typing import Any

from deepseek接口 import call_json


SENDERS = [f"0x{i:040x}" for i in (0x10000, 0x20000, 0x30000, 0x40000, 0x50000)]
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def normalize_argument(kind: str, value: Any) -> Any:
    if kind == "address":
        if not isinstance(value, str) or not ADDRESS_RE.fullmatch(value):
            raise ValueError(f"非法 address 参数：{value!r}")
        return value.lower()
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"bool 参数必须是 JSON 布尔值：{value!r}")
        return value
    match = re.fullmatch(r"(u?int)([0-9]*)", kind)
    if not match:
        raise ValueError(f"暂不支持原生语料编码类型：{kind}")
    bits = int(match.group(2) or "256")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{kind} 参数必须是十进制整数或字符串")
    if isinstance(value, str) and not re.fullmatch(r"-?[0-9]+", value):
        raise ValueError(f"{kind} 参数不是十进制整数：{value!r}")
    number = int(value)
    if match.group(1) == "uint":
        low, high = 0, (1 << bits) - 1
    else:
        low, high = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
    if not low <= number <= high:
        raise ValueError(f"参数 {number} 超出 {kind} 范围 [{low}, {high}]")
    return number


def _abi_value(kind: str, value: Any) -> dict[str, Any]:
    normalized = normalize_argument(kind, value)
    if kind == "address":
        return {"tag": "AbiAddress", "contents": str(int(normalized, 16))}
    if kind == "bool":
        return {"tag": "AbiBool", "contents": normalized}
    match = re.fullmatch(r"(u?int)([0-9]*)", kind)
    bits = int(match.group(2) or "256")
    tag = "AbiUInt" if match.group(1) == "uint" else "AbiInt"
    return {"tag": tag, "contents": [bits, str(normalized)]}


def _validator(context: dict[str, Any], candidate: dict[str, Any], feedback: str | None):
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    action_index = {action["abi_signature"]: action for action in property_context["candidate_actions"]
                    if action.get("seed_compatible") and action.get("abi_signature")}
    expected_steps = candidate["steps"]

    def validate(data: dict[str, Any]) -> None:
        if data.get("property_id") != candidate["property_id"]:
            raise ValueError("Agent B 返回了错误的 property_id")
        if data.get("candidate_id") != candidate["candidate_id"]:
            raise ValueError("Agent B 返回了错误的 candidate_id")
        transactions = data.get("transactions")
        if not isinstance(transactions, list) or len(transactions) != len(expected_steps):
            raise ValueError("交易数必须与 Agent A 规划完全一致")
        for expected, tx in zip(expected_steps, transactions):
            signature = expected["function"]
            if tx.get("function") != signature:
                raise ValueError(f"Agent B 改变了规划函数：{signature}")
            action = action_index[signature]
            params = action["abi_inputs"]
            arguments = tx.get("arguments")
            if not isinstance(arguments, list) or len(arguments) != len(params):
                raise ValueError(f"{signature} 参数数量不匹配")
            tx["arguments"] = [normalize_argument(param["type"], value)
                                for param, value in zip(params, arguments)]
            sender = tx.get("sender")
            if not isinstance(sender, str) or sender.lower() not in SENDERS:
                raise ValueError(f"sender 必须来自固定测试账户池：{sender!r}")
            tx["sender"] = sender.lower()
            value_wei = tx.get("value_wei", "0")
            if isinstance(value_wei, bool) or not re.fullmatch(r"[0-9]+", str(value_wei)):
                raise ValueError("value_wei 必须是非负十进制整数")
            tx["value_wei"] = str(int(value_wei))
            if not action.get("payable") and int(tx["value_wei"]) != 0:
                raise ValueError(f"非 payable 函数 {signature} 的 value 必须为 0")
            for field in ("delay_seconds", "delay_blocks"):
                value = tx.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 86400:
                    raise ValueError(f"{field} 必须是 0 到 86400 之间的整数")
                tx[field] = value
        data["execution_feedback"] = feedback
    return validate


def instantiate_candidate(context: dict[str, Any], candidate: dict[str, Any], *,
                          feedback: str | None = None, attempt: int = 1):
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    actions = {action["abi_signature"]: action for action in property_context["candidate_actions"]
               if action.get("seed_compatible") and action.get("abi_signature")}
    sequence = []
    for step in candidate["steps"]:
        action = actions[step["function"]]
        sequence.append({"function": step["function"], "rationale": step.get("rationale"),
                         "inputs": action["abi_inputs"],
                         "payable": action["payable"],
                         "matched_states": action["matched_states"],
                         "effect_evidence": action["effect_evidence"]})
    selected_actions = [actions[step["function"]] for step in candidate["steps"]]
    selected_full_names = {action["function"] for action in selected_actions}
    relevant_unresolved = [item for item in property_context.get("unresolved_effect_actions", [])
                           if item.get("function") in selected_full_names][:8]
    property_prompt = {key: property_context.get(key) for key in
                       ("property_id", "property", "property_predicate", "read_states",
                        "property_write_states", "analysis_status", "context_status",
                        "dependency_status", "prerequisite_state_closure", "unknowns")}
    property_prompt["planned_actions"] = selected_actions
    property_prompt["unresolved_effect_actions_for_planned_actions"] = relevant_unresolved
    prompt = {
        "task": "为指定交易序列生成可 ABI 编码并可回放的具体多交易种子。",
        "rules": [
            "必须逐笔遵循计划的 function 顺序，不能增删交易。",
            "arguments 必须按 inputs 顺序提供，uint/int 使用十进制字符串，address 使用 40 位十六进制地址，bool 使用 JSON 布尔值。",
            "sender 只能从 sender_pool 选择；payable=false 时 value_wei 必须为 0。",
            "严格满足函数源码、guard、状态依赖和目标谓词；静态不确定项应写入 assumptions。",
            "不要声称已验证可执行；验证器会实际回放并检查目标属性。",
            "严格输出 JSON 对象，字段为 property_id、candidate_id、transactions、assumptions。",
        ],
        "property": property_prompt,
        "candidate": candidate,
        "transactions_to_instantiate": sequence,
        "sender_pool": SENDERS,
        "environment": {"chain_id": 31337, "block_timestamp_policy": "Anvil 默认时间逐交易递增",
                        "gas_limit_per_transaction": 12500000},
        "previous_verifier_feedback": feedback,
        "attempt": attempt,
    }

    def validate(data: dict[str, Any]) -> None:
        _validator(context, candidate, feedback)(data)

    return call_json(
        system="你是智能合约交易参数具体化器。只根据输入 ABI 与源码作答，必须输出合法 JSON。",
        user=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
        tag=f"AgentB_{context['project']}_{candidate['candidate_id']}_try{attempt}",
        max_tokens=4096, validator=validate)


def to_echidna_sequence(candidate: dict[str, Any], transactions: list[dict[str, Any]],
                        context: dict[str, Any]) -> list[dict[str, Any]]:
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    actions = {action["abi_signature"]: action for action in property_context["candidate_actions"]
               if action.get("seed_compatible") and action.get("abi_signature")}
    sequence = []
    for tx in transactions:
        action = actions[tx["function"]]
        short_signature = tx["function"]
        name = short_signature.split("(", 1)[0]
        args = [_abi_value(item["type"], value)
                for item, value in zip(action["abi_inputs"], tx["arguments"])]
        sequence.append({
            "call": {"tag": "SolCall", "contents": [name, args]},
            "delay": [hex(tx["delay_seconds"]), hex(tx["delay_blocks"])],
            "dst": "0x00a329c0648769A73afAc7F9381E08FB43dBEA72",
            "gas": 12500000,
            "gasprice": "0x0",
            "src": tx["sender"],
            "value": hex(int(tx["value_wei"])),
        })
    return sequence

