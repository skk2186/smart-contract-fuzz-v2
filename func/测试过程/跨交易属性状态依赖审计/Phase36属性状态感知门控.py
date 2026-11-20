#!/usr/bin/env python3
"""Phase36 experimental gate. Kept outside reusable/core V2 code."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any


def _key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _last_getters(replay: dict[str, Any]) -> list[dict[str, Any]]:
    txs = replay.get("transactions") or []
    if txs:
        return txs[-1].get("predicate_getter_values") or []
    return replay.get("initial_predicate_getters") or []


def _observed_scalar(getters: list[dict[str, Any]], signature: str) -> int | None:
    rows = [row for row in getters if row.get("signature") == signature]
    if len(rows) != 1 or rows[0].get("status") != "observed":
        return None
    try:
        return int(rows[0].get("value"))
    except (TypeError, ValueError):
        return None


def _is_complete_success(replay: dict[str, Any]) -> bool:
    txs = replay.get("transactions") or []
    return (replay.get("replay_status") == "executable" and bool(txs) and
            all(row.get("status") == "success" for row in txs))


def _guard_false_evidence(proposal: dict[str, Any], replay: dict[str, Any]
                          ) -> dict[str, Any] | None:
    """Prove that an exact appended call contradicts a simple observed static guard."""
    tx = (proposal.get("sequence") or [{}])[-1]
    signature = str(tx.get("function", ""))
    tx_rows = replay.get("transactions") or []
    getters = _last_getters(replay)
    values: dict[str, int] = {}
    for row in getters:
        if row.get("status") != "observed":
            continue
        try:
            value = int(row.get("value"))
        except (TypeError, ValueError):
            continue
        for expr in row.get("expressions") or []:
            if re.fullmatch(r"[A-Za-z_]\w*", str(expr)):
                values[str(expr)] = value
        getter_name = str(row.get("signature", "")).split("(", 1)[0]
        if re.fullmatch(r"[A-Za-z_]\w*", getter_name):
            values.setdefault(getter_name, value)

    checks = []
    for row in tx_rows:
        if row.get("function") != signature or row.get("status") != "success":
            continue
        for guard in row.get("slither_preconditions") or []:
            expression = str(guard.get("expression", ""))
            match = re.search(r"\)\(([^,()]*)\s*,", expression)
            if not match:
                continue
            condition = match.group(1).strip()
            simple = re.fullmatch(r"([A-Za-z_]\w*)\s*(==|!=|>=|<=|>|<)\s*(\d+)", condition)
            if not simple:
                continue
            variable, operator, raw_bound = simple.groups()
            if variable not in values:
                continue
            actual, bound = values[variable], int(raw_bound)
            satisfied = {"==": actual == bound, "!=": actual != bound,
                         ">=": actual >= bound, "<=": actual <= bound,
                         ">": actual > bound, "<": actual < bound}[operator]
            checks.append({"variable": variable, "observed": actual,
                           "operator": operator, "bound": bound,
                           "satisfied": satisfied,
                           "source": guard.get("source"),
                           "state_reads": guard.get("state_reads")})
            if not satisfied:
                return {"kind": "observed_static_guard_is_false",
                        "function": signature, "failed_guard": checks[-1],
                        "conclusion": "appended transaction is predicted to revert from the parent state"}
    return None


def _supply_sum_metric(replay: dict[str, Any], prop: dict[str, Any]
                       ) -> dict[str, Any] | None:
    predicate = str(prop.get("property_predicate") or "")
    # This recognizes a source-level aggregate conservation relation; it does not
    # use the boolean property result as a stopping signal.
    if not (re.search(r"\bsum\s*\+=\s*[^;]*balanceOf\s*\(", predicate) and
            re.search(r"return\s+sum\s*==\s*[^;]*totalSupply\s*\(\s*\)", predicate)):
        return None
    getters = _last_getters(replay)
    balance_rows = [row for row in getters
                    if row.get("signature") == "balanceOf(address)"]
    if not balance_rows or any(row.get("status") != "observed" for row in balance_rows):
        return None
    unique: dict[str, int] = {}
    for row in balance_rows:
        try:
            unique[_key([row.get("receiver_address"), row.get("arguments")])] = int(row["value"])
        except (KeyError, TypeError, ValueError):
            return None
    supply = _observed_scalar(getters, "totalSupply()")
    if supply is None:
        return None
    return {"relation": "aggregate_balance_equals_supply",
            "aggregate_balance": sum(unique.values()), "total_supply": supply,
            "residual": sum(unique.values()) - supply,
            "balance_observation_count": len(unique),
            "evidence": "source property explicitly sums balanceOf observations and compares with totalSupply"}


def _safe_repeat_probe(parent: dict[str, Any], child: dict[str, Any],
                       parent_sequence: list[dict[str, Any]],
                       child_sequence: list[dict[str, Any]],
                       prop: dict[str, Any], max_length: int) -> dict[str, Any] | None:
    if not _is_complete_success(parent) or not _is_complete_success(child):
        return None
    if len(child_sequence) != len(parent_sequence) + 1:
        return None
    added = child_sequence[-1]
    if not any(_key(added) == _key(tx) for tx in parent_sequence):
        return None
    before = _supply_sum_metric(parent, prop)
    after = _supply_sum_metric(child, prop)
    if before is None or after is None or before["residual"] != after["residual"]:
        return None
    delta_supply = after["total_supply"] - before["total_supply"]
    delta_balance = after["aggregate_balance"] - before["aggregate_balance"]
    if delta_supply <= 0 or delta_balance != delta_supply:
        return None
    remaining_slots = max(0, max_length - len(child_sequence))
    projected_supply = after["total_supply"] + remaining_slots * delta_supply
    projected_balance = after["aggregate_balance"] + remaining_slots * delta_balance
    uint256_max = (1 << 256) - 1
    if projected_supply > uint256_max or projected_balance > uint256_max:
        return None
    return {"kind": "bounded_repeat_preserves_explicit_aggregate_relation",
            "parent_metric": before, "child_metric": after,
            "delta_supply": delta_supply, "delta_aggregate_balance": delta_balance,
            "remaining_slots_at_max_length": remaining_slots,
            "projected_supply_upper_bound": projected_supply,
            "projected_balance_upper_bound": projected_balance,
            "integer_limit": uint256_max,
            "conclusion": "one clean replay measured equal coupled increments; the exact repeated call leaves the source-level relation residual unchanged and the bounded horizon remains below uint256"}


class AdaptiveGate:
    """Conservative candidate gate. Unexplained cases remain executable."""

    def __init__(self, prop: dict[str, Any], max_length: int):
        self.prop = prop
        self.max_length = max_length
        self.probed_repeats: dict[str, dict[str, Any]] = {}

    def decide(self, proposal: dict[str, Any], parent_replay: dict[str, Any],
               parent_sequence: list[dict[str, Any]]) -> dict[str, Any]:
        started = time.monotonic()
        origin = proposal.get("operator")
        if not _is_complete_success(parent_replay):
            return {"decision": "unknown", "action": "extend",
                    "reason": "parent sequence is incomplete or contains a failed transaction; preserve expansion",
                    "evidence": {"replay_status": parent_replay.get("replay_status")},
                    "elapsed_seconds": time.monotonic() - started}
        if origin != "state_supported_repetition":
            return {"decision": "extend", "action": "extend",
                    "reason": "candidate is an insertion/role/resource variation or an unclassified type; preserve expansion",
                    "evidence": {"origin": origin, "proposal_evidence": proposal.get("evidence")},
                    "elapsed_seconds": time.monotonic() - started}

        guard = _guard_false_evidence(proposal, parent_replay)
        if guard:
            return {"decision": "skip", "action": "skip", "reason": guard["conclusion"],
                    "evidence": guard, "elapsed_seconds": time.monotonic() - started}

        appended = (proposal.get("sequence") or [{}])[-1]
        repeat_key = hashlib.sha256(_key([appended.get("function"), appended.get("arguments"),
                                         appended.get("sender"), appended.get("value_wei")]).encode()).hexdigest()
        prior_probe = self.probed_repeats.get(repeat_key)
        if prior_probe:
            return {"decision": "skip", "action": "skip",
                    "reason": "a prior clean probe of this exact repeated call preserved a complete source-level aggregate relation within the frozen numeric horizon",
                    "evidence": prior_probe,
                    "elapsed_seconds": time.monotonic() - started}
        return {"decision": "extend", "action": "extend",
                "reason": "no sound static guard contradiction or prior relation-preserving probe; default to execute",
                "evidence": {"origin": origin, "proposal_evidence": proposal.get("evidence")},
                "elapsed_seconds": time.monotonic() - started,
                "repeat_key": repeat_key}

    def observe(self, repeat_key: str | None, parent_replay: dict[str, Any],
                child_replay: dict[str, Any], parent_sequence: list[dict[str, Any]],
                child_sequence: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not repeat_key:
            return None
        proof = _safe_repeat_probe(parent_replay, child_replay,
                                   parent_sequence, child_sequence,
                                   self.prop, self.max_length)
        if proof:
            self.probed_repeats[repeat_key] = proof
        return proof
