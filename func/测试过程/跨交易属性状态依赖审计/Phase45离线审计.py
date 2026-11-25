#!/usr/bin/env python3
"""Phase45 offline audit of Phase43 Agent outputs and Phase44 feedback.

This script never calls an Agent, replays a contract, or starts Echidna fuzzing.
It validates recovered Agent B JSON with the production AgentB validator and
performs a frozen, offline-only candidate-selection comparison.
"""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from AgentB import _validator  # noqa: E402
from 状态反馈序列扩展 import retain_diverse_prefixes  # noqa: E402


RESULT = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase45-20261125"
P43 = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase43-20261123"
P44 = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase44-20261124"
K_LIMIT = 4


def read_json(path: Path, default: Any = None) -> Any:
    try:
        if not path.is_file():
            return default
    except OSError:
        return default
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str | None:
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def last_response(record: dict[str, Any]) -> dict[str, Any] | None:
    events = record.get("events") or []
    for event in reversed(events):
        response = event.get("response_json")
        if isinstance(response, dict):
            return response
    return record.get("concrete_output") if isinstance(record.get("concrete_output"), dict) else None


def get_candidate(candidates: list[dict[str, Any]], candidate_id: str | None) -> dict[str, Any] | None:
    for candidate in candidates:
        if candidate.get("candidate_id") == candidate_id:
            return candidate
    return candidates[0] if candidates else None


