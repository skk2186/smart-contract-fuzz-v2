#!/usr/bin/env python3
"""复用 V2 Agent/E2/E3 与统一 Foundry/Echidna 后端运行 Drips Phase41。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "deepseek/实验过程")]

import 真实合约统一执行适配器 as adapter
from 跨交易状态约束 import (bind_inserted_prerequisite,
                           cross_transaction_write_read_matches,
                           extract_numeric_guard_evidence,
                           propose_numeric_repair, propagate_argument_updates)
from 状态反馈序列扩展 import (build_action_templates, feedback_vector,
                           propose_extensions, retain_diverse_prefixes,
                           sequence_fingerprint)
from 种子验证 import run_echidna
from 属性种子上下文 import PROJECTS, load_project_context
from AgentB import to_echidna_sequence
from deepseek接口 import CallBudget
from 运行Agent种子流程 import (_agent_a_for_property, _agent_b_call,
                          _api_summary, _candidate_context)


RESULT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase41-20261123/Drips"
MANIFEST = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置/Drips.json"
PROPERTY_ID = "6e7899beaef22d4a3a87"
PROPERTY_SIGNATURE = (
    "EchidnaSqueezeTests.testSqueezableAmountCantBeUndone"
    "(uint8,uint8,uint160,uint32,uint32,int128)")
PAIRED_SEEDS = [4041, 4042, 4043]
MAX_SEQUENCE_LENGTH = 8
E3_CANDIDATE_BUDGET = 24


def write_json(path: Path, value: Any) -> None:
    adapter.write_json(path, value)


def read_json(path: Path) -> Any:
    return adapter.read_json(path)


def _runtime(manifest: dict[str, Any]) -> dict[str, Any]:
    execution = manifest.get("execution", {})
    deployment = manifest.get("deployment", {})
    return {
        "chain_id": int(execution.get("chain_id", 1)),
        "initial_timestamp": int(execution.get("deployment_timestamp", 1524785992)),
        "initial_block_number": int(execution.get("deployment_block_number", 4370000)),
        "evm_revision": str(execution.get("hardfork", "shanghai")),
        "harness_address": str(deployment.get("contract_address")),
        "property_sender": manifest["accounts"][0]["address"],
        "gas_price_wei": int(execution.get("gas_price", 0)),
        "gas_limit_per_transaction": int(execution.get("max_transaction_gas", 12500000)),
    }


def _context_for_agent(manifest: dict[str, Any], deployment_state: dict[str, Any]
                       ) -> tuple[dict[str, Any], dict[str, Any]]:
    full = load_project_context("Drips", [PROPERTY_ID])
    prop = full["properties"][0]
    if prop.get("property") != PROPERTY_SIGNATURE:
        raise RuntimeError("冻结属性与已有 Drips Slither 属性报告不一致")
    source_guard_documents = []
    for source in manifest.get("numeric_guard_sources", []):
        path = ROOT / str(source)
        if path.is_file():
            source_guard_documents.append({"source": str(source),
                                           "text": path.read_text(encoding="utf-8")})
    for action in prop.get("candidate_actions", []):
        action["numeric_guard_evidence"] = extract_numeric_guard_evidence(
            source_guard_documents, action.get("abi_inputs", []))
    senders = [item["address"] for item in manifest.get("accounts", [])]
    context = {**full, "deployment_state": deployment_state,
               "sender_pool": senders, "agent_environment": _runtime(manifest)}
    return context, prop


def _foundry(manifest: dict[str, Any], output: Path
             ) -> tuple[adapter.FoundryCheatcodeBackend, Path, dict[str, str], dict[str, Any]]:
    prep_path = RESULT / "准备/01-source-dependency-preparation.json"
    prep = read_json(prep_path)
    if prep.get("status") not in {"ready", "ready_with_verified_adapter"}:
        raise RuntimeError("Drips 固定源码准备未 ready: " + json.dumps(prep, ensure_ascii=False))
    workspace = Path(prep["cache"]["workspace"])
    env, tools = adapter.tool_environment(manifest, output)
    return adapter.FoundryCheatcodeBackend(manifest, workspace, output, env, tools["forge"]), workspace, env, tools


def _freeze_task(manifest: dict[str, Any], prop: dict[str, Any],
                 initial_feedback: dict[str, Any], tools: dict[str, Any]) -> dict[str, Any]:
    source = ROOT / "sol/真实项目/DripsSCFuzzBench/src/echidna/EchidnaSqueezeTests.sol"
    freeze = {
        "schema_version": 1, "project": "Drips",
        "classification": "engineering_integration_and_regression_only",
        "source_commit": manifest["project"]["commit"],
        "source_tree_sha256": manifest["project"]["source_tree_sha256"],
        "property_source_file_sha256": adapter.sha256_file(source),
        "property_id": PROPERTY_ID, "property": prop["property"],
        "property_kind": prop["property_kind"], "property_abi": prop["property_abi"],
        "property_source": prop["property_source"],
        "property_predicate_excerpt": prop["property_predicate"],
        "assertion_sites": prop.get("assertion_sites", []),
        "read_states": prop.get("read_states", []),
        "property_write_states": prop.get("property_write_states", []),
        "dependency_status": prop.get("dependency_status"),
        "analysis_unknowns": prop.get("unknowns", []),
        "predicate_observation": manifest.get("property_observation", {}).get(
            prop["assertion_trigger"]["abi_signature"], {}),
        "initial_observed_state": initial_feedback.get("state_before", []),
        "initial_target_property_state": "unknown; original assertion has parameters and is not called during deploy-only observation",
        "deployment": manifest.get("deployment", {}),
        "accounts": manifest.get("accounts", []),
        "execution": manifest.get("execution", {}),
        "tool_versions": tools.get("versions", {}),
        "budgets": {
            "agent_a_calls": 1, "agent_b_calls": 1, "agent_a_candidates": 1,
            "agent_a_max_steps": MAX_SEQUENCE_LENGTH, "planning_repairs": 0,
            "agent_b_schema_repairs": 0, "execution_replans": 0,
            "e2_parameter_repairs": 1, "e3_candidate_budget_per_group": E3_CANDIDATE_BUDGET,
            "max_sequence_length": MAX_SEQUENCE_LENGTH, "echidna_test_limit": 500,
            "paired_echidna_seeds": PAIRED_SEEDS, "workers": 1,
        },
        "known_phase40_sequence_excluded_from_agent_input_and_seed_groups": True,
        "frozen_before_agent_output": True,
    }
    return freeze


def run_agent() -> dict[str, Any]:
    out = RESULT / "agent"
    out.mkdir(parents=True, exist_ok=True)
    result_path = out / "agent-run.json"
    if result_path.exists():
        previous = read_json(result_path)
        events = (previous.get("agent_a") or {}).get("events", [])
        # A budget preflight rejection sends no request to the model and creates
        # no plan. Preserve it, then allow the one actual initial planning call.
        is_unsent_budget_rejection = (
            previous.get("status") == "agent_a_error" and bool(events) and
            all(event.get("error_kind") == "token_budget_exceeded" and
                not event.get("http_status") and not event.get("response_id")
                for event in events))
        if not is_unsent_budget_rejection:
            raise FileExistsError("Agent A/B 已有本轮原始输出；拒绝重复规划: " + str(result_path))
        archived = out / "agent-preflight-budget-error.json"
        if archived.exists():
            raise FileExistsError("Agent 预算预检证据已存在；拒绝覆盖: " + str(archived))
        result_path.replace(archived)
    manifest = read_json(MANIFEST)
    freeze_path = out / "task-freeze.json"
    context_path = out / "agent-context.json"
    preflight_path = out / "deployment-preflight-v2-feedback.json"
    if freeze_path.exists() or context_path.exists():
        if not (freeze_path.is_file() and context_path.is_file() and preflight_path.is_file()):
            raise RuntimeError("已有任务冻结证据不完整；拒绝重建或覆盖")
        context = read_json(context_path)
        prop = next(item for item in context["properties"]
                    if item.get("property_id") == PROPERTY_ID)
    else:
        backend, workspace, env, tools = _foundry(manifest, out / "deployment-preflight")
        preflight_raw = backend.execute_sequence(adapter.ExecutionRequest(
            "phase41-agent-deployment-preflight", []))
        preflight = backend.to_v2_feedback(preflight_raw)
        write_json(preflight_path, preflight)
        if preflight_raw.get("status") != "passed" or not preflight.get("deployment", {}).get("success"):
            result = {"status": "deployment_preflight_failed", "raw": preflight_raw,
                      "feedback": preflight}
            write_json(result_path, result)
            return result

        context, prop = _context_for_agent(manifest, {
            "status": "success", "contract_address": preflight["deployment"].get("target_address"),
            "observed_state": preflight.get("state_before", []),
            "role_addresses": [{"role": item.get("role"), "address": item["address"]}
                               for item in manifest.get("accounts", [])],
            "observation_completeness": preflight.get("capabilities", {}).get("state_observation"),
        })
        freeze = _freeze_task(manifest, prop, preflight, tools)
        write_json(freeze_path, freeze)
        write_json(context_path, context)

    api_log = out / "API调用.jsonl"
    # Drips' existing static evidence is large. The prior local preflight
    # estimated a 628,555-token worst-case request before any HTTP call.
    budget = CallBudget(1_500_000, deadline_monotonic=time.monotonic() + 1800)
    call_options = {"budget": budget, "log_path": api_log,
                    "record_request_body": True, "max_retries": 0}
    candidates, a_events, planning = _agent_a_for_property(
        context, PROPERTY_ID, max_candidates=1, max_steps=MAX_SEQUENCE_LENGTH,
        planning_repairs=0, tag="Phase41_Drips_AgentA_initial",
        call_options=call_options)
    candidate = _candidate_context(candidates[0], context) if candidates else None
    concrete, b_events, b_error = (None, [], None)
    if candidate:
        concrete, b_events, b_error = _agent_b_call(
            context, candidate, feedback=None, first_attempt=1, schema_repairs=0,
            call_options=call_options)
    result = {
        "schema_version": 1, "project": "Drips", "property_id": PROPERTY_ID,
        "task_freeze": str(freeze_path.relative_to(ROOT)),
        "agent_a": {"events": a_events, "planning": planning,
                    "candidate_count": len(candidates)},
        "agent_b": {"events": b_events, "error": b_error},
        "plan": candidates[0] if candidates else None,
        "concrete_output": concrete,
        "status": ("agent_b_output_ready" if concrete else
                   planning.get("status", "agent_a_no_candidate") if not candidates
                   else "agent_b_failed"),
        "api_usage": _api_summary(api_log),
        "actual_model_requested": "deepseek-flash",
        "request_log": str(api_log.relative_to(ROOT)) if api_log.exists() else None,
        "request_log_contains_prompt_and_response": bool(api_log.exists()),
        "elapsed_seconds": sum(float(row.get("elapsed_seconds", 0))
                               for row in [*a_events, *b_events]),
    }
    write_json(result_path, result)
    return result


def _as_execution_request(scenario_id: str, sequence: list[dict[str, Any]],
                          manifest: dict[str, Any]) -> adapter.ExecutionRequest:
    block = int(manifest.get("execution", {}).get("deployment_block_number", 1))
    transactions = []
    for row in sequence:
        delay_blocks = int(row.get("delay_blocks", 0))
        if delay_blocks:
            block += delay_blocks
        transactions.append(adapter.Transaction(
            signature=row["function"], arguments=row.get("arguments", []),
            sender=row["sender"], value_wei=str(row.get("value_wei", "0")),
            timestamp=row.get("timestamp"), delay_seconds=int(row.get("delay_seconds", 0)),
            block_number=block if delay_blocks else row.get("block_number"),
            origin=row.get("origin")))
    return adapter.ExecutionRequest(scenario_id, transactions, False)


def _replay(backend: adapter.FoundryCheatcodeBackend, manifest: dict[str, Any],
            sequence: list[dict[str, Any]], scenario_id: str, output: Path,
            target_signature: str) -> tuple[dict[str, Any], dict[str, Any]]:
    write_json(output / (scenario_id + ".sequence.json"), sequence)
    raw = backend.execute_sequence(_as_execution_request(scenario_id, sequence, manifest))
    feedback = backend.to_v2_feedback(raw, target_property_signature=target_signature)
    write_json(output / (scenario_id + ".v2-feedback.json"), feedback)
    return raw, feedback


def _e2_repair(context: dict[str, Any], sequence: list[dict[str, Any]],
               feedback: dict[str, Any], *,
               source_guard_documents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    prop = context["properties"][0]
    action_by_signature = {item.get("abi_signature"): item
                           for item in prop.get("candidate_actions", [])}
    proposals = []
    for row in feedback.get("transactions", []):
        if row.get("status") == "success":
            continue
        action = action_by_signature.get(row.get("function"), {})
        guards = [guard for effect in action.get("effect_evidence", [])
                  for guard in effect.get("guards", [])]
        source_guards = (action.get("numeric_guard_evidence") or
                         extract_numeric_guard_evidence(source_guard_documents or [],
                                                        action.get("abi_inputs", [])))
        observations = []
        for item in row.get("state_getter_values", []):
            if item.get("status") != "observed":
                continue
            try:
                value = int(item.get("value"))
            except (TypeError, ValueError):
                continue
            observations.append({"outputs": [{"name": item.get("name"),
                                               "type": item.get("output_type"),
                                               "value": value}],
                                 "source": item.get("source")})
        proposal = propose_numeric_repair(
            action.get("abi_inputs", []), row.get("arguments", []), observations,
            [str(row.get("revert_reason") or "")],
            static_guards=[*guards, *source_guards],
            source_excerpt=str(action.get("source_excerpt") or ""))
        proposals.append({"transaction_index": row.get("transaction_index"),
                          "function": row.get("function"), "proposal": proposal,
                          "source_guard_evidence": source_guards})
    chosen = next((item for item in proposals if item.get("proposal")), None)
    repaired = [dict(item) for item in sequence]
    propagated = []
    if chosen:
        index = int(chosen["transaction_index"]) - 1
        proposal = chosen["proposal"]
        abi_by_signature = {
            str(action.get("abi_signature", "")).rsplit(".", 1)[-1]: {
                "inputs": action.get("abi_inputs", [])}
            for action in prop.get("candidate_actions", []) if action.get("abi_signature")}
        trigger = prop.get("assertion_trigger") or {}
        if trigger.get("abi_signature"):
            abi_by_signature[str(trigger["abi_signature"]).rsplit(".", 1)[-1]] = {
                "inputs": trigger.get("abi_inputs", [])}
        repaired, propagated = propagate_argument_updates(
            repaired, index, proposal, abi_by_signature)
    return {"proposals": proposals, "applied": chosen is not None,
            "sequence": repaired if chosen else sequence,
            "propagated_argument_updates": propagated}


def _action_evidence(prop: dict[str, Any]) -> tuple[list[dict[str, Any]],
                                                     dict[str, dict[str, Any]], set[str]]:
    templates_evidence = []
    evidence_by_signature = {}
    for action in prop.get("candidate_actions", []):
        signature = action.get("abi_signature")
        if not signature:
            continue
        writes = sorted({str(effect.get("state")) for effect in action.get("effect_evidence", [])
                         if effect.get("state")})
        evidence = {**action, "write_states": writes,
                    "read_states": sorted({str(state) for effect in action.get("effect_evidence", [])
                                           for guard in effect.get("guards", [])
                                           for state in guard.get("state_reads", [])})}
        templates_evidence.append(action)
        evidence_by_signature[signature] = evidence
    target_states = set(prop.get("read_states", [])) | set(prop.get("property_write_states", []))
    return templates_evidence, evidence_by_signature, target_states


def _run_e3_group(group: str, base_sequence: list[dict[str, Any]],
                  base_feedback: dict[str, Any], context: dict[str, Any],
                  manifest: dict[str, Any], backend: adapter.FoundryCheatcodeBackend,
                  output: Path, *, bind_phase37: bool) -> dict[str, Any]:
    from 真实合约统一执行适配器 import read_json as adapter_read_json

    prop = context["properties"][0]
    artifact_path = PROJECTS["Drips"]["artifact"]
    artifact = adapter_read_json(ROOT / artifact_path)
    abi_by_signature = {
        item["name"] + "(" + ",".join(arg["type"] for arg in item.get("inputs", [])) + ")": item
        for item in artifact.get("abi", []) if item.get("type") == "function"}
    report = read_json(ROOT / PROJECTS["Drips"]["report"])
    templates, template_decisions = build_action_templates(
        prop.get("candidate_actions", []), abi_by_signature, base_sequence,
        [item["address"] for item in manifest.get("accounts", [])])
    action_evidence, evidence_by_signature, target_states = _action_evidence(prop)
    del action_evidence
    group_root = output / group
    group_root.mkdir(parents=True, exist_ok=True)
    budget_left = E3_CANDIDATE_BUDGET
    seen = {sequence_fingerprint(base_sequence)}
    frontier = [{"sequence": base_sequence, "feedback": base_feedback}]
    records = []
    while frontier and budget_left > 0:
        next_frontier = []
        for parent_index, parent in enumerate(frontier):
            if budget_left <= 0:
                break
            proposals = propose_extensions(
                parent["sequence"], templates, evidence_by_signature, abi_by_signature,
                mode="state_feedback", replay=parent["feedback"], target_states=target_states,
                senders=[item["address"] for item in manifest.get("accounts", [])],
                max_sequence_length=MAX_SEQUENCE_LENGTH,
                max_proposals=min(E3_CANDIDATE_BUDGET, budget_left),
                random_seed=4100 + parent_index)
            scored = []
            for proposal in proposals:
                if budget_left <= 0:
                    break
                sequence = proposal["sequence"]
                fingerprint = sequence_fingerprint(sequence)
                if fingerprint in seen:
                    continue
                seen.add(fingerprint)
                binding = None
                binding_matches = []
                binding_status = "disabled_in_G1" if not bind_phase37 else "not_evaluated"
                if bind_phase37:
                    binding_matches = cross_transaction_write_read_matches(
                        parent["sequence"], sequence, report.get("effect_catalog", {}))
                    if binding_matches:
                        binding = bind_inserted_prerequisite(
                            parent["sequence"], sequence, report.get("effect_catalog", {}),
                            abi_by_signature, parent_replay=parent["feedback"])
                        binding_status = ("applied" if binding and binding.get("status") == "applied"
                                          else "matched_but_unresolved")
                        if binding:
                            sequence = binding["sequence"]
                            fingerprint = sequence_fingerprint(sequence)
                            if fingerprint in seen:
                                continue
                            seen.add(fingerprint)
                    else:
                        binding_status = "not_applicable_no_matching_cross_transaction_constraint"
                index = E3_CANDIDATE_BUDGET - budget_left + 1
                scenario_id = "%s-e3-%02d" % (group, index)
                raw, feedback = _replay(backend, manifest, sequence, scenario_id, group_root,
                                       prop["assertion_trigger"]["abi_signature"])
                budget_left -= 1
                vector = feedback_vector(feedback, property_source=prop.get("property_predicate") or "")
                record = {"candidate_index": index, "scenario_id": scenario_id,
                          "operator": proposal.get("operator"),
                          "proposal_reason": proposal.get("proposal_reason"),
                          "proposal_evidence": proposal.get("evidence"),
                          "phase37_binding": binding,
                          "phase37_binding_status": binding_status,
                          "phase37_matching_constraints": binding_matches,
                          "sequence": sequence, "backend_status": raw.get("status"),
                          "replay_status": feedback.get("replay_status"),
                          "feedback": vector, "raw_log": raw.get("log")}
                records.append(record)
                scored.append({"sequence": sequence, "feedback": vector,
                               "record": record})
            if scored:
                retained = retain_diverse_prefixes(scored, limit=4)
                for retained_row in retained:
                    record = retained_row["record"]
                    if (record.get("replay_status") != "executable" and
                            len(retained_row["sequence"]) < MAX_SEQUENCE_LENGTH):
                        feedback_path = group_root / (record["scenario_id"] + ".v2-feedback.json")
                        next_frontier.append({"sequence": retained_row["sequence"],
                                              "feedback": read_json(feedback_path)})
        frontier = next_frontier
    valid = [row for row in records if row.get("replay_status") == "executable"]
    return {"group": group,
            "status": "valid_sequence_found" if any(
                row.get("replay_status") == "executable" for row in records)
            else "no_valid_sequence_within_budget",
            "phase37_binding_enabled": bind_phase37,
            "starting_sequence_fingerprint": sequence_fingerprint(base_sequence),
            "starting_sequence": base_sequence,
            "action_template_count": len(templates), "template_decisions": template_decisions,
            "candidate_budget": E3_CANDIDATE_BUDGET,
            "candidate_count": len(records), "candidates": records,
            "valid_sequence_count": len(valid),
            "valid_sequence": valid[0]["sequence"] if valid else None}


def run_comparison() -> dict[str, Any]:
    out = RESULT / "comparison"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "G0-E1-G1-G2-summary.json"
    if path.exists():
        raise FileExistsError("对照组结果已存在；拒绝覆盖历史结果")
    agent = read_json(RESULT / "agent/agent-run.json")
    context = read_json(RESULT / "agent/agent-context.json")
    manifest = read_json(MANIFEST)
    prop = context["properties"][0]
    backend, _, _, _ = _foundry(manifest, out / "deployment-tooling")
    result: dict[str, Any] = {
        "schema_version": 1, "project": "Drips", "property_id": PROPERTY_ID,
        "group_configuration": {"max_sequence_length": MAX_SEQUENCE_LENGTH,
                                "e3_candidate_budget": E3_CANDIDATE_BUDGET,
                                "phase37_binding_enabled": {"G1": False, "G2": True},
                                "agent_output_sha256": adapter.sha256_file(
                                    RESULT / "agent/agent-run.json")},
        "E1": {"status": "not_run"}, "E2": {"status": "not_run"},
        "G1": {"status": "not_run"}, "G2": {"status": "not_run"},
    }
    concrete = agent.get("concrete_output")
    if not concrete or not concrete.get("transactions"):
        result["E1"] = {"status": "no_agent_b_transactions",
                        "reason": agent.get("status")}
        result["E2"] = {"status": "not_applicable",
                        "reason": "Agent B did not produce a concrete output"}
        result["G1"] = {"status": "not_applicable",
                        "reason": "no concrete Agent B sequence"}
        result["G2"] = {"status": "not_applicable",
                        "reason": "no concrete Agent B sequence"}
        write_json(path, result)
        return result

    sequence = concrete["transactions"]
    e1_raw, e1_feedback = _replay(
        backend, manifest, sequence, "E1-agent-output", out / "E1",
        prop["assertion_trigger"]["abi_signature"])
    result["E1"] = {"status": e1_feedback.get("replay_status"),
                    "backend_status": e1_raw.get("status"),
                    "sequence": sequence, "feedback": e1_feedback,
                    "log": e1_raw.get("log")}
    e2 = _e2_repair(context, sequence, e1_feedback)
    e2_sequence = e2["sequence"]
    if e2["applied"]:
        e2_raw, e2_feedback = _replay(
            backend, manifest, e2_sequence, "E2-repaired-sequence", out / "E2",
            prop["assertion_trigger"]["abi_signature"])
    else:
        e2_raw, e2_feedback = e1_raw, e1_feedback
    result["E2"] = {"status": "repair_applied_and_replayed" if e2["applied"]
                    else "no_evidence_based_parameter_repair",
                    "proposals": e2["proposals"], "applied": e2["applied"],
                    "sequence": e2_sequence, "replay_status": e2_feedback.get("replay_status"),
                    "backend_status": e2_raw.get("status")}
    for group, bind in [("G1", False), ("G2", True)]:
        result[group] = _run_e3_group(
            group, e2_sequence, e2_feedback, context, manifest, backend, out,
            bind_phase37=bind)
        if result[group]["status"] == "not_run":
            result[group]["status"] = ("valid_sequence_found" if
                                       result[group].get("valid_sequence_count") else
                                       "no_valid_sequence_within_budget")
    result["selected_seed_sequences"] = {
        "E1": sequence if e1_feedback.get("replay_status") == "executable" else None,
        "G1": result["G1"].get("valid_sequence"),
        "G2": result["G2"].get("valid_sequence"),
    }
    write_json(path, result)
    return result


def _save_seed(sequence: list[dict[str, Any]], context: dict[str, Any],
               candidate: dict[str, Any], path: Path) -> None:
    serialized = to_echidna_sequence(
        candidate, sequence, context, contract_address="0xa647ff3c36cfab592509e13860ab8c4f28781a66")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError("种子文件已存在，拒绝覆盖: " + str(path))
    path.write_text(json.dumps(serialized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_fuzz_campaign(corpus: Path, *, seed: int, test_limit: int,
                       seed_file: Path | None, workspace: Path,
                       senders: list[str]) -> dict[str, Any]:
    corpus.parent.mkdir(parents=True, exist_ok=True)
    if seed_file:
        coverage = corpus / "coverage"
        coverage.mkdir(parents=True, exist_ok=True)
        shutil.copy2(seed_file, coverage / "seed-agent.txt")
    result = run_echidna(
        "Drips", corpus, property_name=PROPERTY_SIGNATURE,
        test_limit=test_limit, timeout=600, seed=seed,
        test_mode="assertion", property_prefix="echidna_",
        seq_len=MAX_SEQUENCE_LENGTH, stop_on_fail=False,
        disable_slither=True, sender_pool=senders,
        working_directory=workspace)
    log_path = Path(result.get("full_log_path") or "")
    log_text = (log_path.read_text(encoding="utf-8", errors="replace")
                if log_path.is_file() else str(result.get("output", "")))
    log_text = re.sub(r"\x1b\[[0-9;]*m", "", log_text)
    failures = sorted(set(re.findall(r"Test ([^\n]+?) falsified!", log_text)) |
                      set(re.findall(r"^([^\n:]+): failed!?", log_text,
                                     flags=re.MULTILINE)))
    target_failures = [name for name in failures
                       if PROPERTY_SIGNATURE in name or name.strip() == PROPERTY_SIGNATURE]
    result["all_harness_assertion_failures"] = failures
    result["other_harness_assertion_failures"] = [name for name in failures
                                                   if name not in target_failures]
    result["target_property_failure_reported"] = bool(target_failures)
    result["campaign_budget_completed"] = bool(
        test_limit > 0 and not result.get("timed_out") and
        int(result.get("fuzzing_progress_limit") or 0) >= test_limit)
    result["campaign_status"] = (
        "completed_with_assertion_failures"
        if result["campaign_budget_completed"] and result.get("exit_code") != 0 else
        "completed" if result["campaign_budget_completed"] and result.get("exit_code") == 0 else
        "seed_only_completed" if test_limit == 0 and result.get("status") == "completed" else
        "incomplete")
    return result


def run_echidna_comparison() -> dict[str, Any]:
    out = RESULT / "echidna"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "paired-fuzz-summary.json"
    if path.exists():
        raise FileExistsError("Echidna 对照结果已存在；拒绝覆盖")
    manifest = read_json(MANIFEST)
    prep = read_json(RESULT / "准备/01-source-dependency-preparation.json")
    workspace = Path(prep["cache"]["workspace"])
    senders = [item["address"] for item in manifest.get("accounts", [])]
    context = read_json(RESULT / "agent/agent-context.json")
    agent = read_json(RESULT / "agent/agent-run.json")
    comparison = read_json(RESULT / "comparison/G0-E1-G1-G2-summary.json")
    concrete = agent.get("concrete_output") or {}
    candidate = {**(comparison.get("E1", {}).get("candidate") or {}),
                 "property_id": PROPERTY_ID,
                 "assertion_trigger": context["properties"][0].get("assertion_trigger")}
    target_tx_signature = context["properties"][0]["assertion_trigger"]["abi_signature"]
    if not candidate.get("steps"):
        candidate = {"property_id": PROPERTY_ID,
                     "assertion_trigger": context["properties"][0].get("assertion_trigger")}
    sequences = {
        "E1": comparison.get("selected_seed_sequences", {}).get("E1"),
        "G1": comparison.get("selected_seed_sequences", {}).get("G1"),
        "G2": comparison.get("selected_seed_sequences", {}).get("G2"),
    }
    if not concrete.get("transactions"):
        sequences = {"E1": None, "G1": None, "G2": None}
    result: dict[str, Any] = {"test_limit": 500, "paired_seeds": PAIRED_SEEDS,
                              "workers": 1, "test_mode": "assertion",
                              "groups": {}, "status": "running"}
    for paired_seed in PAIRED_SEEDS:
        g0_corpus = out / "G0" / ("seed-%d-fuzz" % paired_seed)
        g0 = _run_fuzz_campaign(g0_corpus, seed=paired_seed, test_limit=500,
                                seed_file=None, workspace=workspace, senders=senders)
        result["groups"].setdefault("G0", []).append({
            "paired_seed": paired_seed, "external_seed_count": 0,
            "fuzz": g0, "status": g0.get("campaign_status")})
    for group, sequence in sequences.items():
        if not sequence:
            result["groups"][group] = {"status": "no_valid_seed",
                                       "reason": "no Foundry verified sequence available"}
            continue
        seed_path = out / "frozen-seeds" / group / "seed-agent.txt"
        _save_seed(sequence, context, candidate, seed_path)
        group_rows = []
        for paired_seed in PAIRED_SEEDS:
            seed_only_corpus = out / group / ("seed-%d-seed-only" % paired_seed)
            seed_only = _run_fuzz_campaign(
                seed_only_corpus, seed=paired_seed, test_limit=0,
                seed_file=seed_path, workspace=workspace, senders=senders)
            fuzz_corpus = out / group / ("seed-%d-fuzz" % paired_seed)
            fuzz = _run_fuzz_campaign(
                fuzz_corpus, seed=paired_seed, test_limit=500,
                seed_file=seed_path, workspace=workspace, senders=senders)
            seed_coverage = seed_only.get("unique_instructions")
            fuzz_coverage = fuzz.get("unique_instructions")
            coverage_delta = (fuzz_coverage - seed_coverage
                              if isinstance(seed_coverage, int) and
                              isinstance(fuzz_coverage, int) else None)
            group_rows.append({
                "paired_seed": paired_seed, "external_seed_count": 1,
                "seed_sequence_length": len(sequence),
                "target_transaction_in_seed": target_tx_signature in
                    [item.get("function") for item in sequence],
                "seed_only": seed_only, "fuzz": fuzz,
                "seed_only_coverage": seed_coverage,
                "final_coverage": fuzz_coverage,
                "fuzz_added_coverage_instructions": coverage_delta,
                "seed_replay_observed": seed_only.get("replay_evidence"),
                "loaded_seed_count": seed_only.get("loaded_seed_count"),
                "replayed_sequence_count": seed_only.get("replayed_sequence_count"),
                "target_property_failures": fuzz.get("property_failures", []),
            })
        result["groups"][group] = group_rows
    result["status"] = "completed"
    write_json(path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["agent", "comparison", "echidna"],
                        required=True)
    args = parser.parse_args()
    try:
        if args.stage == "agent":
            result = run_agent()
        elif args.stage == "comparison":
            result = run_comparison()
        else:
            result = run_echidna_comparison()
    except Exception as exc:
        error_path = RESULT / args.stage / "driver-errors.jsonl"
        error_path.parent.mkdir(parents=True, exist_ok=True)
        with error_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps({"stage": args.stage,
                                     "error_type": type(exc).__name__,
                                     "error": str(exc),
                                     "traceback": traceback.format_exc()},
                                    ensure_ascii=False) + "\n")
        raise
    print(json.dumps({"stage": args.stage, "status": result.get("status"),
                      "result_root": str(RESULT.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
