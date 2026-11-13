#!/usr/bin/env python3
"""运行统一预算下的 Request 多属性种子生成与 Echidna 对照。"""

from __future__ import annotations

import json
import random
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from AgentA import generate_candidates  # noqa: E402
from AgentB import HARNESS_ADDRESS, PROPERTY_SENDER, SENDERS, instantiate_candidate  # noqa: E402
from deepseek接口 import CallBudget, DeepSeekCallError  # noqa: E402
from 属性种子上下文 import compact_for_agent, load_project_context, read_json  # noqa: E402
from 种子验证 import (AnvilSession, echidna_corpus_evidence, new_seed_id, replay_seed,
                     run_echidna, write_corpus)  # noqa: E402


PROJECT = "Request"
GROUP_INDEX = 1
GROUP_FILE = ROOT / ".tools/results/属性关联分组.json"
PROPERTY_IDS = [
    "63038d1bdccedd2b3b59",  # escrow_not_token_sink
    "66c6ef28ea17e22739c7",  # wrapper_not_token_sink
    "c451c42790194538cf50",  # token_conservation
    "eebf858bb07972b2891e",  # fee_receiver_only_gets_fees
]
TRIVIAL_EXCLUDED_ID = "3c71336db5b9fcd64ac6"
PREFIX_FUNCTION = "driver_authorizePayment(uint256,uint256,uint16)"
CAPTURE_PROPERTY_ID = "eebf858bb07972b2891e"
CAPTURE_FUNCTION = "driver_capturePayment(uint256,uint256,uint16)"
METHODS = ("native_echidna", "independent_dual", "random_batch_dual",
           "associated_dual", "associated_no_shared_prefix",
           "associated_no_execution_feedback")
BASE_SEED = 20261113
REPETITIONS = 2
MAX_GROUP_SIZE = 4
SEED_BUDGET = 4
TOKEN_BUDGET = 400_000
WALL_TIME_BUDGET_SECONDS = 240
ECHIDNA_TEST_LIMIT_PER_PROPERTY = 20
ECHIDNA_PROCESS_TIMEOUT_SECONDS = 40
MAX_SEQUENCE_STEPS = 6
MAX_AGENT_REPAIRS = 1


def _bare_property(property_context: dict[str, Any]) -> str:
    return property_context["property"].rsplit(".", 1)[-1].split("(", 1)[0]


def _selected_group() -> dict[str, Any]:
    group_data = read_json(GROUP_FILE)
    groups = group_data["projects"][PROJECT]["groups"]
    group = groups[GROUP_INDEX]
    group_ids = [member["property_id"] for member in group["members"]]
    if not set(PROPERTY_IDS).issubset(group_ids):
        raise ValueError("手工审核属性并非都来自注册的 Request 关联组")
    if len(PROPERTY_IDS) > MAX_GROUP_SIZE:
        raise ValueError("预注册属性数超过共享上下文组规模上限")
    return group


def _partition(ids: list[str], method: str, repetition: int) -> list[list[str]]:
    if method in {"associated_dual", "associated_no_shared_prefix",
                  "associated_no_execution_feedback"}:
        return [ids[i:i + MAX_GROUP_SIZE] for i in range(0, len(ids), MAX_GROUP_SIZE)]
    if method == "independent_dual":
        return [[property_id] for property_id in ids]
    if method == "random_batch_dual":
        arranged = list(ids)
        random.Random(BASE_SEED + repetition * 101).shuffle(arranged)
        return [arranged[i:i + 2] for i in range(0, len(arranged), 2)]
    return []


def _prefix_hint(ids: list[str], method: str, repetition: int,
                 batch_index: int) -> dict[str, Any] | None:
    if len(ids) < 2 or method in {"native_echidna", "independent_dual",
                                  "associated_no_shared_prefix"}:
        return None
    return {"prefix_id": f"{method}-r{repetition}-b{batch_index}",
            "property_ids": ids,
            "steps": [{"function": PREFIX_FUNCTION,
                       "rationale": "创建 paymentRef；capturePayment 在引用计数为零时直接返回"}],
            "evidence": "Request Harness 的 driver_capturePayment 对 paymentRefCounter==0 提前返回；授权入口提升该计数"}