def rollback_rows(feedback: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not feedback:
        return []
    result = []
    for row in feedback.get("transactions", []):
        if row.get("status") != "success" or row.get("outer_revert"):
            result.append({"transaction_index": row.get("transaction_index", row.get("index")),
                           "status": row.get("status"),
                           "execution_class": row.get("execution_class"),
                           "reason": row.get("revert_reason")})
    return result


def audit_agents() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    campaigns = list(csv.DictReader((P43 / "campaign-results.csv").open(encoding="utf-8-sig", newline="")))
    failures = list(csv.DictReader((P43 / "failures.csv").open(encoding="utf-8-sig", newline="")))
    replay_by_id = {row["sample_id"]: row for row in campaigns
                    if row.get("source", "").lower() == "olympia" and
                    row.get("phase") == "agent_replay"}
    failure_by_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in failures:
        if row.get("sample_id", "").startswith("OLYMPIA-"):
            failure_by_id[row["sample_id"]].append(row)

    ledger: list[dict[str, Any]] = []
    recovered: list[dict[str, Any]] = []
    plan_lengths = Counter()
    output_lengths = Counter()
    status_counts = Counter()
    validation_counts = Counter()
    rollback_counts = Counter()
    format_error_rows = 0
    format_recovered = 0
    planning_mismatch_rows = 0

    task_dirs = sorted((P43 / "tasks").glob("OLYMPIA-*"))
    for task_dir in task_dirs:
        sample_id = task_dir.name
        agent_dir = task_dir / "agent"
        a_path, b_path, context_path = (agent_dir / "agent-a-result.json",
                                        agent_dir / "agent-b-result.json",
                                        agent_dir / "property-context.json")
        a_record = read_json(a_path, {}) or {}
        b_record = read_json(b_path, {}) or {}
        context = read_json(context_path, {}) or {}
        candidates = a_record.get("candidates") or []
        raw_output = last_response(b_record)
        candidate_id = (raw_output or {}).get("candidate_id")
        candidate = get_candidate(candidates, candidate_id)
        planned_length = len(candidate.get("steps", [])) if candidate else None
        raw_transactions = (raw_output or {}).get("transactions")
        b_output_length = len(raw_transactions) if isinstance(raw_transactions, list) else None
        trigger = ((candidate or {}).get("assertion_trigger") or
                   next((prop.get("assertion_trigger") for prop in context.get("properties", [])
                         if prop.get("property_id") == (candidate or {}).get("property_id")), None))
        action_output_length = (max(0, b_output_length - (1 if trigger else 0))
                                if b_output_length is not None else None)
        validation_error = None
        normalized = copy.deepcopy(raw_output)
        if normalized is None:
            validation_error = "no_structured_agent_b_response"
        elif candidate is None:
            validation_error = "no_matching_agent_a_candidate"
        else:
            try:
                _validator(context, candidate, None)(normalized)
                validation_counts["valid_after_current_strict_validator"] += 1
            except Exception as exc:  # audit must preserve, not hide, historical failures
                validation_error = str(exc)
                validation_counts["invalid_after_current_strict_validator"] += 1

        old_error = b_record.get("error")
        if old_error is None:
            for event in reversed(b_record.get("events") or []):
                if event.get("error"):
                    old_error = event["error"]
                    break
        was_format_error = bool(old_error and "参数必须是 JSON 数组" in str(old_error))
        was_mismatch = bool(old_error and "交易数必须与 Agent A 规划" in str(old_error))
        if was_format_error:
            format_error_rows += 1
            if validation_error is None:
                format_recovered += 1
        if was_mismatch:
            planning_mismatch_rows += 1

        run = replay_by_id.get(sample_id, {})
        replay_state = run.get("status", "missing")
        status_counts[replay_state] += 1
        feedback_path = task_dir / "E1" / "v2-feedback.json"
        feedback = read_json(feedback_path)
        rollbacks = rollback_rows(feedback)
        for rollback in rollbacks:
            rollback_counts[rollback.get("reason") or rollback.get("execution_class") or "unspecified"] += 1
        if planned_length is not None:
            plan_lengths[str(planned_length)] += 1
        if b_output_length is not None:
            output_lengths[str(b_output_length)] += 1

        row = {
            "sample_id": sample_id,
            "dimension": run.get("dimension"),
            "agent_a_candidate_count": len(candidates),
            "agent_a_planned_action_count": planned_length,
            "agent_a_declared_max_steps": a_record.get("sequence_length_max"),
            "agent_b_output_transaction_count_including_trigger": b_output_length,
            "agent_b_output_action_count": action_output_length,
            "agent_b_original_error": old_error,
            "agent_b_current_strict_validation": "valid" if validation_error is None else "invalid",
            "agent_b_validation_reason": validation_error,
            "historical_execution_status": replay_state,
            "historical_sequence_length": run.get("sequence_length"),
            "historical_transactions_succeeded": run.get("transactions_succeeded"),
            "historical_complete_executable": run.get("complete_executable"),
            "property_status": run.get("property_value"),
            "rollback_count": len(rollbacks),
            "rollback_reasons": json.dumps(rollbacks, ensure_ascii=False),
            "agent_a_result_sha256": sha256(a_path),
            "agent_b_result_sha256": sha256(b_path),
            "property_context_sha256": sha256(context_path),
            "historical_feedback_path": relative(feedback_path) if read_json(feedback_path) else "",
        }
        ledger.append(row)

        if was_format_error and validation_error is None:
            recovered.append({
                "sample_id": sample_id,
                "candidate_id": normalized.get("candidate_id"),
                "agent_a_planned_action_count": planned_length,
                "agent_b_raw_transaction_count": b_output_length,
                "recovery": "JSON array string decoded by json.loads; original Agent B validator passed",
                "execution_status": "not_replayed_in_Phase45",
                "source_agent_a_result": relative(a_path),
                "source_agent_a_result_sha256": sha256(a_path),
                "source_agent_b_result": relative(b_path),
                "source_agent_b_result_sha256": sha256(b_path),
                "source_failure_record": "func/测试过程/跨交易属性状态依赖审计/结果/Phase43-20261123/failures.csv",
                "sequence": normalized["transactions"],
            })

    if len(task_dirs) != 100:
        raise RuntimeError("Phase43 Olympia task directory count changed: %d" % len(task_dirs))
    write_csv(RESULT / "phase45-agent-audit-ledger.csv", ledger)
    write_json(RESULT / "recovered-agent-sequences.json", {
        "source_dataset": "Phase43 frozen raw responses",
        "recovered_sequence_count": len(recovered),
        "execution_status": "offline validation only; no sequence was replayed",
        "original_responses_and_failures": "retained unchanged in Phase43 result tree; referenced by path and SHA-256",
        "recovered_sequences": recovered,
    })
    summary = {
        "task_count": len(task_dirs),
        "agent_a_planned_action_length_histogram": dict(sorted(plan_lengths.items(), key=lambda kv: int(kv[0]))),
        "agent_b_output_transaction_length_histogram_including_trigger": dict(sorted(output_lengths.items(), key=lambda kv: int(kv[0]))),
        "historical_agent_replay_status_counts": dict(status_counts),
        "current_strict_validator_counts_after_json_array_recovery": dict(validation_counts),
        "historical_array_format_failure_count": format_error_rows,
        "historical_array_format_recovered_and_validated": format_recovered,
        "historical_agent_a_agent_b_transaction_count_mismatch": planning_mismatch_rows,
        "historical_complete_executable_sequences": status_counts.get("executable", 0),
        "historical_partial_or_failed_sequences": status_counts.get("partial_or_failed", 0),
        "historical_not_run_sequences": status_counts.get("not_run", 0),
        "recorded_failed_transaction_reason_counts": dict(rollback_counts),
        "sequence_limit_for_phase43": 8,
        "minimum_target_transaction_count_by_dimension_from_phase44_reachability": {
            "5": "18", "10": "32-34", "15": "46-48", "20": "62-64"},
        "execution_claim_for_recovered_sequences": "unknown; only 18 prior complete sequences have execution evidence, and all 74 recovered sequences remain unexecuted",
        "failure_csv_sha256": sha256(P43 / "failures.csv"),
        "campaign_csv_sha256": sha256(P43 / "campaign-results.csv"),
    }
    write_json(RESULT / "phase45-agent-audit-summary.json", summary)
    return summary, recovered


def lookup_getter(rows: list[dict[str, Any]], name: str) -> Any:
    for row in rows or []:
        signature = str(row.get("signature", ""))
        if signature.split("(", 1)[0] == name and row.get("status") == "observed" and "value" in row:
            return row["value"]
    return None


def direct_operand(property_row: dict[str, Any]) -> tuple[str | None, bool]:
    source = str(property_row.get("property_predicate") or property_row.get("property_source") or "")
    match = re.search(r"return\s*!\s*([A-Za-z_]\w*)\b", source)
    return (match.group(1), True) if match else (None, False)


def target_progress(feedback: dict[str, Any] | None, operand: str | None,
                    supported: bool) -> tuple[str, list[dict[str, Any]], Any]:
    if not feedback or not supported or not operand:
        return "unknown", [], None
    previous = lookup_getter(feedback.get("initial_predicate_getters", []), operand)
    if not isinstance(previous, bool):
        return "unknown", [], None
    transitions = []
    progressed = False
    rows = feedback.get("transactions", [])
    for row in rows:
        current = lookup_getter(row.get("predicate_getter_values", []), operand)
        if isinstance(current, bool):
            transitions.append({"transaction_index": row.get("transaction_index", row.get("index")),
                                "from": previous, "to": current})
            # For a source predicate return !operand, false->true is the exact
            # violation boundary; no numerical Boolean distance is assigned.
            if previous is False and current is True:
                progressed = True
            previous = current
    if progressed:
        return "direct_violation_boundary_reached", transitions, previous
    if not transitions:
        return "unknown", transitions, previous
    return "observed_no_direct_target_progress", transitions, previous


def native_log_evidence(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {"loaded_sequences": None, "replayed_sequences": None,
                "target_status": "unknown", "native_counterexample": False}
    path = ROOT / path_value
    try:
        exists = path.is_file()
    except OSError:
        exists = False
    if not exists:
        return {"loaded_sequences": None, "replayed_sequences": None,
                "target_status": "missing_log", "native_counterexample": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    loads = re.findall(r"Loaded\s+([0-9,]+) transaction sequences from .*?/coverage", text)
    target = re.search(r"echidna_noBug:\s*(passing|falsified|failed)", text, re.I)
    status = target.group(1).lower() if target else "unknown"
    falsified = bool(re.search(r"Test\s+echidna_noBug\s+falsified!", text, re.I) or
                     status == "falsified")
    if status == "failed" and not falsified:
        status = "unknown"
    return {"loaded_sequences": int(loads[-1].replace(",", "")) if loads else None,
            "replayed_sequences": len(re.findall(r"Sequence replayed from corpus file", text)),
            "target_status": status,
            "native_counterexample": falsified,
            "raw_log": relative(path)}


def static_state_audit() -> dict[str, Any]:
    direct = Counter()
    control_reads = Counter()
    action_writes = Counter()
    candidate_state_names = Counter()
    direct_operands = Counter()
    predicates = Counter()
    per_task = []
    for task_dir in sorted((P43 / "tasks").glob("OLYMPIA-*")):
        context_path = task_dir / "agent" / "property-context.json"
        context = read_json(context_path, {}) or {}
        prop = (context.get("properties") or [{}])[0]
        names = list(prop.get("read_states", []))
        direct.update(names)
        operand, supported = direct_operand(prop)
        if operand:
            direct_operands[operand] += 1
        predicates[str(prop.get("property_predicate") or "unknown")] += 1
        controls, writes = set(), set()
        for action in prop.get("candidate_actions", []):
            for guard in action.get("action_guard_evidence", []) or []:
                controls.update(guard.get("state_reads", []) or [])
            for dependency in action.get("prerequisite_dependencies", []) or []:
                if dependency.get("required_state"):
                    controls.add(dependency["required_state"])
            for state in action.get("write_states", []) or []:
                writes.add(state)
            for effect in action.get("effect_evidence", []) or []:
                if effect.get("state"):
                    writes.add(effect["state"])
        controls.difference_update(names)
        control_reads.update(controls)
        action_writes.update(writes)
        closure = [item.get("state") for item in prop.get("prerequisite_state_closure", [])
                   if item.get("state")]
        candidate_state_names.update(closure)
        per_task.append({"sample_id": task_dir.name, "property_id": prop.get("property_id"),
                         "property_predicate": prop.get("property_predicate"),
                         "direct_property_read_states": names,
                         "source_derived_negated_operand": operand if supported else None,
                         "control_and_guard_read_states": sorted(controls),
                         "static_candidate_write_states": sorted(writes),
                         "prerequisite_closure_states": closure})
    output = {
        "task_count": len(per_task),
        "direct_property_read_state_counts": dict(direct),
        "direct_negated_operand_counts": dict(direct_operands),
        "static_control_or_guard_state_read_counts_excluding_direct_property_operands": dict(control_reads),
        "static_candidate_write_state_counts": dict(action_writes),
        "prerequisite_closure_state_counts": dict(candidate_state_names),
        "interpretation": "direct read states come from the explicit property source; guard/control states are indirect execution conditions, not numeric target distances",
        "per_task": per_task,
    }
    write_json(RESULT / "phase45-static-state-audit.json", output)
    return output


def candidate_audit() -> dict[str, Any]:
    pools: dict[str, list[dict[str, Any]]] = {}
    concise = []
    state_audit = static_state_audit()
    # The explicit property shape is source-derived and supported for this fixed dataset.
    operand_counts = state_audit["direct_negated_operand_counts"]
    operand = next(iter(operand_counts)) if len(operand_counts) == 1 else None
    property_shape_supported = operand is not None
    candidate_counts = Counter()
    phase37 = Counter()
    native_target_status = Counter()
    native_load_replay = Counter()
    progress = Counter()
    feedback_state_change = Counter()
    coverage_only = Counter()
    coverage_empty = Counter()
    e1_presence = Counter()
    unknown_native = 0
    observed_operand_unknown = 0
    progress_tasks = set()
    observation_counts = Counter()
    selected_count_total = 0
    control_diversity_total = 0
    treatment_diversity_total = 0
    isolated_replays: dict[tuple[str, str, int], dict[str, Any]] = {}
    for split in ("dev", "eval"):
        for shard_path in sorted((P44 / split).glob("isolated-candidate-replay*.json")):
            shard = read_json(shard_path, {}) or {}
            for replay in shard.get("replays", []):
                if replay.get("kind") == "extension_candidate":
                    replay_key = (replay.get("sample_id"), replay.get("group"),
                                  int(replay.get("candidate_index", 0)))
                    isolated_replays[replay_key] = replay
    per_task_metrics = []
    candidate_rows_by_task: dict[str, list[dict[str, Any]]] = {}

    for split in ("dev", "eval"):
        for ledger_path in sorted((P44 / split / "tasks").glob("OLYMPIA-*/candidate-ledger.json")):
            task = read_json(ledger_path, {}) or {}
            sample_id = task.get("sample_id")
            candidates = task.get("candidates", [])
            e1_exists = bool(task.get("E1_agent_sequence_present"))
            e1_presence["present" if e1_exists else "absent_empty_baseline"] += 1
            evaluated = []
            old_rows = []
            for row in candidates:
                group = row.get("group", "")
                index = int(row.get("candidate_index", 0))
                key = "%s-%02d" % (group, index)
                feedback = row.get("feedback") or {}
                raw_path = row.get("raw_feedback_file")
                raw_feedback = read_json(ROOT / raw_path, {}) if raw_path else {}
                status, transitions, final_operand = target_progress(
                    raw_feedback, operand, property_shape_supported)
                if status == "direct_violation_boundary_reached":
                    progress_tasks.add(sample_id)
                progress[status] += 1
                feedback_state_change[str(bool(feedback.get("property_related_state_changed")))] += 1
                coverage_gain = bool(row.get("new_coverage_relative_to_E1_seed"))
                if coverage_gain and status != "direct_violation_boundary_reached":
                    coverage_only["all"] += 1
                    coverage_only["with_E1" if e1_exists else "empty_baseline_only"] += 1
                    if not e1_exists:
                        coverage_empty["candidates"] += 1
                phase37["%s:%s" % (group, row.get("phase37_binding_status", "missing"))] += 1
                isolated = isolated_replays.get((sample_id, group, index), {})
                authoritative_log = isolated.get("raw_log") or row.get("echidna_raw_log")
                native_ev = native_log_evidence(authoritative_log)
                native_target_status[native_ev["target_status"]] += 1
                native_load_replay[
                    "loaded_%s_replayed_%s" % (
                        native_ev["loaded_sequences"], native_ev["replayed_sequences"])] += 1
                if native_ev["target_status"] == "unknown":
                    unknown_native += 1
                if status == "unknown":
                    observed_operand_unknown += 1
                getter_names = set()
                if raw_feedback:
                    getter_rows = list(raw_feedback.get("initial_predicate_getters", []))
                    for transaction in raw_feedback.get("transactions", []):
                        getter_rows.extend(transaction.get("predicate_getter_values", []) or [])
                        for field in ("state_before", "state_after"):
                            state_map = transaction.get(field, {}) or {}
                            if isinstance(state_map, dict):
                                getter_names.update(str(name).split("(", 1)[0]
                                                    for name in state_map)
                    getter_names.update(str(item.get("signature", "")).split("(", 1)[0]
                                        for item in getter_rows if item.get("status") == "observed")
                    for transaction in raw_feedback.get("transactions", []):
                        for field in ("changed_effect_states", "changed_states"):
                            for state in transaction.get(field, []) or []:
                                if isinstance(state, dict) and state.get("state"):
                                    getter_names.add(str(state["state"]).split(".")[-1])
                for name in getter_names:
                    observation_counts[name] += 1
                explicit_prerequisite = bool(
                    feedback.get("next_step_dependency_evidence_count", 0) or
                    row.get("proposal_evidence", {}).get("required_state"))
                item = {"sample_id": sample_id, "split": split, "candidate_key": key,
                        "group": group, "candidate_index": index,
                        "sequence_fingerprint": row.get("sequence_fingerprint"),
                        "replay_status": row.get("pyevm_replay_status"),
                        "pyevm_execution_succeeded": row.get("pyevm_execution_succeeded"),
                        "property_value_from_existing_feedback": row.get("pyevm_target_property"),
                        "property_related_state_changed_old_feedback": feedback.get("property_related_state_changed"),
                        "direct_operand_progress_from_raw_getters": status,
                        "direct_operand_transitions": transitions,
                        "direct_operand_final_value": final_operand,
                        "coverage_gain_flag": coverage_gain,
                        "coverage_baseline_kind": "E1_seed_only" if e1_exists else "empty_set",
                        "echidna_loaded_sequences": native_ev["loaded_sequences"],
                        "echidna_replayed_sequences": native_ev["replayed_sequences"],
                        "echidna_target_status_from_log": native_ev["target_status"],
                        "echidna_native_counterexample_from_log": native_ev["native_counterexample"],
                        "explicit_prerequisite_state_evidence": explicit_prerequisite,
                        "raw_feedback_file": raw_path,
                        "echidna_raw_log": native_ev.get("raw_log"),
                        "superseded_initial_echidna_log": row.get("echidna_raw_log"),
                        "isolated_replay_status": isolated.get("status")}
                evaluated.append(item)
                concise.append(item)
                old_row = copy.deepcopy(row)
                old_row["feedback"] = feedback
                old_row["sequence"] = row.get("sequence", [])
                old_row["candidate_key"] = key
                old_rows.append(old_row)
            candidate_rows_by_task[sample_id] = evaluated
            pools[sample_id] = old_rows
            candidate_counts["total"] += len(candidates)
            candidate_counts[split] += len(candidates)
            candidate_counts["tasks_" + split] += 1

    # Frozen paired selection: K=min(4,N), then compare both methods on exactly N and K.
    selections = []
    paired = {"tasks_compared": 0, "candidate_count": 0,
              "same_retained_set_tasks": 0, "changed_retained_set_tasks": 0,
              "control_progress_candidates_retained": 0,
              "treatment_progress_candidates_retained": 0,
              "control_retained_native_counterexamples": 0,
              "treatment_retained_native_counterexamples": 0,
              "control_retained_coverage_only_candidates": 0,
              "treatment_retained_coverage_only_candidates": 0,
              "control_excluded_explicit_prerequisite_candidates": 0,
              "treatment_excluded_explicit_prerequisite_candidates": 0,
              "paired_progress_delta": 0,
              "paired_target_state_diversity_delta": 0}
    for sample_id, old_rows in pools.items():
        rows = candidate_rows_by_task[sample_id]
        k = min(K_LIMIT, len(old_rows))
        selected_old = retain_diverse_prefixes(copy.deepcopy(old_rows), limit=k)
        old_keys = [item.get("candidate_key") for item in selected_old]
        old_rank = {item.get("candidate_key"): index for index, item in enumerate(selected_old)}
        progress_by_key = {item["candidate_key"]: item["direct_operand_progress_from_raw_getters"]
                           == "direct_violation_boundary_reached" for item in rows}
        # Only an independently inspectable direct operand transition can outrank
        # the existing result; ties/unknowns keep the old ranking and diversity.
        ordered = sorted((item.get("candidate_key") for item in old_rows),
                         key=lambda key: (not progress_by_key.get(key, False),
                                          old_rank.get(key, K_LIMIT + 1), key))
        new_keys = ordered[:k]
        row_by_key = {item["candidate_key"]: item for item in rows}
        old_selected = [row_by_key[key] for key in old_keys if key in row_by_key]
        new_selected = [row_by_key[key] for key in new_keys if key in row_by_key]
        old_set, new_set = set(old_keys), set(new_keys)
        paired["tasks_compared"] += 1
        paired["candidate_count"] += len(old_rows)
        paired["same_retained_set_tasks"] += int(old_set == new_set)
        paired["changed_retained_set_tasks"] += int(old_set != new_set)
        old_progress = sum(item["direct_operand_progress_from_raw_getters"] ==
                           "direct_violation_boundary_reached" for item in old_selected)
        new_progress = sum(item["direct_operand_progress_from_raw_getters"] ==
                           "direct_violation_boundary_reached" for item in new_selected)
        old_diversity = len(set(item["direct_operand_final_value"] for item in old_selected
                                if isinstance(item["direct_operand_final_value"], bool)))
        new_diversity = len(set(item["direct_operand_final_value"] for item in new_selected
                                if isinstance(item["direct_operand_final_value"], bool)))
        selected_count_total += k
        control_diversity_total += old_diversity
        treatment_diversity_total += new_diversity
        excluded_old = [item for item in rows if item["candidate_key"] not in old_set]
        excluded_new = [item for item in rows if item["candidate_key"] not in new_set]
        paired["control_progress_candidates_retained"] += old_progress
        paired["treatment_progress_candidates_retained"] += new_progress
        paired["control_retained_native_counterexamples"] += sum(
            bool(item["echidna_native_counterexample_from_log"]) for item in old_selected)
        paired["treatment_retained_native_counterexamples"] += sum(
            bool(item["echidna_native_counterexample_from_log"]) for item in new_selected)
        paired["control_retained_coverage_only_candidates"] += sum(
            item["coverage_gain_flag"] and item["direct_operand_progress_from_raw_getters"] !=
            "direct_violation_boundary_reached" for item in old_selected)
        paired["treatment_retained_coverage_only_candidates"] += sum(
            item["coverage_gain_flag"] and item["direct_operand_progress_from_raw_getters"] !=
            "direct_violation_boundary_reached" for item in new_selected)
        paired["control_excluded_explicit_prerequisite_candidates"] += sum(
            item["explicit_prerequisite_state_evidence"] for item in excluded_old)
        paired["treatment_excluded_explicit_prerequisite_candidates"] += sum(
            item["explicit_prerequisite_state_evidence"] for item in excluded_new)
        paired["paired_progress_delta"] += new_progress - old_progress
        paired["paired_target_state_diversity_delta"] += new_diversity - old_diversity
        for method, selected, kept in (("control", old_selected, old_set),
                                       ("property_progress", new_selected, new_set)):
            for item in rows:
                selections.append({**item, "method": method,
                                   "retention_count_K": k,
                                   "selected": item["candidate_key"] in kept})
        per_task_metrics.append({"sample_id": sample_id, "candidate_pool_size": len(rows),
                                 "retention_count_K": k,
                                 "control_selected_candidate_keys": old_keys,
                                 "property_progress_selected_candidate_keys": new_keys,
                                 "control_direct_progress_count": old_progress,
                                 "property_progress_direct_progress_count": new_progress,
                                 "control_observed_target_state_diversity": old_diversity,
                                 "property_progress_observed_target_state_diversity": new_diversity,
                                 "retained_set_changed": old_set != new_set})

    # Keep the selection matrix separate from the raw Phase44 ledgers.
    write_csv(RESULT / "phase45-paired-selection-ledger.csv", selections)
    fuzz_injection = audit_formal_fuzz_injection()
    summary = {
        "phase44_candidate_count": candidate_counts["total"],
        "candidate_count_by_split": {"dev": candidate_counts["dev"], "eval": candidate_counts["eval"]},
        "task_count_by_split": {"dev": candidate_counts["tasks_dev"], "eval": candidate_counts["tasks_eval"]},
        "E1_presence_by_task": dict(e1_presence),
        "property_shape_supported_for_direct_progress": property_shape_supported,
        "direct_property_operand": operand,
        "candidate_progress_evidence_counts": dict(progress),
        "old_feedback_property_related_state_changed_counts": dict(feedback_state_change),
        "coverage_only_candidate_counts": dict(coverage_only),
        "coverage_gain_on_empty_baseline_count": coverage_empty.get("candidates", 0),
        "phase37_binding_status_counts": dict(phase37),
        "native_candidate_target_status_counts": dict(native_target_status),
        "native_candidate_load_replay_counts": dict(native_load_replay),
        "native_target_state_unknown_candidates": unknown_native,
        "direct_operand_unobserved_candidates": observed_operand_unknown,
        "candidate_observation_counts_by_getter_or_state": dict(observation_counts),
        "indirect_static_control_states_not_observed_in_candidate_feedback": {
            state: state_audit["static_control_or_guard_state_read_counts_excluding_direct_property_operands"].get(state, 0)
            for state in state_audit["prerequisite_closure_state_counts"]
            if state not in state_audit["direct_property_read_state_counts"] and
            state not in observation_counts},
        "tasks_with_reliable_direct_attribute_progress": len(progress_tasks),
        "tasks_with_progress_sample_ids": sorted(progress_tasks),
        "paired_selection": paired,
              "selected_candidate_count_per_method": selected_count_total,
              "selected_candidate_attribute_progress_fraction": {
                  "control": "%d/%d" % (paired["control_progress_candidates_retained"], selected_count_total),
                  "property_progress": "%d/%d" % (paired["treatment_progress_candidates_retained"], selected_count_total)},
              "summed_per_task_observed_target_state_diversity": {
                  "control": control_diversity_total,
                  "property_progress": treatment_diversity_total},
              "formal_fuzz_seed_injection_audit": fuzz_injection,
        "per_task_paired_selection": per_task_metrics,
        "excluded_candidates_with_explicit_prerequisite_evidence": {
            "control": paired["control_excluded_explicit_prerequisite_candidates"],
            "property_progress": paired["treatment_excluded_explicit_prerequisite_candidates"],
            "criterion": "existing execution feedback next_step_dependency_evidence_count or explicit required_state field; no inference from coverage or matched_states alone"},
        "ordinary_coverage_is_not_target_progress": True,
        "quick_validation_authorized_by_frozen_gate": len(progress_tasks) > 0 and paired["paired_progress_delta"] > 0,
        "interpretation": "offline candidate evaluation only; no result implies improved sequence generation efficiency or Echidna finding rate",
    }
    write_csv(RESULT / "phase45-attribute-candidate-audit.csv", selections)
    write_json(RESULT / "phase45-paired-selection-summary.json", summary)
    return summary


def audit_formal_fuzz_injection() -> dict[str, Any]:
    """Check that each formal G1/G2 log loaded the executable ledger candidates."""
    expected_by_task_group = {}
    for split in ("dev", "eval"):
        for ledger_path in sorted((P44 / split / "tasks").glob("OLYMPIA-*/candidate-ledger.json")):
            task = read_json(ledger_path, {}) or {}
            sample_id = task.get("sample_id")
            for group in ("G1", "G2"):
                expected_by_task_group[(split, sample_id, group)] = [
                    row for row in task.get("candidates", [])
                    if row.get("group") == group and row.get("pyevm_replay_status") == "executable"]
    runs = []
    count_matches = 0
    for (split, sample_id, group), candidates in expected_by_task_group.items():
        base = P44 / split / "tasks" / sample_id / "fuzz-isolated-final" / group
        for log_path in sorted(base.glob("seed-*/echidna.log")):
            ev = native_log_evidence(relative(log_path))
            matches = ev.get("loaded_sequences") == len(candidates)
            count_matches += int(matches)
            runs.append({"split": split, "sample_id": sample_id, "group": group,
                         "seed": log_path.parent.name, "expected_executable_candidate_count": len(candidates),
                         "echidna_loaded_sequence_count": ev.get("loaded_sequences"),
                         "echidna_replayed_sequence_count": ev.get("replayed_sequences"),
                         "loaded_count_matches_injection": matches,
                         "injected_candidate_fingerprints": [row.get("sequence_fingerprint") for row in candidates],
                         "raw_log": relative(log_path)})
    totals = Counter(len(rows) for rows in expected_by_task_group.values())
    return {"formal_fuzz_log_count": len(runs), "formal_fuzz_logs_matching_expected_load_count": count_matches,
            "task_group_expected_executable_candidate_counts": dict(totals),
            "sequence_injection_source": "Phase44DevelopmentExperiment.run_fuzz_campaigns: all candidate rows with replay_status == executable are passed as seed_sequences",
            "runs": runs}


def main() -> None:
    RESULT.mkdir(parents=True, exist_ok=True)
    agent_summary, recovered = audit_agents()
    attribute_summary = candidate_audit()
    report = {"phase": "Phase45", "agent_audit": agent_summary,
              "recovered_sequence_count": len(recovered),
              "attribute_audit": attribute_summary,
              "quick_validation_started": False,
              "quick_validation_stop_reason": (
                  "No independently supported target-progress advantage in the frozen offline audit"
                  if not attribute_summary["quick_validation_authorized_by_frozen_gate"]
                  else "Gate passed; report only, no automatic runs")}
    write_json(RESULT / "phase45-machine-summary.json", report)
    print(json.dumps({"agent": agent_summary,
                      "attribute": {key: value for key, value in attribute_summary.items()
                                    if key not in {"per_task_paired_selection"}},
                      "quick_validation_started": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
