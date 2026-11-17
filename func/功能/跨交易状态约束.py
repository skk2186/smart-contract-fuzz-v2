#!/usr/bin/env python3
"""从成功前缀中的事件与 getter 结果修复跨交易参数约束。"""

from __future__ import annotations

import re
from typing import Any


_OBJECT_KEY_TOKENS = {"id", "key", "ref", "reference", "hash", "nonce"}


def _canonical_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower().lstrip("_"))


def _semantic_tokens(value: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value.lstrip("_"))
    tokens = set(re.findall(r"[a-z]+|[0-9]+", spaced.lower()))
    # 轻量处理常见英语派生形式，让 refundable 与 refund 保持可比较。
    return {token[:-4] if token.endswith("able") and len(token) > 5 else token
            for token in tokens}


def _normalize_argument(kind: str, value: Any) -> Any | None:
    try:
        from AgentB import normalize_argument
        return normalize_argument(kind, value)
    except (ImportError, TypeError, ValueError):
        return None


def slither_guard_evidence(action: dict[str, Any]) -> list[dict[str, Any]]:
    """提取 Slither 已有的守卫与状态依赖证据，不按项目或函数名筛选。"""
    rows = []
    effects = action.get("effect_evidence", []) or []
    if isinstance(effects, dict):
        effects = [effects]
    for evidence in effects:
        guards = evidence.get("guards", []) or []
        if isinstance(guards, dict):
            guards = [guards]
        for guard in guards:
            rows.append({"state": evidence.get("state"),
                         "writer": evidence.get("writer"),
                         **guard})
    action_guards = action.get("action_guard_evidence", []) or []
    if isinstance(action_guards, dict):
        action_guards = [action_guards]
    for guard in action_guards:
        rows.append(guard)
    return rows


def matching_event_values(name: str, kind: str,
                         prior_events: list[list[dict[str, Any]]], *,
                         transaction_index: int) -> list[dict[str, Any]]:
    """按精确字段名和 ABI 类型，从此前交易事件收集可编码值。"""
    canonical = _canonical_name(name)
    rows = []
    for source_index, events in enumerate(prior_events, start=1):
        if source_index >= transaction_index:
            continue
        for event_index, event in enumerate(events):
            for field, raw in event.get("fields", {}).items():
                if _canonical_name(str(field)) != canonical:
                    continue
                value = _normalize_argument(kind, raw)
                if value is not None:
                    rows.append({"value": value,
                                 "source": {"from_transaction": source_index,
                                            "event": event.get("name"),
                                            "event_address": event.get("address"),
                                            "event_index": event_index,
                                            "field": field}})
    return rows


def infer_object_argument(arguments: list[Any], abi_inputs: list[dict[str, Any]],
                          prior_events: list[list[dict[str, Any]]], *,
                          transaction_index: int) -> tuple[list[Any], list[dict[str, Any]]]:
    """只在对象标识字段有唯一、ABI 可编码的前序事件值时绑定参数。"""
    resolved = list(arguments)
    bindings: list[dict[str, Any]] = []
    for arg_index, param in enumerate(abi_inputs):
        name = str(param.get("name") or "")
        if not name or not (_semantic_tokens(name) & _OBJECT_KEY_TOKENS):
            continue
        candidates: dict[str, dict[str, Any]] = {}
        for match in matching_event_values(name, str(param.get("type", "")),
                                           prior_events,
                                           transaction_index=transaction_index):
            value, source = match["value"], match["source"]
            key = repr(value)
            row = candidates.setdefault(key, {"value": value, "sources": []})
            row["sources"].append(source)
        if len(candidates) != 1:
            continue
        row = next(iter(candidates.values()))
        original = resolved[arg_index]
        resolved[arg_index] = row["value"]
        bindings.append({"argument_index": arg_index,
                         "argument_name": name,
                         "original": original,
                         "resolved": row["value"],
                         "sources": row["sources"],
                         "binding_mode": "unique_prior_event_object_id"})
    return resolved, bindings


def _zero_based_event_index(source_excerpt: str, abi_inputs: list[dict[str, Any]]) -> int | None:
    """识别通用的 1+(index % counter) 映射，不绑定任何 ABI 名称。"""
    expression = re.compile(
        r"\b1\s*\+\s*\(\s*([A-Za-z_]\w*)\s*%\s*([A-Za-z_]\w*)\s*\)")
    matches = {_canonical_name(match.group(1)) for match in expression.finditer(source_excerpt)}
    if not matches:
        return None
    for index, param in enumerate(abi_inputs):
        name = str(param.get("name") or "")
        if (_canonical_name(name) in matches and
                _semantic_tokens(name) & {"index", "position", "ordinal"}):
            return index
    return None