def _sample_constraints(property_id: str) -> list[str]:
    if property_id == CAPTURE_PROPERTY_ID:
        return [
            "目标属性的真实多交易触发路径是 driver_authorizePayment 之后调用 driver_capturePayment；capturePayment 在 paymentRefCounter 为零时提前返回。",
            "capturePayment 的 paymentIndex 使用模 paymentRefCounter；本样本使用有效索引，captureAmount 不大于此前授权金额，feeBps 在 0 到 10000 之间。",
            "不要用 driver_chargePayment 单笔快捷路径替代 authorize→capture 两笔路径。",
        ]
    return ["候选序列至少两笔交易，并保留属性组提供的共同授权前缀。"]


def _audit_context(context: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["property_id"]: item for item in context["properties"]}
    if set(by_id) != set(PROPERTY_IDS):
        raise ValueError("测试输入属性集合与预注册集合不一致")
    expected_prefix = PREFIX_FUNCTION
    for property_id, prop in by_id.items():
        if not prop.get("property_predicate"):
            raise ValueError(f"属性谓词源码不可用：{property_id}")
        actions = {item.get("abi_signature") for item in prop.get("candidate_actions", [])
                   if item.get("seed_compatible")}
        if expected_prefix not in actions:
            raise ValueError(f"共同授权前缀不是属性 {property_id} 的可序列化候选入口")
    context["association_evidence"] = {
        "source_group_index": GROUP_INDEX,
        "shared_core": group.get("shared_core", {}),
        "selected_property_ids": PROPERTY_IDS,
        "selection_note": "从同一关联组中剔除 balance < type(uint256).max 的弱属性，保留四个余额/支付状态谓词。",
    }
    return {"selected_property_count": len(PROPERTY_IDS),
            "association_group_index": GROUP_INDEX,
            "association_group_size_before_filter": len(group.get("members", [])),
            "selected_property_ids": PROPERTY_IDS,
            "predicate_source_count": sum(bool(prop.get("property_predicate")) for prop in by_id.values()),
            "common_prefix_signature": expected_prefix,
            "common_prefix_candidate_count": len(PROPERTY_IDS)}


def _compact_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    usage_events = [event.get("usage", {}) for event in events if event.get("usage")]
    failures = [event for event in events if not event.get("ok")]
    return {
        "calls": len(events),
        "failed_calls": len(failures),
        "prompt_tokens": sum(int(item.get("prompt_tokens", 0)) for item in usage_events),
        "completion_tokens": sum(int(item.get("completion_tokens", 0)) for item in usage_events),
        "total_tokens": sum(int(item.get("total_tokens", 0)) for item in usage_events),
        "estimated_cost_usd_offpeak": sum(float(item.get("estimated_cost_usd", {}).get("offpeak", 0))
                                           for item in usage_events),
        "estimated_cost_usd_peak": sum(float(item.get("estimated_cost_usd", {}).get("peak", 0))
                                        for item in usage_events),
        "event_tags": [event.get("tag") for event in events],
        "errors": [{"tag": event.get("tag"), "kind": event.get("error_kind"),
                    "error": event.get("error")} for event in failures],
    }


def _candidate_for(context: dict[str, Any], raw: dict[str, Any], experiment_id: str,
                   method: str, repetition: int) -> dict[str, Any]:
    prop = next(item for item in context["properties"]
                if item["property_id"] == raw["property_id"])
    return {**raw,
            "candidate_id": f"cand-{experiment_id[:10]}-{method}-r{repetition}-{raw['property_id']}",
            "project": context["project"], "context": context,
            "property": prop["property"],
            "execution_constraints": _sample_constraints(raw["property_id"])}


def _execution_feedback(replay: dict[str, Any]) -> str:
    failed = next((tx for tx in replay.get("transactions", [])
                   if tx.get("status") != "success" or
                   tx.get("observed_effect_status") == "not_observed"), None)
    if failed:
        detail = {key: failed.get(key) for key in
                  ("index", "function", "arguments", "sender", "status", "error",
                   "property_error", "observed_effect_status", "expected_effect_states",
                   "observed_effect_states", "changed_effect_states", "execution_effect_error")}
    else:
        detail = {"replay_status": replay.get("replay_status"),
                  "environment": replay.get("environment"),
                  "deployment_status": replay.get("deployment_status"),
                  "error": replay.get("error")}
    return ("Anvil 已对完整交易序列进行真实回放，结果失败或未观察到 Slither 证据支持的状态写入。"
            "请保持函数顺序和已固定的共享前缀，"
            "只修复参数、发送者、金额或延迟；不要把失败候选当作有效种子。实际失败证据：" +
            json.dumps(detail, ensure_ascii=False)[:1800])


