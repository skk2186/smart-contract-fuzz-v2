#!/usr/bin/env python3
"""Freeze and run Phase37's paired adaptive-E3 prerequisite-binding diagnostic."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计"
PHASE36_DIR = ROOT / "func/测试过程/跨交易属性状态依赖审计"
RESULTS = BASE / "结果/Phase37-20261121"
FREEZE = RESULTS / "00-Phase37冻结.json"
SUMMARY = RESULTS / "Phase37-开发集结果.json"
PHASE36_RESULTS = BASE / "结果/Phase36-20261120"
PHASE36_FREEZE = PHASE36_RESULTS / "00-Phase36冻结.json"
GATE_FILE = BASE / "Phase36属性状态感知门控.py"
DRIVER36_FILE = BASE / "Phase36自适应扩展.py"
DRIVER37_FILE = Path(__file__)
UNIT_FILE = BASE / "Phase37机制单元测试.py"
TASKS = ("BWorkflow", "CMsgSender", "DAllowance")
MAX_LENGTH, MAX_CANDIDATES, RETAINED_PREFIXES = 8, 24, 4
SEED_BASE = 20261120
TASK_PROJECTS = {
    "BWorkflow": ("AuditBWorkflow", "WorkflowHarness",
        "sol/单合约测试/StateDependencyAuditBWorkflow/WorkflowHarness.sol"),
    "CMsgSender": ("AuditCMsgSender", "MsgSenderDelegationHarness",
        "sol/单合约测试/StateDependencyAuditCMsgSender/MsgSenderDelegationHarness.sol"),
    "DAllowance": ("AuditDAllowance", "AllowanceHarness",
        "sol/单合约测试/StateDependencyAuditDAllowance/AllowanceHarness.sol"),
}

CODE_FILES = (
    "func/功能/状态反馈序列扩展.py",
    "func/功能/跨交易状态约束.py",
    "func/功能/属性分析适配器.py",
    "func/功能/属性种子上下文.py",
    "func/功能/属性种子上下文.py",
    "func/功能/种子验证.py",
    "func/测试过程/SCFuzzBench公开项目接入/Phase32有限扩展与对照.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase36属性状态感知门控.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase36自适应扩展.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase37前置约束绑定验证.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase37机制单元测试.py",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sequence_sha(sequence: list[dict[str, Any]]) -> str:
    packed = json.dumps(sequence, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")).encode()
    return hashlib.sha256(packed).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载实验模块：{path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_contexts(phase36_freeze: dict[str, Any]):
    """Build contexts from frozen incomplete inputs and static analysis only.

    Deliberately does not import 运行能力审计.py: that module contains the
    independent complete Oracle sequences used for prior diagnosis.
    """
    sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                    str(PHASE36_DIR), str(ROOT / "func/测试过程/SCFuzzBench公开项目接入")]
    phase36 = load_module("phase37_phase36_driver", DRIVER36_FILE)
    from 属性种子上下文 import PROJECTS, load_project_context

    static_root = BASE / "结果/20261120/01-编译与静态分析"
    safety = phase36_freeze["missing_prerequisite_safety_inputs"]
    contexts: dict[str, dict[str, Any]] = {}
    for task_id, (project, contract, source_relative) in TASK_PROJECTS.items():
        report = static_root / task_id / "属性分析.json"
        artifact = static_root / task_id / "编译产物.json"
        report_data = read_json(report)
        property_id = phase36_freeze["tasks"][task_id]["property_id"]
        raw_prop = next(item for item in report_data["properties"]
                        if item.get("property_id") == property_id)
        environment = read_json(
            PHASE36_RESULTS / "SafetyMissingPrerequisite" / task_id / "G1" / "G1-原始E3.json"
        )["records"][0]["replay"]["environment"]
        senders = list(environment["sender_pool"])
        source = ROOT / source_relative
        PROJECTS[project] = {
            "report": str(report.relative_to(ROOT)),
            "artifact": str(artifact.relative_to(ROOT)),
            "source_root": str(source.parent.relative_to(ROOT)),
            "contract": contract,
            "target": source_relative,
            "fuzzer_target": str(source),
            "solc_version": "0.8.28",
            "solc": "/home/skk/.solc-select/artifacts/solc-0.8.28/solc-0.8.28",
            "solc_args": "--optimize --optimize-runs 200 --evm-version shanghai",
            "foundry": False,
            "constructor_args": [],
            "deployment": {"mode": "constructor", "constructor_args": [],
                "deployer": environment["deployer"],
                "contract_address": environment["contract_address"],
                "address_derivation": "CREATE(deployer, nonce=0)"},
            "execution": {"chain_id": environment["chain_id"],
                "deployment_timestamp": environment["deployment_timestamp"],
                "deployment_block_number": environment["deployment_block_number"],
                "base_fee_per_gas": 0, "gas_price": environment["gas_price_wei"],
                "block_gas_limit": 100000000, "initial_balance": 100000000000000000000,
                "max_transaction_gas": environment["gas_limit_per_transaction"],
                "hardfork": environment["evm_revision"]},
            "property": {"mode": "property", "prefix": "echidna_",
                "sender": environment["property_sender"],
                "target_property": raw_prop["property"]},
            "senders": senders,
            "echidna": {"prefix": "echidna_", "workers": 1,
                "call_sequence_length": MAX_LENGTH, "stop_on_fail": False,
                "disable_slither": True},
        }
        context = load_project_context(project, [property_id])
        prop = context["properties"][0]
        context = {**context, "properties": [prop], "sender_pool": senders}
        sequence = copy.deepcopy(safety[task_id]["sequence"])
        contexts[task_id] = {
            "project": project, "property_id": property_id, "context": context,
            "prop": prop, "senders": senders,
            "candidate": {"project": project, "property_id": property_id,
                "candidate_id": f"phase37-{task_id}", "transactions": sequence,
                "property": prop["property"], "context": context},
            "sequence": sequence,
        }

    # Existing project profiles come from the V2 declaration files. These
    # controls use their frozen baseline inputs, not the missing-step Oracle.
    for task_id, target_key in (("A_Wallet02Refund", "Wallet02Refund"),
                                ("E_PigfoxRWASupplySum", "Phase32PigfoxRWADemo")):
        frozen = phase36_freeze["tasks"][task_id]
        context = load_project_context(frozen["project"], [frozen["property_id"]])
        prop = context["properties"][0]
        senders = list(PROJECTS[frozen["project"]].get("senders", []))
        if not senders:
            senders = sorted({str(tx["sender"]) for tx in frozen["sequence"]})
        context = {**context, "properties": [prop], "sender_pool": senders}
        sequence = copy.deepcopy(frozen["sequence"])
        contexts[target_key] = {
            "project": frozen["project"], "property_id": frozen["property_id"],
            "context": context, "prop": prop, "senders": senders,
            "candidate": {"project": frozen["project"],
                "property_id": frozen["property_id"], "candidate_id": f"phase37-{target_key}",
                "transactions": sequence, "property": prop["property"], "context": context},
            "sequence": sequence,
        }
    return phase36, contexts, PROJECTS


def _abi_map(artifact_path: Path) -> dict[str, dict[str, Any]]:
    artifact = read_json(artifact_path)
    return {entry["name"] + "(" + ",".join(item["type"] for item in entry.get("inputs", [])) + ")": entry
            for entry in artifact.get("abi", []) if entry.get("type") == "function"}


def _profile_paths(project: str, spec: dict[str, Any], projects: dict[str, Any]) -> tuple[Path, Path]:
    report = Path(spec.get("report_path") or projects[project]["report"])
    artifact = Path(spec.get("artifact_path") or projects[project]["artifact"])
    if not report.is_absolute():
        report = ROOT / report
    if not artifact.is_absolute():
        artifact = ROOT / artifact
    if not report.is_file():
        report = Path(projects[project]["report"])
        if not report.is_absolute():
            report = ROOT / report
    if not artifact.is_file():
        artifact = Path(projects[project]["artifact"])
        if not artifact.is_absolute():
            artifact = ROOT / artifact
    return report, artifact


def _git_state() -> tuple[str, str]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    return head, branch


def _target_spec(task_id: str, sequence: list[dict[str, Any]]) -> dict[str, Any]:
    """Reporting-only goal, derived from the incomplete input and source contract."""
    if task_id == "BWorkflow":
        return {"kind": "workflow_stage", "stage_getter": "stage()",
                "completed_getter": "completedAmount()", "stage": 3,
                "completed_min": 1}
    if task_id == "CMsgSender":
        consumer = sequence[-1]
        return {"kind": "delegated_execution", "owner": consumer["arguments"][0],
                "operator": consumer["sender"], "executed_getter": "executedFor(address)",
                "deposit_getter": "depositedCredit(address)",
                "available_getter": "availableCredit(address)",
                "authorization_getter": "authorizedOperator(address)",
                "amount": int(consumer["arguments"][1])}
    if task_id == "DAllowance":
        mint, consumer = sequence[0], sequence[-1]
        return {"kind": "delegated_spend", "owner": mint["arguments"][0],
                "spender": consumer["sender"], "recipient": consumer["arguments"][1],
                "amount": int(consumer["arguments"][2]),
                "balance_getter": "balanceOf(address)",
                "allowance_getter": "allowance(address,address)",
                "grant_getter": "totalGranted(address,address)",
                "spent_getter": "delegatedSpent(address,address)",
                "supply_getter": "totalSupply()"}
    if task_id == "A_Wallet02Refund":
        return {"kind": "wallet_counterexample"}
    if task_id == "E_PigfoxRWASupplySum":
        return {"kind": "rwa_supply_sum"}
    raise ValueError(f"No reporting target definition for {task_id}")


def freeze_inputs() -> None:
    if FREEZE.exists() or SUMMARY.exists():
        raise FileExistsError("Phase37 冻结或正式结果已存在；拒绝覆盖或重复运行。")
    if not PHASE36_FREEZE.is_file():
        raise FileNotFoundError(f"缺少 Phase36 冻结输入：{PHASE36_FREEZE}")
    phase36_freeze = read_json(PHASE36_FREEZE)
    current_head, current_branch = _git_state()
    if current_head != "f809887cff7d17c307c982dd054b4cd2ba21c5df" or current_branch != "main":
        raise RuntimeError(f"当前仓库基线不是指定的 main/f809887：{current_branch}/{current_head}")
    safety = phase36_freeze.get("missing_prerequisite_safety_inputs", {})
    frozen_tasks = {}
    for task_id in TASKS:
        if task_id not in safety:
            raise ValueError(f"Phase36 冻结文件缺少删步输入：{task_id}")
        sequence = copy.deepcopy(safety[task_id]["sequence"])
        project, _contract, source_relative = TASK_PROJECTS[task_id]
        report = BASE / "结果/20261120/01-编译与静态分析" / task_id / "属性分析.json"
        artifact = BASE / "结果/20261120/01-编译与静态分析" / task_id / "编译产物.json"
        raw_g1_path = PHASE36_RESULTS / "SafetyMissingPrerequisite" / task_id / "G1" / "G1-原始E3.json"
        raw_g1 = read_json(raw_g1_path)
        environment = raw_g1["records"][0]["replay"]["environment"]
        raw_report = read_json(report)
        property_id = phase36_freeze["tasks"][task_id]["property_id"]
        raw_prop = next(row for row in raw_report["properties"]
                        if row.get("property_id") == property_id)
        frozen_tasks[task_id] = {
            "project": project,
            "property_id": property_id,
            "input_sequence": sequence,
            "input_sequence_sha256": sequence_sha(sequence),
            "deleted_operation_for_evaluation_only": safety[task_id].get("deleted_function"),
            "consumer_signature_for_evaluation_only": sequence[-1].get("function"),
            "target_state_spec_for_reporting_only": _target_spec(task_id, sequence),
            "sender_pool": list(environment["sender_pool"]),
            "frozen_anvil_environment": environment,
            "analysis_contract": raw_prop["analysis_contract"],
            "analysis_contract_source": raw_prop["analysis_contract_source"],
            "source_path": source_relative,
            "source_sha256": sha(ROOT / source_relative),
            "phase36_g1_trace": str(raw_g1_path.relative_to(ROOT)),
            "phase36_g1_trace_sha256": sha(raw_g1_path),
            "static_report": str(report.relative_to(ROOT)),
            "static_report_sha256": sha(report),
            "abi_artifact": str(artifact.relative_to(ROOT)),
            "abi_artifact_sha256": sha(artifact),
        }
    code_hashes = {relative: sha(ROOT / relative) for relative in CODE_FILES}
    freeze = {
        "schema_version": 1,
        "phase": "Phase37",
        "created_before_formal_run_utc": datetime.now(timezone.utc).isoformat(),
        "repository_head": current_head,
        "branch": current_branch,
        "phase36_freeze_path": str(PHASE36_FREEZE.relative_to(ROOT)),
        "phase36_freeze_sha256": sha(PHASE36_FREEZE),
        "phase36_historical_head": phase36_freeze.get("head"),
        "inputs": frozen_tasks,
        "arms": {
            "G1": "Phase36 自适应 E3（AdaptiveGate + state_feedback），关闭本轮前置约束绑定",
            "G2": "与 G1 同一自适应 E3、相同 gate 与运行时参数修复，开启本轮前置约束绑定",
            "same_initial_sequence_per_pair": True,
            "same_project_profile_accounts_and_anvil_session": True,
            "full_oracle_sequences_passed_to_algorithm": False,
            "model_calls": 0,
        },
        "parameters": {
            "max_sequence_length": MAX_LENGTH,
            "candidate_consideration_budget_per_arm": MAX_CANDIDATES,
            "retained_prefixes": RETAINED_PREFIXES,
            "extension_random_seed_base": SEED_BASE,
            "parameter_repair_attempts_per_replay": 1,
            "binding_candidate_limit_per_proposal": 1,
        },
        "environment": {
            "anvil_and_account_configuration_source": "frozen Phase36 G1 replay environment; identical profile reused for G1/G2",
            "phase36_frozen_account_config_source": phase36_freeze.get("algorithm_parameters", {}).get("account_config_source"),
            "evm_parameters_source": "frozen Phase36 G1 replay environment and Phase36 PROJECTS profile",
            "g1_and_g2_use_separate_clean_anvil_sessions": True,
        },
        "frozen_code_sha256": code_hashes,
        "acceptance": {
            "development_set_full_sequence_successes_required": ">=2 of B/C/D",
            "must_reach_frozen_target_state_for_each_counted_success": True,
            "binding_source_must_include_state_writer_guard_and_abi_or_sender_relation": True,
            "wallet_counterexample_must_remain_and_pass_anvil_and_echidna_seed_only": True,
            "phase36_low_value_filtering_must_remain_without_obvious_regression": True,
            "costs_must_report_considered_candidates_replays_and_elapsed_time": True,
            "do_not_count_state_completion_as_property_violation": True,
            "max_common_cause_fixes": 1,
            "stop_after_failed_threshold_without_adding_favorable_cases": True,
        },
        "holdout_policy": "若开发集达标，先冻结绑定机制，再以至少两个不同状态依赖任务做最小留出；不得机械改名，若无合格任务则记为待验证。",
        "oracle_isolation": {
            "complete_oracle_sequences_loaded_by_formal_driver": False,
            "algorithm_receives_only": ["Phase36冻结删步输入序列", "Slither属性与effect_catalog", "ABI", "实际消费者调用与replay反馈"],
            "target_state_specs_are_reporting_only": True,
        },
    }
    write_json(FREEZE, freeze)
    print(json.dumps({"status": "frozen", "path": str(FREEZE.relative_to(ROOT)),
                      "tasks": {task: item["input_sequence_sha256"]
                                for task, item in frozen_tasks.items()},
                      "code_files": len(code_hashes)}, ensure_ascii=False))


def _state_target(replay: dict[str, Any], goal: dict[str, Any]) -> dict[str, Any]:
    tx_rows = replay.get("transactions", [])
    final_rows = tx_rows[-1].get("predicate_getter_values", []) if tx_rows else replay.get("initial_predicate_getters", [])
    values = {(str(row.get("signature")), json.dumps(row.get("arguments", []), sort_keys=True)): row.get("value")
              for row in final_rows if row.get("status") == "observed"}

    def get(signature: str, arguments: list[Any] | None = None, default: Any = None):
        return values.get((signature, json.dumps(arguments or [], sort_keys=True)), default)

    kind = goal.get("kind")
    if kind == "workflow_stage":
        state = {"stage": get(goal["stage_getter"]),
                 "completed": get(goal["completed_getter"], default=0)}
        reached = state["stage"] == goal["stage"] and state["completed"] is not None and state["completed"] >= goal["completed_min"]
    elif kind == "delegated_execution":
        owner = goal["owner"]
        operator = get(goal["authorization_getter"], [owner])
        state = {"deposit": get(goal["deposit_getter"], [owner], 0),
                 "available": get(goal["available_getter"], [owner], 0),
                 "authorized_operator": operator,
                 "executed": get(goal["executed_getter"], [owner], 0)}
        reached = bool(state["deposit"] and state["executed"] >= goal["amount"] and
                       isinstance(operator, str) and operator.lower() == goal["operator"].lower())
    elif kind == "delegated_spend":
        owner, spender = goal["owner"], goal["spender"]
        pair = [owner, spender]
        state = {"owner_balance": get(goal["balance_getter"], [owner], 0),
                 "spender_balance": get(goal["balance_getter"], [spender], 0),
                 "allowance": get(goal["allowance_getter"], pair, 0),
                 "total_granted": get(goal["grant_getter"], pair, 0),
                 "delegated_spent": get(goal["spent_getter"], pair, 0),
                 "total_supply": get(goal["supply_getter"], default=0)}
        reached = (state["total_granted"] >= goal["amount"] and
                   state["delegated_spent"] >= goal["amount"] and
                   state["allowance"] < state["total_granted"])
    elif kind == "wallet_counterexample":
        state = {"target_property": tx_rows[-1].get("target_property") if tx_rows else None}
        reached = state["target_property"] is False
    elif kind == "rwa_supply_sum":
        state = {"property_related_state_changed": bool(
            (replay.get("target_property_state") or {}).get("property_related_state_changed"))}
        reached = state["property_related_state_changed"]
    else:
        state, reached = {}, False
    return {"goal_kind": kind, "reached": bool(reached), "goal_state_values": state,
            "property_value": tx_rows[-1].get("target_property") if tx_rows else
                next(iter(replay.get("initial_property_values", {}).values()), None),
            "replay_status": replay.get("replay_status")}


def _property_counterexample(replay: dict[str, Any]) -> bool:
    if replay.get("target_property_violation"):
        return True
    if any(row.get("target_property") is False for row in replay.get("transactions", [])):
        return True
    return any(value is False for value in (replay.get("all_property_values") or {}).values())


def _annotate_result(result: dict[str, Any], task_id: str,
                     frozen_task: dict[str, Any]) -> None:
    deleted = frozen_task.get("deleted_operation_for_evaluation_only")
    consumer = frozen_task.get("consumer_signature_for_evaluation_only")
    for record in result.get("records", []):
        sequence = record.get("sequence", [])
        tx_functions = [tx.get("function") for tx in sequence]
        consumer_index = next((index for index, signature in enumerate(tx_functions)
                               if signature == consumer), len(sequence))
        inserted_before = any(signature == deleted for signature in tx_functions[:consumer_index])
        replay = record.get("replay") or {}
        transactions = replay.get("transactions") or []
        complete = (replay.get("replay_status") == "executable" and bool(transactions) and
                    all(tx.get("status") == "success" for tx in transactions))
        target_state = _state_target(replay, frozen_task.get("target_state_spec_for_reporting_only", {}))
        record["phase37_evaluation"] = {
            "correct_prerequisite_operation_before_consumer": bool(inserted_before),
            "binding_status": (record.get("constraint_binding") or {}).get("status"),
            "constraint_binding_evidence": (record.get("constraint_binding") or {}).get("evidence"),
            "full_sequence_executed": complete,
            "target_state_reached": target_state.get("reached", False),
            "target_state": target_state,
            "security_property_counterexample": _property_counterexample(replay),
        }
    counts = {"candidate_operations_inserted_before_consumer": 0,
              "binding_applied_or_confirmed": 0,
              "full_sequences_executed": 0,
              "frozen_target_state_reached": 0,
              "security_property_counterexamples": 0}
    for record in result.get("records", []):
        metrics = record.get("phase37_evaluation", {})
        counts["candidate_operations_inserted_before_consumer"] += int(
            metrics.get("correct_prerequisite_operation_before_consumer", False))
        counts["binding_applied_or_confirmed"] += int(
            metrics.get("binding_status") in {"applied", "already_satisfied"})
        counts["full_sequences_executed"] += int(metrics.get("full_sequence_executed", False))
        counts["frozen_target_state_reached"] += int(metrics.get("target_state_reached", False))
        counts["security_property_counterexamples"] += int(
            metrics.get("security_property_counterexample", False))
    result["phase37_counts"] = counts
    result["task_id"] = task_id


def _run_arm(phase36, gate_module, row: dict[str, Any],
             frozen_task: dict[str, Any], task_id: str, group: str,
             output_dir: Path, binding_enabled: bool) -> dict[str, Any]:
    from 属性种子上下文 import PROJECTS

    raw_path = output_dir / f"{group}-完整候选轨迹.json"
    if raw_path.exists():
        prior = read_json(raw_path)
        if (prior.get("input_sequence_sha256") != sequence_sha(frozen_task["input_sequence"]) or
                prior.get("constraint_binding_enabled") != binding_enabled):
            raise RuntimeError(f"已完成组与本轮输入不符：{output_dir}")
        print(f"REUSE completed {task_id}/{group}", flush=True)
        return prior
    print(f"START {task_id}/{group} binding={binding_enabled}", flush=True)
    project = row["project"]
    candidate = copy.deepcopy(row["candidate"])
    sequence = copy.deepcopy(frozen_task["input_sequence"])
    candidate["transactions"] = copy.deepcopy(sequence)
    candidate["context"] = row["context"]
    profile = PROJECTS[project]
    artifact = Path(profile["artifact"])
    report_path = Path(profile["report"])
    if not artifact.is_absolute():
        artifact = ROOT / artifact
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    abi = _abi_map(artifact)
    senders = list(frozen_task.get("sender_pool") or row.get("senders") or profile.get("senders", []))
    effect_catalog = read_json(report_path).get("effect_catalog", {})
    phase36.MAX_LENGTH = MAX_LENGTH
    phase36.MAX_EXECUTIONS = MAX_CANDIDATES
    phase36.RETAINED_PREFIXES = RETAINED_PREFIXES
    phase36.SEED_BASE = SEED_BASE
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = phase36._run_g2(project, candidate, row["prop"], abi, sequence,
        senders, output_dir, gate_module,
        binding_enabled=binding_enabled, effect_catalog=effect_catalog)
    result.update({"group": group, "task_id": task_id,
                   "input_sequence": sequence,
                   "input_sequence_sha256": sequence_sha(sequence),
                   "adaptive_gate_enabled": True,
                   "constraint_binding_enabled": binding_enabled,
                   "accounts": senders,
                   "anvil_profile": copy.deepcopy(frozen_task.get("frozen_anvil_environment") or
                       profile.get("execution", {})),
                   "elapsed_seconds_wall": round(time.monotonic() - started, 6)})
    _annotate_result(result, task_id, frozen_task)
    write_json(output_dir / f"{group}-完整候选轨迹.json", result)
    write_json(output_dir / f"{group}-门控与绑定流.json",
               {"gate_records": result.get("gate_records", []),
                "candidate_records": [{"candidate_no": row.get("candidate_no"),
                    "proposal_no": row.get("proposal_no"), "origin": row.get("origin"),
                    "proposal_evidence": row.get("proposal_evidence"),
                    "constraint_binding": row.get("constraint_binding"),
                    "post_repair_binding_preserved": row.get("post_repair_binding_preserved"),
                    "phase37_evaluation": row.get("phase37_evaluation")}
                    for row in result.get("records", [])]})
    print(f"DONE {task_id}/{group} candidates={result['candidate_executions']} counts={result['phase37_counts']}", flush=True)
    return result


def _rows_for_run(contexts, frozen_tasks):
    rows = {}
    for task_id in TASKS:
        row = contexts[task_id]
        rows[task_id] = {**row, "sequence": copy.deepcopy(frozen_tasks[task_id]["input_sequence"]),
                         "candidate": {**copy.deepcopy(row["candidate"]),
                                       "transactions": copy.deepcopy(frozen_tasks[task_id]["input_sequence"])}}
    return rows


def _verify_freeze(freeze: dict[str, Any]) -> None:
    # The retained environment-blocked freeze predates this driver's detailed
    # schema. Verify it verbatim; construct reporting fields only in memory.
    if "algorithm_version" in freeze:
        head, branch = _git_state()
        if branch != "main" or head != freeze["head"]:
            raise RuntimeError("当前 main HEAD 与原 Phase37 冻结不符。")
        hashes = {**freeze["algorithm_version"]["core_sha256"],
                  **freeze["frozen_inputs_sha256"]}
        for relative, expected in hashes.items():
            if sha(ROOT / relative) != expected:
                amendment = read_json(RESULTS / "05-ABI变量执行修复.json")
                if not (relative == amendment["file"] and expected == amendment["frozen_sha256"] and
                        sha(ROOT / relative) == amendment["execution_sha256"]):
                    raise RuntimeError(f"原 Phase37 冻结哈希不符：{relative}")
                original_bytes = (ROOT / relative).read_bytes().replace(
                    amendment["new"].encode(), amendment["old"].encode())
                if hashlib.sha256(original_bytes).hexdigest() != expected:
                    raise RuntimeError("执行修复超出两处 ABI 变量引用。")
        freeze["last_verified_execution_head"] = head
        return
    if freeze.get("repository_head") != "f809887cff7d17c307c982dd054b4cd2ba21c5df":
        raise RuntimeError("冻结记录 HEAD 与本轮指定版本不符。")
    for relative, expected in freeze.get("frozen_code_sha256", {}).items():
        path = ROOT / relative
        if not path.is_file() or sha(path) != expected:
            raise RuntimeError(f"正式运行前算法文件哈希不符：{relative}")
    if sha(PHASE36_FREEZE) != freeze.get("phase36_freeze_sha256"):
        raise RuntimeError("Phase36 冻结输入已变化，停止运行。")
    if freeze.get("oracle_isolation", {}).get("complete_oracle_sequences_loaded_by_formal_driver") is not False:
        raise RuntimeError("冻结记录未证明 Oracle 完整序列隔离，停止运行。")
    for task_id, row in freeze.get("inputs", {}).items():
        checks = ((row["static_report"], row["static_report_sha256"]),
                  (row["abi_artifact"], row["abi_artifact_sha256"]),
                  (row["source_path"], row["source_sha256"]),
                  (row["phase36_g1_trace"], row["phase36_g1_trace_sha256"]))
        for relative, expected in checks:
            path = ROOT / relative
            if not path.is_file() or sha(path) != expected:
                raise RuntimeError(f"Phase37 冻结数据文件哈希不符：{task_id}/{relative}")
    current_head, current_branch = _git_state()
    if current_branch != freeze.get("branch"):
        raise RuntimeError("分支与 Phase37 冻结值不符，停止运行。")
    freeze["last_verified_execution_head"] = current_head


def _execution_freeze(freeze: dict[str, Any], phase36_freeze: dict[str, Any]):
    if "inputs" in freeze:
        return freeze
    tasks = {}
    for task_id in TASKS:
        sequence = copy.deepcopy(phase36_freeze["missing_prerequisite_safety_inputs"][task_id]["sequence"])
        original = read_json(PHASE36_RESULTS / "SafetyMissingPrerequisite" /
                             task_id / "G1/G1-原始E3.json")
        environment = original["records"][0]["replay"]["environment"]
        tasks[task_id] = {
            "input_sequence": sequence,
            "deleted_operation_for_evaluation_only": phase36_freeze["missing_prerequisite_safety_inputs"][task_id]["deleted_function"],
            "consumer_signature_for_evaluation_only": sequence[-1]["function"],
            "target_state_spec_for_reporting_only": _target_spec(task_id, sequence),
            "sender_pool": environment["sender_pool"],
            "frozen_anvil_environment": environment,
        }
    return {**freeze, "repository_head": freeze["head"], "inputs": tasks}


def _wallet_seed_only(row, result):
    """Use the retained Phase36 corpusDir correction on the new seed."""
    from 属性种子上下文 import PROJECTS
    from 种子验证 import new_seed_id, run_echidna, write_corpus

    record = result["target_candidate"]
    replay, sequence = record["replay"], record["sequence"]
    project, prop = row["project"], row["prop"]
    output = RESULTS / "Regression/Wallet02Refund/Echidna-seed-only"
    corpus = output / "corpus-input"
    seed = write_corpus(project, row["candidate"],
        replay.get("resolved_transactions") or sequence, row["context"], corpus,
        replay=replay, seed_id=new_seed_id())
    name = str(prop.get("property_abi") or prop["property"]).split("(", 1)[0].rsplit(".", 1)[-1]
    functions = [f"{PROJECTS[project]['contract']}.{item['abi_signature']}"
                 for item in prop["candidate_actions"]
                 if item.get("seed_compatible") and item.get("abi_signature")]
    functions.append(f"{PROJECTS[project]['contract']}.{name}()")
    run = run_echidna(project, corpus, property_name=name, test_limit=0,
        timeout=180, seed=20261125, test_mode="property", property_prefix=name,
        filter_functions=functions, seq_len=MAX_LENGTH, shrink_limit=1,
        stop_on_fail=False, disable_slither=True,
        sender_pool=row["context"]["sender_pool"],
        working_directory=ROOT / PROJECTS[project]["source_root"])
    evidence = run.get("corpus_evidence", {})
    passed = (evidence.get("loaded_seed_count", 0) == 1 and
              evidence.get("replayed_sequence_count", 0) >= 1 and
              evidence.get("property_failure_reported") and not evidence.get("worker_crashes"))
    summary = {"status": "complete" if passed else "failed_validation",
        "test_limit": 0, "fuzz_campaign": False,
        "seed_path": str(seed.relative_to(ROOT)), "sequence": sequence,
        "sequence_sha256": sequence_sha(sequence),
        "loaded_seed_count": evidence.get("loaded_seed_count"),
        "replayed_sequence_count": evidence.get("replayed_sequence_count"),
        "echidna_property_failure": evidence.get("property_failure_reported"),
        "raw_run": run}
    write_json(output / "seed-only-summary.json", summary)
    return summary


def _direct_anvil_goal_check(project: str, row: dict[str, Any],
                             sequence: list[dict[str, Any]]) -> dict[str, Any]:
    """Replay one bound sequence on a clean Anvil and read its exact goal getters."""
    from web3 import Web3
    from 种子验证 import AnvilSession, _deploy

    tx_results = []
    with AnvilSession(project=project) as session:
        contract, _ = _deploy(session, project)
        for tx in sequence:
            for _ in range(int(tx.get("delay_blocks", 0))):
                latest = int(session.web3.eth.get_block("latest")["timestamp"])
                session.rpc("evm_setNextBlockTimestamp", [latest + 1])
                session.rpc("evm_mine", [])
            latest = int(session.web3.eth.get_block("latest")["timestamp"])
            session.rpc("evm_setNextBlockTimestamp",
                        [latest + max(1, int(tx.get("delay_seconds", 0)))])
            function = contract.get_function_by_signature(tx["function"])(*tx["arguments"])
            tx_hash = session.web3.eth.send_transaction({
                "from": Web3.to_checksum_address(tx["sender"]),
                "to": contract.address, "data": function._encode_transaction_data(),
                "value": int(tx.get("value_wei", 0)), "gas": session.max_transaction_gas,
                "gasPrice": 0})
            receipt = session.web3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
            tx_results.append({"function": tx["function"], "receipt_status": int(receipt.status),
                               "block_number": int(receipt.blockNumber),
                               "transaction_hash": tx_hash.hex()})

        task_id = row["task_id"]
        if task_id == "BWorkflow":
            state = {"stage": contract.get_function_by_signature("stage()")().call(),
                     "completed_amount": contract.get_function_by_signature("completedAmount()")().call(),
                     "execution_limit": contract.get_function_by_signature("executionLimit()")().call()}
            reached = state["stage"] == 3 and state["completed_amount"] >= 1
        elif task_id == "CMsgSender":
            owner, amount = sequence[-1]["arguments"]
            operator = sequence[-1]["sender"]
            state = {"deposit": contract.get_function_by_signature("depositedCredit(address)")(owner).call(),
                     "available": contract.get_function_by_signature("availableCredit(address)")(owner).call(),
                     "authorized_operator": contract.get_function_by_signature("authorizedOperator(address)")(owner).call(),
                     "executed": contract.get_function_by_signature("executedFor(address)")(owner).call()}
            reached = (state["deposit"] > 0 and state["executed"] >= int(amount) and
                       state["authorized_operator"].lower() == operator.lower())
        elif task_id == "DAllowance":
            owner = sequence[0]["arguments"][0]
            consumer = next(tx for tx in sequence if tx["function"].startswith("transferFrom("))
            spender, recipient, amount = consumer["sender"], consumer["arguments"][1], int(consumer["arguments"][2])
            pair = [owner, spender]
            state = {"owner_balance": contract.get_function_by_signature("balanceOf(address)")(owner).call(),
                     "recipient_balance": contract.get_function_by_signature("balanceOf(address)")(recipient).call(),
                     "allowance": contract.get_function_by_signature("allowance(address,address)")(*pair).call(),
                     "total_granted": contract.get_function_by_signature("totalGranted(address,address)")(*pair).call(),
                     "delegated_spent": contract.get_function_by_signature("delegatedSpent(address,address)")(*pair).call(),
                     "total_supply": contract.get_function_by_signature("totalSupply()")().call()}
            reached = (state["total_granted"] >= amount and state["delegated_spent"] >= amount and
                       state["allowance"] < state["total_granted"] and
                       state["recipient_balance"] >= amount)
        else:
            raise ValueError(f"No direct target getter check for {task_id}")
        prop_signature = row["prop"]["property_abi"].rsplit(".", 1)[-1]
        property_value = contract.get_function_by_signature(prop_signature)().call()
    all_success = bool(tx_results) and all(tx["receipt_status"] == 1 for tx in tx_results)
    return {"task_id": task_id, "sequence": sequence, "transactions": tx_results,
            "all_transactions_succeeded": all_success, "target_state": state,
            "target_state_reached": bool(reached), "property_value": bool(property_value)}


def run_experiment() -> None:
    if not FREEZE.is_file() or (SUMMARY.exists() and read_json(SUMMARY).get("status") == "complete"):
        raise RuntimeError("缺少实验前冻结，或正式结果已完成；拒绝覆盖/重复运行。")
    freeze = read_json(FREEZE)
    _verify_freeze(freeze)
    phase36_freeze = read_json(PHASE36_FREEZE)
    freeze = _execution_freeze(freeze, phase36_freeze)
    phase36, contexts, _projects = _runtime_contexts(phase36_freeze)
    gate_module = load_module("phase37_adaptive_gate", GATE_FILE)
    frozen_tasks = freeze["inputs"]
    rows = _rows_for_run(contexts, frozen_tasks)
    summary = {"schema_version": 1, "phase": "Phase37", "freeze_sha256": sha(FREEZE),
               "frozen_baseline_head": freeze["repository_head"],
               "execution_head": freeze.get("last_verified_execution_head"),
               "created_utc": datetime.now(timezone.utc).isoformat(), "development_set": {},
               "controls": {}, "wallet_echidna_seed_only": None,
               "model_calls": 0, "real_project_campaigns": 0}
    try:
        for task_id in TASKS:
            task_summary = {}
            for group, binding_enabled in (("G1", False), ("G2", True)):
                output = RESULTS / "Development" / task_id / group
                result = _run_arm(phase36, gate_module, rows[task_id],
                                  frozen_tasks[task_id], task_id, group, output,
                                  binding_enabled)
                task_summary[group] = {
                    "candidate_proposals_considered": result.get("candidate_proposals_considered"),
                    "candidate_executions": result.get("candidate_executions"),
                    "total_anvil_replays": result.get("total_anvil_replays"),
                    "parameter_repair_replays": result.get("parameter_repair_replays"),
                    "binding_replays": result.get("binding_replays"),
                    "elapsed_seconds": result.get("elapsed_seconds"),
                    "gate_elapsed_seconds": result.get("gate_elapsed_seconds"),
                    "phase37_counts": result.get("phase37_counts"),
                    "status": result.get("status"),
                    "raw_path": str((output / f"{group}-完整候选轨迹.json").relative_to(ROOT)),
                }
                summary["development_set"].setdefault(task_id, {})[group] = task_summary[group]
                write_json(SUMMARY, summary)

        # Regression controls use the original Phase36 complete B state machine and
        # Pigfox no-progress input. They are reported separately from B's deleted-step
        # development task.
        phase36_frozen = phase36_freeze
        b_control_sequence = copy.deepcopy(phase36_frozen["tasks"]["BWorkflow"]["sequence"])
        pigfox_sequence = copy.deepcopy(phase36_frozen["tasks"]["E_PigfoxRWASupplySum"]["sequence"])
        control_rows = {
            "BWorkflowCompleteStateMachine": (contexts["BWorkflow"],
                b_control_sequence,
                "BWorkflow"),
            "PigfoxNoProgress": (contexts["Phase32PigfoxRWADemo"],
                pigfox_sequence,
                "E_PigfoxRWASupplySum"),
        }
        for control_id, (original_row, sequence, source_task) in control_rows.items():
            control_row = {**original_row, "sequence": sequence,
                           "candidate": {**copy.deepcopy(original_row["candidate"]),
                                         "transactions": copy.deepcopy(sequence)}}
            control_freeze = {"input_sequence": sequence,
                "input_sequence_sha256": sequence_sha(sequence),
                "deleted_operation_for_evaluation_only": None,
                "consumer_signature_for_evaluation_only": None,
                "target_state_spec_for_reporting_only": _target_spec(
                    "BWorkflow" if control_id == "BWorkflowCompleteStateMachine" else
                    "E_PigfoxRWASupplySum", sequence),
                "sender_pool": list(original_row["senders"])}
            arms = {}
            # Same-run ungated E3 reference for the efficiency regression.
            # G1/G2 below retain the Phase37 meaning (both gated).
            import Phase32有限扩展与对照 as extension_driver
            from 属性种子上下文 import PROJECTS
            artifact = ROOT / PROJECTS[control_row["project"]]["artifact"]
            previous_modes = extension_driver.MODE_GROUPS
            try:
                extension_driver.MODE_GROUPS = {"state_feedback": "E3"}
                extension_driver.MAX_LENGTH = MAX_LENGTH
                extension_driver.MAX_EXECUTIONS = MAX_CANDIDATES
                extension_driver.RETAINED_PREFIXES = RETAINED_PREFIXES
                reference = extension_driver._expand(control_row["project"],
                    copy.deepcopy(control_row["candidate"]), control_row["prop"],
                    _abi_map(artifact), copy.deepcopy(sequence), control_row["senders"],
                    RESULTS / "Regression" / control_id / "Ungated")
                reference = reference["modes"]["state_feedback"]
                write_json(RESULTS / "Regression" / control_id / "Ungated/无门控完整轨迹.json", reference)
                arms["Ungated"] = {key: reference.get(key) for key in (
                    "candidate_executions", "total_anvil_replays", "elapsed_seconds", "status")}
            finally:
                extension_driver.MODE_GROUPS = previous_modes
            for group, binding_enabled in (("G1", False), ("G2", True)):
                output = RESULTS / "Regression" / control_id / group
                result = _run_arm(phase36, gate_module, control_row, control_freeze,
                                  control_id, group, output, binding_enabled)
                arms[group] = {"candidate_proposals_considered": result.get("candidate_proposals_considered"),
                    "candidate_executions": result.get("candidate_executions"),
                    "skipped_by_gate": sum(row.get("action") == "skip" for row in result.get("gate_records", [])),
                    "total_anvil_replays": result.get("total_anvil_replays"),
                    "elapsed_seconds": result.get("elapsed_seconds"), "status": result.get("status"),
                    "raw_path": str((output / f"{group}-完整候选轨迹.json").relative_to(ROOT))}
            summary["controls"][control_id] = {"source_task": source_task, "arms": arms}
            write_json(SUMMARY, summary)

        # Re-run the Wallet counterexample with the adaptive gate and no new binding.
        # Echidna receives only the found counterexample seed and testLimit=0.
        wallet_row = contexts["Wallet02Refund"]
        wallet_freeze = phase36_frozen["tasks"]["A_Wallet02Refund"]
        wallet_data = {"input_sequence": copy.deepcopy(wallet_freeze["sequence"]),
                       "input_sequence_sha256": sequence_sha(wallet_freeze["sequence"]),
                       "deleted_operation_for_evaluation_only": None,
                       "consumer_signature_for_evaluation_only": None,
                       "target_state_spec_for_reporting_only": _target_spec(
                           "A_Wallet02Refund", wallet_freeze["sequence"]),
                       "sender_pool": list(wallet_row["senders"])}
        wallet_row = {**wallet_row, "sequence": wallet_data["input_sequence"],
                      "candidate": {**copy.deepcopy(wallet_row["candidate"]),
                                    "transactions": wallet_data["input_sequence"]}}
        wallet_results = {}
        for group, binding_enabled in (("G1", False), ("G2", True)):
            wallet_results[group] = _run_arm(phase36, gate_module, wallet_row, wallet_data,
                "Wallet02Refund", group, RESULTS / "Regression" / "Wallet02Refund" / group,
                binding_enabled)
        wallet_result = wallet_results["G2"]
        summary["wallet_anvil"] = {group: {
            "candidate_executions": result["candidate_executions"],
            "total_anvil_replays": result["total_anvil_replays"],
            "elapsed_seconds": result["elapsed_seconds"],
            "phase37_counts": result["phase37_counts"],
            "target_candidate_no": (result.get("target_candidate") or {}).get("candidate_no"),
        } for group, result in wallet_results.items()}
        if not wallet_result.get("target_candidate"):
            raise RuntimeError("Wallet adaptive E3 未保留已知 Anvil 反例，停止后续验证。")
        echidna = _wallet_seed_only(wallet_row, wallet_result)
        summary["wallet_echidna_seed_only"] = echidna
        write_json(SUMMARY, summary)
    finally:
        # Each arm's full raw evidence is written before the next arm starts.
        pass

    summary["status"] = "complete"
    write_json(SUMMARY, summary)
    print(json.dumps({"status": "complete", "summary": str(SUMMARY.relative_to(ROOT)),
                      "development_set": summary["development_set"],
                      "controls": summary["controls"],
                      "wallet_echidna": (summary["wallet_echidna_seed_only"] or {}).get("status")},
                     ensure_ascii=False))


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "run"))
    args = parser.parse_args()
    freeze_inputs() if args.command == "freeze" else run_experiment()


if __name__ == "__main__":
    main()
