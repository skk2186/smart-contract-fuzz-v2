#!/usr/bin/env python3
"""复用 Phase31 扩展规则，在 Phase32 冻结任务上做有限 Anvil/Echidna 对照。"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek")]

from AgentB import to_echidna_sequence  # noqa: E402
from 属性种子上下文 import PROJECTS, load_project_context, read_json  # noqa: E402
from 种子验证 import (AnvilSession, new_seed_id, replay_seed, run_echidna,
                    write_corpus)  # noqa: E402
from 状态反馈序列扩展 import (build_action_templates, feedback_vector,
                           propose_extensions, retain_diverse_prefixes,
                           sequence_fingerprint)  # noqa: E402


RESULTS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120"
AGENT_ROOT = RESULTS / "AgentAB"
MAX_LENGTH = 8
MAX_EXECUTIONS = 24
RETAINED_PREFIXES = 4
SEEDS = [20261125, 20261135, 20261145]
TASKS = {
    "Phase32PigfoxRWADemo": ["2e998090c7de1e70f195", "eaf144ea41a1f5bc076d"],
    "Phase32ReconVaultExample": ["be946ac20a91ff2f9904", "76606be646ce1a2dbd78"],
}
MODE_GROUPS = {"random": "R", "static": "S", "state_feedback": "E3"}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _tx(tx: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in tx.items()
            if key in {"function", "arguments", "sender", "value_wei", "delay_seconds",
                       "delay_blocks", "expected_outcome", "data_dependencies"}}


def _repair_once(project: str, candidate: dict[str, Any], sequence: list[dict[str, Any]],
                 replay: dict[str, Any], session: AnvilSession
                 ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None, int]:
    for index, row in enumerate(replay.get("transactions", [])):
        proposal = row.get("constraint_repair_proposal")
        if not proposal:
            continue
        repaired = copy.deepcopy(sequence)
        tx_index = int(proposal.get("transaction_index", index + 1)) - 1
        if not 0 <= tx_index < len(repaired):
            continue
        arguments = list(repaired[tx_index].get("arguments", []))
        updates = proposal.get("argument_updates") or [{
            "argument_index": proposal["argument_index"],
            "repaired_value": proposal["repaired_value"]}]
        applied = []
        for update in updates:
            argument_index = int(update["argument_index"])
            if 0 <= argument_index < len(arguments):
                applied.append({"argument_index": argument_index,
                                "before": arguments[argument_index],
                                "after": update["repaired_value"]})
                arguments[argument_index] = update["repaired_value"]
        if not applied:
            continue
        repaired[tx_index]["arguments"] = arguments
        repaired_replay = replay_seed(project, candidate, [_tx(item) for item in repaired],
                                      session=session, runtime_constraints=False)
        return repaired, repaired_replay, {
            "transaction_index": tx_index + 1, "updates": applied,
            "proposal": proposal}, 1
    return sequence, replay, None, 0


def _replay_candidate(project: str, candidate: dict[str, Any],
                      sequence: list[dict[str, Any]], session: AnvilSession
                      ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None, int]:
    clean = [_tx(item) for item in sequence]
    replay = replay_seed(project, candidate, clean, session=session,
                         runtime_constraints=True)
    return _repair_once(project, candidate, clean, replay, session)


def _split_trigger(prop: dict[str, Any], transactions: list[dict[str, Any]],
                   sender: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    trigger = prop.get("assertion_trigger")
    if not trigger or not trigger.get("seed_compatible"):
        return copy.deepcopy(transactions), None
    signature = trigger["abi_signature"]
    rows = copy.deepcopy(transactions)
    trigger_tx = next((row for row in reversed(rows) if row.get("function") == signature), None)
    if trigger_tx is not None:
        rows.remove(trigger_tx)
    else:
        trigger_tx = {"function": signature, "arguments": [], "sender": sender,
                      "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0,
                      "expected_outcome": "no_state_change"}
    return rows, trigger_tx


def _with_trigger(sequence: list[dict[str, Any]], trigger: dict[str, Any] | None
                  ) -> list[dict[str, Any]]:
    rows = copy.deepcopy(sequence)
    if trigger is not None:
        rows.append(copy.deepcopy(trigger))
    return rows


def _valid_sequence(sequence: list[dict[str, Any]], abi_by_signature: dict[str, dict[str, Any]]) -> tuple[bool, str | None]:
    if not sequence or len(sequence) > MAX_LENGTH:
        return False, "sequence length outside the frozen bound"
    for item in sequence:
        abi = abi_by_signature.get(str(item.get("function", "")))
        if abi is None or len(abi.get("inputs", [])) != len(item.get("arguments", [])):
            return False, "function signature or argument count does not match ABI"
        if not isinstance(item.get("sender"), str) or not str(item["sender"]).startswith("0x"):
            return False, "missing sender address"
    return True, None


def _expand(project: str, candidate: dict[str, Any], prop: dict[str, Any],
            abi_by_signature: dict[str, dict[str, Any]], base_full: list[dict[str, Any]],
            senders: list[str], output: Path) -> dict[str, Any]:
    started = time.monotonic()
    prep, trigger = _split_trigger(prop, base_full, senders[0])
    max_preparation_length = MAX_LENGTH - (1 if trigger else 0)
    inventory = [item for item in prop.get("candidate_actions", [])
                 if item.get("seed_compatible") and item.get("abi_signature")]
    templates, template_decisions = build_action_templates(
        inventory, abi_by_signature, prep, senders)
    evidence = {str(item["abi_signature"]): item for item in inventory}
    target_states = set(prop.get("read_states", [])) | set(prop.get("property_write_states", []))
    mode_results = {}
    for mode, group in MODE_GROUPS.items():
        budget_executions = 0
        total_anvil_replays = 0
        repair_replays = 0
        records: list[dict[str, Any]] = []
        decisions: list[dict[str, Any]] = []
        seen_sequences = {sequence_fingerprint(prep)}
        seen_states: set[str] = set()
        target_candidate = None
        with AnvilSession(project=project) as session:
            base_full = _with_trigger(prep, trigger)
            repaired_base, base_replay, base_repair, repair_count = _replay_candidate(
                project, candidate, base_full, session)
            total_anvil_replays += 1 + repair_count
            repair_replays += repair_count
            # Parameter repair can change action arguments; remove the assertion trigger again.
            base_prep, _ = _split_trigger(prop, repaired_base, senders[0])
            records.append({"candidate_no": 0, "origin": "frozen_base_replay",
                            "sequence": repaired_base, "replay": base_replay,
                            "parameter_repair": base_repair,
                            "feedback": feedback_vector(base_replay,
                                                        property_source=str(prop.get("property_source", "")))})
            frontier = [{"sequence": base_prep, "replay": base_replay, "depth": 0}]
            seen_sequences = {sequence_fingerprint(base_prep)}
            iteration = 0
            while frontier and budget_executions < MAX_EXECUTIONS and target_candidate is None:
                iteration += 1
                pool = []
                for parent in frontier:
                    proposals = propose_extensions(
                        parent["sequence"], templates, evidence, abi_by_signature,
                        mode=mode, replay=parent["replay"], target_states=target_states,
                        senders=senders, max_sequence_length=max_preparation_length,
                        max_proposals=MAX_EXECUTIONS - budget_executions,
                        random_seed=20261120 + iteration + parent["depth"])
                    for proposal in proposals:
                        preparation = proposal["sequence"]
                        fingerprint = proposal["fingerprint"]
                        if fingerprint in seen_sequences:
                            decisions.append({"iteration": iteration, "operator": proposal["operator"],
                                              "sequence_fingerprint": fingerprint,
                                              "decision": "discarded", "reason": "semantic duplicate"})
                            continue
                        full = _with_trigger(preparation, trigger)
                        valid, reason = _valid_sequence(full, abi_by_signature)
                        if not valid:
                            decisions.append({"iteration": iteration, "operator": proposal["operator"],
                                              "sequence_fingerprint": fingerprint,
                                              "decision": "discarded", "reason": reason})
                            continue
                        one_started = time.monotonic()
                        repaired, replay, repair, repair_count = _replay_candidate(
                            project, candidate, full, session)
                        elapsed = time.monotonic() - one_started
                        seen_sequences.add(fingerprint)
                        budget_executions += 1
                        total_anvil_replays += 1 + repair_count
                        repair_replays += repair_count
                        vector = feedback_vector(replay, property_source=str(prop.get("property_source", "")),
                                                 seen_states=seen_states)
                        seen_states.update(vector.get("getter_state_fingerprints", []))
                        record = {"candidate_no": budget_executions, "iteration": iteration,
                                  "origin": proposal["operator"],
                                  "proposal_reason": proposal["proposal_reason"],
                                  "proposal_evidence": proposal.get("evidence"),
                                  "sequence_fingerprint": sequence_fingerprint(repaired),
                                  "sequence": repaired, "replay": replay,
                                  "parameter_repair": repair,
                                  "elapsed_seconds": round(elapsed, 6),
                                  "feedback": vector, "retention_decision": "pending"}
                        records.append(record)
                        decisions.append({"iteration": iteration,
                                          "sequence_fingerprint": fingerprint,
                                          "operator": proposal["operator"],
                                          "decision": "executed",
                                          "reason": proposal["proposal_reason"]})
                        if vector["counterexample_reached"] and replay.get("replay_status") == "executable":
                            target_candidate = record
                            break
                        if (replay.get("transactions") and
                                (vector["property_related_state_changed"] or
                                 any(item.get("status") == "success"
                                     for item in replay["transactions"]))):
                            pool.append({"sequence": _split_trigger(prop, repaired, senders[0])[0],
                                         "replay": replay, "depth": parent["depth"] + 1,
                                         "feedback": vector, "record": record})
                        if budget_executions >= MAX_EXECUTIONS:
                            break
                    if target_candidate or budget_executions >= MAX_EXECUTIONS:
                        break
                if target_candidate:
                    target_candidate["retention_decision"] = "target_reached_stop"
                    break
                retained = retain_diverse_prefixes(pool, RETAINED_PREFIXES)
                for node in pool:
                    node["record"]["retention_decision"] = (
                        "retained_diverse_prefix" if node in retained else
                        "discarded_budget_or_lower_feedback_and_lower_diversity")
                frontier = retained
        eligible = [row for row in records
                    if row.get("replay", {}).get("replay_status") == "executable" and
                    (row.get("feedback", {}).get("property_related_state_changed") or
                     row.get("feedback", {}).get("counterexample_reached"))]
        mode_result = {"mode": mode, "group": group,
                       "status": "target_reached" if target_candidate else
                       "valid_related_state_candidate" if eligible else
                       "no_valid_related_state_candidate",
                       "base_sequence": base_full,
                       "base_parameter_repair": records[0]["parameter_repair"],
                       "max_sequence_length": MAX_LENGTH,
                       "retained_prefixes": RETAINED_PREFIXES,
                       "candidate_execution_budget": MAX_EXECUTIONS,
                       "candidate_executions": budget_executions,
                       "base_replay_executions": 1,
                       "parameter_repair_replays": repair_replays,
                       "total_anvil_replays": total_anvil_replays,
                       "elapsed_seconds": round(time.monotonic() - started, 6),
                       "api_calls": 0, "api_tokens": 0,
                       "template_decisions": template_decisions,
                       "records": records, "decisions": decisions,
                       "target_candidate": target_candidate,
                       "eligible_candidates": eligible}
        mode_results[mode] = mode_result
        _write_json(output / f"{group}-扩展回放.json", mode_result)
    return {"task_id": candidate.get("property_id"), "modes": mode_results}


def _coverage_lines(root: Path) -> set[tuple[str, int]]:
    lines: set[tuple[str, int]] = set()
    for path in root.rglob("*.lcov"):
        source = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("SF:"):
                source = line[3:]
            elif line.startswith("DA:"):
                fields = line[3:].split(",")
                if len(fields) > 1 and fields[0].isdigit() and int(fields[1]) > 0:
                    lines.add((source, int(fields[0])))
    return lines


def _property_filter(prop: dict[str, Any], artifact: dict[str, Any], contract_name: str,
                     assertion_only: bool) -> list[str]:
    target_name = prop.get("property_abi", "").split("(", 1)[0]
    actions = {item.get("abi_signature") for item in prop.get("candidate_actions", [])
               if item.get("seed_compatible") and item.get("abi_signature")}
    if not assertion_only:
        actions = {entry["name"] + "(" + ",".join(x["type"] for x in entry.get("inputs", [])) + ")"
                   for entry in artifact.get("abi", [])
                   if entry.get("type") == "function" and
                   entry.get("stateMutability") not in {"view", "pure"} and
                   not entry["name"].startswith("echidna_") and
                   not entry["name"].startswith("property_")}
    if assertion_only and target_name:
        actions.add(prop["property_abi"])
    return sorted(f"{contract_name}.{signature}" for signature in actions if signature)


def _run_echidna_task(project: str, candidate: dict[str, Any], prop: dict[str, Any],
                      artifact: dict[str, Any], context: dict[str, Any],
                      group_seeds: dict[str, tuple[list[dict[str, Any]], dict[str, Any], Path | None]],
                      output: Path) -> dict[str, Any]:
    mode = "assertion" if prop.get("property_kind") == "assertion_test" else "property"
    name = prop.get("property_abi", prop.get("property", "")).split("(", 1)[0]
    prop_filter = _property_filter(prop, artifact, PROJECTS[project]["contract"], mode == "assertion")
    results = []
    for group, (sequence, replay, seed_path) in group_seeds.items():
        if group not in {"E0", "E1", "E2", "E3", "R", "S"}:
            continue
        if group != "E0" and (not seed_path or replay.get("replay_status") != "executable"):
            results.append({"group": group, "status": "skipped_no_executable_seed",
                            "sequence_length": len(sequence),
                            "target_property_violation": replay.get("target_property_violation")})
            continue
        group_lines = {}
        for seed in SEEDS:
            for stage, limit in (("seed-only", 0), ("fuzz-500", 500)):
                if (group != "E0" and stage == "fuzz-500" and
                        not replay.get("phase32_seed_utility_eligible", False)):
                    results.append({"group": group, "seed": seed, "stage": stage,
                                    "status": "skipped_preregistered_utility_gate",
                                    "reason": "seed was executable but did not show a target violation or property-related getter change"})
                    continue
                corpus = output / "Echidna" / group / f"seed-{seed}" / stage
                corpus.mkdir(parents=True, exist_ok=True)
                if seed_path is not None:
                    destination = corpus / "coverage" / seed_path.name
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(seed_path, destination)
                run = run_echidna(
                    project, corpus, property_name=name,
                    test_limit=limit, timeout=180, seed=seed,
                    test_mode=mode, property_prefix=name,
                    filter_functions=prop_filter, seq_len=MAX_LENGTH,
                    shrink_limit=1, stop_on_fail=False, disable_slither=True,
                    sender_pool=context.get("sender_pool"),
                    working_directory=(ROOT / PROJECTS[project]["source_root"]))
                run["group"] = group
                run["stage"] = stage
                run["external_seed_used"] = seed_path is not None
                run["external_seed_path"] = str(seed_path.relative_to(ROOT)) if seed_path else None
                run["seed_target_violation_before_fuzz"] = replay.get("target_property_violation")
                _write_json(corpus / "summary.json", run)
                lines = _coverage_lines(Path(run["full_log_path"]).parent)
                if stage == "seed-only":
                    group_lines[seed] = {"seed_only": lines}
                else:
                    base = group_lines.setdefault(seed, {"seed_only": set()})["seed_only"]
                    group_lines[seed]["final"] = lines
                    group_lines[seed]["fuzz_added"] = lines - base
                results.append(run)
        for seed, coverage in group_lines.items():
            _write_json(output / "Echidna" / group / f"seed-{seed}" / "coverage-summary.json", {
                "group": group, "seed": seed,
                "seed_only_lines": sorted(coverage.get("seed_only", set())),
                "fuzz_added_lines": sorted(coverage.get("fuzz_added", set())),
                "final_lines": sorted(coverage.get("final", set())),
                "seed_only_count": len(coverage.get("seed_only", set())),
                "fuzz_added_count": len(coverage.get("fuzz_added", set())),
                "final_count": len(coverage.get("final", set()))})
    return {"target_mode": mode, "property_filter": prop_filter, "runs": results}


def _prepare_seed(project: str, candidate: dict[str, Any], sequence: list[dict[str, Any]],
                  context: dict[str, Any], replay: dict[str, Any], output: Path,
                  group: str) -> Path | None:
    if replay.get("replay_status") != "executable":
        return None
    return write_corpus(project, candidate, [_tx(item) for item in sequence], context,
                        output / "seed-pack" / group, replay=replay,
                        seed_id=new_seed_id())


def main() -> None:
    overall = {"schema_version": 1, "baseline_commit": "3eb48e4e7eca917c645305935227f15f28a38d80",
               "tasks": []}
    for project, property_ids in TASKS.items():
        agent_path = AGENT_ROOT / project / "Agent种子流程.json"
        agent = read_json(agent_path)
        full_context = load_project_context(project, property_ids)
        props = {item["property_id"]: item for item in full_context["properties"]}
        artifact = read_json(PROJECTS[project]["artifact"])
        abi_by_signature = {entry["name"] + "(" + ",".join(x["type"] for x in entry.get("inputs", [])) + ")": entry
                            for entry in artifact.get("abi", []) if entry.get("type") == "function"}
        project_task_rows = []
        for property_result in agent.get("property_results", []):
            property_id = property_result["property_id"]
            prop = props[property_id]
            task_root = RESULTS / "Tasks" / project / property_id
            task_root.mkdir(parents=True, exist_ok=True)
            candidates = property_result.get("candidate_results", [])
            candidate_result = candidates[0] if candidates else None
            seed_groups: dict[str, tuple[list[dict[str, Any]], dict[str, Any], Path | None]] = {
                "E0": ([], {"replay_status": "empty_corpus", "target_property_violation": None}, None)}
            summary = {"project": project, "property_id": property_id,
                       "property": prop.get("property"),
                       "property_kind": prop.get("property_kind"),
                       "agent_status": property_result.get("status"),
                       "candidate_id": candidate_result.get("candidate_id") if candidate_result else None,
                       "candidate_groups": {}, "expansion": None, "echidna": None}
            candidate = None
            base_for_expansion = []
            if candidate_result and candidate_result.get("concrete_seed"):
                concrete = candidate_result["concrete_seed"]
                raw_concrete = candidate_result.get("raw_concrete_seed") or concrete
                one_prop_context = {**full_context, "properties": [prop]}
                candidate = {**concrete, "project": project, "property": prop["property"],
                             "context": one_prop_context}
                raw_candidate = {**raw_concrete, "project": project,
                                 "property": prop["property"], "context": one_prop_context}
                raw_replay = candidate_result.get("raw_replay") or {}
                attempts = candidate_result.get("replay_attempts", [])
                final_replay = attempts[-1] if attempts else raw_replay
                e1_path = _prepare_seed(project, raw_candidate, raw_concrete["transactions"],
                                        one_prop_context, raw_replay,
                                        task_root, "E1")
                e2_path = _prepare_seed(project, candidate, concrete["transactions"],
                                        one_prop_context, final_replay,
                                        task_root, "E2")
                related = lambda replay: bool(
                    replay.get("target_property_violation") or
                    (replay.get("target_property_state") or {}).get("property_related_state_changed"))
                raw_replay = {**raw_replay,
                              "phase32_seed_utility_eligible": related(raw_replay)}
                final_replay = {**final_replay,
                                "phase32_seed_utility_eligible": related(final_replay)}
                summary["candidate_groups"]["E1"] = {
                    "sequence": raw_concrete["transactions"], "replay_status": raw_replay.get("replay_status"),
                    "seed_path": str(e1_path.relative_to(ROOT)) if e1_path else None,
                    "seed_utility_eligible": bool(e1_path and related(raw_replay)),
                    "target_property_violation": raw_replay.get("target_property_violation"),
                    "property_related_state_changed": related(raw_replay)}
                summary["candidate_groups"]["E2"] = {
                    "sequence": concrete["transactions"], "replay_status": final_replay.get("replay_status"),
                    "seed_path": str(e2_path.relative_to(ROOT)) if e2_path else None,
                    "seed_utility_eligible": bool(e2_path and related(final_replay)),
                    "target_property_violation": final_replay.get("target_property_violation"),
                    "property_related_state_changed": related(final_replay)}
                if e1_path:
                    seed_groups["E1"] = (raw_concrete["transactions"], raw_replay, e1_path)
                if e2_path:
                    seed_groups["E2"] = (concrete["transactions"], final_replay, e2_path)
                base_for_expansion = concrete["transactions"]
            if candidate is not None:
                senders = property_result.get("sender_pool") or PROJECTS[project].get("senders") or []
                expansion_summary = _expand(project, candidate, prop, abi_by_signature,
                                            base_for_expansion, senders, task_root / "扩展")
                summary["expansion"] = expansion_summary
                for mode, group in MODE_GROUPS.items():
                    result = expansion_summary["modes"][mode]
                    choice = result.get("target_candidate") or next(
                        (row for row in result.get("eligible_candidates", [])
                         if row.get("origin") != "frozen_base_replay"), None)
                    if choice is None:
                        summary["candidate_groups"][group] = {
                            "status": "no_valid_related_state_candidate",
                            "candidate_executions": result.get("candidate_executions"),
                            "target_property_violation": None}
                        continue
                    replay = choice["replay"]
                    sequence = choice["sequence"]
                    seed_path = _prepare_seed(project, candidate, sequence,
                                              candidate["context"], replay,
                                              task_root, group)
                    summary["candidate_groups"][group] = {
                        "status": "target_reached" if replay.get("target_property_violation") else "candidate",
                        "sequence": sequence, "replay_status": replay.get("replay_status"),
                        "seed_path": str(seed_path.relative_to(ROOT)) if seed_path else None,
                        "seed_utility_eligible": bool(seed_path and
                            (replay.get("target_property_violation") or
                             choice.get("feedback", {}).get("property_related_state_changed"))),
                        "target_property_violation": replay.get("target_property_violation"),
                        "property_related_state_changed": choice.get("feedback", {}).get(
                            "property_related_state_changed"),
                        "candidate_executions": result.get("candidate_executions")}
                    if seed_path:
                        replay = {**replay, "phase32_seed_utility_eligible": True}
                        seed_groups[group] = (sequence, replay, seed_path)
            # Run one-time E1/E2 replay-only evidence even when the frozen utility-entry gate failed.
            # Fuzz-500 campaigns only run for seeds that satisfy that pre-registered gate.
            echidna_summary = _run_echidna_task(project, candidate or {
                "property_id": property_id, "property": prop["property"],
                "project": project, "context": {**full_context, "properties": [prop]}},
                prop, artifact, {**full_context, "sender_pool": property_result.get("sender_pool")},
                seed_groups, task_root)
            summary["echidna"] = echidna_summary
            project_task_rows.append(summary)
            _write_json(task_root / "任务汇总.json", summary)
        overall["tasks"].extend(project_task_rows)
    _write_json(RESULTS / "Phase32对照汇总.json", overall)
    print(json.dumps({"tasks": len(overall["tasks"]),
                      "result": str((RESULTS / "Phase32对照汇总.json").relative_to(ROOT))},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
