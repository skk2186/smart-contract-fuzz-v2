#!/usr/bin/env python3
"""Agent B：将 Agent A 序列实例化为具有完整 ABI 参数与发送者的交易。"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from deepseek接口 import call_json
from 属性种子上下文 import compact_effect_evidence


SENDERS = [f"0x{i:040x}" for i in (0x10000, 0x20000, 0x30000, 0x40000, 0x50000)]
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
HARNESS_ADDRESS = "0xA647ff3c36cFab592509E13860ab8c4F28781a66"
PROPERTY_SENDER = "0x0000000000000000000000000000000000010000"


def normalize_argument(kind: str, value: Any) -> Any:
    array_match = re.fullmatch(r"(.+)\[\]", kind)
    if array_match:
        # Some historical model responses encoded a JSON array inside a JSON
        # string (for example, "[1, -1]"). Decode only valid JSON here; do not
        # evaluate Python expressions or rewrite individual array elements.
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except (json.JSONDecodeError, TypeError) as exc:
                raise ValueError(f"{kind} 参数字符串不是合法 JSON 数组：{value!r}") from exc
        if not isinstance(value, list):
            raise ValueError(f"{kind} 参数必须是 JSON 数组：{value!r}")
        element_kind = array_match.group(1)
        return [normalize_argument(element_kind, item) for item in value]
    if kind == "string":
        if not isinstance(value, str):
            raise ValueError(f"string 参数必须是 JSON 字符串：{value!r}")
        if len(value.encode("utf-8")) > 128:
            raise ValueError("string 参数 UTF-8 编码长度不得超过 128 字节")
        return value
    if kind == "address":
        if not isinstance(value, str) or not ADDRESS_RE.fullmatch(value):
            raise ValueError(f"非法 address 参数：{value!r}")
        return value.lower()
    if kind == "bool":
        if not isinstance(value, bool):
            raise ValueError(f"bool 参数必须是 JSON 布尔值：{value!r}")
        return value
    bytes_match = re.fullmatch(r"bytes([1-9]|[12][0-9]|3[0-2])", kind)
    if bytes_match:
        size = int(bytes_match.group(1))
        if (not isinstance(value, str) or
                not re.fullmatch(r"0x[0-9a-fA-F]{" + str(size * 2) + r"}", value)):
            raise ValueError(f"{kind} 参数必须是含 {size} 字节的 0x 十六进制字符串")
        return value.lower()
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
    array_match = re.fullmatch(r"(.+)\[\]", kind)
    if array_match:
        element_kind = array_match.group(1)
        integer_match = re.fullmatch(r"(u?int)([0-9]*)", element_kind)
        if not integer_match:
            raise ValueError(f"Echidna 动态数组原生语料暂不支持元素类型：{element_kind}")
        bits = int(integer_match.group(2) or "256")
        type_tag = "AbiUIntType" if integer_match.group(1) == "uint" else "AbiIntType"
        return {"tag": "AbiArrayDynamic",
                "contents": [{"tag": type_tag, "contents": bits},
                             [_abi_value(element_kind, item) for item in normalized]]}
    if kind == "string":
        escaped = '"'
        for byte in normalized.encode("utf-8"):
            if byte == 34:
                escaped += '\\"'
            elif byte == 92:
                escaped += "\\\\"
            elif byte == 10:
                escaped += "\\n"
            elif byte == 13:
                escaped += "\\r"
            elif byte == 9:
                escaped += "\\t"
            elif 32 <= byte < 127:
                escaped += chr(byte)
            else:
                escaped += f"\\{byte}\\&"
        return {"tag": "AbiString", "contents": escaped + '"'}
    if kind == "address":
        return {"tag": "AbiAddress", "contents": normalized}
    if kind == "bool":
        return {"tag": "AbiBool", "contents": normalized}
    if re.fullmatch(r"bytes([1-9]|[12][0-9]|3[0-2])", kind):
        size = int(kind[5:])
        byte_string = bytes.fromhex(normalized[2:])
        escaped = '"' + "".join(f"\\{byte}" for byte in byte_string) + '"'
        # Echidna 的 AbiBytes 长度单位是字节；原生 corpus 使用 [N, Haskell-string]。
        return {"tag": "AbiBytes", "contents": [size, escaped]}
    match = re.fullmatch(r"(u?int)([0-9]*)", kind)
    bits = int(match.group(2) or "256")
    tag = "AbiUInt" if match.group(1) == "uint" else "AbiInt"
    return {"tag": tag, "contents": [bits, str(normalized)]}


def _validator(context: dict[str, Any], candidate: dict[str, Any], feedback: str | None,
               fixed_prefix_transactions: list[dict[str, Any]] | None = None):
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    trigger = candidate.get("assertion_trigger") or property_context.get("assertion_trigger")
    action_index = {action["abi_signature"]: action for action in property_context["candidate_actions"]
                    if action.get("seed_compatible") and action.get("abi_signature")}
    expected_steps = candidate["steps"]
    expected_transactions = [
        {"function": step["function"], "action": action_index.get(step["function"])}
        for step in expected_steps
    ]
    if trigger:
        expected_transactions.append({"function": trigger["abi_signature"], "action": trigger})

    def validate(data: dict[str, Any]) -> None:
        if data.get("property_id") != candidate["property_id"]:
            raise ValueError("Agent B 返回了错误的 property_id")
        if data.get("candidate_id") != candidate["candidate_id"]:
            raise ValueError("Agent B 返回了错误的 candidate_id")
        transactions = data.get("transactions")
        if not isinstance(transactions, list) or len(transactions) != len(expected_transactions):
            raise ValueError("交易数必须与 Agent A 规划及目标断言调用完全一致")
        for tx_index, (expected, tx) in enumerate(zip(expected_transactions, transactions)):
            signature = expected["function"]
            if tx.get("function") != signature:
                raise ValueError(f"Agent B 改变了规划函数：{signature}")
            action = expected["action"]
            if action is None:
                raise ValueError(f"交易函数没有对应 ABI：{signature}")
            params = action["abi_inputs"]
            arguments = tx.get("arguments")
            if not isinstance(arguments, list) or len(arguments) != len(params):
                raise ValueError(f"{signature} 参数数量不匹配")
            normalized = []
            for param, value in zip(params, arguments):
                if isinstance(value, dict):
                    if (set(value) != {"from_transaction", "event", "field"} or
                            type(value["from_transaction"]) is not int or
                            not 1 <= value["from_transaction"] <= tx_index or
                            not all(isinstance(value[key], str) and value[key]
                                    for key in ("event", "field"))):
                        raise ValueError(f"{signature} 的事件参数引用无效")
                    normalized.append(value)
                else:
                    normalized.append(normalize_argument(param["type"], value))
            tx["arguments"] = normalized
            if tx.get("expected_outcome") not in {"rejection", "state_change", "no_state_change"}:
                raise ValueError(f"{signature} 必须声明 expected_outcome")
            sender = tx.get("sender")
            allowed_senders = [item.lower() for item in context.get("sender_pool", SENDERS)]
            if not isinstance(sender, str) or sender.lower() not in allowed_senders:
                raise ValueError(f"sender 必须来自当前属性可用账户池：{sender!r}")
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
        if fixed_prefix_transactions:
            if len(fixed_prefix_transactions) > len(transactions):
                raise ValueError("固定共享前缀长于候选交易序列")
            for index, fixed in enumerate(fixed_prefix_transactions):
                actual = transactions[index]
                for field in ("function", "arguments", "sender", "value_wei",
                              "delay_seconds", "delay_blocks"):
                    if actual.get(field) != fixed.get(field):
                        raise ValueError(f"共享前缀第 {index + 1} 笔交易字段 {field} 与已实例化前缀不一致")
        data["execution_feedback"] = feedback
    return validate


def instantiate_candidate(context: dict[str, Any], candidate: dict[str, Any], *,
                          feedback: str | None = None, attempt: int = 1,
                          fixed_prefix_transactions: list[dict[str, Any]] | None = None,
                          environment: dict[str, Any] | None = None,
                          goal_mode: str = "default",
                          call_options: dict[str, Any] | None = None):
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    trigger = candidate.get("assertion_trigger") or property_context.get("assertion_trigger")
    actions = {action["abi_signature"]: action for action in property_context["candidate_actions"]
               if action.get("seed_compatible") and action.get("abi_signature")}
    sequence = []
    for step in candidate["steps"]:
        action = actions[step["function"]]
        evidence = compact_effect_evidence(action.get("effect_evidence", []))
        sequence.append({"function": step["function"], "rationale": step.get("rationale"),
                         "inputs": action["abi_inputs"],
                         "payable": action["payable"],
                         "matched_states": action["matched_states"],
                         **evidence,
                         "source_excerpt": action.get("source_excerpt")})
    if trigger:
        if not trigger.get("seed_compatible"):
            raise ValueError(f"目标断言函数 ABI 暂不支持种子编码：{trigger.get('seed_limitation')}")
        sequence.append({"function": trigger["abi_signature"],
                         "rationale": "状态准备完成后调用目标断言检查",
                         "inputs": trigger["abi_inputs"], "payable": trigger["payable"],
                         "matched_states": [], "effect_evidence": [],
                         "assertion_trigger": True})
    selected_actions = [actions[step["function"]] for step in candidate["steps"]]
    selected_full_names = {action["function"] for action in selected_actions}
    relevant_unresolved = [item for item in property_context.get("unresolved_effect_actions", [])
                           if item.get("function") in selected_full_names][:8]
    property_prompt = {key: property_context.get(key) for key in
                       ("property_id", "property", "property_predicate", "read_states",
                        "property_write_states", "analysis_status", "context_status",
                        "dependency_status", "prerequisite_state_closure", "unknowns")}
    property_prompt["planned_actions"] = []
    for action in selected_actions:
        planned = {key: action.get(key) for key in
                   ("function", "abi_signature", "abi_inputs", "payable",
                    "matched_states", "source_excerpt")}
        planned.update(compact_effect_evidence(action.get("effect_evidence", [])))
        property_prompt["planned_actions"].append(planned)
    property_prompt["unresolved_effect_actions_for_planned_actions"] = relevant_unresolved
    shared_ids = list(dict.fromkeys(candidate.get("shared_prefix_property_ids", [])))
    shared_contexts = [{key: item.get(key) for key in
                        ("property_id", "property", "property_predicate", "read_states",
                         "property_write_states", "unknowns")}
                       for item in context["properties"] if item["property_id"] in shared_ids]
    prompt = {
        "task": "为指定交易序列生成可 ABI 编码并可回放的具体多交易种子。",
        "rules": [
            "必须逐笔遵循计划的 function 顺序，不能增删交易。",
            "只根据 ABI、属性谓词、源码、守卫与 Slither 状态依赖推断参数；无法确认的语义写入 assumptions。",
            "负责为每笔交易具体化全部参数、sender 与跨交易数据依赖；需要相同用户、tokenId、paymentId、commit 数据或前序创建对象时，应在后续交易中复用一致的值，并在 assumptions 中说明依赖关系。",
            "若后续参数是前序交易产生的对象 ID，必须使用事件引用对象 {from_transaction: 1, event: '事件名', field: '字段名'}；序号从 1 开始。不要把 nonce、输入参数或猜测的哈希当作执行结果。若源码未证明可取得，写入 assumptions；本地执行器找不到唯一事件字段时会反馈失败。",
            "每笔交易必须声明 expected_outcome 为 rejection、state_change 或 no_state_change。只有计划本身要检验权限拒绝时才选 rejection；需要建立后续依赖时选 state_change。",
            "arguments 必须按 inputs 顺序提供，uint/int 使用十进制字符串，address 使用 40 位十六进制地址，bool 使用 JSON 布尔值。",
            "bytesN 使用恰好 N 字节的 0x 十六进制字符串。",
            "sender 只能从 sender_pool 选择；payable=false 时 value_wei 必须为 0。",
            "没有源码证据要求时，delay_seconds 与 delay_blocks 都设为 0。",
            "严格满足函数源码、guard、状态依赖和目标谓词；静态不确定项应写入 assumptions。",
            "不要声称已验证可执行；验证器会实际回放并检查目标属性。",
            "若提供 fixed_shared_prefix_transactions，必须逐字段原样复用这些交易；不得改变函数、参数、sender、金额或延迟。",
            "严格输出 JSON 对象，字段为 property_id、candidate_id、transactions、assumptions；每笔交易含 expected_outcome；可附带 data_dependencies 数组，记录依赖的前序交易索引与字段关系。",
        ],
        "property": property_prompt,
        "shared_property_contexts": shared_contexts,
        "fixed_shared_prefix_transactions": fixed_prefix_transactions or [],
        "shared_prefix_steps": candidate.get("shared_prefix_steps", []),
        "candidate": {key: value for key, value in candidate.items() if key != "context"},
        "transactions_to_instantiate": sequence,
        "sender_pool": context.get("sender_pool", SENDERS),
        "environment": {"chain_id": 1, "initial_timestamp": 1524785992,
                        "initial_block_number": 4370000,
                        "evm_revision": "shanghai",
                        "harness_address": HARNESS_ADDRESS,
                        "property_sender": PROPERTY_SENDER,
                        "gas_price_wei": 0, "gas_limit_per_transaction": 12500000,
                        **(environment or {})},
        "deployment_state": context.get("deployment_state"),
        "previous_verifier_feedback": feedback,
        "attempt": attempt,
    }

    if goal_mode == "falsify":
        prompt["rules"].extend([
            "务必优先从 deployment_state.view_values 和 environment.harness_address 读取真实部署地址（如 token1()、token2()、player()、owner() 等），禁止随意杜撰地址。",
            "根据源码中的余额、授权、价格或算术公式精确推算每笔交易的 arguments、sender 与 value_wei，确保每笔交易都能通过 require 守卫，同时尽可能逼近或直接触发目标安全属性的违反条件。",
            "在跨账户协作场景中，明确在不同交易间切换 sender_pool 中的不同 sender（如先由主账户转账/存款，再切换第二账户 approve 或存款，再切回触发目标操作）。",
        ])

    def validate(data: dict[str, Any]) -> None:
        _validator(context, candidate, feedback, fixed_prefix_transactions)(data)

    encoding_started = time.perf_counter()
    user_message = json.dumps(prompt, ensure_ascii=False, separators=(",", ":"))
    prompt_encoding_seconds = time.perf_counter() - encoding_started
    call_kwargs = dict(call_options or {})
    max_tokens = int(call_kwargs.pop("max_tokens", 4096))
    data, event = call_json(
        system="你是智能合约交易参数具体化器。只根据输入 ABI、链上初始/执行状态与源码精确推算参数，思考请保持简洁高效，尽快输出合法 JSON。",
        user=user_message,
        tag=f"AgentB_{context['project']}_{candidate['candidate_id']}_try{attempt}",
        max_tokens=max_tokens, validator=validate, **call_kwargs)
    event["prompt_json_encoding_seconds"] = round(prompt_encoding_seconds, 9)
    event["prompt_utf8_bytes"] = len(user_message.encode("utf-8"))
    return data, event


def to_echidna_sequence(candidate: dict[str, Any], transactions: list[dict[str, Any]],
                        context: dict[str, Any], *,
                        contract_address: str = HARNESS_ADDRESS) -> list[dict[str, Any]]:
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    actions = {action["abi_signature"]: action for action in property_context["candidate_actions"]
               if action.get("seed_compatible") and action.get("abi_signature")}
    trigger = candidate.get("assertion_trigger") or property_context.get("assertion_trigger")
    if trigger and trigger.get("seed_compatible"):
        actions[trigger["abi_signature"]] = trigger
    sequence = []
    def word_hex(value: Any) -> str:
        return "0x" + int(value).to_bytes(32, byteorder="big", signed=False).hex()

    for tx in transactions:
        action = actions[tx["function"]]
        short_signature = tx["function"]
        name = short_signature.split("(", 1)[0]
        args = [_abi_value(item["type"], value)
                for item, value in zip(action["abi_inputs"], tx["arguments"])]
        sequence.append({
            "call": {"tag": "SolCall", "contents": [name, args]},
            "delay": [word_hex(tx["delay_seconds"]), word_hex(tx["delay_blocks"])],
            "dst": contract_address,
            "gas": 12500000,
            "gasprice": word_hex(0),
            "src": tx["sender"],
            "value": word_hex(tx["value_wei"]),
        })
    return sequence

