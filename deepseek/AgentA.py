#!/usr/bin/env python3
"""Agent A：依据属性上下文为每条属性生成多条 ABI 可调用序列。"""

from __future__ import annotations

import json
import time
from typing import Any

from deepseek接口 import call_json
from 属性种子上下文 import compact_for_agent


def _validator(context: dict[str, Any], max_candidates: int, max_steps: int):
    properties = {item["property_id"]: item for item in context["properties"]}

    def validate(data: dict[str, Any]) -> None:
        rows = data.get("property_sequences")
        if not isinstance(rows, list):
            raise ValueError("property_sequences 必须是数组")
        seen_ids: set[str] = set()
        counts = {property_id: 0 for property_id in properties}
        for row in rows:
            property_id = row.get("property_id")
            if property_id not in properties:
                raise ValueError(f"未知 property_id：{property_id}")
            candidate_id = row.get("candidate_id")
            if not isinstance(candidate_id, str) or not candidate_id.strip() or candidate_id in seen_ids:
                candidate_id = f"{property_id[:10]}-{counts[property_id] + 1:02d}"
                row["candidate_id"] = candidate_id
                row["candidate_id_generated"] = True
            if candidate_id in seen_ids:
                raise ValueError("自动生成的 candidate_id 仍重复")
            seen_ids.add(candidate_id)
            counts[property_id] += 1
            if counts[property_id] > max_candidates:
                raise ValueError(f"属性 {property_id} 候选序列超过上限")
            steps = row.get("steps")
            if not isinstance(steps, list) or not 1 <= len(steps) <= max_steps:
                raise ValueError(f"{candidate_id} 的 steps 长度不合法")
            available = {action["abi_signature"] for action in
                         properties[property_id]["candidate_actions"]
                         if action.get("seed_compatible") and action.get("abi_signature")}
            for step in steps:
                if step.get("function") not in available:
                    raise ValueError(f"序列引用非候选或不可序列化入口：{step.get('function')}")
        prefixes = data.get("shared_prefixes", [])
        if not isinstance(prefixes, list):
            raise ValueError("shared_prefixes 必须是数组")
        for prefix in prefixes:
            ids = prefix.get("property_ids", [])
            steps = prefix.get("steps", [])
            if len(ids) < 2 or any(item not in properties for item in ids):
                raise ValueError("共享前缀必须关联至少两条已知属性")
            if not isinstance(steps, list) or not steps or len(steps) > max_steps:
                raise ValueError("共享前缀 steps 无效")
    return validate


def _normalize_response(data: dict[str, Any]) -> None:
    """把常见的按属性嵌套 sequences 响应展平为一个属性一条候选的记录。"""
    rows = data.get("property_sequences")
    if not isinstance(rows, list):
        return
    flattened = []
    for row in rows:
        nested = row.get("sequences")
        if not isinstance(nested, list):
            flattened.append(row)
            continue
        base_id = row.get("candidate_id")
        for index, sequence in enumerate(nested, start=1):
            item = {key: value for key, value in row.items() if key != "sequences"}
            item.update(sequence)
            if not item.get("candidate_id"):
                if len(nested) == 1 and base_id:
                    item["candidate_id"] = base_id
                else:
                    item["candidate_id"] = f"{row.get('property_id', 'property')[:10]}-{index:02d}"
                    item["candidate_id_generated"] = True
            flattened.append(item)
    data["property_sequences"] = flattened


def generate_candidates(context: dict[str, Any], *, max_candidates: int = 2,
                        max_steps: int = 5, tag: str | None = None):
    """返回 (结构化候选, API 调用记录)。不补造静态分析未提供的入口。"""
    compact_started = time.perf_counter()
    agent_context = compact_for_agent(context)
    compact_seconds = time.perf_counter() - compact_started
    prompt = {
        "task": "为每条目标安全属性规划可执行的多交易准备序列。",
        "rules": [
            "每条输出必须绑定自己的 property_id，不能把组内属性合并成一个谓词。",
            "只使用 candidate_actions 中 seed_compatible=true 的 abi_signature。",
            "根据 property_predicate、候选函数源码、effect_evidence 与守卫推断顺序；不要把静态候选当成已证明可行。",
            "每条属性至多给出指定数量的不同序列；避免仅重排同一交易的重复候选。",
            "允许输出 shared_prefixes，但只有确实存在多个属性都需要的同一准备前缀时才填写。",
            "不负责参数具体化；step 只含 function 与简短 rationale。",
            "无法判断时通过 assumptions 说明，不得杜撰约束。",
            "严格输出 JSON 对象，property_sequences 为扁平数组，每个元素只代表一条候选，包含 property_id、candidate_id、steps。",
            "每个 steps 元素包含 function（完整 abi_signature）和 rationale。shared_prefixes 元素包含 property_ids 与 steps。",
            "输出形状示例：{\"property_sequences\":[{\"property_id\":\"...\",\"candidate_id\":\"...\",\"steps\":[{\"function\":\"mint(uint256)\",\"rationale\":\"...\"}]}],\"shared_prefixes\":[],\"assumptions\":[]}",
        ],
        "max_candidates_per_property": max_candidates,
        "max_steps_per_sequence": max_steps,
        "context": agent_context,
    }

    def validate(data: dict[str, Any]) -> None:
        _normalize_response(data)
        _validator(context, max_candidates, max_steps)(data)

    data, event = call_json(
        system="你是智能合约测试序列规划器。只根据给定 Slither 证据和源码作答，必须输出合法 JSON。",
        user=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
        tag=tag or f"AgentA_{context['project']}", max_tokens=4096,
        validator=validate)
    event["local_context_dedup_seconds"] = round(compact_seconds, 9)
    return data, event

