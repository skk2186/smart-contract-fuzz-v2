#!/usr/bin/env python3
"""Budgeted sequence extension driven by ABI, dependency, and execution evidence.

This module does not classify function meaning from function names. It accepts
property/action evidence from the caller and produces bounded transaction-list
edits. All proposed sequences still require a fresh Anvil replay.
"""

from __future__ import annotations

import copy
import hashlib
import json
import random
import re
from typing import Any, Iterable


ROLE_TOKENS = {"actor", "account", "user", "caller", "owner", "sender",
               "recipient", "spender", "operator", "index", "participant"}
_UINT = re.compile(r"^uint([0-9]*)$")
_INT = re.compile(r"^int([0-9]*)$")
_DYNAMIC_INT_ARRAY = re.compile(r"^(uint|int)([0-9]*)\[\]$")
_BYTES = re.compile(r"^bytes([1-9]|[12][0-9]|3[0-2])$")
MAX_DYNAMIC_ARRAY_ELEMENTS = 16
MAX_DYNAMIC_ARRAY_HINTS = 12


def _json_key(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def transaction_fingerprint(tx: dict[str, Any]) -> tuple[Any, ...]:
    return (str(tx.get("function", "")), _json_key(tx.get("arguments", [])),
            str(tx.get("sender", "")).lower(), str(tx.get("value_wei", "0")),
            int(tx.get("delay_seconds", 0)), int(tx.get("delay_blocks", 0)))


def sequence_fingerprint(sequence: list[dict[str, Any]]) -> str:
    raw = _json_key([transaction_fingerprint(tx) for tx in sequence]).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _role_input(item: dict[str, Any]) -> bool:
    name = str(item.get("name") or "").lower()
    tokens = set(re.findall(r"[a-z]+", re.sub(r"([a-z])([A-Z])", r"\1 \2", name)))
    return bool(tokens & ROLE_TOKENS)


def _type_default(item: dict[str, Any], senders: list[str],
                  exemplars: list[tuple[str, Any]]) -> Any | None:
    kind = str(item.get("type", ""))
    name = str(item.get("name") or "")
    role = _role_input(item)
    for old_name, old_value in exemplars:
        if old_name.lower() == name.lower() and _value_fits(kind, old_value):
            return copy.deepcopy(old_value)
    if kind == "address":
        return senders[0] if senders else "0x" + "00" * 20
    if kind == "bool":
        return False
    if _UINT.fullmatch(kind) or _INT.fullmatch(kind):
        return 0 if role else 1
    if _DYNAMIC_INT_ARRAY.fullmatch(kind):
        # Zero is ABI-valid for every signed/unsigned integer element type and
        # a one-element default also satisfies common non-empty array guards.
        return [0]
    match = _BYTES.fullmatch(kind)
    if match:
        return "0x" + "00" * int(match.group(1))
    if kind == "string":
        return ""
    return None


def _value_fits(kind: str, value: Any) -> bool:
    if kind == "address":
        return isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{40}", value) is not None
    if kind == "bool":
        return isinstance(value, bool)
    if _UINT.fullmatch(kind):
        number = _safe_int(value)
        bits = int(kind[4:] or "256")
        return number is not None and 0 <= number < 2 ** bits
    if _INT.fullmatch(kind):
        number = _safe_int(value)
        bits = int(kind[3:] or "256")
        return number is not None and -(2 ** (bits - 1)) <= number < 2 ** (bits - 1)
    array_match = _DYNAMIC_INT_ARRAY.fullmatch(kind)
    if array_match:
        if not isinstance(value, list):
            return False
        element_type = array_match.group(1) + array_match.group(2)
        return all(_value_fits(element_type, item) for item in value)
    match = _BYTES.fullmatch(kind)
    if match:
        return isinstance(value, str) and re.fullmatch(
            r"0x[0-9a-fA-F]{" + str(2 * int(match.group(1))) + r"}", value) is not None
    return kind == "string" and isinstance(value, str)


def build_action_templates(action_inventory: list[dict[str, Any]],
                           abi_by_signature: dict[str, dict[str, Any]],
                           base_transactions: list[dict[str, Any]],
                           senders: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Create only ABI-valid, evidence-linked templates; payable value is copied from a seed."""
    payable_values = [int(tx.get("value_wei", 0)) for tx in base_transactions
                      if int(tx.get("value_wei", 0)) > 0]
    default_payable_value = min(payable_values) if payable_values else None
    exemplars = []
    for tx in base_transactions:
        abi = abi_by_signature.get(str(tx.get("function", "")), {})
        for item, value in zip(abi.get("inputs", []), tx.get("arguments", [])):
            exemplars.append((str(item.get("name") or ""), value))
    templates: list[dict[str, Any]] = []
    decisions = []
    seen = set()
    for action in action_inventory:
        signature = str(action.get("abi_signature") or "")
        abi = abi_by_signature.get(signature)
        if not signature or not abi or not action.get("seed_compatible", True):
            decisions.append({"function": signature or action.get("function"),
                              "decision": "discarded", "reason": "missing or unsupported ABI"})
            continue
        if signature in seen:
            continue
        seen.add(signature)
        if action.get("analysis_status") not in {None, "candidate_only", "analyzed", "supported"}:
            decisions.append({"function": signature, "decision": "discarded",
                              "reason": "no usable static action evidence"})
            continue
        arguments = []
        unsupported = None
        for item in abi.get("inputs", []):
            value = _type_default(item, senders, exemplars)
            if value is None:
                unsupported = "ABI argument type has no safe default: " + str(item.get("type"))
                break
            arguments.append(value)
        if unsupported:
            decisions.append({"function": signature, "decision": "discarded", "reason": unsupported})
            continue
        payable = bool(action.get("payable") or abi.get("stateMutability") == "payable")
        if payable and default_payable_value is None:
            decisions.append({"function": signature, "decision": "discarded",
                              "reason": "no prior legal payable value to reuse"})
            continue
        tx = {"function": signature, "arguments": arguments,
              "sender": senders[0] if senders else base_transactions[0].get("sender"),
              "value_wei": str(default_payable_value if payable else 0),
              "delay_seconds": 0, "delay_blocks": 0,
              "expected_outcome": "state_change",
              "sequence_extension_evidence": {
                  "matched_states": list(action.get("matched_states", [])),
                  "read_states": list(action.get("read_states", [])),
                  "write_states": list(action.get("write_states", [])),
                  "evidence_origin": "property_action_inventory"}}
        if not _valid_transaction(tx, abi):
            decisions.append({"function": signature, "decision": "discarded",
                              "reason": "local ABI shape validation failed"})
            continue
        templates.append(tx)
        decisions.append({"function": signature, "decision": "template_created",
                          "reason": "ABI-valid and linked to property action evidence"})
    return templates, decisions


def _valid_transaction(tx: dict[str, Any], abi: dict[str, Any]) -> bool:
    inputs = abi.get("inputs", [])
    args = tx.get("arguments", [])
    return (len(inputs) == len(args) and all(_value_fits(str(item.get("type", "")), value)
                                             for item, value in zip(inputs, args)) and
            isinstance(tx.get("sender"), str) and
            re.fullmatch(r"0x[0-9a-fA-F]{40}", tx["sender"]) is not None and
            _safe_int(tx.get("value_wei", 0)) is not None and
            int(tx.get("value_wei", 0)) >= 0)


def role_variants(tx: dict[str, Any], abi: dict[str, Any], *,
                  senders: list[str], values: Iterable[int] = (0, 1, 2)) -> list[dict[str, Any]]:
    """Enumerate small ABI-valid caller/actor variants from named role inputs."""
    result = []
    inputs = abi.get("inputs", [])
    for index, item in enumerate(inputs):
        if index >= len(tx.get("arguments", [])) or not _role_input(item):
            continue
        kind = str(item.get("type", ""))
        if not (_UINT.fullmatch(kind) or _INT.fullmatch(kind)):
            continue
        for value in values:
            changed = copy.deepcopy(tx)
            if value == _safe_int(changed["arguments"][index]):
                continue
            changed["arguments"][index] = value
            if _valid_transaction(changed, abi):
                result.append(changed)
    for sender in senders:
        if sender.lower() == str(tx.get("sender", "")).lower():
            continue
        changed = copy.deepcopy(tx)
        changed["sender"] = sender
        if _valid_transaction(changed, abi):
            result.append(changed)
    return result


def trace_addresses(trace: dict[str, Any] | None) -> set[str]:
    addresses: set[str] = set()
    if not isinstance(trace, dict):
        return addresses
    stack = [trace]
    while stack:
        node = stack.pop()
        for field in ("from", "to"):
            value = node.get(field)
            if isinstance(value, str) and value.startswith("0x"):
                addresses.add(value.lower())
        stack.extend(item for item in node.get("calls", []) if isinstance(item, dict))
    return addresses


def shared_resource_edges(replay: dict[str, Any]) -> list[dict[str, Any]]:
    """Find cross-transaction contract targets with observed balance movement."""
    transactions = replay.get("transactions", [])
    per_tx = []
    for row in transactions:
        changes = {str(item.get("address", "")).lower(): int(item.get("delta_wei", 0))
                   for item in row.get("balance_changes", [])}
        targets = trace_addresses(row.get("internal_call_trace"))
        per_tx.append({"index": row.get("index"), "targets": targets, "changes": changes,
                       "status": row.get("status")})
    edges = []
    for left_index, left in enumerate(per_tx):
        for right in per_tx[left_index + 1:]:
            common = (left["targets"] & right["targets"] &
                      set(left["changes"]) & set(right["changes"]))
            for address in sorted(common):
                if left["changes"][address] > 0 and right["changes"][address] < 0:
                    edges.append({"producer_transaction": left["index"],
                                  "consumer_transaction": right["index"],
                                  "resource_address": address,
                                  "producer_delta_wei": left["changes"][address],
                                  "consumer_delta_wei": right["changes"][address],
                                  "evidence": "same traced contract target; observed positive then negative balance delta"})
    return edges


def _getter_map(rows: list[dict[str, Any]]) -> dict[tuple[str, str], int]:
    values: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.get("status") != "observed" or "value" not in row:
            continue
        number = _safe_int(row.get("value"))
        if number is None:
            continue
        signature = str(row.get("signature", ""))
        name = signature.split("(", 1)[0]
        key = _json_key(row.get("arguments", []))
        values[(name, key)] = number
    return values


def numeric_violation_distance(property_source: str,
                               getter_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Compute normalized distance for a simple comparison that returns false on violation."""
    pairs = []
    patterns = [
        re.compile(r"if\s*\(\s*(?P<a>[A-Za-z_]\w*)\s*\[\s*(?P<idx>[A-Za-z_]\w*)\s*\]\s*(?P<op>>=|>|<=|<)\s*(?P<b>[A-Za-z_]\w*)\s*\[\s*(?P=idx)\s*\]\s*\)\s*(?:\{\s*)?return\s+false", re.I),
        re.compile(r"return\s+(?P<a>[A-Za-z_]\w*)\s*\[\s*(?P<idx>[A-Za-z_]\w*)\s*\]\s*(?P<op><=|<|>=|>)\s*(?P<b>[A-Za-z_]\w*)\s*\[\s*(?P=idx)\s*\]", re.I),
    ]
    for pattern in patterns:
        pairs.extend(pattern.finditer(property_source))
    observed = _getter_map(getter_rows)
    candidates = []
    for match in pairs:
        a_name, b_name, operator = match.group("a"), match.group("b"), match.group("op")
        common_keys = {key for name, key in observed if name == a_name} & {
            key for name, key in observed if name == b_name}
        for key in common_keys:
            a, b = observed[(a_name, key)], observed[(b_name, key)]
            # `if (condition) return false` means condition itself is the violation.
            if operator == ">":
                raw = max(0, b - a + 1)
            elif operator == ">=":
                raw = max(0, b - a)
            elif operator == "<":
                raw = max(0, a - b + 1)
            else:  # <=
                raw = max(0, a - b)
            scale = max(abs(a), abs(b), 1)
            candidates.append({"left_getter": a_name, "right_getter": b_name,
                               "operator": operator, "left_value": a,
                               "right_value": b, "distance": raw / scale,
                               "distance_units": raw, "arguments": json.loads(key)})
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item["distance"], item["left_getter"],
                                             item["right_getter"]))


