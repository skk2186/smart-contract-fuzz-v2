#!/usr/bin/env python3
"""从成功前缀中的事件与 getter 结果修复跨交易参数约束。"""

from __future__ import annotations

import copy
import re
from typing import Any


_OBJECT_KEY_TOKENS = {"id", "key", "ref", "reference", "hash", "nonce"}


def _canonical_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower().lstrip("_"))


def _semantic_tokens(value: str) -> set[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value.lstrip("_"))
    tokens = set(re.findall(r"[a-z]+|[0-9]+", spaced.lower()))
    # 轻量处理常见英语派生形式，让 refundable 与 refund 保持可比较。
    normalized = {token[:-4] if token.endswith("able") and len(token) > 5 else token
                  for token in tokens}
    aliases = {"amt": "amount", "qty": "quantity", "sec": "second",
               "secs": "second", "minimum": "min"}
    return {aliases.get(token, token) for token in normalized}


def extract_numeric_guard_evidence(source_documents: list[dict[str, Any]],
                                   abi_inputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract source-level require bounds tied to a numeric ABI parameter.

    This is intentionally a small, evidence-preserving Solidity scanner. It only
    emits simple identifier comparisons found in a require condition; it does
    not evaluate arbitrary expressions or claim that a guard is reachable.
    """
    parameter_tokens = [_semantic_tokens(str(item.get("name") or ""))
                        for item in abi_inputs]
    rows: list[dict[str, Any]] = []
    for document in source_documents:
        text = str(document.get("text") or "")
        source = str(document.get("source") or "unknown")
        for match in re.finditer(r"\brequire\s*\(", text):
            opening = text.find("(", match.start())
            depth = 0
            end = None
            for index in range(opening, len(text)):
                if text[index] == "(":
                    depth += 1
                elif text[index] == ")":
                    depth -= 1
                    if depth == 0:
                        end = index
                        break
            if end is None:
                continue
            body = text[opening + 1:end]
            depth = 0
            condition_end = len(body)
            for index, char in enumerate(body):
                if char in "([{":
                    depth += 1
                elif char in ")]}":
                    depth = max(0, depth - 1)
                elif char == "," and depth == 0:
                    condition_end = index
                    break
            condition = body[:condition_end].strip()
            for comparison in re.finditer(
                    r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(>=|>|<=|<)\s*"
                    r"([A-Za-z_]\w*)(?![A-Za-z0-9_])", condition):
                left, operator, right = comparison.groups()
                left_tokens, right_tokens = _semantic_tokens(left), _semantic_tokens(right)
                matched = [index for index, tokens in enumerate(parameter_tokens)
                           if tokens and (tokens <= left_tokens or
                                          len(tokens & left_tokens) == len(tokens))]
                if not matched:
                    continue
                rows.append({"kind": "source_require_numeric_bound",
                             "expression": condition,
                             "left_identifier": left, "operator": operator,
                             "right_identifier": right,
                             "parameter_indices": matched,
                             "variables_read": [left, right],
                             "source": source,
                             "line": text.count("\n", 0, match.start()) + 1})
    return rows


def _guarded_lower_bound(guards: list[dict[str, Any]], parameter_name: str,
                         output_name: str) -> list[dict[str, Any]]:
    parameter = _semantic_tokens(parameter_name)
    output = _semantic_tokens(output_name)
    matched = []
    for guard in guards:
        expression = str(guard.get("expression") or "")
        left = str(guard.get("left_identifier") or "")
        right = str(guard.get("right_identifier") or "")
        operator = str(guard.get("operator") or "")
        if not left or not right:
            for item in re.finditer(
                    r"(?<![A-Za-z0-9_])([A-Za-z_]\w*)\s*(>=|>|<=|<)\s*"
                    r"([A-Za-z_]\w*)(?![A-Za-z0-9_])", expression):
                lhs, op, rhs = item.groups()
                if _semantic_tokens(lhs) == parameter and _semantic_tokens(rhs) == output:
                    left, right, operator = lhs, rhs, op
                    break
                if _semantic_tokens(rhs) == parameter and _semantic_tokens(lhs) == output:
                    left, right, operator = rhs, lhs, {">=": "<=", ">": "<",
                                                       "<=": ">=", "<": ">"}[op]
                    break
        if not left or not right:
            continue
        left_tokens, right_tokens = _semantic_tokens(left), _semantic_tokens(right)
        if left_tokens == parameter and right_tokens == output and operator in {">=", ">"}:
            matched.append(guard)
        elif left_tokens == output and right_tokens == parameter and operator in {"<=", "<"}:
            matched.append(guard)
    return matched


def _failure_indicates_lower_bound(failure_texts: list[str]) -> bool:
    text = " ".join(failure_texts).lower()
    return bool(re.search(r"\b(?:too\s+low|below|under\s+(?:the\s+)?minimum|"
                          r"less\s+than\s+(?:the\s+)?minimum|minimum\s+(?:not\s+met|violation))\b", text))


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
    lower_failure = _failure_indicates_lower_bound(failure_texts)
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
        lower_guards = (_guarded_lower_bound(static_guards or [], param_name, output_name)
                        if lower_failure else [])
        lower_bound_available = bool(lower_guards) and any(
            row["value"] > current for row in bounds)
        upper_bound_available = any(0 < value <= current for value in distinct_bounds)
        if overlap and bounds and (upper_bound_available or lower_bound_available):
            relevant_guards = [guard for guard in (static_guards or [])
                               if guard in lower_guards or
                               param_name.lower() in str(guard.get("expression", "")).lower() or
                               any(param_name.lower() in str(variable).lower()
                                   for variable in (guard.get("variables_read") or [])) or
                               param_name.lower() in json_compact(
                                   guard.get("data_dependencies", {})).lower()]
            candidates.append({"argument_index": index,
                               "argument_name": param.get("name"),
                               "current_value": current,
                               "semantic_score": len(overlap),
                               "slither_guards": relevant_guards,
                               "bounds": bounds,
                               "lower_guards": lower_guards})
    if not candidates:
        return None
    best_score = max(row["semantic_score"] for row in candidates)
    best_candidates = [row for row in candidates if row["semantic_score"] == best_score]
    if len(best_candidates) != 1:
        return None
    selected = best_candidates[0]
    distinct_bounds = {row["value"] for row in selected["bounds"]}
    updates = []
    lower_bound_applied = False
    if selected["lower_guards"] and lower_failure:
        viable_lower = sorted({row["value"] for row in selected["bounds"]
                               if row["value"] > selected["current_value"]})
        if len(viable_lower) == 1:
            boundary = viable_lower[0]
            strict = any(guard.get("operator") in {">", "<"}
                         for guard in selected["lower_guards"])
            repaired = boundary + 1 if strict else boundary
            if _numeric_type_fits(str(abi_inputs[selected["argument_index"]].get("type", "")),
                                  repaired):
                updates.append({"argument_index": selected["argument_index"],
                                "argument_name": selected["argument_name"],
                                "original_value": selected["current_value"],
                                "repaired_value": repaired,
                                "reason": "getter_observed_numeric_lower_bound",
                                "bound_value": boundary,
                                "guard_operator": ">" if strict else ">="})
                lower_bound_applied = True
    index_argument = _zero_based_event_index(source_excerpt, abi_inputs)
    if not lower_bound_applied and len(distinct_bounds) == 1:
        bound = next(iter(distinct_bounds))
        if 0 < bound < selected["current_value"]:
            updates.append({"argument_index": selected["argument_index"],
                            "argument_name": selected["argument_name"],
                            "original_value": selected["current_value"],
                            "repaired_value": bound,
                            "reason": "getter_observed_numeric_upper_bound"})
    elif not lower_bound_applied and index_argument is not None and index_argument < len(arguments):
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
            "repair_mode": ("observed_numeric_lower_bound" if lower_bound_applied else
                            "observed_keyed_numeric_constraint" if index_argument is not None
                            else "observed_numeric_upper_bound")}


def _short_signature(value: Any) -> str:
    return str(value or "").rsplit(".", 1)[-1]


def propagate_argument_updates(sequence: list[dict[str, Any]], source_index: int,
                               proposal: dict[str, Any],
                               abi_by_signature: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply a proved parameter repair to explicitly linked later arguments only."""
    repaired = copy.deepcopy(sequence)
    propagation: list[dict[str, Any]] = []
    updates = proposal.get("argument_updates") or [{
        "argument_index": proposal.get("argument_index"),
        "argument_name": proposal.get("argument_name"),
        "repaired_value": proposal.get("repaired_value"),
    }]
    if not 0 <= source_index < len(repaired):
        return repaired, propagation
    for update in updates:
        name = str(update.get("argument_name") or "")
        value = update.get("repaired_value")
        argument_index = update.get("argument_index")
        if not name or argument_index is None:
            continue
        args = list(repaired[source_index].get("arguments", []))
        if 0 <= int(argument_index) < len(args):
            old = args[int(argument_index)]
            args[int(argument_index)] = value
            repaired[source_index]["arguments"] = args
            propagation.append({"transaction_index": source_index + 1,
                                "argument_name": name, "argument_index": int(argument_index),
                                "before": old, "after": value,
                                "evidence": "direct_numeric_repair"})
        source_name = _canonical_name(name)
        for consumer_index in range(source_index + 1, len(repaired)):
            consumer = repaired[consumer_index]
            dependencies = consumer.get("data_dependencies", []) or []
            for dependency in dependencies:
                try:
                    from_transaction = int(dependency.get("from_transaction", 0))
                except (TypeError, ValueError):
                    continue
                if from_transaction != source_index + 1:
                    continue
                fields = dependency.get("fields", []) or []
                consumer_name = None
                for field in fields:
                    parts = [part.strip() for part in str(field).split("->")]
                    if parts and _canonical_name(parts[0]) == source_name:
                        consumer_name = parts[-1] if len(parts) > 1 else parts[0]
                        break
                    if len(parts) > 1 and _canonical_name(parts[-1]) == source_name:
                        consumer_name = parts[0]
                        break
                if not consumer_name:
                    continue
                signature = _short_signature(consumer.get("function"))
                abi = (abi_by_signature.get(signature) or
                       abi_by_signature.get(str(consumer.get("function"))))
                inputs = abi.get("inputs", []) if isinstance(abi, dict) else []
                matches = [index for index, item in enumerate(inputs)
                           if _canonical_name(str(item.get("name") or "")) ==
                           _canonical_name(consumer_name)]
                if len(matches) != 1 or matches[0] >= len(consumer.get("arguments", [])):
                    continue
                consumer_args = list(consumer.get("arguments", []))
                old = consumer_args[matches[0]]
                consumer_args[matches[0]] = value
                consumer["arguments"] = consumer_args
                propagation.append({"transaction_index": consumer_index + 1,
                                    "argument_name": inputs[matches[0]].get("name"),
                                    "argument_index": matches[0], "before": old,
                                    "after": value,
                                    "evidence": "explicit_data_dependency_fields",
                                    "source_argument_name": name,
                                    "dependency": dependency})
    return repaired, propagation


def _effect_values(effect_catalog: Any) -> list[dict[str, Any]]:
    if isinstance(effect_catalog, dict):
        return [row for row in effect_catalog.values() if isinstance(row, dict)]
    if isinstance(effect_catalog, list):
        return [row for row in effect_catalog if isinstance(row, dict)]
    return []


def _effects_for_transaction(effect_catalog: Any, signature: str) -> list[dict[str, Any]]:
    target = _short_signature(signature)
    return [row for row in _effect_values(effect_catalog)
            if _short_signature(row.get("writer")) == target]


def _transaction_key(tx: dict[str, Any]) -> tuple[str, str, str, str]:
    return (_short_signature(tx.get("function")),
            json_compact(tx.get("arguments", [])),
            str(tx.get("sender", "")).lower(),
            str(tx.get("value_wei", "0")))


def _inserted_positions(parent: list[dict[str, Any]],
                        child: list[dict[str, Any]]) -> list[int]:
    """Return child indexes absent from an LCS alignment with its parent."""
    left = [_transaction_key(row) for row in parent]
    right = [_transaction_key(row) for row in child]
    rows, cols = len(left), len(right)
    lengths = [[0] * (cols + 1) for _ in range(rows + 1)]
    for i in range(rows - 1, -1, -1):
        for j in range(cols - 1, -1, -1):
            lengths[i][j] = (1 + lengths[i + 1][j + 1] if left[i] == right[j]
                             else max(lengths[i + 1][j], lengths[i][j + 1]))
    matched_child: set[int] = set()
    i = j = 0
    while i < rows and j < cols:
        if left[i] == right[j]:
            matched_child.add(j)
            i += 1
            j += 1
        elif lengths[i + 1][j] >= lengths[i][j + 1]:
            i += 1
        else:
            j += 1
    return [index for index in range(cols) if index not in matched_child]


def _state_access(expression: str, state: str) -> tuple[str, list[str]] | None:
    base = str(state or "").rsplit(".", 1)[-1]
    if not base:
        return None
    match = re.search(r"(?<![A-Za-z0-9_])" + re.escape(base) +
                      r"\s*((?:\[[^\]]*\]\s*)*)", expression)
    if not match:
        return None
    indexes = [item.strip() for item in re.findall(r"\[([^\]]*)\]", match.group(1))]
    return base, indexes


def _guard_condition(expression: str) -> str | None:
    marker = expression.find(")(")
    if marker < 0:
        return None
    body = expression[marker + 2:]
    depth = 0
    for index, char in enumerate(body):
        if char in "([{}":
            depth += 1
        elif char in ")]}":
            if char == ")" and depth == 0:
                return None
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            return body[:index].strip()
    return None


def _condition_comparisons(condition: str) -> list[tuple[str, str, str]]:
    pattern = re.compile(r"([^&|]+?)\s*(>=|<=|==|!=|>|<)\s*([^&|]+?)"
                         r"(?=\s*(?:&&|\|\|)|$)")
    return [(match.group(1).strip().strip("()"), match.group(2),
             match.group(3).strip().strip("()"))
            for match in pattern.finditer(condition)]


def _abi_inputs(abi_by_signature: dict[str, dict[str, Any]],
                signature: str) -> list[dict[str, Any]] | None:
    entry = abi_by_signature.get(_short_signature(signature))
    return entry.get("inputs", []) if isinstance(entry, dict) else None


def _argument_index(inputs: list[dict[str, Any]], name: str) -> int | None:
    key = _canonical_name(name)
    matches = [index for index, item in enumerate(inputs)
               if key and _canonical_name(str(item.get("name") or "")) == key]
    return matches[0] if len(matches) == 1 else None


def _resolve_consumer_value(expression: str, consumer: dict[str, Any],
                            inputs: list[dict[str, Any]]) -> tuple[Any, str] | None:
    value = expression.strip().strip("()")
    if value == "msg.sender":
        return consumer.get("sender"), "consumer.msg.sender"
    index = _argument_index(inputs, value)
    arguments = consumer.get("arguments", [])
    if index is not None and index < len(arguments):
        return arguments[index], f"consumer.arguments[{index}]"
    if re.fullmatch(r"0x[0-9a-fA-F]{40}", value):
        return value, "guard_literal_address"
    if re.fullmatch(r"-?\d+", value):
        return int(value), "guard_literal_integer"
    return None


def _producer_argument(inputs: list[dict[str, Any]], expression: str) -> int | None:
    value = expression.strip().strip("()")
    if not re.fullmatch(r"[A-Za-z_]\w*", value):
        return None
    return _argument_index(inputs, value)


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, str) and isinstance(right, str) and left.startswith("0x") and right.startswith("0x"):
        return left.lower() == right.lower()
    return left == right


