#!/usr/bin/env python3
"""Run frozen Phase36 G0/G1/G2 and missing-prerequisite safety diagnostics."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "func/测试过程/跨交易属性状态依赖审计"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入")]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计"
RESULTS = BASE / "结果/Phase36-20261120"
FREEZE = RESULTS / "00-Phase36冻结.json"
SUMMARY = RESULTS / "Phase36-G0-G1-G2总汇.json"
GATE_FILE = BASE / "Phase36属性状态感知门控.py"
DRIVER_FILE = Path(__file__)
AUDIT35_FILE = BASE / "运行能力审计.py"
DELETED_STEP = {"BWorkflow": "configureTask(uint256)",
                "CMsgSender": "authorizeOperator(address)",
                "DAllowance": "approve(address,uint256)"}
TASKS = ["A_Wallet02Refund", "BWorkflow", "CMsgSender", "DAllowance",
         "E_PigfoxRWASupplySum"]
MAX_LENGTH, MAX_EXECUTIONS, RETAINED_PREFIXES = 8, 24, 4
SEED_BASE = 20261120


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seq_sha(sequence: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(sequence, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法导入既有驱动：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_contexts():
    audit35 = load_module("phase36_audit35", AUDIT35_FILE)
    from 属性种子上下文 import PROJECTS, load_project_context

    analysis_rows = read_json(RESULTS.parent / "20261120/01-编译与静态分析/静态分析汇总.json")
    analysis_by_task = {row["task_id"]: row for row in analysis_rows}
    contexts: dict[str, dict[str, Any]] = {}
    specs: dict[str, dict[str, Any]] = {}

    wallet_spec, wallet_context, wallet_prop, wallet_candidate, _wallet_raw, wallet_meta = audit35._historical_wallet_input()
    e2 = read_json(RESULTS.parent / "20261120/04-Anvil对照/A_Wallet02Refund/E2-参数修复.json")
    wallet_candidate["transactions"] = copy.deepcopy(e2["sequence"])
    contexts["A_Wallet02Refund"] = {"spec": wallet_spec, "context": wallet_context,
        "prop": wallet_prop, "candidate": wallet_candidate,
        "sequence": copy.deepcopy(e2["sequence"]), "goal": {"kind": "wallet_counterexample"},
        "project": "Wallet02Refund", "property_id": wallet_candidate.get("property_id")}

    for task_id in ("BWorkflow", "CMsgSender", "DAllowance"):
        spec = copy.deepcopy(audit35.TASK_SPECS[task_id])
        row = analysis_by_task[task_id]
        report = ROOT / row["report_path"]
        artifact = RESULTS.parent / "20261120/01-编译与静态分析" / task_id / "编译产物.json"
        spec["runtime_property_id"] = row["property_id"]
        spec["report_path"] = report
        spec["artifact_path"] = artifact
        audit35._register_profile(task_id, spec, report, artifact)
        context = load_project_context(spec["project"], [row["property_id"]])
        prop = context["properties"][0]
        context = {**context, "properties": [prop],
                   "sender_pool": list(PROJECTS[spec["project"]].get("senders") or audit35.SENDERS)}
        agent_record = read_json(RESULTS.parent / "20261120/03-Agent输入与输出" / task_id / "AgentAB初始种子.json")
        e2 = read_json(RESULTS.parent / "20261120/04-Anvil对照" / task_id / "E2-参数修复.json")
        sequence = copy.deepcopy(e2["sequence"])
        candidate = {"project": spec["project"], "property_id": row["property_id"],
                     "candidate_id": agent_record.get("candidate", {}).get("candidate_id"),
                     "transactions": copy.deepcopy(sequence), "property": prop["property"],
                     "context": context}
        contexts[task_id] = {"spec": spec, "context": context, "prop": prop,
            "candidate": candidate, "sequence": sequence, "goal": spec["goal"],
            "project": spec["project"], "property_id": row["property_id"]}

    phase32r = audit35._load_phase32r_driver()
    pigfox_spec, pigfox_context, pigfox_prop, pigfox_candidate, _pigfox_raw, _pigfox_meta = audit35._historical_pigfox_input(phase32r)
    pigfox_spec["goal"] = {"kind": "rwa_supply_sum", "expected_property": True,
                            "low_dependency_negative_control": True}
    pigfox_e2 = read_json(RESULTS.parent / "20261120/04-Anvil对照/E_PigfoxRWASupplySum/E2-参数修复.json")
    pigfox_candidate["transactions"] = copy.deepcopy(pigfox_e2["sequence"])
    contexts["E_PigfoxRWASupplySum"] = {"spec": pigfox_spec, "context": pigfox_context,
        "prop": pigfox_prop, "candidate": pigfox_candidate,
        "sequence": copy.deepcopy(pigfox_e2["sequence"]), "goal": pigfox_spec["goal"],
        "project": pigfox_candidate["project"], "property_id": pigfox_candidate["property_id"]}
    return audit35, contexts


def freeze_inputs() -> None:
    if FREEZE.exists() or SUMMARY.exists():
        raise FileExistsError("Phase36冻结或正式结果已存在；拒绝覆盖和重复运行。")
    audit35, contexts = _load_contexts()
    oracle_file = RESULTS.parent / "20261120/00-独立Oracle计划.json"
    prior = read_json(RESULTS.parent / "20261120/00-实验冻结方案.json")
    oracle_plan = read_json(oracle_file)
    oracle_by_task = {row["task_id"]: row["sequence"] for row in oracle_plan["manual_oracle_sequences"]}
    safety = {}
    for task_id, deleted in DELETED_STEP.items():
        rows = copy.deepcopy(oracle_by_task[task_id])
        matches = [i for i, tx in enumerate(rows) if tx["function"] == deleted]
        if len(matches) != 1:
            raise RuntimeError(f"Oracle 步骤删除定位不唯一：{task_id}/{deleted}")
        reduced = rows[:matches[0]] + rows[matches[0] + 1:]
        safety[task_id] = {"deleted_function": deleted, "sequence": reduced,
                           "sequence_sha256": seq_sha(reduced),
                           "input_isolation": "仅此删减后序列进入 G1/G2；完整 Oracle 序列不进入正式算法输入"}

    frozen_tasks = {}
    for task_id in TASKS:
        row = contexts[task_id]
        source_paths: list[Path] = []
        if task_id in audit35.TASK_SPECS:
            source_paths.append(ROOT / audit35.TASK_SPECS[task_id]["source"])
            static = next(x for x in read_json(RESULTS.parent / "20261120/01-编译与静态分析/静态分析汇总.json")
                          if x["task_id"] == task_id)
            source_paths.extend([ROOT / static["report_path"],
                                 RESULTS.parent / "20261120/01-编译与静态分析" / task_id / "编译产物.json"])
        elif task_id == "E_PigfoxRWASupplySum":
            source_paths += [audit35.PIGFOX_COMPAT / "Properties.sol",
                             audit35.PIGFOX_COMPAT / "native-solc-source-manifest.json",
                             audit35.PIGFOX_COMPAT / "../src/RWAToken.sol"]
        else:
            source_paths += [audit35.HISTORICAL_WALLET, audit35.WALLET_ORACLE]
        source_hashes = {str(path.relative_to(ROOT)): sha(path) for path in source_paths if path.is_file()}
        if task_id == "A_Wallet02Refund":
            phase31_path = ROOT / "func/测试过程/SCFuzzBench公开项目接入/Phase31状态反馈序列扩展.py"
            source_hashes[str(phase31_path.relative_to(ROOT))] = sha(phase31_path)
        frozen_tasks[task_id] = {"project": row["project"], "property_id": row["property_id"],
            "sequence": row["sequence"], "sequence_sha256": seq_sha(row["sequence"]),
            "source_hashes": source_hashes,
            "input_source": str((RESULTS.parent / "20261120/04-Anvil对照" / task_id / "E2-参数修复.json").relative_to(ROOT)),
            "input_source_sha256": sha(RESULTS.parent / "20261120/04-Anvil对照" / task_id / "E2-参数修复.json"),
            "agent_calls_this_phase": 0}

    required_sources = ["func/功能/状态反馈序列扩展.py", "func/功能/属性分析适配器.py",
                        "func/功能/跨交易状态约束.py", "func/功能/种子验证.py",
                        "deepseek/AgentA.py", "deepseek/AgentB.py"]
    freeze = {"schema_version": 1, "phase": "Phase36", "created_before_g0_g1_g2_execution_utc": datetime.now(timezone.utc).isoformat(),
        "head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "remote_main_head": prior.get("remote_main_head_verified_via_github_read_only_api"),
        "baseline_phase35_freeze_sha256": sha(RESULTS.parent / "20261120/00-实验冻结方案.json"),
        "algorithm_files_sha256": {path: sha(ROOT / path) for path in required_sources},
        "phase36_files_sha256": {"gate": sha(GATE_FILE), "driver": sha(DRIVER_FILE)},
        "algorithm_parameters": {"max_sequence_length": MAX_LENGTH,
            "candidate_execution_budget": MAX_EXECUTIONS, "retained_prefixes": RETAINED_PREFIXES,
            "extension_random_seed_base": SEED_BASE,
            "account_config_source": "Phase35 frozen configuration",
            "model_calls": 0, "AgentA_B_prompts_modified": False,
            "echidna_fuzz_campaign": False},
        "arms": {"G0": "对相同 E2 序列进行一次干净 Anvil 基线回放，不生成 E3 候选",
                 "G1": "原始 Phase32 state_feedback E3，不改规则，预算 24",
                 "G2": "相同 propose_extensions 与回放接口，Anvil 前运行 Phase36 门控；未知默认执行"},
        "tasks": frozen_tasks, "missing_prerequisite_safety_inputs": safety,
        "oracle_handling": {"oracle_plan_sha256": sha(oracle_file),
            "used_only_to_construct_three_deleted-step_sequences": True,
            "formal_main_task_sequences_source": "frozen E2 outputs only",
            "full_oracle_sequence_passed_to_gate_or_E3": False},
        "comparison": {"same_frozen_e2_input": True,
            "separate_clean_anvil_sessions_for_G0_G1_G2": True,
            "candidate_replay_counter_excludes_base_replay": True,
            "gate_overhead_included_in_G2_total_elapsed": True},
        "prior_phase35_candidate_counts_reference_only": {"Wallet": 10, "BWorkflow": 24,
            "CMsgSender": 0, "DAllowance": 5, "Pigfox": 7}}
    write_json(FREEZE, freeze)
    write_json(RESULTS / "00-缺失前置步骤删减输入.json", safety)
    print(json.dumps({"status": "frozen", "freeze": str(FREEZE.relative_to(ROOT)),
                      "tasks": list(frozen_tasks), "safety_inputs": list(safety)}, ensure_ascii=False))


def _fingerprint(sequence: list[dict[str, Any]]) -> str:
    from 状态反馈序列扩展 import sequence_fingerprint
    return sequence_fingerprint(sequence)


def _run_g2(project: str, candidate: dict[str, Any], prop: dict[str, Any],
            abi_by_signature: dict[str, dict[str, Any]], sequence: list[dict[str, Any]],
            senders: list[str], output: Path, gate_module, *,
            binding_enabled: bool = False, effect_catalog: dict[str, Any] | None = None
            ) -> dict[str, Any]:
    import Phase32有限扩展与对照 as extension_driver
    from 种子验证 import AnvilSession, replay_seed
    from 状态反馈序列扩展 import (build_action_templates, feedback_vector,
        propose_extensions, retain_diverse_prefixes, sequence_fingerprint)
    if binding_enabled:
        from 跨交易状态约束 import bind_inserted_prerequisite

    started = time.monotonic()
    prep, trigger = extension_driver._split_trigger(prop, sequence, senders[0])
    max_preparation_length = MAX_LENGTH - (1 if trigger else 0)
    inventory = [row for row in prop.get("candidate_actions", [])
                 if row.get("seed_compatible") and row.get("abi_signature")]
    templates, template_decisions = build_action_templates(inventory, abi_by_signature, prep, senders)
    evidence = {str(row["abi_signature"]): row for row in inventory}
    target_states = set(prop.get("read_states", [])) | set(prop.get("property_write_states", []))
    gate = gate_module.AdaptiveGate(prop, MAX_LENGTH)
    considered = executed = total_replays = repair_replays = binding_replays = gate_seconds = 0
    records: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    gate_records: list[dict[str, Any]] = []
    seen_sequences = {_fingerprint(prep)}
    seen_states: set[str] = set()
    target_candidate = None
    with AnvilSession(project=project) as session:
        base_full = extension_driver._with_trigger(prep, trigger)
        base_sequence, base_replay, base_repair, base_repair_count = extension_driver._replay_candidate(
            project, candidate, base_full, session)
        total_replays += 1 + base_repair_count
        repair_replays += base_repair_count
        base_prep, _ = extension_driver._split_trigger(prop, base_sequence, senders[0])
        records.append({"candidate_no": 0, "proposal_no": 0, "origin": "frozen_base_replay",
            "sequence": base_sequence, "replay": base_replay, "parameter_repair": base_repair,
            "feedback": feedback_vector(base_replay, property_source=str(prop.get("property_source", "")))} )
        frontier = [{"sequence": base_prep, "replay": base_replay, "depth": 0}]
        seen_sequences = {_fingerprint(base_prep)}
        iteration = 0
        while frontier and considered < MAX_EXECUTIONS and target_candidate is None:
            iteration += 1
            pool = []
            for parent in frontier:
                remaining = MAX_EXECUTIONS - considered
                proposals = propose_extensions(parent["sequence"], templates, evidence,
                    abi_by_signature, mode="state_feedback", replay=parent["replay"],
                    target_states=target_states, senders=senders,
                    max_sequence_length=max_preparation_length, max_proposals=remaining,
                    random_seed=SEED_BASE + iteration + parent["depth"])
                for proposal in proposals:
                    preparation = proposal["sequence"]
                    fingerprint = proposal["fingerprint"]
                    if fingerprint in seen_sequences:
                        decisions.append({"iteration": iteration, "operator": proposal["operator"],
                            "sequence_fingerprint": fingerprint, "decision": "discarded",
                            "reason": "semantic duplicate"})
                        continue
                    full = extension_driver._with_trigger(preparation, trigger)
                    valid, invalid_reason = extension_driver._valid_sequence(full, abi_by_signature)
                    if not valid:
                        decisions.append({"iteration": iteration, "operator": proposal["operator"],
                            "sequence_fingerprint": fingerprint, "decision": "discarded",
                            "reason": invalid_reason})
                        continue
                    considered += 1
                    seen_sequences.add(fingerprint)
                    gate_decision = gate.decide(proposal, parent["replay"], parent["sequence"])
                    gate_seconds += float(gate_decision.get("elapsed_seconds", 0))
                    gate_record = {"proposal_no": considered, "iteration": iteration,
                        "operator": proposal["operator"], "sequence_fingerprint": fingerprint,
                        "proposal_reason": proposal.get("proposal_reason"),
                        "proposal_evidence": proposal.get("evidence"),
                        "decision": gate_decision["decision"], "action": gate_decision["action"],
                        "reason": gate_decision["reason"], "evidence": gate_decision.get("evidence"),
                        "elapsed_seconds": gate_decision.get("elapsed_seconds")}
                    gate_records.append(gate_record)
                    decisions.append({"iteration": iteration, "operator": proposal["operator"],
                        "sequence_fingerprint": fingerprint,
                        "decision": "skipped_by_adaptive_gate" if gate_decision["action"] == "skip" else "executed",
                        "reason": gate_decision["reason"]})
                    if gate_decision["action"] == "skip":
                        continue
                    one_started = time.monotonic()
                    parent_sequence = copy.deepcopy(parent["sequence"])
                    parent_replay = parent["replay"]
                    binding = None
                    replay_input = full
                    if binding_enabled:
                        binding = bind_inserted_prerequisite(
                            parent_sequence, preparation, effect_catalog or {}, abi_by_signature,
                            parent_replay=parent_replay)
                        if binding:
                            replay_input = extension_driver._with_trigger(binding["sequence"], trigger)
                    repaired, replay, repair, repair_count = extension_driver._replay_candidate(
                        project, candidate, replay_input, session)
                    binding_replay_count = 0
                    repair_preserved_binding = None
                    if binding and repair:
                        repaired_prep, _ = extension_driver._split_trigger(prop, repaired, senders[0])
                        rebound = bind_inserted_prerequisite(
                            parent_sequence, repaired_prep, effect_catalog or {}, abi_by_signature,
                            parent_replay=parent_replay)
                        if rebound is None:
                            # Reject a consumer-side repair that loses the prerequisite
                            # relation; replay the original bound sequence as the final record.
                            repaired = replay_input
                            replay = replay_seed(project, candidate,
                                [extension_driver._tx(item) for item in repaired],
                                session=session, runtime_constraints=False)
                            binding_replay_count += 1
                            repair_preserved_binding = False
                        elif rebound["sequence"] != repaired_prep:
                            repaired = extension_driver._with_trigger(rebound["sequence"], trigger)
                            replay = replay_seed(project, candidate,
                                [extension_driver._tx(item) for item in repaired],
                                session=session, runtime_constraints=False)
                            binding_replay_count += 1
                            binding = {**rebound,
                                       "post_parameter_repair_rebinding": True}
                            repair_preserved_binding = True
                        else:
                            binding = {**rebound,
                                       "post_parameter_repair_rebinding": False}
                            repair_preserved_binding = True
                    elapsed = time.monotonic() - one_started
                    executed += 1
                    total_replays += 1 + repair_count + binding_replay_count
                    repair_replays += repair_count
                    binding_replays += binding_replay_count
                    vector = feedback_vector(replay, property_source=str(prop.get("property_source", "")),
                                             seen_states=seen_states)
                    seen_states.update(vector.get("getter_state_fingerprints", []))
                    proof = gate.observe(gate_decision.get("repeat_key"), parent_replay, replay,
                                         parent_sequence, _fingerprint_sequence(repaired, prop, senders))
                    record = {"candidate_no": executed, "proposal_no": considered,
                        "iteration": iteration, "origin": proposal["operator"],
                        "proposal_reason": proposal.get("proposal_reason"),
                        "proposal_evidence": proposal.get("evidence"),
                        "sequence_fingerprint": sequence_fingerprint(repaired),
                        "sequence": repaired, "replay": replay, "parameter_repair": repair,
                        "constraint_binding": binding,
                        "post_repair_binding_preserved": repair_preserved_binding,
                        "binding_replay_count": binding_replay_count,
                        "elapsed_seconds": round(elapsed, 6), "feedback": vector,
                        "adaptive_relation_probe": proof, "retention_decision": "pending"}
                    records.append(record)
                    if vector["counterexample_reached"] and replay.get("replay_status") == "executable":
                        target_candidate = record
                        break
                    if replay.get("transactions") and (vector["property_related_state_changed"] or
                            any(row.get("status") == "success" for row in replay["transactions"])):
                        pool.append({"sequence": extension_driver._split_trigger(prop, repaired, senders[0])[0],
                            "replay": replay, "depth": parent["depth"] + 1,
                            "feedback": vector, "record": record})
                    if considered >= MAX_EXECUTIONS:
                        break
                if target_candidate or considered >= MAX_EXECUTIONS:
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
    eligible = [row for row in records if row.get("replay", {}).get("replay_status") == "executable" and
        (row.get("feedback", {}).get("property_related_state_changed") or
         row.get("feedback", {}).get("counterexample_reached"))]
    return {"mode": "state_feedback_adaptive", "group": "G2", "status": "target_reached" if target_candidate else
        "valid_related_state_candidate" if eligible else "no_valid_related_state_candidate",
        "base_sequence": base_sequence, "base_replay": base_replay,
        "base_parameter_repair": base_repair, "max_sequence_length": MAX_LENGTH,
        "retained_prefixes": RETAINED_PREFIXES, "candidate_execution_budget": MAX_EXECUTIONS,
        "candidate_proposals_considered": considered, "candidate_executions": executed,
        "base_replay_executions": 1, "parameter_repair_replays": repair_replays,
        "binding_replays": binding_replays, "constraint_binding_enabled": binding_enabled,
        "total_anvil_replays": total_replays, "elapsed_seconds": round(time.monotonic() - started, 6),
        "gate_elapsed_seconds": round(gate_seconds, 6), "api_calls": 0, "api_tokens": 0,
        "template_decisions": template_decisions, "records": records,
        "gate_records": gate_records, "decisions": decisions,
        "target_candidate": target_candidate, "eligible_candidates": eligible}


def _fingerprint_sequence(sequence: list[dict[str, Any]], prop: dict[str, Any], senders: list[str]):
    import Phase32有限扩展与对照 as extension_driver
    prep, _ = extension_driver._split_trigger(prop, sequence, senders[0])
    return prep


def _run_task(task_id: str, row: dict[str, Any], group: str, output: Path,
              gate_module, phase35) -> dict[str, Any]:
    import Phase32有限扩展与对照 as extension_driver
    from 属性种子上下文 import PROJECTS
    from 种子验证 import replay_seed

    project, candidate, prop = row["project"], copy.deepcopy(row["candidate"]), row["prop"]
    sequence = copy.deepcopy(row["sequence"])
    candidate["transactions"] = copy.deepcopy(sequence)
    context = candidate["context"]
    artifact_path = Path(PROJECTS[project]["artifact"])
    if not artifact_path.is_absolute():
        artifact_path = ROOT / artifact_path
    abi_artifact = read_json(artifact_path)
    abi = {entry["name"] + "(" + ",".join(x["type"] for x in entry.get("inputs", [])) + ")": entry
           for entry in abi_artifact["abi"] if entry.get("type") == "function"}
    senders = list(PROJECTS[project].get("senders") or phase35.SENDERS)
    output.mkdir(parents=True, exist_ok=True)

    if group == "G0":
        started = time.monotonic()
        replay = replay_seed(project, candidate, copy.deepcopy(sequence), runtime_constraints=False)
        elapsed = time.monotonic() - started
        result = {"group": group, "task_id": task_id, "input_sequence": sequence,
            "input_sha256": seq_sha(sequence), "candidate_executions": 0,
            "candidate_proposals": 0, "candidate_replays": 0,
            "base_replay_executions": 1, "total_anvil_replays": 1,
            "elapsed_seconds": round(elapsed, 6), "gate_elapsed_seconds": 0,
            "replay": replay, "target_state": phase35._target_state(replay, row["goal"], prop)}
        write_json(output / "G0-无E3.json", result)
        return result

    extension_driver.MAX_LENGTH = MAX_LENGTH
    extension_driver.MAX_EXECUTIONS = MAX_EXECUTIONS
    extension_driver.RETAINED_PREFIXES = RETAINED_PREFIXES
    if group == "G1":
        previous_modes = extension_driver.MODE_GROUPS
        try:
            extension_driver.MODE_GROUPS = {"state_feedback": "E3"}
            started = time.monotonic()
            expanded = extension_driver._expand(project, candidate, prop, abi, copy.deepcopy(sequence),
                                                senders, output)
            elapsed = time.monotonic() - started
        finally:
            extension_driver.MODE_GROUPS = previous_modes
        result = expanded["modes"]["state_feedback"]
        result = {**result, "group": group, "task_id": task_id,
                  "input_sequence": sequence, "input_sha256": seq_sha(sequence),
                  "candidate_proposals_considered": result.get("candidate_executions"),
                  "gate_elapsed_seconds": 0, "elapsed_seconds_wall": round(elapsed, 6)}
        write_json(output / "G1-原始E3.json", result)
        return result

    result = _run_g2(project, candidate, prop, abi, copy.deepcopy(sequence),
                     senders, output, gate_module)
    result.update({"task_id": task_id, "input_sequence": sequence,
                   "input_sha256": seq_sha(sequence)})
    # Write full raw traces separately, plus the gate stream as a directly auditable file.
    write_json(output / "G2-自适应E3.json", result)
    write_json(output / "G2-逐候选门控决策.json", result["gate_records"])
    return result


def _safety_runs(task_id: str, row: dict[str, Any], reduced: list[dict[str, Any]],
                 gate_module, phase35) -> dict[str, Any]:
    import Phase32有限扩展与对照 as extension_driver
    from 属性种子上下文 import PROJECTS

    safety_row = {**row, "sequence": copy.deepcopy(reduced),
                  "candidate": {**row["candidate"], "transactions": copy.deepcopy(reduced)}}
    root = RESULTS / "SafetyMissingPrerequisite" / task_id
    out = {}
    for group in ("G1", "G2"):
        out[group] = _run_task(task_id + "-missing-step", safety_row, group,
                               root / group, gate_module, phase35)
    return {"task_id": task_id, "deleted_function": DELETED_STEP[task_id],
            "input_sequence": reduced, "input_sha256": seq_sha(reduced),
            "initial_status_G1": ((out["G1"].get("records") or [{}])[0].get("replay", {}).get("replay_status")
                                  if out["G1"].get("records") else "unknown"),
            "G1": out["G1"], "G2": out["G2"],
            "gate_false_skip": any(item.get("action") == "skip" for item in out["G2"].get("gate_records", [])),
            "g2_kept_or_unknown_candidates": sum(item.get("action") == "extend" for item in out["G2"].get("gate_records", []))}


def _run_wallet_echidna(row: dict[str, Any], record: dict[str, Any],
                        output_root: Path | None = None) -> dict[str, Any]:
    from 属性种子上下文 import PROJECTS
    from 种子验证 import new_seed_id, run_echidna, write_corpus

    candidate_record = record.get("target_candidate")
    if candidate_record is None:
        return {"status": "not_run_no_g2_counterexample"}
    replay = candidate_record["replay"]
    sequence = candidate_record["sequence"]
    project, candidate, context, prop = row["project"], row["candidate"], row["context"], row["prop"]
    out = output_root or RESULTS / "Echidna-seed-only/Wallet02Refund/G2"
    corpus_root = out / "corpus-input"
    seed_path = write_corpus(project, candidate, replay.get("resolved_transactions") or sequence,
                             context, corpus_root, replay=replay, seed_id=new_seed_id())
    name = str(prop.get("property_abi") or prop.get("property", "")).split("(", 1)[0].rsplit(".", 1)[-1]
    action_sigs = [item.get("abi_signature") for item in prop.get("candidate_actions", [])
                   if item.get("seed_compatible") and item.get("abi_signature")]
    filter_functions = [f"{PROJECTS[project]['contract']}.{sig}" for sig in action_sigs]
    filter_functions.append(f"{PROJECTS[project]['contract']}.{name}()")
    source_root = Path(PROJECTS[project]["source_root"])
    working = source_root if source_root.is_absolute() else ROOT / source_root
    run = run_echidna(project, out / "run", property_name=name, test_limit=0,
        timeout=180, seed=20261125, test_mode="property", property_prefix=name,
        filter_functions=filter_functions, seq_len=MAX_LENGTH, shrink_limit=1,
        stop_on_fail=False, disable_slither=True, sender_pool=context.get("sender_pool"),
        working_directory=working)
    result = {"status": "complete" if run.get("exit_code") == 0 or
              run.get("corpus_evidence", {}).get("property_failure_reported") else "echidna_failed",
        "group": record.get("group", "G2"), "candidate_no": candidate_record.get("candidate_no"),
        "anvil_property_violation": replay.get("target_property_violation"),
        "sequence": sequence, "sequence_sha256": seq_sha(sequence),
        "seed_path": str(seed_path.relative_to(ROOT)), "test_limit": 0,
        "fuzz_campaign": False, "loaded_seed_count": run.get("corpus_evidence", {}).get("loaded_seed_count"),
        "replayed_sequence_count": run.get("corpus_evidence", {}).get("replayed_sequence_count"),
        "echidna_property_failure": run.get("corpus_evidence", {}).get("property_failure_reported"),
        "elapsed_seconds": run.get("elapsed_seconds"), "exit_code": run.get("exit_code"),
        "full_log_path": run.get("full_log_path"), "raw_run": run}
    write_json(out / "G2-seed-only-summary.json", result)
    return result


def run_experiment() -> None:
    if not FREEZE.is_file() or SUMMARY.exists():
        raise RuntimeError("缺少实验前冻结，或正式结果已存在；停止重跑。")
    freeze = read_json(FREEZE)
    if freeze.get("phase36_files_sha256") != {"gate": sha(GATE_FILE), "driver": sha(DRIVER_FILE)}:
        raise RuntimeError("门控或驱动哈希与实验前冻结不一致。")
    if __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze["head"]:
        raise RuntimeError("HEAD 已变化；拒绝在不同算法版本上运行。")
    phase35, contexts = _load_contexts()
    gate_module = load_module("phase36_adaptive_gate", GATE_FILE)
    results = {"schema_version": 1, "phase": "Phase36", "freeze_sha256": sha(FREEZE),
        "created_utc": datetime.now(timezone.utc).isoformat(), "scenarios": {},
        "safety_checks": {}, "echidna_wallet": None,
        "model_calls": 0, "core_algorithm_modified": False}
    for task_id in TASKS:
        row = contexts[task_id]
        frozen = freeze["tasks"][task_id]
        if seq_sha(row["sequence"]) != frozen["sequence_sha256"]:
            raise RuntimeError(f"冻结 E2 序列变化：{task_id}")
        groups = {}
        for group in ("G0", "G1", "G2"):
            groups[group] = _run_task(task_id, row, group,
                RESULTS / "Main" / task_id / group, gate_module, phase35)
        for group, group_result in groups.items():
            if group_result.get("input_sha256") != frozen["sequence_sha256"]:
                raise RuntimeError(f"组间 E2 输入不一致：{task_id}/{group}")
        results["scenarios"][task_id] = {
            "input_sequence_sha256": frozen["sequence_sha256"],
            "E1_E2_source": frozen["input_source"],
            "G0": _summary_metrics(groups["G0"], contexts[task_id]),
            "G1": _summary_metrics(groups["G1"], contexts[task_id]),
            "G2": _summary_metrics(groups["G2"], contexts[task_id]),
            "raw_paths": {group: str((RESULTS / "Main" / task_id / group).relative_to(ROOT))
                          for group in groups}}
        if task_id == "A_Wallet02Refund":
            results["echidna_wallet"] = _run_wallet_echidna(row, groups["G2"])
        write_json(RESULTS / "Phase36-部分汇总.json", results)

    safety_freeze = freeze["missing_prerequisite_safety_inputs"]
    for task_id, safety in safety_freeze.items():
        result = _safety_runs(task_id, contexts[task_id], safety["sequence"], gate_module, phase35)
        results["safety_checks"][task_id] = result
        write_json(RESULTS / "Phase36-部分汇总.json", results)

    write_json(SUMMARY, results)
    print(json.dumps({"status": "complete", "summary": str(SUMMARY.relative_to(ROOT)),
        "wallet_g2_candidate_executions": results["scenarios"]["A_Wallet02Refund"]["G2"]["candidate_replays"],
        "wallet_echidna": (results.get("echidna_wallet") or {}).get("status")}, ensure_ascii=False))


def _summary_metrics(result: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    import importlib
    phase35 = sys.modules.get("phase36_audit35")
    records = result.get("records", [])
    if result.get("group") == "G0":
        base_replay = result.get("replay", {})
        target = phase35._target_state(base_replay, row["goal"], row["prop"])
        records = []
    else:
        base_replay = result.get("base_replay")
        if base_replay is None and records:
            base_replay = records[0].get("replay", {})
        target = phase35._target_state(base_replay or {}, row["goal"], row["prop"])
    candidates = [record for record in records if record.get("candidate_no", 0) > 0]
    reached = []
    for record in candidates:
        replay = record.get("replay", {})
        state = phase35._target_state(replay, row["goal"], row["prop"])
        record["target_state"] = state
        if state.get("reached"):
            reached.append(record)
    target_candidate = result.get("target_candidate")
    if target_candidate:
        target_candidate["target_state"] = phase35._target_state(
            target_candidate.get("replay", {}), row["goal"], row["prop"])
    return {"strategy": result.get("group"), "base_replay_status": (base_replay or {}).get("replay_status"),
        "base_target_state": target, "candidate_proposals": result.get("candidate_proposals_considered", 0),
        "candidate_replays": result.get("candidate_executions", result.get("candidate_replays", 0)),
        "complete_candidate_sequences": sum(r.get("replay", {}).get("replay_status") == "executable" for r in candidates),
        "frozen_goal_sequences": len(reached),
        "property_counterexamples": sum(bool(r.get("replay", {}).get("target_property_violation")) for r in candidates),
        "total_anvil_replays": result.get("total_anvil_replays", 1),
        "total_elapsed_seconds": result.get("elapsed_seconds_wall", result.get("elapsed_seconds")),
        "gate_elapsed_seconds": result.get("gate_elapsed_seconds", 0),
        "skipped_candidate_proposals": sum(item.get("action") == "skip" for item in result.get("gate_records", [])),
        "target_candidate_no": target_candidate.get("candidate_no") if target_candidate else None,
        "target_candidate_sequence": target_candidate.get("sequence") if target_candidate else None,
        "target_candidate_property_violation": (target_candidate.get("replay", {}).get("target_property_violation")
                                                if target_candidate else None)}


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.freeze_only:
        freeze_inputs()
    elif args.run:
        run_experiment()
    else:
        parser.error("选择 --freeze-only 或 --run")


if __name__ == "__main__":
    main()