def _matches_explicit_guard_error(reason: str, guards: list[dict[str, Any]]) -> bool:
    """Match a revert identifier only when it appears in an evidenced source guard."""
    observed_codes = set(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b", reason.upper()))
    guard_codes = set()
    for guard in guards:
        guard_codes.update(re.findall(r"\b[A-Z][A-Z0-9_]{2,}\b",
                                     str(guard.get("expression", "")).upper()))
    return bool(observed_codes & guard_codes)


def feedback_vector(replay: dict[str, Any], *, property_source: str = "",
                    seen_states: set[str] | None = None,
                    action_evidence: dict[str, dict[str, Any]] | None = None,
                    parent_vector: dict[str, Any] | None = None,
                    target_states: set[str] | None = None) -> dict[str, Any]:
    rows = replay.get("transactions", [])
    getter_states = []
    prior = replay.get("initial_predicate_getters", [])
    getter_states.append(_json_key([(row.get("signature"), row.get("arguments"), row.get("value"))
                                   for row in prior if row.get("status") == "observed"]))
    for row in rows:
        getter_states.append(_json_key([(item.get("signature"), item.get("arguments"), item.get("value"))
                                        for item in row.get("predicate_getter_values", [])
                                        if item.get("status") == "observed"]))
    fingerprints = {hashlib.sha256(item.encode("utf-8")).hexdigest() for item in getter_states}
    prior_seen = seen_states or set()
    related_changes = sum(len(row.get("changed_predicate_getters", []))
                          for row in replay.get("target_property_state", {}).get("trajectory", []))
    property_rows = [(index + 1, row) for index, row in enumerate(rows)
                     if row.get("target_property") is not None]
    property_check_index, property_check_row = property_rows[-1] if property_rows else (None, None)
    target_state = replay.get("target_property_state", {})
    initial_values = replay.get("initial_property_values", {})
    target_signature = str(target_state.get("property") or "")
    initial_matches = [value for signature, value in initial_values.items()
                       if target_signature and
                       str(signature).rsplit(".", 1)[-1] == target_signature.rsplit(".", 1)[-1]]
    property_value = (property_check_row.get("target_property") if property_check_row else
                      initial_matches[0] if len(initial_matches) == 1 else None)
    property_check_status = (property_check_row.get("target_property_status")
                             if property_check_row else None)
    property_check_status = property_check_status or (
        "passed" if property_value is True else
        "failed" if property_value is False else "unknown")
    final_getters = rows[-1].get("predicate_getter_values", []) if rows else prior
    distance = numeric_violation_distance(property_source, final_getters)
    target_progress = {"status": "unknown", "direction": "unknown", "evidence": None}
    if property_value is False:
        target_progress = {"status": "goal_reached", "direction": "violation_observed",
                           "evidence": "original target property evaluated false"}
    elif distance is not None and parent_vector and parent_vector.get("numeric_target_distance"):
        parent_distance = parent_vector["numeric_target_distance"]
        same_operands = all(distance.get(key) == parent_distance.get(key)
                            for key in ("left_getter", "right_getter", "operator", "arguments"))
        if same_operands and distance["distance"] < parent_distance["distance"]:
            target_progress = {"status": "directional_progress", "direction": "toward_violation",
                               "evidence": {"previous_distance": parent_distance["distance"],
                                            "current_distance": distance["distance"],
                                            "operand_evidence": distance}}
        elif same_operands:
            target_progress = {"status": "observed_no_directional_progress",
                               "direction": "unchanged_or_away_from_violation",
                               "evidence": {"previous_distance": parent_distance["distance"],
                                            "current_distance": distance["distance"],
                                            "operand_evidence": distance}}
    elif property_value is True:
        # A passing Boolean or relational property has no scalar distance. Keep it
        # observed, but do not turn True/False into an invented numeric score.
        target_progress = {"status": "observed_safe_no_directional_progress",
                           "direction": "unknown", "evidence": "original property evaluated true"}
    prerequisite_conditions = []
    evidence_by_action = action_evidence or {}
    observed_target_state_changes = []
    target_state_names = set(target_states or [])
    for index, row in enumerate(rows, start=1):
        changed_effects = {str(item.get("state") if isinstance(item, dict) else item)
                           for item in (row.get("changed_effect_states") or [])}
        matched_target_changes = sorted(changed_effects & target_state_names)
        if matched_target_changes:
            observed_target_state_changes.append({"transaction_index": index,
                "function": row.get("function"), "changed_states": matched_target_changes,
                "evidence": "execution backend reported changed_effect_states"})
        if row.get("changed_predicate_getters"):
            observed_target_state_changes.append({"transaction_index": index,
                "function": row.get("function"),
                "changed_predicate_getters": copy.deepcopy(row.get("changed_predicate_getters")),
                "evidence": "execution backend reported changed predicate getter values",
                "direction": "unknown unless property comparison supplies a boundary"})
        signature = str(row.get("function", ""))
        action = evidence_by_action.get(signature, {})
        guards = [guard for effect in action.get("effect_evidence", []) or []
                  for guard in effect.get("guards", []) or []]
        guards.extend(action.get("action_guard_evidence", []) or [])
        evidenced_guards = [guard for guard in guards
                            if guard.get("source") and guard.get("state_reads")]
        if not evidenced_guards:
            continue
        failed_reason = str(row.get("revert_reason") or row.get("property_error") or "")
        normalized_reason = failed_reason.replace("_", " ")
        state_related_failure = (_matches_explicit_guard_error(failed_reason, evidenced_guards) or
            bool(re.search(r"not\s+found|unknown\s+(?:account|object|key)|missing|not\s+initiali[sz]ed|"
                r"does\s+not\s+exist|unauthori[sz]ed|insufficient|not\s+registered|"
                r"too\s+low|below|under\s+(?:the\s+)?minimum", normalized_reason, re.I)))
        guard_states = sorted({str(state) for guard in evidenced_guards
                               for state in guard.get("state_reads", []) or []})
        preceding_writers = []
        for prior_index, prior_row in enumerate(rows[:index - 1], start=1):
            if prior_row.get("status") != "success":
                continue
            prior_signature = str(prior_row.get("function", ""))
            prior_action = evidence_by_action.get(prior_signature, {})
            actual_changes = {str(item.get("state") if isinstance(item, dict) else item)
                              for item in (prior_row.get("changed_effect_states") or [])}
            matched = actual_changes & set(guard_states)
            if matched:
                preceding_writers.append({"transaction_index": prior_index,
                    "function": prior_signature, "changed_guard_states": sorted(matched),
                    "static_write_states": sorted(set(prior_action.get("write_states", [])) & matched)})
        if row.get("status") == "success" and preceding_writers:
            status = "precondition_established"
        elif row.get("status") == "success":
            status = "consumer_succeeded_state_unobserved"
        elif state_related_failure:
            status = "state_prerequisite_unmet"
        else:
            status = "unknown"
        prerequisite_conditions.append({"transaction_index": index,
            "consumer_function": signature, "status": status,
            "consumer_arguments": copy.deepcopy(row.get("arguments", [])),
            "consumer_sender": row.get("sender"),
            "guard_sources": sorted({str(guard["source"]) for guard in evidenced_guards}),
            "guard_states": guard_states, "preceding_writers": preceding_writers,
            "failure_evidence": failed_reason if state_related_failure else None})
    parent_conditions = {(item.get("consumer_function"), _json_key(item.get("consumer_arguments", [])),
                          item.get("consumer_sender"), tuple(item.get("guard_states", []))):
                         item.get("status") for item in (parent_vector or {}).get("precondition_conditions", [])}
    prerequisite_progress = []
    for condition in prerequisite_conditions:
        key = (condition.get("consumer_function"), _json_key(condition.get("consumer_arguments", [])),
               condition.get("consumer_sender"), tuple(condition.get("guard_states", [])))
        if (parent_conditions.get(key) == "state_prerequisite_unmet" and
                condition.get("status") == "precondition_established"):
            prerequisite_progress.append({"consumer_function": key[0],
                "guard_states": key[3], "consumer_arguments": condition.get("consumer_arguments"),
                "consumer_sender": condition.get("consumer_sender"),
                "preceding_writers": condition.get("preceding_writers"),
                "evidence": "same consumer changed from a state-related revert to success after an observed change to its statically read guard state"})
    dependent_successors = sum(
        1 for index, row in enumerate(rows)
        if row.get("status") == "success" and (row.get("changed_effect_states") or
                                                 row.get("changed_predicate_getters")))
    return {"transactions_succeeded": sum(row.get("status") == "success" for row in rows),
            "transactions_total": len(rows),
            "replay_complete": replay.get("replay_status") == "executable",
            "property_related_state_changed": bool(target_state.get("property_related_state_changed")),
            "changed_predicate_getter_count": related_changes,
            "new_relevant_state_count": len(fingerprints - prior_seen),
            "next_step_dependency_evidence_count": dependent_successors,
            "numeric_target_distance": distance,
            "target_progress": target_progress,
            "precondition_conditions": prerequisite_conditions,
            "precondition_progress": prerequisite_progress,
            "observed_target_state_changes": observed_target_state_changes,
            "counterexample_reached": property_value is False or bool(target_state.get("counterexample_state_established")),
            "property_value": property_value,
            "property_check_transaction_index": property_check_index,
            "property_check_status": property_check_status,
            "shared_resource_edges": shared_resource_edges(replay),
            "getter_state_fingerprints": sorted(fingerprints)}


def _insert(sequence: list[dict[str, Any]], tx: dict[str, Any], index: int) -> list[dict[str, Any]]:
    return [*copy.deepcopy(sequence[:index]), copy.deepcopy(tx), *copy.deepcopy(sequence[index:])]


def _dynamic_array_domain(kind: str) -> tuple[str, int, int] | None:
    match = _DYNAMIC_INT_ARRAY.fullmatch(kind)
    if not match:
        return None
    bits = int(match.group(2) or "256")
    if match.group(1) == "uint":
        return "uint" + match.group(2), 0, 2 ** bits - 1
    return "int" + match.group(2), -(2 ** (bits - 1)), 2 ** (bits - 1) - 1


def _feedback_integer_hints(replay: dict[str, Any] | None) -> tuple[list[tuple[int, str, dict[str, Any]]], int | None]:
    """Extract bounded numeric hints from generic execution/error observations."""
    if not replay:
        return [], None
    hints: list[tuple[int, str, dict[str, Any]]] = []
    seen: set[tuple[int, str]] = set()
    required_length = None

    def add(value: Any, source: str, evidence: dict[str, Any]) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            return
        key = (value, source)
        if key not in seen:
            seen.add(key)
            hints.append((value, source, evidence))

    def walk_numeric(value: Any, source: str, evidence: dict[str, Any]) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int):
            add(value, source, evidence)
        elif isinstance(value, str) and re.fullmatch(r"[-+]?\d+", value.strip()):
            add(int(value.strip()), source, evidence)
        elif isinstance(value, dict):
            for child in value.values():
                walk_numeric(child, source, evidence)
        elif isinstance(value, list):
            for child in value:
                walk_numeric(child, source, evidence)

    state_tokens = ("observation", "getter", "state", "balance", "effect", "amount")
    error_keys = {"revert_reason", "failure_reason", "property_error", "error", "message"}
    for tx_index, row in enumerate(replay.get("transactions", []) or [], 1):
        if not isinstance(row, dict):
            continue
        for key, value in row.items():
            normalized = str(key).lower()
            if normalized in error_keys and isinstance(value, str):
                evidence = {"transaction_index": tx_index, "feedback_field": str(key)}
                numbers = [int(token) for token in re.findall(r"(?<![A-Za-z_])[-+]?\d+", value)]
                for number in numbers:
                    add(number, "execution_failure_detail", evidence)
                    # A value adjacent to a reported bound is a generic repair
                    # candidate; ABI checks below discard out-of-range values.
                    add(number - 1, "neighbor_of_execution_failure_value", evidence)
                    add(number + 1, "neighbor_of_execution_failure_value", evidence)
                if re.search(r"length|size|elements?|items?", value, re.IGNORECASE):
                    required = re.search(
                        r"(?:at\s+least|minimum(?:\s+of)?|(?:length|size)\s*(?:>=|>|must\s+be|is|of))\s*(\d+)",
                        value, re.IGNORECASE)
                    if required:
                        candidate = int(required.group(1))
                        required_length = max(required_length or 0, candidate)
            elif any(token in normalized for token in state_tokens):
                walk_numeric(value, "observed_execution_state", {
                    "transaction_index": tx_index, "feedback_field": str(key)})
    return hints[:MAX_DYNAMIC_ARRAY_HINTS], required_length