def _instantiate_and_replay(context: dict[str, Any], candidate: dict[str, Any], *,
                            session: AnvilSession, fixed_prefix: list[dict[str, Any]] | None,
                            feedback_enabled: bool, call_options: dict[str, Any]) -> tuple[
                                dict[str, Any] | None, dict[str, Any] | None,
                                list[dict[str, Any]], int, str | None]:
    events: list[dict[str, Any]] = []
    feedback = None
    schema_repairs = 0
    execution_repairs = 0
    attempts = 0
    concrete = None
    replay = None
    max_calls = 1 + MAX_AGENT_REPAIRS * 2
    while attempts < max_calls:
        attempts += 1
        try:
            concrete, event = instantiate_candidate(
                context, candidate, feedback=feedback, attempt=attempts,
                fixed_prefix_transactions=fixed_prefix,
                call_options=call_options)
            events.append(event)
        except DeepSeekCallError as exc:
            if exc.event:
                events.append(exc.event)
            if schema_repairs >= MAX_AGENT_REPAIRS:
                return None, None, events, execution_repairs, str(exc)[:1000]
            schema_repairs += 1
            feedback = ("上一次响应未通过交易结构或 ABI 本地校验，请只修复所列结构问题，保持原函数顺序。" +
                        str(exc))[:1600]
            continue
        try:
            replay = replay_seed(PROJECT, candidate, concrete["transactions"], session=session)
        except Exception as exc:
            replay = {"replay_status": "replay_failed", "transactions": [],
                      "deployment_status": "error", "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}
        if replay.get("replay_status") == "executable":
            return concrete, replay, events, execution_repairs, None
        if not feedback_enabled or execution_repairs >= MAX_AGENT_REPAIRS:
            break
        execution_repairs += 1
        feedback = _execution_feedback(replay)
    return concrete, replay, events, execution_repairs, None


def _classify_campaign(echidna: dict[str, Any], property_name: str,
                       seed_row: dict[str, Any] | None) -> None:
    failures = echidna.get("property_failures", [])
    initial_lines = [line for line in failures if "no transactions made" in line.lower()]
    non_initial_lines = [line for line in failures if "no transactions made" not in line.lower()]
    replay = (seed_row or {}).get("replay", {})
    target_violation = replay.get("target_property_violation")
    prevalidated_seed_violation = bool(target_violation and not target_violation.get("initial_state"))
    prevalidated_initial_violation = bool(target_violation and target_violation.get("initial_state"))
    echidna.update({
        "target_property": property_name,
        "initial_state_failure": bool(initial_lines),
        "initial_state_failure_lines": initial_lines,
        "prevalidated_initial_property_violation": prevalidated_initial_violation,
        "prevalidated_seed_property_violation": prevalidated_seed_violation,
        "non_initial_failures_not_prevalidated": non_initial_lines if not prevalidated_seed_violation else [],
        "failure_discovery_attribution": (
            "initial_state" if initial_lines else
            "prevalidated_seed" if prevalidated_seed_violation else
            "post_initial_fuzz_campaign" if non_initial_lines else "no_failure"),
    })


def _campaigns(context: dict[str, Any], method: str, repetition: int,
               condition_root: Path, seed_rows: list[dict[str, Any]],
               deadline: float) -> list[dict[str, Any]]:
    results = []
    by_property = {row["property_id"]: row for row in seed_rows}
    for index, property_context in enumerate(context["properties"], start=1):
        property_id = property_context["property_id"]
        property_name = _bare_property(property_context)
        campaign_root = condition_root / "echidna" / f"{index:02d}-{property_id}"
        coverage = campaign_root / "coverage"
        coverage.mkdir(parents=True, exist_ok=True)
        seed_row = by_property.get(property_id)
        source_file = (ROOT / seed_row["corpus_file"]
                       if seed_row and seed_row.get("corpus_file") else None)
        if source_file and source_file.is_file():
            shutil.copy2(source_file, coverage / source_file.name)
        if time.monotonic() >= deadline:
            results.append({"property_id": property_id, "property_name": property_name,
                            "status": "wall_time_budget_exhausted", "loaded_seed_count": 0})
            continue
        try:
            result = run_echidna(
                PROJECT, campaign_root, property_name=property_name,
                test_limit=ECHIDNA_TEST_LIMIT_PER_PROPERTY,
                timeout=ECHIDNA_PROCESS_TIMEOUT_SECONDS,
                seed=BASE_SEED + repetition,
                campaign_deadline=deadline)
            _classify_campaign(result, property_name, seed_row)
            result.update({"property_id": property_id,
                           "status": "completed",
                           "external_seed_id": seed_row.get("seed_id") if seed_row else None,
                           "external_seed_replay_status": seed_row.get("status") if seed_row else None})
            results.append(result)
        except Exception as exc:
            results.append({"property_id": property_id, "property_name": property_name,
                            "status": "campaign_failed",
                            "error": f"{type(exc).__name__}: {str(exc)[:1500]}"})
    return results


def _qualify_sample(context: dict[str, Any], experiment_id: str) -> dict[str, Any]:
    """在 API 对照前验证初始属性状态和预注册两笔路径。"""
    output_root = ROOT / "deepseek/结果/分组可信度修复实验" / experiment_id / "资格预检"
    output_root.mkdir(parents=True, exist_ok=False)
    fee_prop = next(item for item in context["properties"]
                    if item["property_id"] == CAPTURE_PROPERTY_ID)
    amount = 10**18
    candidate = {"candidate_id": f"qualification-{experiment_id[:10]}",
                 "property_id": CAPTURE_PROPERTY_ID,
                 "property": fee_prop["property"], "context": context}
    transactions = [
        {"function": PREFIX_FUNCTION, "arguments": [amount, amount, 0],
         "sender": SENDERS[0], "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0},
        {"function": CAPTURE_FUNCTION, "arguments": [0, amount, 1000],
         "sender": SENDERS[0], "value_wei": "0", "delay_seconds": 0, "delay_blocks": 0},
    ]
    replay = replay_seed(PROJECT, candidate, transactions)
    selected_names = {_bare_property(item) + "()" for item in context["properties"]}
    initial = {name: value for name, value in replay.get("initial_property_values", {}).items()
               if name in selected_names}
    if (replay.get("replay_status") != "executable" or len(replay.get("transactions", [])) != 2 or
            any(tx.get("status") != "success" for tx in replay.get("transactions", [])) or
            set(initial) != selected_names or any(value is not True for value in initial.values())):
        raise RuntimeError("Request 手工资格种子未能在 Anvil 中通过初始状态和逐笔回放检查")
    anvil_summary = {"replay_status": replay["replay_status"],
                     "initial_property_values": initial,
                     "transaction_functions": [tx["function"] for tx in replay["transactions"]],
                     "transaction_statuses": [tx["status"] for tx in replay["transactions"]],
                     "target_property_values": [tx.get("target_property") for tx in replay["transactions"]],
                     "environment": replay["environment"]}

    echidna_rows = []
    for index, prop in enumerate(context["properties"], start=1):
        name = _bare_property(prop)
        campaign_root = output_root / f"{index:02d}-{prop['property_id']}"
        (campaign_root / "coverage").mkdir(parents=True, exist_ok=True)
        result = run_echidna(PROJECT, campaign_root, property_name=name,
                             test_limit=1, timeout=30, seed=BASE_SEED)
        failed = bool(result.get("property_failures"))
        passing = any(line.startswith(name + ": passing")
                      for line in result.get("target_property_results", []))
        echidna_rows.append({"property_id": prop["property_id"], "property_name": name,
                             "exit_code": result.get("exit_code"),
                             "passing": passing, "initial_failure": bool(result.get("initial_state_failures")),
                             "loaded_seed_count": result.get("loaded_seed_count", 0),
                             "elapsed_seconds": result.get("elapsed_seconds"),
                             "result_lines": result.get("target_property_results", [])})
        if failed or not passing:
            raise RuntimeError(f"Echidna 初始状态资格检查失败：{name}")
    return {"anvil_two_transaction_path": anvil_summary,
            "echidna_empty_corpus_initial_checks": echidna_rows,
            "qualified": True,
            "excluded_weak_property": {"property_id": TRIVIAL_EXCLUDED_ID,
                                       "source_reason": "返回 merchant balance < type(uint256).max，未保留为研究目标。"}}


def run_condition(context: dict[str, Any], group: dict[str, Any], *,
                  experiment_id: str, method: str, repetition: int) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + WALL_TIME_BUDGET_SECONDS
    condition_root = ROOT / "deepseek/结果/分组可信度修复实验" / experiment_id / f"{method}-r{repetition}"
    condition_root.mkdir(parents=True, exist_ok=False)
    api_log = condition_root / "api调用.jsonl"
    budget = CallBudget(TOKEN_BUDGET, deadline_monotonic=deadline)
    call_options = {"budget": budget, "log_path": api_log,
                    "timeout": 120, "max_retries": 1}
    batches = ([] if method == "native_echidna" else
               _partition(PROPERTY_IDS, method, repetition))
    audited_batches = ([PROPERTY_IDS] if method == "native_echidna" else batches)
    audit = {"property_ids": PROPERTY_IDS, "input_count": len(PROPERTY_IDS),
             "batch_sizes": [len(batch) for batch in audited_batches],
             "max_group_size": MAX_GROUP_SIZE,
             "exact_cover": sorted([item for batch in audited_batches for item in batch]) == sorted(PROPERTY_IDS)}
    if not audit["exact_cover"]:
        raise ValueError("分组策略未覆盖完全相同且唯一的属性集合")

    a_events: list[dict[str, Any]] = []
    b_events: list[dict[str, Any]] = []
    batch_rows: list[dict[str, Any]] = []
    candidates_by_property: dict[str, dict[str, Any]] = {}
    for batch_index, batch_ids in enumerate(batches, start=1):
        if time.monotonic() >= deadline:
            batch_rows.append({"batch_index": batch_index, "property_ids": batch_ids,
                               "status": "wall_time_budget_exhausted"})
            continue
        batch_context = load_project_context(PROJECT, batch_ids)
        batch_context["association_evidence"] = context.get("association_evidence", {})
        batch_context["association_group_members"] = batch_ids
        prefix_hint = _prefix_hint(batch_ids, method, repetition, batch_index)
        constraints = [rule for property_id in batch_ids for rule in _sample_constraints(property_id)]
        try:
            output, event = generate_candidates(
                batch_context, max_candidates=1, max_steps=MAX_SEQUENCE_STEPS,
                min_steps=2,
                use_shared_prefixes=method != "associated_no_shared_prefix",
                shared_prefix_hint=prefix_hint,
                task_constraints=constraints,
                tag=f"AgentA_{experiment_id[:10]}_{method}_r{repetition}_b{batch_index}",
                call_options=call_options)
            a_events.append(event)
            rows = output.get("property_sequences", [])
            for row in rows:
                row["batch_id"] = batch_index
                row["execution_constraints"] = _sample_constraints(row["property_id"])
                candidates_by_property.setdefault(row["property_id"], row)
            initially_valid_ids = {row["property_id"] for row in rows}
            missing_ids = [property_id for property_id in batch_ids
                           if property_id not in initially_valid_ids]
            recovery = {"requested_property_ids": missing_ids,
                        "status": "not_needed" if not missing_ids else "pending",
                        "invalid_records": output.get("invalid_records", [])}
            if missing_ids and time.monotonic() < deadline:
                try:
                    recovery_context = load_project_context(PROJECT, missing_ids)
                    recovery_context["association_evidence"] = context.get("association_evidence", {})
                    recovery_context["association_group_members"] = batch_ids
                    recovery_hint = None
                    if prefix_hint and len(missing_ids) >= 2:
                        recovery_hint = {**prefix_hint,
                                         "prefix_id": f"{prefix_hint['prefix_id']}-local-recovery",
                                         "property_ids": missing_ids}
                    recovery_constraints = [
                        constraint for property_id in missing_ids
                        for constraint in _sample_constraints(property_id)]
                    recovery_constraints.append(
                        "局部恢复请求：只为本次输入中的属性分别给出有效候选；不要输出已成功属性或其他属性的记录。"
                    )
                    recovered, recovery_event = generate_candidates(
                        recovery_context, max_candidates=1, max_steps=MAX_SEQUENCE_STEPS,
                        min_steps=2,
                        use_shared_prefixes=method != "associated_no_shared_prefix",
                        shared_prefix_hint=recovery_hint,
                        task_constraints=recovery_constraints,
                        tag=(f"AgentA_{experiment_id[:10]}_{method}_r{repetition}_"
                             f"b{batch_index}_local_recovery"),
                        call_options=call_options)
                    a_events.append(recovery_event)
                    recovered_rows = recovered.get("property_sequences", [])
                    for row in recovered_rows:
                        row["batch_id"] = batch_index
                        row["local_recovery_attempt"] = 1
                        row["execution_constraints"] = _sample_constraints(row["property_id"])
                        candidates_by_property.setdefault(row["property_id"], row)
                    recovered_ids = {row["property_id"] for row in recovered_rows}
                    recovery.update({"status": "completed",
                                     "recovered_property_ids": sorted(recovered_ids),
                                     "invalid_records": recovered.get("invalid_records", []),
                                     "applied_shared_prefixes": recovered.get(
                                         "applied_shared_prefixes", [])})
                except DeepSeekCallError as exc:
                    if exc.event:
                        a_events.append(exc.event)
                    recovery.update({"status": "failed",
                                     "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
                except Exception as exc:
                    recovery.update({"status": "failed",
                                     "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
            elif missing_ids:
                recovery["status"] = "budget_exhausted"
            batch_rows.append({"batch_index": batch_index, "property_ids": batch_ids,
                               "status": "completed",
                               "candidate_property_ids": sorted(
                                   property_id for property_id in batch_ids
                                   if property_id in candidates_by_property),
                               "candidate_count": sum(property_id in candidates_by_property
                                                      for property_id in batch_ids),
                               "invalid_records": output.get("invalid_records", []),
                               "raw_shared_prefix_count": len(output.get("shared_prefixes", [])),
                               "applied_shared_prefixes": output.get("applied_shared_prefixes", []),
                               "local_recovery": recovery,
                               "prefix_hint": prefix_hint})
        except DeepSeekCallError as exc:
            if exc.event:
                a_events.append(exc.event)
            batch_rows.append({"batch_index": batch_index, "property_ids": batch_ids,
                               "status": "agent_a_failed", "error": str(exc)[:1200]})

    seed_rows: list[dict[str, Any]] = []
    prefix_instances: dict[str, list[dict[str, Any]]] = {}
    repair_counts: dict[str, int] = {}
    feedback_enabled = method != "associated_no_execution_feedback"
    seed_bundle = condition_root / "种子包"
    seed_bundle.mkdir(parents=True, exist_ok=True)
    with AnvilSession() as session:
        for property_id in PROPERTY_IDS:
            prop = next(item for item in context["properties"] if item["property_id"] == property_id)
            property_signature = prop["property"]
            raw = candidates_by_property.get(property_id)
            if not raw:
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "status": ("native_baseline_no_external_seed"
                                             if method == "native_echidna"
                                             else "agent_a_no_valid_candidate")})
                continue
            if sum(row.get("seed_id") is not None for row in seed_rows) >= SEED_BUDGET:
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "status": "seed_budget_exhausted"})
                continue
            candidate = _candidate_for(context, raw, experiment_id, method, repetition)
            prefix_id = candidate.get("shared_prefix_id")
            prefix_steps = candidate.get("shared_prefix_steps") or []
            fixed_prefix = prefix_instances.get(prefix_id) if prefix_id else None
            concrete, replay, events, repairs, error = _instantiate_and_replay(
                context, candidate, session=session, fixed_prefix=fixed_prefix,
                feedback_enabled=feedback_enabled, call_options=call_options)
            b_events.extend(events)
            repair_counts[property_id] = repairs
            if concrete is None:
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "candidate_id": candidate["candidate_id"],
                                  "plan": candidate["steps"], "status": "agent_b_failed",
                                  "error": error})
                continue
            replay_ok = replay and replay.get("replay_status") == "executable"
            seed_id = None
            corpus_file = None
            status = "executable" if replay_ok else "replay_failed"
            if replay_ok:
                seed_id = new_seed_id()
                path = write_corpus(PROJECT, candidate, concrete["transactions"], context,
                                    seed_bundle, replay=replay, seed_id=seed_id)
                corpus_file = str(path.relative_to(ROOT))
                if prefix_id and prefix_steps and prefix_id not in prefix_instances:
                    prefix_instances[prefix_id] = concrete["transactions"][:len(prefix_steps)]
            seed_rows.append({"property_id": property_id, "property": property_signature,
                              "candidate_id": candidate["candidate_id"], "seed_id": seed_id,
                              "plan": candidate["steps"], "seed": concrete,
                              "replay": replay, "corpus_file": corpus_file,
                              "status": status, "shared_prefix_id": prefix_id,
                              "fixed_shared_prefix_used": bool(fixed_prefix),
                              "shared_prefix_transaction_count": len(prefix_steps),
                              "real_execution_repairs": repairs})

    echidna_runs = _campaigns(context, method, repetition, condition_root, seed_rows, deadline)
    valid_seeds = [row for row in seed_rows if row.get("status") == "executable"]
    prefix_reuse = {}
    for prefix_id, txs in prefix_instances.items():
        members = [row for row in seed_rows if row.get("shared_prefix_id") == prefix_id]
        prefix_reuse[prefix_id] = {
            "member_property_ids": [row["property_id"] for row in members],
            "instantiated_transaction": txs,
            "generated_candidate_count": len(members),
            "reused_after_leader": sum(bool(row.get("fixed_shared_prefix_used")) for row in members),
        }
    actual_api = _compact_events(a_events + b_events)
    api_summary = {**actual_api,
                   "budget_ceiling_tokens": TOKEN_BUDGET,
                   "budget_preflight_charged_tokens": budget.spent_tokens,
                   "budget_calls": budget.calls,
                   "wall_time_budget_seconds": WALL_TIME_BUDGET_SECONDS,
                   "actual_condition_wall_seconds": round(time.monotonic() - started, 3)}
    return {
        "project": PROJECT, "method": method, "repetition": repetition,
        "property_ids": PROPERTY_IDS, "batch_sizes": audit["batch_sizes"],
        "partition_audit": audit, "batches": batch_rows,
        "agent_a_candidate_property_ids": sorted(candidates_by_property),
        "agent_a": _compact_events(a_events), "agent_b": _compact_events(b_events),
        "api_budget": api_summary,
        "seed_budget": {"maximum": SEED_BUDGET, "valid_seed_count": len(valid_seeds),
                        "failed_or_missing_candidates": (0 if method == "native_echidna"
                                                         else len(PROPERTY_IDS) - len(valid_seeds))},
        "seed_candidates": seed_rows,
        "shared_prefix_reuse": prefix_reuse,
        "execution_repair_counts": repair_counts,
        "echidna": echidna_runs,
        "corpus_root": str(condition_root.relative_to(ROOT)),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "condition_status": "completed" if time.monotonic() < deadline else "wall_time_budget_reached",
    }