def _set_binding(changes: dict[str, Any], field: str, value: Any) -> bool:
    if field in changes and not _same_value(changes[field], value):
        return False
    changes[field] = value
    return True


def _numeric_type_fits(kind: str, value: int) -> bool:
    match = re.fullmatch(r"(u?)int(\d*)", kind)
    if not match:
        return False
    bits = int(match.group(2) or 256)
    if not 8 <= bits <= 256 or bits % 8:
        return False
    return 0 <= value < (1 << bits) if match.group(1) else -(1 << (bits - 1)) <= value < (1 << (bits - 1))


def _invert_comparison(operator: str) -> str:
    return {">=": "<=", "<=": ">=", ">": "<", "<": ">",
            "==": "==", "!=": "!="}[operator]


def _numeric_boundary(operator: str, raw_value: Any, kind: str) -> tuple[int, dict[str, Any]] | None:
    if not isinstance(raw_value, int) or isinstance(raw_value, bool):
        return None
    selected = {">=": raw_value, ">": raw_value + 1,
                "<=": raw_value, "<": raw_value - 1,
                "==": raw_value}.get(operator)
    if selected is None or not _numeric_type_fits(kind, selected):
        return None
    signed = kind.startswith("int")
    bits_match = re.fullmatch(r"(?:u?)int(\d*)", kind)
    bits = int(bits_match.group(1) or 256) if bits_match else 256
    lower = -(1 << (bits - 1)) if signed else 0
    upper = (1 << (bits - 1)) - 1 if signed else (1 << bits) - 1
    return selected, {"operator": operator, "observed_consumer_value": raw_value,
                      "satisfying_range": {"minimum": max(lower, raw_value) if operator in {">=", ">"} else lower,
                                           "maximum": min(upper, raw_value) if operator in {"<=", "<"} else upper},
                      "selected_boundary_value": selected}