def _sequence_array_hints(sequence: list[dict[str, Any]],
                          abi_by_signature: dict[str, dict[str, Any]],
                          element_type: str) -> list[tuple[int, dict[str, Any]]]:
    values: list[tuple[int, dict[str, Any]]] = []
    seen = set()
    for tx_index, tx in enumerate(sequence, 1):
        abi = abi_by_signature.get(str(tx.get("function", "")), {})
        for argument_index, item in enumerate(abi.get("inputs", [])):
            kind = str(item.get("type", ""))
            domain = _dynamic_array_domain(kind)
            arguments = tx.get("arguments", [])
            if not domain or domain[0] != element_type or argument_index >= len(arguments):
                continue
            array = arguments[argument_index]
            if not isinstance(array, list):
                continue
            for element_index, value in enumerate(array):
                number = _safe_int(value)
                if number is None or not _value_fits(element_type, number) or number in seen:
                    continue
                seen.add(number)
                values.append((number, {"transaction_index": tx_index,
                                        "argument_index": argument_index,
                                        "element_index": element_index}))
    return values


def _dynamic_array_variants(kind: str, value: Any,
                            sequence_hints: list[tuple[int, dict[str, Any]]],
                            feedback_hints: list[tuple[int, str, dict[str, Any]]],
                            required_length: int | None) -> list[tuple[list[int], str, dict[str, Any]]]:
    domain = _dynamic_array_domain(kind)
    if not domain or not _value_fits(kind, value):
        return []
    element_type, lower, upper = domain
    values: list[tuple[int, str, dict[str, Any]]] = []
    value_sources: dict[int, tuple[str, dict[str, Any]]] = {}

    def add_value(number: int, source: str, evidence: dict[str, Any]) -> None:
        if not _value_fits(element_type, number):
            return
        if number not in value_sources:
            value_sources[number] = (source, evidence)
            values.append((number, source, evidence))

    add_value(lower, "ABI lower bound", {"abi_minimum": str(lower)})
    add_value(upper, "ABI upper bound", {"abi_maximum": str(upper)})
    add_value(0, "ABI-valid zero element", {"abi_range": [str(lower), str(upper)]})
    if element_type.startswith("int"):
        add_value(-1, "ABI-valid negative element", {"abi_range": [str(lower), str(upper)]})
    add_value(1, "ABI-valid positive element", {"abi_range": [str(lower), str(upper)]})
    for number, evidence in sequence_hints:
        add_value(number, "copied from a valid sequence array element", evidence)
    for number, source, evidence in feedback_hints:
        add_value(number, source, evidence)

    current = list(value)
    variants: list[tuple[list[int], str, dict[str, Any]]] = []
    seen: set[tuple[int, ...]] = set()

    def add_variant(candidate: list[int], reason: str, evidence: dict[str, Any]) -> None:
        if len(candidate) > MAX_DYNAMIC_ARRAY_ELEMENTS or not _value_fits(kind, candidate):
            return
        key = tuple(candidate)
        if key not in seen and candidate != current:
            seen.add(key)
            variants.append((candidate, reason, evidence))

    for number, source, source_evidence in values:
        if not current:
            add_variant([number], "create a one-element dynamic integer array from " + source,
                        {"value_source": source, "source_evidence": source_evidence,
                         "abi_element_range": [str(lower), str(upper)]})
        else:
            for element_index, old_value in enumerate(current):
                if _safe_int(old_value) == number:
                    continue
                candidate = list(current)
                candidate[element_index] = number
                add_variant(candidate, "adjust an array element using " + source,
                            {"element_index": element_index, "old_value": str(old_value),
                             "new_value": str(number), "value_source": source,
                             "source_evidence": source_evidence,
                             "abi_element_range": [str(lower), str(upper)]})
        if len(current) < MAX_DYNAMIC_ARRAY_ELEMENTS:
            add_variant([*current, number], "append an ABI-valid element from " + source,
                        {"element_index": len(current), "new_value": str(number),
                         "value_source": source, "source_evidence": source_evidence,
                         "abi_element_range": [str(lower), str(upper)]})

    if len(current) > 1:
        add_variant(current[:-1], "shorten the dynamic array by one element",
                    {"old_length": len(current), "new_length": len(current) - 1,
                     "value_source": "existing valid sequence parameter"})
    if required_length and len(current) < required_length <= MAX_DYNAMIC_ARRAY_ELEMENTS:
        candidate = current + [0] * (required_length - len(current))
        add_variant(candidate, "extend the array to the minimum length indicated by execution failure feedback",
                    {"old_length": len(current), "required_length": required_length,
                     "value_source": "execution failure detail"})
    return variants