def run_experiment(repetitions: int = REPETITIONS) -> dict[str, Any]:
    if sys.version_info < (3, 11):
        raise RuntimeError("实验需要 Python 3.11；请使用 contract-fuzz Conda 环境。")
    if not 1 <= repetitions <= 3:
        raise ValueError("本次小规模对照限制为 1 到 3 次重复")
    group = _selected_group()
    context = load_project_context(PROJECT, PROPERTY_IDS)
    preflight = _audit_context(context, group)
    experiment_id = uuid.uuid4().hex
    qualification = _qualify_sample(context, experiment_id)
    started = time.monotonic()
    runs = []
    for repetition in range(1, repetitions + 1):
        for method in METHODS:
            result = run_condition(context, group, experiment_id=experiment_id,
                                   method=method, repetition=repetition)
            runs.append(result)
            print(json.dumps({"method": method, "repetition": repetition,
                              "valid_seeds": result["seed_budget"]["valid_seed_count"],
                              "api_tokens": result["api_budget"]["total_tokens"],
                              "prefix_reuses": sum(row["reused_after_leader"]
                                                    for row in result["shared_prefix_reuse"].values()),
                              "elapsed_seconds": result["elapsed_seconds"]}, ensure_ascii=False), flush=True)
    return {
        "schema_version": 2, "experiment_id": experiment_id,
        "model": "deepseek-flash", "model_thinking": "disabled",
        "python_version": sys.version.split()[0],
        "project": PROJECT, "association_group_index": GROUP_INDEX,
        "property_ids": PROPERTY_IDS,
        "excluded_property": {"property_id": TRIVIAL_EXCLUDED_ID,
                              "reason": "echidna_merchant_receives_nonnegative 仅检查余额小于 uint256 最大值，语义过弱，预先排除。"},
        "sample_preflight": preflight,
        "sample_qualification": qualification,
        "budget": {"api_token_ceiling_per_condition": TOKEN_BUDGET,
                   "wall_time_ceiling_seconds_per_condition": WALL_TIME_BUDGET_SECONDS,
                   "valid_seed_ceiling_per_condition": SEED_BUDGET,
                   "echidna_test_limit_per_property": ECHIDNA_TEST_LIMIT_PER_PROPERTY,
                   "echidna_target_properties_per_condition": len(PROPERTY_IDS),
                   "max_group_size": MAX_GROUP_SIZE},
        "environment_alignment": {
            "anvil": {"chain_id": 1, "initial_timestamp": 1524785992,
                      "initial_block_number": 4370000, "hardfork": "shanghai",
                      "deployer": "0x0000000000000000000000000000000000030000",
                      "contract_address": HARNESS_ADDRESS.lower(),
                      "property_sender": PROPERTY_SENDER.lower(),
                      "sender_pool": [sender.lower() for sender in SENDERS],
                      "account_balance_wei": 0xffffffff,
                      "gas_price_wei": 0, "gas_limit_per_transaction": 12500000},
            "echidna": {"version": "2.3.2", "chain_id": 1,
                        "initial_timestamp": 1524785992,
                        "initial_block_number": 4370000,
                        "deployer": "0x0000000000000000000000000000000000030000",
                        "contract_address": HARNESS_ADDRESS.lower(),
                        "property_sender": PROPERTY_SENDER.lower(),
                        "sender_pool": [sender.lower() for sender in SENDERS],
                        "account_balance_wei": 0xffffffff,
                        "gas_price_wei": 0,
                        "gas_limit_per_transaction": 12500000,
                        "max_time_delay_seconds": 86400,
                        "max_block_delay": 86400,
                        "initial_time_and_block_source": "Echidna 2.3.2 deterministic runtime defaults",
                        "initial_time_and_block_configurable": False,
                        "evm_hardfork_explicitly_configurable": False},
            "alignment_check": "Anvil deployment block/time/address and four property initial values were checked before every formal experiment.",
        },
        "repetitions": repetitions, "methods": list(METHODS), "runs": runs,
        "total_elapsed_seconds": round(time.monotonic() - started, 3),
        "limitations": [
            "这是一个经过源码审阅的单项目小规模方向实验，不足以支持跨项目泛化结论。",
            "共享授权前缀是基于本样本的 Slither 候选关系和人工审阅的 capture 守卫预注册；实验检验其复用闭环，不把前缀发现能力本身计为 Agent 成果。",
            "每个条件最多为四条属性各生成一个候选；失败候选消耗预算但不进入 Echidna 语料。",
            "属性测试按 exact property 前缀拆分运行，每条属性获得相同 Echidna test-limit；这是为了保留初始状态与属性失败归因。",
            "结果应视为小规模可行性和方向筛选证据，不能单独得出统计显著性结论。",
        ],
    }


def main() -> None:
    report = run_experiment()
    output = ROOT / "deepseek/结果/DeepSeek分组可信度修复实验.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "experiment_id": report["experiment_id"],
                      "runs": len(report["runs"]),
                      "total_elapsed_seconds": report["total_elapsed_seconds"]},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
