#!/usr/bin/env python3
"""Agent A：依据属性上下文为每条属性生成多条 ABI 可调用序列。"""

from __future__ import annotations

import json
import time
from typing import Any

from deepseek接口 import call_json
from 属性种子上下文 import compact_for_agent


def _normalize_response(data: dict[str, Any], issues: list[dict[str, Any]]) -> None:
    """把常见的按属性嵌套 sequences 响应展平为一个属性一条候选的记录。"""
    rows = data.get("property_sequences")
    if not isinstance(rows, list):
        return
    flattened = []
    for row_index, row in enumerate(rows):
        if not isinstance(row, dict):
            issues.append({"record_type": "property_sequence", "record_index": row_index,
                           "reason": "记录必须是 JSON 对象"})
            continue
        nested = row.get("sequences")
        if not isinstance(nested, list):
            flattened.append(row)
            continue
        base_id = row.get("candidate_id")
        for index, sequence in enumerate(nested, start=1):
            if not isinstance(sequence, dict):
                issues.append({"record_type": "property_sequence", "record_index": row_index,
                               "nested_index": index, "reason": "嵌套候选必须是 JSON 对象"})
                continue
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


def normalize_agent_a_response(context: dict[str, Any], data: dict[str, Any], *,
                               max_candidates: int, max_steps: int,
                               min_steps: int = 1,
                               use_shared_prefixes: bool = True,
                               shared_prefix_hint: dict[str, Any] | None = None) -> dict[str, Any]:
    """逐条恢复候选记录；无效项进入 invalid_records，不丢弃同组有效项。"""
    properties = {item["property_id"]: item for item in context.get("properties", [])}
    issues: list[dict[str, Any]] = []
    _normalize_response(data, issues)
    raw_rows = data.get("property_sequences")
    if not isinstance(raw_rows, list):
        issues.append({"record_type": "property_sequences", "reason": "字段缺失或不是数组"})
        raw_rows = []

    valid_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    counts = {property_id: 0 for property_id in properties}
    for row_index, row in enumerate(raw_rows):
        issue = None
        if not isinstance(row, dict):
            issue = "候选必须是 JSON 对象"
        else:
            property_id = row.get("property_id")
            if not isinstance(property_id, str) or property_id not in properties:
                issue = f"未知 property_id：{property_id}"
        if issue:
            issues.append({"record_type": "property_sequence", "record_index": row_index,
                           "reason": issue})
            continue

        property_id = row["property_id"]
        steps = row.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= max_steps:
            issues.append({"record_type": "property_sequence", "record_index": row_index,
                           "property_id": property_id, "reason": "steps 长度非法"})
            continue
        available = {action["abi_signature"] for action in properties[property_id].get("candidate_actions", [])
                     if action.get("seed_compatible") and action.get("abi_signature")}
        if any(not isinstance(step, dict) or not isinstance(step.get("function"), str) or
               step.get("function") not in available for step in steps):
            issues.append({"record_type": "property_sequence", "record_index": row_index,
                           "property_id": property_id,
                           "reason": "存在非候选或不可序列化函数"})
            continue
        if counts[property_id] >= max_candidates:
            issues.append({"record_type": "property_sequence", "record_index": row_index,
                           "property_id": property_id, "reason": "超过单属性候选数量上限"})
            continue

        candidate_id = row.get("candidate_id")
        if not isinstance(candidate_id, str) or not candidate_id.strip() or candidate_id in seen_ids:
            base = f"{property_id[:10]}-{counts[property_id] + 1:02d}"
            candidate_id = base
            suffix = 1
            while candidate_id in seen_ids:
                suffix += 1
                candidate_id = f"{base}-{suffix}"
            row["candidate_id"] = candidate_id
            row["candidate_id_generated"] = True
        seen_ids.add(candidate_id)
        counts[property_id] += 1
        valid_rows.append(row)

    valid_prefixes: list[dict[str, Any]] = []
    raw_prefixes = data.get("shared_prefixes", [])
    if not isinstance(raw_prefixes, list):
        issues.append({"record_type": "shared_prefix", "reason": "字段不是数组"})
        raw_prefixes = []
    if use_shared_prefixes and shared_prefix_hint:
        hint = {**shared_prefix_hint, "source": "pre_registered_dependency_evidence"}
        raw_prefixes = [hint, *raw_prefixes]
    for prefix_index, prefix in enumerate(raw_prefixes):
        if not isinstance(prefix, dict):
            issues.append({"record_type": "shared_prefix", "record_index": prefix_index,
                           "reason": "记录必须是 JSON 对象"})
            continue
        ids, steps = prefix.get("property_ids"), prefix.get("steps")
        if (not isinstance(ids, list) or len(ids) < 2 or
                any(not isinstance(property_id, str) or property_id not in properties for property_id in ids) or
                len(ids) != len(set(ids))):
            issues.append({"record_type": "shared_prefix", "record_index": prefix_index,
                           "reason": "至少两个唯一且已知的 property_id"})
            continue
        if not isinstance(steps, list) or not 1 <= len(steps) <= max_steps:
            issues.append({"record_type": "shared_prefix", "record_index": prefix_index,
                           "reason": "steps 长度非法"})
            continue
        signatures_by_property = [
            {action["abi_signature"] for action in properties[property_id].get("candidate_actions", [])
             if action.get("seed_compatible") and action.get("abi_signature")}
            for property_id in ids]
        common_signatures = set.intersection(*signatures_by_property) if signatures_by_property else set()
        if any(not isinstance(step, dict) or not isinstance(step.get("function"), str) or
               step.get("function") not in common_signatures
               for step in steps):
            issues.append({"record_type": "shared_prefix", "record_index": prefix_index,
                           "reason": "前缀函数并非所有关联属性共同支持的可序列化入口"})
            continue
        valid_prefixes.append(prefix)

    data["property_sequences"] = valid_rows
    data["shared_prefixes"] = valid_prefixes if use_shared_prefixes else []
    data["shared_prefixes_ignored"] = not use_shared_prefixes
    applied: list[dict[str, Any]] = []
    if use_shared_prefixes:
        prefix_by_property: dict[str, dict[str, Any]] = {}
        for prefix_index, prefix in enumerate(valid_prefixes):
            for property_id in prefix["property_ids"]:
                prior = prefix_by_property.get(property_id)
                if prior is not None and [s["function"] for s in prior["steps"]] != [
                        s["function"] for s in prefix["steps"]]:
                    issues.append({"record_type": "shared_prefix", "record_index": prefix_index,
                                   "property_id": property_id,
                                   "reason": "同一属性出现冲突共享前缀，保留先到记录"})
                    continue
                prefix_by_property[property_id] = prefix
        for row in valid_rows:
            prefix = prefix_by_property.get(row["property_id"])
            if not prefix:
                continue
            prefix_steps = prefix["steps"]
            current = row["steps"]
            same_leading = (len(current) >= len(prefix_steps) and
                            [step["function"] for step in current[:len(prefix_steps)]] ==
                            [step["function"] for step in prefix_steps])
            combined = current if same_leading else prefix_steps + current
            if len(combined) > max_steps:
                issues.append({"record_type": "shared_prefix_application",
                               "candidate_id": row["candidate_id"],
                               "property_id": row["property_id"],
                               "reason": "合并前缀后超过最大交易步数"})
                continue
            row["steps"] = combined
            row["shared_prefix_id"] = prefix.get("prefix_id", f"prefix-{valid_prefixes.index(prefix)+1}")
            row["shared_prefix_property_ids"] = list(prefix["property_ids"])
            row["shared_prefix_steps"] = prefix_steps
            applied.append({"candidate_id": row["candidate_id"],
                            "property_id": row["property_id"],
                            "prefix_id": row["shared_prefix_id"],
                            "steps": prefix_steps})

    final_rows = []
    for row in valid_rows:
        if len(row["steps"]) < min_steps:
            issues.append({"record_type": "property_sequence", "candidate_id": row["candidate_id"],
                           "property_id": row["property_id"],
                           "reason": f"最终序列少于 {min_steps} 笔交易"})
            continue
        final_rows.append(row)
    data["property_sequences"] = final_rows
    data["applied_shared_prefixes"] = applied
    data["invalid_records"] = issues
    data["recovery_summary"] = {"valid_candidate_count": len(final_rows),
                                "invalid_record_count": len(issues),
                                "applied_shared_prefix_count": len(applied)}
    return data


