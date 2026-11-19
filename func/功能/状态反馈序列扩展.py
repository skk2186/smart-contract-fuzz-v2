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
_BYTES = re.compile(r"^bytes([1-9]|[12][0-9]|3[0-2])$")


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


def feedback_vector(replay: dict[str, Any], *, property_source: str = "",
                    seen_states: set[str] | None = None) -> dict[str, Any]:
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
    property_value = rows[-1].get("target_property") if rows else next(
        iter(replay.get("initial_property_values", {}).values()), None)
    target_state = replay.get("target_property_state", {})
    final_getters = rows[-1].get("predicate_getter_values", []) if rows else prior
    distance = numeric_violation_distance(property_source, final_getters)
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
            "counterexample_reached": property_value is False or bool(target_state.get("counterexample_state_established")),
            "property_value": property_value,
            "shared_resource_edges": shared_resource_edges(replay),
            "getter_state_fingerprints": sorted(fingerprints)}


def _insert(sequence: list[dict[str, Any]], tx: dict[str, Any], index: int) -> list[dict[str, Any]]:
    return [*copy.deepcopy(sequence[:index]), copy.deepcopy(tx), *copy.deepcopy(sequence[index:])]


def propose_extensions(sequence: list[dict[str, Any]], action_templates: list[dict[str, Any]],
                       action_evidence: dict[str, dict[str, Any]],
                       abi_by_signature: dict[str, dict[str, Any]],
                       *, mode: str, replay: dict[str, Any] | None = None,
                       target_states: set[str] | None = None,
                       senders: list[str] | None = None,
                       max_sequence_length: int = 8,
                       max_proposals: int = 24,
                       random_seed: int = 0) -> list[dict[str, Any]]:
    """Generate one bounded layer of candidates; caller executes and feeds back each result."""
    if mode not in {"random", "static", "state_feedback"}:
        raise ValueError(f"unsupported extension mode: {mode}")
    if len(sequence) >= max_sequence_length:
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

    # Static and full modes may add a missing action only when static property-action
    # evidence ties it to a target state read/written by the property.
    present_functions = {str(tx.get("function", "")) for tx in sequence}
    for template in action_templates:
        signature = str(template.get("function", ""))
        if signature in present_functions:
            continue
        evidence = action_evidence.get(signature, {})
        relevant = set(evidence.get("matched_states", [])) | set(evidence.get("read_states", [])) | set(evidence.get("write_states", []))
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


def retain_diverse_prefixes(scored: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
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
            score = (int(vector.get("counterexample_reached", False)),
                     int(vector.get("replay_complete", False)),
                     int(vector.get("property_related_state_changed", False)),
                     int(vector.get("new_relevant_state_count", 0)),
                     int(vector.get("next_step_dependency_evidence_count", 0)),
                     -float((vector.get("numeric_target_distance") or {}).get("distance", 1.0)),
                     int(vector.get("transactions_succeeded", 0)))
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