def _trace_match(parent_replay: dict[str, Any] | None, consumer: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(parent_replay, dict):
        return None
    signature = _short_signature(consumer.get("function"))
    args = json_compact(consumer.get("arguments", []))
    sender = str(consumer.get("sender", "")).lower()
    for row in parent_replay.get("transactions", []):
        if (_short_signature(row.get("function")) == signature and
                json_compact(row.get("arguments", [])) == args and
                str(row.get("sender", "")).lower() == sender):
            return {key: row.get(key) for key in
                    ("index", "function", "arguments", "sender", "status",
                     "execution_class", "property_error", "state_fingerprint_before",
                     "state_fingerprint_after")}
    return None


def _derive_writer_binding(writer_effect: dict[str, Any],
                           consumer_effect: dict[str, Any],
                           guard: dict[str, Any],
                           producer: dict[str, Any], consumer: dict[str, Any],
                           producer_inputs: list[dict[str, Any]],
                           consumer_inputs: list[dict[str, Any]]) -> dict[str, Any] | None:
    state = str(writer_effect.get("state") or "")
    writer_expression = str(writer_effect.get("expression") or "")
    assignment = re.search(r"^\s*(?P<lhs>.+?)\s*(?P<op>\+=|-=|=(?!=))\s*(?P<rhs>[^;]+?)\s*$",
                           writer_expression)
    condition = _guard_condition(str(guard.get("expression") or ""))
    if not assignment or assignment.group("op") != "=" or not condition:
        return None
    write_access = _state_access(assignment.group("lhs"), state)
    if write_access is None:
        return None
    state_reads = set(guard.get("state_reads") or [])
    if state not in state_reads:
        return None

    changes: dict[str, Any] = {}
    bindings: list[dict[str, Any]] = []
    read_state_expression = None
    numeric_constraint = None
    write_keys = write_access[1]

    for left, operator, right in _condition_comparisons(condition):
        left_access = _state_access(left, state)
        right_access = _state_access(right, state)
        if bool(left_access) == bool(right_access):
            continue
        read_side = left if left_access else right
        other_side = right if left_access else left
        read_keys = (left_access or right_access)[1]
        read_state_expression = read_side
        if len(write_keys) != len(read_keys):
            continue

        # Mapping-key positions define the correspondence. Resolve the consumer key
        # through its ABI input or actual sender, then bind the producer key to it.
        mapping_ok = True
        mapping_updates = []
        for position, (write_key, read_key) in enumerate(zip(write_keys, read_keys)):
            resolved = _resolve_consumer_value(read_key, consumer, consumer_inputs)
            if resolved is None or resolved[0] is None:
                mapping_ok = False
                break
            value, source = resolved
            if write_key == "msg.sender":
                field = "sender"
            else:
                arg_index = _producer_argument(producer_inputs, write_key)
                if arg_index is None:
                    mapping_ok = False
                    break
                field = f"argument:{arg_index}"
            if not _set_binding(changes, field, value):
                return None
            mapping_updates.append({"producer_field": field, "before": (
                producer.get("sender") if field == "sender" else
                (producer.get("arguments", [])[int(field.split(":")[1])] if
                 int(field.split(":")[1]) < len(producer.get("arguments", [])) else None)),
                "after": value, "relation": "same mapping index position",
                "mapping_position": position, "consumer_key": read_key,
                "consumer_value_source": source})
        if not mapping_ok:
            continue

        rhs = assignment.group("rhs").strip().strip("()")
        rhs_index = _producer_argument(producer_inputs, rhs)
        if rhs_index is None:
            if mapping_updates:
                continue
            continue

        other_value = _resolve_consumer_value(other_side, consumer, consumer_inputs)
        if other_value is None:
            continue
        value, value_source = other_value
        producer_kind = str(producer_inputs[rhs_index].get("type", ""))
        effective_operator = operator if left_access else _invert_comparison(operator)
        numeric_proof = None
        if producer_kind.startswith(("uint", "int")):
            boundary = _numeric_boundary(effective_operator, value, producer_kind)
            if boundary is None:
                continue
            value, numeric_proof = boundary
            numeric_constraint = numeric_proof
        elif effective_operator != "==":
            continue
        field = f"argument:{rhs_index}"
        if not _set_binding(changes, field, value):
            return None
        bindings.extend(mapping_updates)
        bindings.append({"producer_field": field,
                         "before": producer.get("arguments", [])[rhs_index]
                         if rhs_index < len(producer.get("arguments", [])) else None,
                         "after": value, "relation": "writer value satisfies consumer guard",
                         "consumer_expression": other_side,
                         "consumer_value_source": value_source,
                         "guard_operator": effective_operator,
                         "numeric_constraint": numeric_proof})
        return {"state": state, "read_state_expression": read_state_expression,
                "writer_expression": writer_expression,
                "consumer_guard": guard.get("expression"),
                "writer_source": writer_effect.get("source"),
                "guard_source": guard.get("source"),
                "consumer_effect_writer": consumer_effect.get("writer"),
                "bindings": bindings,
                "field_updates": [{"producer_field": field, "after": value}
                                  for field, value in changes.items()],
                "numeric_constraint": numeric_constraint}
    return None


def cross_transaction_write_read_matches(parent_sequence: list[dict[str, Any]],
                                        candidate_sequence: list[dict[str, Any]],
                                        effect_catalog: Any) -> list[dict[str, Any]]:
    """Report exact inserted-writer/later-guard state matches before binding."""
    inserted = _inserted_positions(parent_sequence, candidate_sequence)
    rows = _effect_values(effect_catalog)
    matches = []
    for producer_index in inserted:
        producer_signature = _short_signature(candidate_sequence[producer_index].get("function"))
        writer_effects = _effects_for_transaction(rows, producer_signature)
        for consumer_index in range(producer_index + 1, len(candidate_sequence)):
            consumer_signature = _short_signature(
                candidate_sequence[consumer_index].get("function"))
            consumer_effects = _effects_for_transaction(rows, consumer_signature)
            for writer_effect in writer_effects:
                state = str(writer_effect.get("state") or "")
                if not state:
                    continue
                for consumer_effect in consumer_effects:
                    for guard in consumer_effect.get("guards", []) or []:
                        if state not in set(guard.get("state_reads") or []):
                            continue
                        matches.append({"state": state,
                                        "producer_index": producer_index + 1,
                                        "producer_signature": producer_signature,
                                        "consumer_index": consumer_index + 1,
                                        "consumer_signature": consumer_signature,
                                        "writer_expression": writer_effect.get("expression"),
                                        "guard_expression": guard.get("expression"),
                                        "writer_source": writer_effect.get("source"),
                                        "guard_source": guard.get("source")})
    return matches


def bind_inserted_prerequisite(parent_sequence: list[dict[str, Any]],
                               candidate_sequence: list[dict[str, Any]],
                               effect_catalog: Any,
                               abi_by_signature: dict[str, dict[str, Any]], *,
                               parent_replay: dict[str, Any] | None = None
                               ) -> dict[str, Any] | None:
    """Bind one inserted state writer to a later consumer using Slither and ABI evidence.

    The function only changes the newly inserted transaction. It does not inspect
    oracle sequences or alter transactions already present in the parent prefix.
    """
    inserted = _inserted_positions(parent_sequence, candidate_sequence)
    rows = _effect_values(effect_catalog)
    for producer_index in inserted:
        producer = candidate_sequence[producer_index]
        producer_signature = _short_signature(producer.get("function"))
        producer_inputs = _abi_inputs(abi_by_signature, producer_signature)
        if producer_inputs is None or len(producer_inputs) != len(producer.get("arguments", [])):
            continue
        writer_effects = _effects_for_transaction(rows, producer_signature)
        for consumer_index in range(producer_index + 1, len(candidate_sequence)):
            consumer = candidate_sequence[consumer_index]
            consumer_signature = _short_signature(consumer.get("function"))
            consumer_inputs = _abi_inputs(abi_by_signature, consumer_signature)
            if consumer_inputs is None or len(consumer_inputs) != len(consumer.get("arguments", [])):
                continue
            consumer_effects = _effects_for_transaction(rows, consumer_signature)
            for writer_effect in writer_effects:
                state = str(writer_effect.get("state") or "")
                if not state:
                    continue
                for consumer_effect in consumer_effects:
                    for guard in consumer_effect.get("guards", []) or []:
                        if state not in set(guard.get("state_reads") or []):
                            continue
                        proof = _derive_writer_binding(
                            writer_effect, consumer_effect, guard, producer, consumer,
                            producer_inputs, consumer_inputs)
                        if proof is None:
                            continue
                        bound = [dict(row) for row in candidate_sequence]
                        applied = []
                        for item in proof["field_updates"]:
                            field = item["producer_field"]
                            value = item["after"]
                            if field == "sender":
                                before = bound[producer_index].get("sender")
                                bound[producer_index]["sender"] = value
                            else:
                                arg_index = int(field.split(":", 1)[1])
                                arguments = list(bound[producer_index].get("arguments", []))
                                before = arguments[arg_index]
                                arguments[arg_index] = value
                                bound[producer_index]["arguments"] = arguments
                            if not _same_value(before, value):
                                applied.append({"field": field, "before": before, "after": value})
                        proof.update({"producer_index": producer_index + 1,
                                      "consumer_index": consumer_index + 1,
                                      "producer_signature": producer_signature,
                                      "consumer_signature": consumer_signature,
                                      "runtime_trace": _trace_match(parent_replay, consumer)})
                        return {"status": "applied" if applied else "already_satisfied",
                                "sequence": bound,
                                "bindings": applied, "evidence": proof,
                                "alternative_count": 1,
                                "candidate_limit": 1}
    return None


def json_compact(value: Any) -> str:
    """将守卫依赖结构转为稳定文本，避免引入项目专属字段分支。"""
    if isinstance(value, dict):
        return " ".join(f"{key} {json_compact(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return " ".join(json_compact(item) for item in value)
    return str(value)