def propose_numeric_repair(abi_inputs: list[dict[str, Any]], arguments: list[Any],
                           observations: list[dict[str, Any]],
                           failure_texts: list[str], *,
                           static_guards: list[dict[str, Any]] | None = None,
                           source_excerpt: str = "") -> dict[str, Any] | None:
    """按错误语义、Slither 守卫和真实 getter 值修复数值及零基对象索引。"""
    failure_tokens = set().union(*(_semantic_tokens(text) for text in failure_texts))
    if not failure_tokens:
        return None
    outputs: list[dict[str, Any]] = []
    for observation in observations:
        for output in observation.get("outputs", []):
            kind = str(output.get("type", ""))
            name = str(output.get("name") or "")
            value = output.get("value")
            if (name and kind.startswith(("uint", "int")) and
                    isinstance(value, int) and not isinstance(value, bool)):
                tokens = _semantic_tokens(name)
                overlap = tokens & failure_tokens
                if overlap and len(tokens) <= len(overlap) + 1:
                    outputs.append({**output, "semantic_score": len(overlap),
                                    "observation": observation})
    if not outputs:
        return None
    best_output_score = max(row["semantic_score"] for row in outputs)
    best_outputs = [row for row in outputs if row["semantic_score"] == best_output_score]
    output_names = {row["name"] for row in best_outputs}
    if len(output_names) != 1:
        return None
    output_name = next(iter(output_names))
    output_tokens = _semantic_tokens(str(output_name))
    output_rows = [row for row in best_outputs if row["name"] == output_name]

    candidates = []
    for index, param in enumerate(abi_inputs):
        kind = str(param.get("type", ""))
        param_name = str(param.get("name") or "")
        if index >= len(arguments) or not kind.startswith(("uint", "int")):
            continue
        try:
            current = int(arguments[index])
        except (TypeError, ValueError):
            continue
        overlap = _semantic_tokens(param_name) & output_tokens
        bounds = [row for row in output_rows
                  if isinstance(row.get("value"), int) and not isinstance(row.get("value"), bool)]
        distinct_bounds = {row["value"] for row in bounds}
        if overlap and bounds and any(0 < value <= current for value in distinct_bounds):
            relevant_guards = [guard for guard in (static_guards or [])
                               if (param_name.lower() in str(guard.get("expression", "")).lower() or
                                   any(param_name.lower() in str(variable).lower()
                                       for variable in (guard.get("variables_read") or [])) or
                                   param_name.lower() in json_compact(
                                       guard.get("data_dependencies", {})).lower())]
            candidates.append({"argument_index": index,
                               "argument_name": param.get("name"),
                               "current_value": current,
                               "semantic_score": len(overlap),
                               "slither_guards": relevant_guards,
                               "bounds": bounds})
    if not candidates:
        return None
    best_score = max(row["semantic_score"] for row in candidates)
    best_candidates = [row for row in candidates if row["semantic_score"] == best_score]
    if len(best_candidates) != 1:
        return None
    selected = best_candidates[0]
    distinct_bounds = {row["value"] for row in selected["bounds"]}
    updates = []
    index_argument = _zero_based_event_index(source_excerpt, abi_inputs)
    if len(distinct_bounds) == 1:
        bound = next(iter(distinct_bounds))
        if 0 < bound < selected["current_value"]:
            updates.append({"argument_index": selected["argument_index"],
                            "argument_name": selected["argument_name"],
                            "original_value": selected["current_value"],
                            "repaired_value": bound,
                            "reason": "getter_observed_numeric_upper_bound"})
    elif index_argument is not None and index_argument < len(arguments):
        try:
            current_index = int(arguments[index_argument])
        except (TypeError, ValueError):
            return None
        ordered: dict[str, dict[str, Any]] = {}
        for row in selected["bounds"]:
            observation = row["observation"]
            key_value = observation.get("input", {}).get("value")
            key = repr(key_value)
            sources = observation.get("input_sources", [])
            order = min(((int(source.get("from_transaction", 0)),
                          int(source.get("event_index", 0))) for source in sources),
                        default=(10**9, 10**9))
            previous = ordered.get(key)
            if previous is None or order < previous["order"]:
                ordered[key] = {"key_value": key_value, "value": row["value"],
                                "output": row, "order": order}
        ordered_rows = sorted(ordered.values(), key=lambda row: row["order"])
        if ordered_rows:
            current_position = current_index % len(ordered_rows)
            current_bound = ordered_rows[current_position]["value"]
            if 0 < current_bound <= selected["current_value"]:
                chosen_position = current_position
            else:
                viable = [(position, row) for position, row in enumerate(ordered_rows)
                          if 0 < row["value"] <= selected["current_value"]]
                if not viable:
                    return None
                chosen_position, _ = viable[0]
            chosen = ordered_rows[chosen_position]
            if chosen_position != current_index:
                index_param = abi_inputs[index_argument]
                updates.append({"argument_index": index_argument,
                                "argument_name": index_param.get("name"),
                                "original_value": current_index,
                                "repaired_value": chosen_position,
                                "reason": "slither_zero_based_index_to_observed_event_key"})
            if chosen["value"] < selected["current_value"]:
                updates.append({"argument_index": selected["argument_index"],
                                "argument_name": selected["argument_name"],
                                "original_value": selected["current_value"],
                                "repaired_value": chosen["value"],
                                "reason": "getter_observed_numeric_upper_bound"})
    if not updates:
        return None
    sources = [row["observation"] for row in selected["bounds"]]
    return {"argument_index": updates[0]["argument_index"],
            "argument_name": updates[0]["argument_name"],
            "current_value": updates[0]["original_value"],
            "repaired_value": updates[0]["repaired_value"],
            "argument_updates": updates,
            "constraint_source": sources,
            "constraint_output_name": output_name,
            "failure_texts": failure_texts,
            "slither_guards": selected["slither_guards"],
            "slither_index_mapping_detected": index_argument is not None,
            "slither_source_excerpt": source_excerpt,
            "repair_mode": ("observed_keyed_numeric_constraint" if index_argument is not None
                            else "observed_numeric_upper_bound")}


def json_compact(value: Any) -> str:
    """将守卫依赖结构转为稳定文本，避免引入项目专属字段分支。"""
    if isinstance(value, dict):
        return " ".join(f"{key} {json_compact(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(json_compact(item) for item in value)
    return str(value)
