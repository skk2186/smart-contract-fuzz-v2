#!/usr/bin/env python3
"""双层两阶段执行反馈闭环（Layer 1 确定性约束修复 + Layer 2 LLM 可执行修复与属性深化）及三臂对照。"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [
    str(ROOT / ".tools/phase43-runtime-py311"),
    str(ROOT / "deepseek"),
    str(ROOT / "func/功能"),
]

from AgentA import generate_candidates
from AgentB import SENDERS, instantiate_candidate
from deepseek接口 import CallBudget, DeepSeekCallError
from 属性种子上下文 import PROJECTS, find_property, load_project_context
from 种子验证 import (
    AnvilSession,
    inspect_initial_state,
    new_seed_id,
    replay_seed,
    run_echidna,
    write_corpus,
)


M1_TARGETS = [
    ("Wallet02Refund", "8e75f62866f6d582a033", "echidna_wallet_accounting_respected"),
    ("EthernautDex", "36dfdfaa21bb1b408da9", "echidna_dex_reserves_non_empty"),
    ("TokenWhale", "85ecbb71ea3e7168edab", "echidna_no_token_inflation"),
    ("Request", "bc39edeb78eed12c3bea", "echidna_captured_never_exceeds_authorized"),
    ("BeeStorage", "2c68514fc72b1303d6e8", "echidna_stamp_internal_pot_not_above_contract_balance"),
]


def _decode_revert_reason(data: Any) -> str | None:
    if not isinstance(data, str):
        return None
    encoded = data[2:] if data.startswith("0x") else data
    try:
        raw = bytes.fromhex(encoded)
        if len(raw) < 4 + 64 or raw[:4] != bytes.fromhex("08c379a0"):
            return None
        args = raw[4:]
        offset = int.from_bytes(args[:32], "big")
        if offset + 32 > len(args):
            return None
        length = int.from_bytes(args[offset : offset + 32], "big")
        start = offset + 32
        if start + length > len(args):
            return None
        return args[start : start + length].decode("utf-8", errors="replace")
    except (ValueError, OverflowError):
        return None


def _api_summary(log_path: Path) -> dict[str, Any]:
    rows = []
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    metered = [row.get("usage") for row in rows if isinstance(row.get("usage"), dict)]
    return {
        "request_attempts": len(rows),
        "failed_request_attempts": sum(not row.get("ok", False) for row in rows),
        "prompt_tokens": sum(int(item.get("prompt_tokens", 0)) for item in metered),
        "completion_tokens": sum(int(item.get("completion_tokens", 0)) for item in metered),
        "total_tokens": sum(int(item.get("total_tokens", 0)) for item in metered),
        "estimated_cost_usd_offpeak": str(
            sum((Decimal(item["estimated_cost_usd"]["offpeak"]) for item in metered), Decimal(0))
        ),
        "estimated_cost_usd_peak": str(
            sum((Decimal(item["estimated_cost_usd"]["peak"]) for item in metered), Decimal(0))
        ),
    }


def _extract_state_snapshot(replay: dict[str, Any], init_state: dict[str, Any]) -> dict[str, Any]:
    """提取适合喂给 LLM 的精简链上状态变化摘要。"""
    txs = replay.get("transactions", [])
    last_views = {}
    last_pred_getters = {}
    for tx in txs:
        if isinstance(tx.get("view_values"), dict) and tx["view_values"]:
            last_views = tx["view_values"]
        if isinstance(tx.get("predicate_getters"), dict) and tx["predicate_getters"]:
            last_pred_getters = tx["predicate_getters"]
    init_views = (init_state or {}).get("view_values") or {}
    view_diffs = {}
    for k, v in last_views.items():
        if init_views.get(k) != v:
            view_diffs[k] = {"before": init_views.get(k), "after": v}
    return {
        "initial_views": dict(list(init_views.items())[:20]),
        "final_views": dict(list(last_views.items())[:20]),
        "changed_views": dict(list(view_diffs.items())[:20]),
        "final_predicate_getters": dict(list(last_pred_getters.items())[:15]),
        "target_property_violation": bool(replay.get("target_property_violation")),
    }


def _build_feasibility_feedback(
    replay: dict[str, Any],
    concrete: dict[str, Any],
    prop_context: dict[str, Any],
    init_state: dict[str, Any],
) -> tuple[str, str]:
    """构建 Stage 1 可执行性修复反馈，返回 (failure_kind, feedback_text)。"""
    tx_rows = replay.get("transactions", [])
    failed_tx = None
    for row in tx_rows:
        if (
            row.get("status") != "success"
            or row.get("execution_class") in {"unexpected_internal_revert", "trace_unavailable"}
            or row.get("dependency_errors")
            or row.get("execution_effect_error")
        ):
            failed_tx = row
            break
    reasons = []
    if failed_tx:
        for field in ("revert_reason", "property_error", "execution_effect_error", "trace_error"):
            if failed_tx.get(field):
                reasons.append(str(failed_tx[field]))
        for ie in failed_tx.get("internal_errors") or []:
            dec = _decode_revert_reason(ie.get("output"))
            if dec:
                reasons.append(dec)
            elif ie.get("error"):
                reasons.append(str(ie["error"]))
        for de in failed_tx.get("dependency_errors") or []:
            reasons.append(str(de))
    reason_text = "; ".join(dict.fromkeys(r for r in reasons if r))[:600]
    lower = reason_text.lower()

    if any(k in lower for k in ("allowance", "approve", "not exist", "unknown id", "invalid token", "batchdoesnotexist", "not initialized")):
        kind = "missing_precondition"
    elif any(k in lower for k in ("owner", "unauthorized", "permission", "approver", "sender")):
        kind = "permission_or_role"
    elif any(k in lower for k in ("balance", "amount", "exceed", "insufficient", "low", "overflow", "underflow", "invalid tokens")):
        kind = "numeric_or_argument"
    else:
        kind = "execution_revert"

    # Find relevant prerequisite producers from static analysis for the failed function
    failed_fn = failed_tx.get("function") if failed_tx else None
    prereq_hints = []
    if failed_fn:
        for act in prop_context.get("candidate_actions", []):
            if act.get("abi_signature") == failed_fn or act.get("function") == failed_fn:
                prereq_hints = act.get("prerequisite_dependencies", [])[:6]
                break

    succeeded_prefix = []
    for tx, rec in zip(replay.get("resolved_transactions", []), tx_rows):
        if rec.get("status") == "success" and not rec.get("internal_errors") and not rec.get("dependency_errors"):
            succeeded_prefix.append(
                {
                    "function": tx.get("function"),
                    "arguments": tx.get("arguments"),
                    "sender": tx.get("sender"),
                    "value_wei": tx.get("value_wei"),
                }
            )
        else:
            break

    payload = {
        "feedback_stage": "stage1_feasibility_repair",
        "failure_kind": kind,
        "failed_step_index": failed_tx.get("index") if failed_tx else None,
        "failed_function": failed_fn,
        "revert_or_error": reason_text or "execution reverted (no reason string)",
        "succeeded_prefix_count": len(succeeded_prefix),
        "succeeded_prefix": succeeded_prefix,
        "attempted_transactions": [
            {
                "function": t.get("function"),
                "arguments": t.get("arguments"),
                "sender": t.get("sender"),
                "value_wei": t.get("value_wei"),
            }
            for t in concrete.get("transactions", [])
        ],
        "static_prerequisite_hints": prereq_hints,
        "observed_state": _extract_state_snapshot(replay, init_state),
        "guidance": (
            "上述交易序列在真实 Anvil 回放中失败。请仔细核对失败原因、所需前置动作（如 approve/create/deposit）、"
            "真实合约/代币地址（来自 observed_state.initial_views）、sender 角色权限及数值余额边界，"
            "重新规划或修正参数使完整序列成功执行，并朝违反目标属性方向推进。"
        ),
    }
    return kind, json.dumps(payload, ensure_ascii=False)[:3500]


def _build_escalation_feedback(
    best_seed: dict[str, Any],
    prop_context: dict[str, Any],
    init_state: dict[str, Any],
    round_index: int,
    prior_attempts_summary: list[dict[str, Any]],
) -> str:
    """构建 Stage 2 属性深化反馈：已有可执行序列但属性仍为 true，驱动 Agent 进一步逼近/击破属性。"""
    replay = best_seed["replay"]
    resolved = replay.get("resolved_transactions", [])
    per_tx_trace = []
    for tx, rec in zip(resolved, replay.get("transactions", [])):
        per_tx_trace.append(
            {
                "step": rec.get("index"),
                "function": tx.get("function"),
                "arguments": tx.get("arguments"),
                "sender": tx.get("sender"),
                "value_wei": tx.get("value_wei"),
                "events": [
                    {"event": ev.get("event"), "args": ev.get("args")}
                    for ev in (rec.get("events") or [])[:4]
                ],
                "changed_predicate_getters": rec.get("changed_predicate_getters", [])[:6],
            }
        )
    payload = {
        "feedback_stage": "stage2_property_escalation",
        "escalation_round": round_index,
        "target_property": prop_context.get("property"),
        "target_property_predicate": prop_context.get("property_predicate"),
        "current_status": "已有可执行多交易序列，但执行后目标属性仍为 true（尚未触发反例）。",
        "best_executable_sequence": per_tx_trace,
        "observed_state_after_best_sequence": _extract_state_snapshot(replay, init_state),
        "prior_executable_fingerprints": prior_attempts_summary[-4:],
        "guidance": (
            "不要重复已经尝试过的浅层安全序列！请分析为什么当前序列执行后目标属性仍为 true，"
            "结合实测的链上余额/状态变化和源码漏洞逻辑（例如：多账户交叉存款/提款/退款、跨 sender 授权与 transferFrom、"
            "多轮交替 swap 持续压低某一方池子余额直到精确抽干为 0、或通过事件 ID 推进到更深状态），"
            "在 max_steps 内规划更深、步数更完整的新多交易序列以直接触发属性违反或极大逼近边界。"
        ),
    }
    return json.dumps(payload, ensure_ascii=False)[:4200]


def _apply_layer1_repair(
    concrete: dict[str, Any],
    replay: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    proposal = replay.get("constraint_repair_proposal")
    if not proposal:
        return None, None
    tx_index = int(proposal["transaction_index"]) - 1
    repaired_transactions = [dict(row) for row in concrete["transactions"]]
    if not 0 <= tx_index < len(repaired_transactions):
        return None, None
    original_tx = repaired_transactions[tx_index]
    repaired_arguments = list(original_tx.get("arguments", []))
    updates = proposal.get("argument_updates") or [
        {
            "argument_index": proposal["argument_index"],
            "argument_name": proposal.get("argument_name"),
            "original_value": proposal.get("current_value"),
            "repaired_value": proposal["repaired_value"],
            "reason": proposal.get("repair_mode"),
        }
    ]
    applied = []
    for update in updates:
        arg_index = int(update["argument_index"])
        if not 0 <= arg_index < len(repaired_arguments):
            continue
        prev = repaired_arguments[arg_index]
        if prev == update["repaired_value"]:
            continue
        repaired_arguments[arg_index] = update["repaired_value"]
        applied.append({**update, "previous_value": prev})
    if not applied:
        return None, None
    original_tx["arguments"] = repaired_arguments
    new_concrete = {**concrete, "transactions": repaired_transactions}
    event = {
        "transaction_index": tx_index + 1,
        "function": original_tx.get("function"),
        "argument_updates": applied,
        "evidence": proposal,
    }
    return new_concrete, event


def _candidate_score(seed_entry: dict[str, Any], init_state: dict[str, Any]) -> tuple[int, int, int, int]:
    """为多样有效种子打分：反例 > 属性相关状态变化数 > 全局视图变化数 > 序列步数。"""
    replay = seed_entry["replay"]
    violation = 1 if replay.get("target_property_violation") else 0
    pred_changes = sum(len(tx.get("changed_predicate_getters") or []) for tx in replay.get("transactions", []))
    snap = _extract_state_snapshot(replay, init_state)
    view_changes = len(snap["changed_views"])
    steps = len(replay.get("resolved_transactions", []))
    return (violation, pred_changes, view_changes, steps)


def _evaluate_candidate_with_repairs(
    project: str,
    context: dict[str, Any],
    prop_context: dict[str, Any],
    init_state: dict[str, Any],
    raw_candidate: dict[str, Any],
    session: AnvilSession,
    *,
    call_options: dict[str, Any],
    agent_b_init_options: dict[str, Any] | None = None,
    goal_mode: str,
    enable_layer1: bool,
    agent_b_repairs: int,
    feedback_hint: str | None = None,
) -> dict[str, Any]:
    candidate = {
        **raw_candidate,
        "project": project,
        "context": context,
        "property": prop_context["property"],
    }
    layer1_repairs = []
    b_attempts = 0
    concrete = None
    last_error = None
    replay = None

    # Initial Agent B instantiation (fast mode by default, upgrade to call_options on repair)
    b_init_opts = agent_b_init_options or call_options
    schema_feedback = feedback_hint
    for schema_try in range(2):
        b_attempts += 1
        try:
            concrete, _ = instantiate_candidate(
                context,
                candidate,
                feedback=schema_feedback,
                attempt=b_attempts,
                environment=context.get("agent_environment"),
                goal_mode=goal_mode,
                call_options=b_init_opts if schema_try == 0 else call_options,
            )
            last_error = None
            break
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:600]}"
            schema_feedback = f"上次 JSON/ABI 参数校验失败，请保持函数顺序修正错误：{last_error}"

    if not concrete:
        return {
            "candidate": candidate,
            "status": "agent_b_failed",
            "error": last_error,
            "concrete": None,
            "replay": None,
            "layer1_repairs": layer1_repairs,
            "layer2_b_repairs": 0,
        }

    layer2_b_used = 0
    layer1_used = 0
    while True:
        replay = replay_seed(
            project,
            candidate,
            concrete["transactions"],
            session=session,
            dependency_hints=concrete.get("data_dependencies"),
            runtime_constraints=enable_layer1,
        )
        if replay.get("replay_status") == "executable":
            break
        if replay.get("deployment_status") != "success":
            break
        # Stage 1 Layer 1: Deterministic runtime constraint repair (0 token)
        if enable_layer1 and layer1_used < 2:
            repaired_concrete, rep_event = _apply_layer1_repair(concrete, replay)
            if repaired_concrete is not None and rep_event is not None:
                layer1_repairs.append(rep_event)
                concrete = repaired_concrete
                layer1_used += 1
                continue
        # Stage 1 Layer 2 (param/sender repair via Agent B)
        if layer2_b_used < agent_b_repairs:
            _, fb = _build_feasibility_feedback(replay, concrete, prop_context, init_state)
            b_attempts += 1
            try:
                repaired_concrete, _ = instantiate_candidate(
                    context,
                    candidate,
                    feedback=fb,
                    attempt=b_attempts,
                    environment=context.get("agent_environment"),
                    goal_mode=goal_mode,
                    call_options=call_options,
                )
                concrete = repaired_concrete
                layer2_b_used += 1
                continue
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:600]}"
                break
        break

    status = "executable" if (replay and replay.get("replay_status") == "executable") else "replay_failed"
    return {
        "candidate": candidate,
        "status": status,
        "error": last_error,
        "concrete": concrete,
        "replay": replay,
        "layer1_repairs": layer1_repairs,
        "layer2_b_repairs": layer2_b_used,
    }


def run_arm(
    project: str,
    property_id: str,
    property_name: str,
    arm: str,
    run_root: Path,
    *,
    echidna_limit: int = 20000,
    echidna_timeout: int = 30,
    echidna_seed: int = 20261128,
    seq_len: int = 10,
    max_steps: int = 10,
    token_budget: int = 200_000,
) -> dict[str, Any]:
    started = time.monotonic()
    arm_root = run_root / project / arm
    if arm_root.exists():
        shutil.rmtree(arm_root)
    arm_root.mkdir(parents=True, exist_ok=True)
    api_log = arm_root / "API调用.jsonl"

    full_context = load_project_context(project, [property_id])
    prop_context = full_context["properties"][0]
    project_config = PROJECTS[project]
    deployment = project_config.get("deployment", {})
    execution = project_config.get("execution", {})
    runtime = {
        "chain_id": execution.get("chain_id", 1),
        "initial_timestamp": execution.get("deployment_timestamp", 1524785992),
        "initial_block_number": execution.get("deployment_block_number", 4370000),
        "evm_revision": execution.get("hardfork", "shanghai"),
        "harness_address": deployment.get(
            "contract_address",
            execution.get("contract_address", "0xA647ff3c36cFab592509E13860ab8c4F28781a66"),
        ),
        "property_sender": project_config.get("property", {}).get(
            "sender", "0x0000000000000000000000000000000000010000"
        ),
        "gas_price_wei": execution.get("gas_price", 0),
        "gas_limit_per_transaction": execution.get("max_transaction_gas", 12500000),
    }

    if arm == "native":
        fuzz_dir = arm_root / "echidna_fuzz"
        fuzz_dir.mkdir(parents=True, exist_ok=True)
        echidna_res = run_echidna(
            project,
            fuzz_dir,
            property_name=property_name,
            test_limit=echidna_limit,
            timeout=echidna_timeout,
            seed=echidna_seed,
            test_mode="property",
            property_prefix=property_name,
            seq_len=seq_len,
            stop_on_fail=True,
            disable_slither=True,
        )
        native_result = {
            "project": project,
            "property_id": property_id,
            "property_name": property_name,
            "arm": arm,
            "valid_seed_count": 0,
            "injected_seed_count": 0,
            "anvil_counterexample": False,
            "echidna_seed_only_falsified": False,
            "echidna_fuzz_falsified": bool(echidna_res.get("property_failures")),
            "echidna_elapsed": echidna_res.get("elapsed_seconds"),
            "echidna_unique_instructions": echidna_res.get("unique_instructions"),
            "echidna_fuzzing_txs": echidna_res.get("fuzzing_transactions"),
            "seed_gen_seconds": 0.0,
            "api_usage": {"request_attempts": 0, "total_tokens": 0, "estimated_cost_usd_offpeak": "0"},
            "total_elapsed": round(time.monotonic() - started, 3),
        }
        (arm_root / "arm_result.json").write_text(
            json.dumps(native_result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return native_result

    # Configure arm hyperparameters
    if arm == "oneshot":
        call_options = {
            "model": "deepseek-flash",
            "thinking": "disabled",
            "max_tokens": 4096,
            "budget": CallBudget(token_budget),
            "log_path": api_log,
        }
        agent_b_init_options = call_options
        goal_mode = "default"
        init_candidates = 1
        enable_layer1 = False
        agent_b_repairs = 0
        stage1_replans = 0
        stage2_escalations = 0
        max_kept_seeds = 1
    elif arm == "hybrid":
        shared_budget = CallBudget(max(token_budget, 400_000))
        call_options = {
            "model": "deepseek-flash",
            "thinking": "enabled",
            "max_tokens": 24576,
            "max_retries": 1,
            "timeout": 180,
            "budget": shared_budget,
            "log_path": api_log,
        }
        agent_b_init_options = {
            "model": "deepseek-flash",
            "thinking": "disabled",
            "max_tokens": 4096,
            "max_retries": 1,
            "timeout": 120,
            "budget": shared_budget,
            "log_path": api_log,
        }
        goal_mode = "falsify"
        init_candidates = 2
        enable_layer1 = True
        agent_b_repairs = 1
        stage1_replans = 2
        stage2_escalations = 2
        max_kept_seeds = 5
    else:
        raise ValueError(f"Unknown arm: {arm}")

    seed_gen_started = time.monotonic()
    valid_seeds: list[dict[str, Any]] = []
    seen_tx_fingerprints: set[str] = set()
    all_eval_logs: list[dict[str, Any]] = []
    counterexample_found = False
    stage1_replan_used = 0
    stage2_escalation_used = 0
    layer1_repair_total = 0

    with AnvilSession(project=project) as session:
        init_state = inspect_initial_state(project, prop_context, session=session)
        role_senders = [item["address"] for item in init_state.get("role_addresses", [])]
        sender_pool = list(dict.fromkeys([*(project_config.get("senders") or SENDERS), *role_senders]))
        for address in role_senders:
            session.rpc("anvil_setBalance", [address, hex(100 * 10**18)])
        context = {
            **full_context,
            "deployment_state": init_state,
            "sender_pool": sender_pool,
            "agent_environment": runtime,
        }

        def record_eval(ev: dict[str, Any], phase_tag: str) -> None:
            nonlocal counterexample_found, layer1_repair_total
            layer1_repair_total += len(ev.get("layer1_repairs") or [])
            summary_row = {
                "phase": phase_tag,
                "candidate_id": ev["candidate"].get("candidate_id"),
                "steps": [s.get("function") for s in ev["candidate"].get("steps", [])],
                "status": ev["status"],
                "layer1_repairs": len(ev.get("layer1_repairs") or []),
                "layer2_b_repairs": ev.get("layer2_b_repairs", 0),
                "target_property_violation": bool((ev.get("replay") or {}).get("target_property_violation")),
                "error": ev.get("error"),
            }
            all_eval_logs.append(summary_row)
            if ev["status"] == "executable" and ev.get("replay"):
                fp = json.dumps(ev["replay"].get("resolved_transactions", []), sort_keys=True)
                if fp not in seen_tx_fingerprints:
                    seen_tx_fingerprints.add(fp)
                    valid_seeds.append({**ev, "phase": phase_tag})
                if ev["replay"].get("target_property_violation"):
                    counterexample_found = True

        # --- Initial Planning (with 1 empty-plan retry) ---
        planned_list = []
        plan_fb = None
        for plan_try in range(2):
            try:
                plan, _ = generate_candidates(
                    context,
                    max_candidates=init_candidates,
                    max_steps=max_steps,
                    min_steps=1,
                    use_shared_prefixes=False,
                    goal_mode=goal_mode,
                    repair_feedback=plan_fb,
                    tag=f"AgentA_{project}_{arm}_init{plan_try + 1}",
                    call_options=call_options,
                )
                planned_list = [r for r in plan.get("property_sequences", []) if r.get("property_id") == property_id]
                if planned_list:
                    break
                plan_fb = (
                    "上次返回的 steps 为空或未通过校验（invalid_records="
                    + json.dumps(plan.get("invalid_records", []), ensure_ascii=False)[:800]
                    + "）。请务必输出至少 1 条包含 1 到 "
                    + str(max_steps)
                    + " 个合法 candidate_actions 步骤的非空序列。"
                )
            except Exception as exc:
                all_eval_logs.append({"phase": f"init_plan_error_{plan_try + 1}", "error": str(exc)[:600]})
                plan_fb = f"上次规划调用失败：{str(exc)[:400]}。请精简输出合法 JSON 序列。"

        failed_evals: list[dict[str, Any]] = []
        for idx, raw_cand in enumerate(planned_list, start=1):
            raw_cand = {**raw_cand, "candidate_id": f"{arm}-init-{idx:02d}"}
            ev = _evaluate_candidate_with_repairs(
                project,
                context,
                prop_context,
                init_state,
                raw_cand,
                session,
                call_options=call_options,
                agent_b_init_options=agent_b_init_options,
                goal_mode=goal_mode,
                enable_layer1=enable_layer1,
                agent_b_repairs=agent_b_repairs,
            )
            record_eval(ev, "initial")
            if ev["status"] != "executable":
                failed_evals.append(ev)
            if counterexample_found:
                break

        # --- Stage 1 Layer 2: Execution-Feedback Replanning for failed candidates ---
        while not counterexample_found and not valid_seeds and failed_evals and stage1_replan_used < stage1_replans:
            stage1_replan_used += 1
            ref_fail = failed_evals[-1]
            if ref_fail.get("replay") and ref_fail.get("concrete"):
                _, fb_text = _build_feasibility_feedback(ref_fail["replay"], ref_fail["concrete"], prop_context, init_state)
            else:
                fb_text = f"上次候选生成失败：{ref_fail.get('error')}。请给出简洁合法的多交易计划。"
            try:
                replan, _ = generate_candidates(
                    context,
                    max_candidates=2,
                    max_steps=max_steps,
                    min_steps=1,
                    use_shared_prefixes=False,
                    goal_mode=goal_mode,
                    repair_feedback=fb_text,
                    tag=f"AgentA_{project}_{arm}_s1replan{stage1_replan_used}",
                    call_options=call_options,
                )
                new_cands = [r for r in replan.get("property_sequences", []) if r.get("property_id") == property_id]
            except Exception as exc:
                all_eval_logs.append({"phase": f"s1_replan{stage1_replan_used}_error", "error": str(exc)[:600]})
                break
            failed_evals = []
            for idx, raw_cand in enumerate(new_cands, start=1):
                raw_cand = {**raw_cand, "candidate_id": f"{arm}-s1r{stage1_replan_used}-{idx:02d}"}
                ev = _evaluate_candidate_with_repairs(
                    project,
                    context,
                    prop_context,
                    init_state,
                    raw_cand,
                    session,
                    call_options=call_options,
                    goal_mode=goal_mode,
                    enable_layer1=enable_layer1,
                    agent_b_repairs=agent_b_repairs,
                    feedback_hint=fb_text,
                )
                record_eval(ev, f"stage1_replan_{stage1_replan_used}")
                if ev["status"] != "executable":
                    failed_evals.append(ev)
                if counterexample_found:
                    break

        # --- Stage 2: Property-Guided Escalation ---
        while not counterexample_found and valid_seeds and stage2_escalation_used < stage2_escalations:
            stage2_escalation_used += 1
            best = max(valid_seeds, key=lambda s: _candidate_score(s, init_state))
            prior_summary = [
                {
                    "phase": s["phase"],
                    "steps": [t.get("function") for t in s["replay"].get("resolved_transactions", [])],
                    "violation": bool(s["replay"].get("target_property_violation")),
                }
                for s in valid_seeds
            ]
            esc_fb = _build_escalation_feedback(best, prop_context, init_state, stage2_escalation_used, prior_summary)
            try:
                esc_plan, _ = generate_candidates(
                    context,
                    max_candidates=2,
                    max_steps=max_steps,
                    min_steps=2,
                    use_shared_prefixes=False,
                    goal_mode=goal_mode,
                    repair_feedback=esc_fb,
                    tag=f"AgentA_{project}_{arm}_s2esc{stage2_escalation_used}",
                    call_options=call_options,
                )
                esc_cands = [r for r in esc_plan.get("property_sequences", []) if r.get("property_id") == property_id]
            except Exception as exc:
                all_eval_logs.append({"phase": f"s2_esc{stage2_escalation_used}_error", "error": str(exc)[:600]})
                break
            for idx, raw_cand in enumerate(esc_cands, start=1):
                raw_cand = {**raw_cand, "candidate_id": f"{arm}-s2e{stage2_escalation_used}-{idx:02d}"}
                ev = _evaluate_candidate_with_repairs(
                    project,
                    context,
                    prop_context,
                    init_state,
                    raw_cand,
                    session,
                    call_options=call_options,
                    goal_mode=goal_mode,
                    enable_layer1=enable_layer1,
                    agent_b_repairs=agent_b_repairs,
                    feedback_hint=esc_fb,
                )
                record_eval(ev, f"stage2_escalation_{stage2_escalation_used}")
                if counterexample_found:
                    break

    seed_gen_seconds = round(time.monotonic() - seed_gen_started, 3)

    # Select top diverse valid seeds (counterexamples first)
    ranked_seeds = sorted(valid_seeds, key=lambda s: _candidate_score(s, init_state), reverse=True)[:max_kept_seeds]
    seed_bank_dir = arm_root / "seed_bank"
    written_files: list[Path] = []
    for entry in ranked_seeds:
        sid = new_seed_id()
        p = write_corpus(
            project,
            entry["candidate"],
            entry["replay"]["resolved_transactions"],
            context,
            seed_bank_dir,
            replay=entry["replay"],
            seed_id=sid,
        )
        written_files.append(p)

    # Echidna seed-only check + full fuzz campaign
    seed_only_res = None
    if written_files:
        so_dir = arm_root / "echidna_seed_only"
        (so_dir / "coverage").mkdir(parents=True, exist_ok=True)
        for wf in written_files:
            shutil.copy2(wf, so_dir / "coverage" / wf.name)
        seed_only_res = run_echidna(
            project,
            so_dir,
            property_name=property_name,
            test_limit=0,
            timeout=20,
            seed=echidna_seed,
            test_mode="property",
            property_prefix=property_name,
            seq_len=seq_len,
            stop_on_fail=True,
            disable_slither=True,
            sender_pool=sender_pool,
        )

    fuzz_dir = arm_root / "echidna_fuzz"
    (fuzz_dir / "coverage").mkdir(parents=True, exist_ok=True)
    for wf in written_files:
        shutil.copy2(wf, fuzz_dir / "coverage" / wf.name)
    echidna_res = run_echidna(
        project,
        fuzz_dir,
        property_name=property_name,
        test_limit=echidna_limit,
        timeout=echidna_timeout,
        seed=echidna_seed,
        test_mode="property",
        property_prefix=property_name,
        seq_len=seq_len,
        stop_on_fail=True,
        disable_slither=True,
        sender_pool=sender_pool,
    )

    api_usage = _api_summary(api_log)
    result = {
        "project": project,
        "property_id": property_id,
        "property_name": property_name,
        "arm": arm,
        "valid_seed_count": len(valid_seeds),
        "injected_seed_count": len(written_files),
        "anvil_counterexample": counterexample_found,
        "layer1_repairs_applied": layer1_repair_total,
        "stage1_replans_used": stage1_replan_used,
        "stage2_escalations_used": stage2_escalation_used,
        "echidna_seed_only_loaded": (seed_only_res or {}).get("loaded_seed_count", 0),
        "echidna_seed_only_replayed": (seed_only_res or {}).get("replayed_sequence_count", 0),
        "echidna_seed_only_falsified": bool((seed_only_res or {}).get("property_failures")),
        "echidna_seed_only_instructions": (seed_only_res or {}).get("unique_instructions"),
        "echidna_fuzz_loaded": echidna_res.get("loaded_seed_count", 0),
        "echidna_fuzz_falsified": bool(echidna_res.get("property_failures")),
        "echidna_elapsed": echidna_res.get("elapsed_seconds"),
        "echidna_unique_instructions": echidna_res.get("unique_instructions"),
        "echidna_fuzzing_txs": echidna_res.get("fuzzing_transactions"),
        "seed_gen_seconds": seed_gen_seconds,
        "api_usage": api_usage,
        "eval_trace": all_eval_logs,
        "winning_seed_transactions": (
            ranked_seeds[0]["replay"]["resolved_transactions"] if ranked_seeds else []
        ),
        "total_elapsed": round(time.monotonic() - started, 3),
    }
    (arm_root / "arm_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects", nargs="*", default=None, help="指定运行的 M1 项目名，默认全部 5 靶")
    parser.add_argument("--arms", nargs="*", default=["native", "oneshot", "hybrid"])
    parser.add_argument("--echidna-limit", type=int, default=20000)
    parser.add_argument("--echidna-timeout", type=int, default=30)
    parser.add_argument("--seed", type=int, default=20261128)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "deepseek/结果/M1双阶段闭环验证/三臂对照")
    args = parser.parse_args()

    selected = [
        t for t in M1_TARGETS
        if args.projects is None or t[0] in args.projects
    ]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_rows = []
    for proj, prop_id, prop_name in selected:
        for arm in args.arms:
            print(f"\n>>> Running {proj} | arm={arm} ...", flush=True)
            row = run_arm(
                proj,
                prop_id,
                prop_name,
                arm,
                args.out_dir,
                echidna_limit=args.echidna_limit,
                echidna_timeout=args.echidna_timeout,
                echidna_seed=args.seed,
            )
            all_rows.append(row)
            print(
                f"    [{proj}/{arm}] seeds={row['valid_seed_count']} "
                f"anvil_ce={row['anvil_counterexample']} "
                f"so_ce={row['echidna_seed_only_falsified']} "
                f"fuzz_ce={row['echidna_fuzz_falsified']} "
                f"instr={row['echidna_unique_instructions']} "
                f"echidna_s={row['echidna_elapsed']} "
                f"tokens={row['api_usage']['total_tokens']} "
                f"cost=${row['api_usage']['estimated_cost_usd_offpeak']}",
                flush=True,
            )
    summary_path = args.out_dir / "m1_three_arm_summary.json"
    summary_path.write_text(json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Saved summary to {summary_path} ===", flush=True)


if __name__ == "__main__":
    main()