def propose_extensions(sequence: list[dict[str, Any]], action_templates: list[dict[str, Any]],
                       action_evidence: dict[str, dict[str, Any]],
                       abi_by_signature: dict[str, dict[str, Any]],
                       *, mode: str, replay: dict[str, Any] | None = None,
                       target_states: set[str] | None = None,
                       senders: list[str] | None = None,
                       max_sequence_length: int = 8,
                       max_proposals: int = 24,
                       random_seed: int = 0,
                       allow_repeated_prerequisite: bool = False) -> list[dict[str, Any]]:
    """Generate one bounded layer of candidates; caller executes and feeds back each result."""
    if mode not in {"random", "static", "state_feedback"}:
        raise ValueError(f"unsupported extension mode: {mode}")
    if max_proposals <= 0 or len(sequence) > max_sequence_length:
        return []
    senders = list(senders or [])
    target_states = target_states or set()
    current = [transaction_fingerprint(tx) for tx in sequence]
    proposals: list[dict[str, Any]] = []
    rng = random.Random(random_seed)

    def add(candidate: list[dict[str, Any]], operator: str, reason: str,
            evidence: Any = None) -> None:
        if not candidate or len(candidate) > max_sequence_length:
            return
        fp = sequence_fingerprint(candidate)
        if fp in {row["fingerprint"] for row in proposals}:
            return
        proposals.append({"sequence": candidate, "fingerprint": fp,
                          "operator": operator, "proposal_reason": reason,
                          "evidence": evidence})

    def add_dynamic_array_candidates() -> None:
        # Reserve half of the shared proposal budget for array operations. The
        # remaining budget stays available to the existing Phase36/E3 operators.
        array_budget = min(max_proposals, max(1, max_proposals // 2))
        has_array_transaction = any(
            any(_DYNAMIC_INT_ARRAY.fullmatch(str(item.get("type", "")))
                for item in abi_by_signature.get(str(tx.get("function", "")), {}).get("inputs", []))
            for tx in sequence)
        copy_reserve = (min(4, len(sequence) + 1) if
                        has_array_transaction and len(sequence) < max_sequence_length else 0)
        adjustment_budget = max(1, array_budget - copy_reserve)
        feedback_hints, required_length = _feedback_integer_hints(replay)
        sequence_hints_by_type: dict[str, list[tuple[int, dict[str, Any]]]] = {}

        def array_hints_for(kind: str) -> list[tuple[int, dict[str, Any]]]:
            domain = _dynamic_array_domain(kind)
            if not domain:
                return []
            element_type = domain[0]
            if element_type not in sequence_hints_by_type:
                sequence_hints_by_type[element_type] = _sequence_array_hints(
                    sequence, abi_by_signature, element_type)
            return sequence_hints_by_type[element_type]

        def replace_array_argument(tx_index: int, argument_index: int,
                                   kind: str, value: Any) -> None:
            if len(proposals) >= adjustment_budget:
                return
            for candidate_value, reason, evidence in _dynamic_array_variants(
                    kind, value, array_hints_for(kind), feedback_hints, required_length):
                candidate = copy.deepcopy(sequence)
                candidate[tx_index]["arguments"][argument_index] = candidate_value
                add(candidate, "dynamic_array_argument_adjustment", reason,
                    {"transaction_index": tx_index + 1,
                     "argument_index": argument_index,
                     "abi_type": kind,
                     "before": copy.deepcopy(value),
                     "after": candidate_value,
                     **evidence})
                if len(proposals) >= adjustment_budget:
                    return

        for tx_index, tx in enumerate(sequence):
            abi = abi_by_signature.get(str(tx.get("function", "")), {})
            arguments = tx.get("arguments", [])
            for argument_index, item in enumerate(abi.get("inputs", [])):
                kind = str(item.get("type", ""))
                if (_DYNAMIC_INT_ARRAY.fullmatch(kind) and
                        argument_index < len(arguments) and
                        isinstance(arguments[argument_index], list)):
                    replace_array_argument(tx_index, argument_index, kind,
                                           arguments[argument_index])

        if len(sequence) < max_sequence_length:
            for tx_index, tx in enumerate(sequence):
                abi = abi_by_signature.get(str(tx.get("function", "")), {})
                if not any(_DYNAMIC_INT_ARRAY.fullmatch(str(item.get("type", "")))
                           for item in abi.get("inputs", [])):
                    continue
                for position in range(len(sequence) + 1):
                    add(_insert(sequence, tx, position), "dynamic_array_transaction_copy",
                        "copy an existing ABI-valid dynamic-array transaction at a new sequence position",
                        {"source_transaction_index": tx_index + 1,
                         "insertion_position": position,
                         "abi_types": [item.get("type") for item in abi.get("inputs", [])
                                       if _DYNAMIC_INT_ARRAY.fullmatch(str(item.get("type", "")))],
                         "value_source": "existing valid sequence transaction"})
                    if len(proposals) >= array_budget:
                        return

            # Action templates are already restricted to property/action
            # evidence. Dynamic arrays may be inserted even when the same
            # function occurs in the seed because only the input sequence is
            # copied; ABI and candidate budgets remain enforced here.
            for template in action_templates:
                signature = str(template.get("function", ""))
                abi = abi_by_signature.get(signature, {})
                arguments = template.get("arguments", [])
                for argument_index, item in enumerate(abi.get("inputs", [])):
                    kind = str(item.get("type", ""))
                    if (not _DYNAMIC_INT_ARRAY.fullmatch(kind) or
                            argument_index >= len(arguments) or
                            not isinstance(arguments[argument_index], list)):
                        continue
                    array_values = [(copy.deepcopy(arguments[argument_index]),
                                     "insert an evidence-linked dynamic-array action template",
                                     {"value_source": "ABI-valid action template"})]
                    array_values.extend(_dynamic_array_variants(
                        kind, arguments[argument_index], array_hints_for(kind),
                        feedback_hints, required_length))
                    seen_arguments = set()
                    for value, reason, evidence in array_values:
                        value_key = _json_key(value)
                        if value_key in seen_arguments:
                            continue
                        seen_arguments.add(value_key)
                        candidate_tx = copy.deepcopy(template)
                        candidate_tx["arguments"][argument_index] = value
                        for position in range(len(sequence) + 1):
                            add(_insert(sequence, candidate_tx, position),
                                "dynamic_array_action_insertion", reason,
                                {"function": signature,
                                 "argument_index": argument_index,
                                 "abi_type": kind,
                                 "insertion_position": position,
                                 **evidence})
                            if len(proposals) >= array_budget:
                                return

    if mode == "state_feedback":
        add_dynamic_array_candidates()

    if mode == "random":
        operations = []
        for template in action_templates:
            abi = abi_by_signature.get(str(template.get("function", "")), {})
            operations.append((template, "random_action"))
            operations.extend((variant, "random_role_or_sender")
                              for variant in role_variants(template, abi, senders=senders))
        rng.shuffle(operations)
        for template, kind in operations:
            positions = list(range(1, len(sequence) + 1))
            rng.shuffle(positions)
            if positions:
                position = positions[0]
                add(_insert(sequence, template, position), kind,
                    "seeded random insertion of an ABI-valid action")
            add([*copy.deepcopy(sequence), copy.deepcopy(template)], kind,
                "seeded random append of an ABI-valid action")
            if len(proposals) >= max_proposals:
                break
        return proposals[:max_proposals]

    present_functions = {str(tx.get("function", "")) for tx in sequence}
    # A failed operation is handled first. Precondition insertion is allowed only
    # when a concrete state written by an available action is read by an explicit
    # guard on the failed operation. Numeric lower-bound failures belong to E2.
    tx_feedback = replay.get("transactions", []) if replay else []
    failed = next((row for row in tx_feedback if row.get("status") != "success" or
                   row.get("execution_class") in {"unexpected_internal_revert", "outer_revert"}), None)
    if mode == "state_feedback" and failed is not None:
        raw_reason = str(failed.get("revert_reason") or failed.get("property_error") or "")
        reason = raw_reason.lower().replace("_", " ")
        failed_index = max(0, int(failed.get("index", failed.get("transaction_index", 1))) - 1)
        failed_signature = str(failed.get("function", ""))
        consumer_evidence = action_evidence.get(failed_signature, {})
        consumer_reads = set(consumer_evidence.get("read_states", []))
        for effect in consumer_evidence.get("effect_evidence", []) or []:
            for guard in effect.get("guards", []) or []:
                consumer_reads.update(guard.get("state_reads", []) or [])
        guards = [guard for effect in consumer_evidence.get("effect_evidence", []) or []
                  for guard in effect.get("guards", []) or []]
        guards.extend(consumer_evidence.get("action_guard_evidence", []) or [])
        explicit_guard_error = _matches_explicit_guard_error(raw_reason, guards)
        if (not explicit_guard_error and re.search(
                r"too\s+low|below|under\s+(?:the\s+)?minimum|less\s+than\s+(?:the\s+)?minimum",
                reason)):
            return []
        failure_is_state_related = (explicit_guard_error or bool(re.search(
            r"not\s+found|unknown\s+(?:account|object|key)|missing|not\s+initiali[sz]ed|"
            r"does\s+not\s+exist|unauthori[sz]ed|insufficient|not\s+registered|"
            r"too\s+low|below|under\s+(?:the\s+)?minimum", reason)))
        if failure_is_state_related and consumer_reads:
            for template in action_templates:
                signature = str(template.get("function", ""))
                if signature in present_functions and not allow_repeated_prerequisite:
                    continue
                evidence = action_evidence.get(signature, {})
                producer_writes = set(evidence.get("write_states", []))
                for effect in evidence.get("effect_evidence", []) or []:
                    if effect.get("state"):
                        producer_writes.add(str(effect["state"]))
                matched = producer_writes & consumer_reads
                if not matched:
                    continue
                add(_insert(sequence, template, failed_index),
                    ("evidence_backed_repeated_prerequisite_insertion" if signature in present_functions else
                     "evidence_backed_failed_prerequisite_insertion"),
                    "insert a statically evidenced state producer before the earliest failed transaction",
                    {"failed_transaction": failed_index + 1,
                     "failed_function": failed_signature,
                     "matched_states": sorted(matched),
                     "guard_sources": [guard.get("source") for guard in guards
                                       if set(guard.get("state_reads", []) or []) & matched],
                     "failure_reason": reason})
                if len(proposals) >= max_proposals:
                    break
        # Do not fill a failed replay's budget with unrelated property-state calls.
        return proposals[:max_proposals]

    # Static and full modes may add a missing action only when a concrete write
    # overlaps a property state. Broad matched_states alone is correlation, not a
    # producer/consumer proof, and cannot consume the candidate budget.
    present_functions = {str(tx.get("function", "")) for tx in sequence}
    for template in action_templates:
        signature = str(template.get("function", ""))
        if signature in present_functions:
            continue
        evidence = action_evidence.get(signature, {})
        relevant = set(evidence.get("write_states", []))
        if target_states and not (relevant & target_states):
            continue
        template_fp = transaction_fingerprint(template)
        if template_fp in current:
            continue
        # Do not spend the state-feedback budget enumerating caller variants before
        # runtime evidence exists. Role expansion is activated below only after a
        # trace proves that a shared resource can fund a failed dependent operation.
        variants = [template]
        for variant in variants:
            for position in range(1, len(sequence) + 1):
                add(_insert(sequence, variant, position), "static_dependency_insertion",
                    "action evidence overlaps a property-relevant state; preserve prior prefix",
                    {"matched_states": sorted(relevant & target_states), "position": position})
                if len(proposals) >= max_proposals:
                    break
            if len(proposals) >= max_proposals:
                break
        if len(proposals) >= max_proposals:
            break

    if mode == "static" or replay is None:
        return proposals[:max_proposals]

    # Dynamic failure repair: insert a role-distinct prior producer immediately before
    # the failed action only when traces prove a common resource address. This uses
    # actual trace/balance feedback, not names or inferred vulnerability labels.
    tx_feedback = replay.get("transactions", [])
    failed = next((row for row in tx_feedback if row.get("status") != "success" or
                   row.get("execution_class") in {"unexpected_internal_revert", "outer_revert"}), None)
    if failed is not None:
        failure_index = max(0, int(failed.get("index", 1)) - 1)
        failed_targets = trace_addresses(failed.get("internal_call_trace"))
        for prior_index, prior_row in enumerate(tx_feedback[:failure_index]):
            prior_tx = sequence[prior_index] if prior_index < len(sequence) else None
            if not prior_tx or prior_row.get("status") != "success":
                continue
            changes = {str(item.get("address", "")).lower(): int(item.get("delta_wei", 0))
                       for item in prior_row.get("balance_changes", [])}
            positive_shared = {address for address, delta in changes.items()
                               if delta > 0 and address in failed_targets}
            if not positive_shared:
                continue
            signature = str(prior_tx.get("function", ""))
            abi = abi_by_signature.get(signature, {})
            for role_tx in role_variants(prior_tx, abi, senders=senders):
                old_roles = [value for item, value in zip(abi.get("inputs", []), prior_tx.get("arguments", []))
                             if _role_input(item)]
                new_roles = [value for item, value in zip(abi.get("inputs", []), role_tx.get("arguments", []))
                             if _role_input(item)]
                if old_roles == new_roles:
                    continue
                candidate = _insert(sequence, role_tx, failure_index)
                add(candidate, "shared_resource_role_expansion",
                    "a successful earlier call increased a traced resource used by the failed action; vary a role input before retry",
                    {"resource_addresses": sorted(positive_shared),
                     "producer_transaction": prior_index + 1,
                     "failed_transaction": failure_index + 1,
                     "old_role_values": old_roles, "new_role_values": new_roles})
                if len(proposals) >= max_proposals:
                    return proposals[:max_proposals]

    # Repetition is allowed only when a successful call changed property-related
    # observations and its trace shows state or shared-resource effects.
    for index, row in enumerate(tx_feedback):
        if index >= len(sequence) or row.get("status") != "success":
            continue
        if not row.get("changed_predicate_getters") and not row.get("changed_effect_states"):
            continue
        has_resource_effect = bool(row.get("balance_changes")) or int(
            row.get("changed_storage_slot_count") or 0) > 0
        if not has_resource_effect:
            continue
        template = copy.deepcopy(sequence[index])
        add([*copy.deepcopy(sequence), template], "state_supported_repetition",
            "repeat a successful property-relevant state transition with observed state/resource effect",
            {"source_transaction": index + 1,
             "changed_predicate_getters": row.get("changed_predicate_getters", []),
             "balance_changes": row.get("balance_changes", [])})
        if len(proposals) >= max_proposals:
            break
    return proposals[:max_proposals]


def retain_diverse_prefixes(scored: list[dict[str, Any]], limit: int = 4, *,
                            target_state_guided: bool = False) -> list[dict[str, Any]]:
    """Keep up to `limit` prefixes across outcome, role, sequence, and state dimensions."""
    if limit <= 0:
        return []
    remaining = list(scored)
    kept: list[dict[str, Any]] = []
    covered: set[str] = set()
    while remaining and len(kept) < limit:
        best = None
        best_key = None
        for row in remaining:
            vector = row.get("feedback", {})
            sequence = row.get("sequence", [])
            roles = _json_key([tx.get("arguments", []) for tx in sequence])
            shape = _json_key([tx.get("function") for tx in sequence])
            states = _json_key(vector.get("getter_state_fingerprints", []))
            categories = {"counterexample" if vector.get("counterexample_reached") else "property_change" if vector.get("property_related_state_changed") else "no_property_change",
                          "distance" if vector.get("numeric_target_distance") else "no_distance",
                          "roles:" + hashlib.sha256(roles.encode()).hexdigest()[:12],
                          "shape:" + hashlib.sha256(shape.encode()).hexdigest()[:12],
                          "state:" + hashlib.sha256(states.encode()).hexdigest()[:12]}
            legacy_score = (int(vector.get("counterexample_reached", False)),
                     int(vector.get("replay_complete", False)),
                     int(vector.get("property_related_state_changed", False)),
                     int(vector.get("new_relevant_state_count", 0)),
                     int(vector.get("next_step_dependency_evidence_count", 0)),
                     -float((vector.get("numeric_target_distance") or {}).get("distance", 1.0)),
                     int(vector.get("transactions_succeeded", 0)))
            if target_state_guided:
                progress = vector.get("target_progress", {})
                goal_score = int(progress.get("status") == "goal_reached")
                directional_score = int(progress.get("status") == "directional_progress")
                prerequisite_score = len(vector.get("precondition_progress", []))
                observed_satisfied = sum(item.get("status") == "consumer_call_succeeded"
                                         for item in vector.get("precondition_conditions", []))
                score = (goal_score, directional_score, prerequisite_score,
                         observed_satisfied, *legacy_score)
                categories.add("target-progress:" + str(progress.get("status", "unknown")))
                categories.add("prerequisite-progress:" + str(prerequisite_score))
            else:
                score = legacy_score
            diversity = len(categories - covered)
            key = (score, diversity)
            if best_key is None or key > best_key:
                best, best_key = row, key
                best["_retain_categories"] = categories
        if best is None:
            break
        best["retention_decision"] = "retained_diverse_prefix"
        kept.append(best)
        covered |= best.pop("_retain_categories", set())
        remaining.remove(best)
    kept_ids = {id(row) for row in kept}
    for row in remaining:
        row["retention_decision"] = "discarded_budget_or_lower_feedback_and_lower_diversity"
    return kept