def generate_candidates(context: dict[str, Any], *, max_candidates: int = 2,
                        max_steps: int = 5, min_steps: int = 1,
                        use_shared_prefixes: bool = True, tag: str | None = None,
                        shared_prefix_hint: dict[str, Any] | None = None,
                        task_constraints: list[str] | None = None,
                        call_options: dict[str, Any] | None = None):
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
            ("若多个属性确实需要同一准备前缀，请在 shared_prefixes 中显式给出，并确保对应候选序列以该前缀开头。"
             if use_shared_prefixes else "shared_prefixes 必须为空；不要为候选序列设计跨属性共享前缀。"),
            "不负责参数具体化；step 只含 function 与简短 rationale。",
            f"每条候选最终至少 {min_steps} 笔交易；共享前缀应与各属性候选的前导步骤一致。",
            "无法判断时通过 assumptions 说明，不得杜撰约束。",
            "严格输出 JSON 对象，property_sequences 为扁平数组，每个元素只代表一条候选，包含 property_id、candidate_id、steps。",
            "每个 steps 元素包含 function（完整 abi_signature）和 rationale。shared_prefixes 元素包含 property_ids 与 steps。",
            "输出形状示例：{\"property_sequences\":[{\"property_id\":\"...\",\"candidate_id\":\"...\",\"steps\":[{\"function\":\"mint(uint256)\",\"rationale\":\"...\"}]}],\"shared_prefixes\":[],\"assumptions\":[]}",
        ],
        "max_candidates_per_property": max_candidates,
        "max_steps_per_sequence": max_steps,
        "shared_prefix_hint": shared_prefix_hint if use_shared_prefixes else None,
        "sample_constraints": list(task_constraints or []),
        "context": agent_context,
    }

    call_kwargs = dict(call_options or {})
    data, event = call_json(
        system="你是智能合约测试序列规划器。只根据给定 Slither 证据和源码作答，必须输出合法 JSON。",
        user=json.dumps(prompt, ensure_ascii=False, separators=(",", ":")),
        tag=tag or f"AgentA_{context['project']}", max_tokens=4096,
        **call_kwargs)
    data = normalize_agent_a_response(context, data, max_candidates=max_candidates,
                                      max_steps=max_steps, min_steps=min_steps,
                                      use_shared_prefixes=use_shared_prefixes,
                                      shared_prefix_hint=shared_prefix_hint)
    event["invalid_record_count"] = data["recovery_summary"]["invalid_record_count"]
    event["applied_shared_prefix_count"] = data["recovery_summary"]["applied_shared_prefix_count"]
    event["local_context_dedup_seconds"] = round(compact_seconds, 9)
    return data, event

