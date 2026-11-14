#!/usr/bin/env python3
"""以固定属性和预算比较无人工路径提示的属性种子生成。"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from AgentA import generate_candidates
from AgentB import instantiate_candidate, to_echidna_sequence
from deepseek接口 import CallBudget, DeepSeekCallError
from 属性种子上下文 import PROJECTS, compact_for_agent, load_project_context, read_json
from 种子验证 import (AnvilSession, echidna_corpus_evidence, new_seed_id,
                     replay_seed, run_echidna, write_corpus)


RESULT_DIR = ROOT / "deepseek/结果/自主种子质量实验"
BASE_SEED = 20261114
TOKEN_BUDGET = 600_000
WALL_BUDGET_SECONDS = 600
ECHIDNA_TEST_LIMIT = 80
ECHIDNA_SEQ_LEN = 8
MAX_GROUP_SIZE = 4
GROUPING_REPETITIONS = 10

# 固定于正式方法调用之前的集合；不根据模型响应或反例结果筛选。
DATASETS: dict[str, list[str]] = {
    "Immutable": [
        "68b39b8ed81f3c0438b7",  # transfer ownership / minted token state
        "a9d9745dffe4118dcc3a",  # multi-operation transfer sequence
        "b4852acf51c51850beb2",  # approval clearing
        "da82f4664fd60ab2be02",  # group operations / bounded repeats
        "6771d7d5854995818cc4",  # group boundary sequence
        "f7d424efa6fd80610b3d",  # maximum token-id boundary
    ],
    "BeeStorage": ["a11cc51249256da90a47"],  # commit / reveal; bytes32
    "Drips": ["6e7899beaef22d4a3a87"],  # time/history sequence with a known counterexample
}
MATRIX_METHODS = ("independent", "random_batch", "associated",
                  "associated_no_prefix", "associated_no_feedback")


def _selected_report(project: str, property_ids: list[str]) -> dict[str, Any]:
    report = read_json(PROJECTS[project]["report"])
    by_id = {prop["property_id"]: prop for prop in report["properties"]}
    missing = sorted(set(property_ids) - set(by_id))
    if missing:
        raise ValueError(f"{project} 属性报告缺少固定样本：{missing}")
    return {**report, "properties": [by_id[pid] for pid in property_ids]}


def _groups_from_result(result: dict[str, Any]) -> list[list[str]]:
    groups = [[member["property_id"] for member in group["members"]]
              for group in result["groups"]]
    bounded: list[list[str]] = []
    for group in groups:
        bounded.extend([group[i:i + MAX_GROUP_SIZE]
                        for i in range(0, len(group), MAX_GROUP_SIZE)])
    return bounded


def _partition(project: str, property_ids: list[str], method: str,
               associated: list[list[str]], repetition: int) -> list[list[str]]:
    if method == "independent":
        return [[pid] for pid in property_ids]
    if method in {"associated", "associated_no_prefix", "associated_no_feedback"}:
        return [list(group) for group in associated]
    if method == "random_batch":
        sizes = [len(group) for group in associated]
        arranged = list(property_ids)
        rng = random.Random(BASE_SEED + repetition * 1009 + sum(map(ord, project)))
        rng.shuffle(arranged)
        batches, offset = [], 0
        for size in sizes:
            batches.append(arranged[offset:offset + size])
            offset += size
        return batches
    raise ValueError(f"未知方法：{method}")


def _event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [event.get("usage") for event in events if event.get("usage")]
    return {
        "calls": len(events),
        "failed_calls": sum(not event.get("ok", False) for event in events),
        "prompt_tokens": sum(item.get("prompt_tokens", 0) for item in measured),
        "completion_tokens": sum(item.get("completion_tokens", 0) for item in measured),
        "total_tokens": sum(item.get("total_tokens", 0) for item in measured),
        "estimated_cost_usd_offpeak": round(sum(
            float(item["estimated_cost_usd"]["offpeak"]) for item in measured), 8),
        "estimated_cost_usd_peak": round(sum(
            float(item["estimated_cost_usd"]["peak"]) for item in measured), 8),
        "elapsed_seconds": round(sum(event.get("elapsed_seconds", 0) for event in events), 4),
        "events": [{key: event.get(key) for key in
                    ("tag", "ok", "error_kind", "error", "usage", "elapsed_seconds",
                     "prompt_utf8_bytes", "local_context_dedup_seconds",
                     "prompt_json_encoding_seconds",
                     "applied_shared_prefix_count", "invalid_record_count")}
                   for event in events],
    }


def _candidate_context(raw: dict[str, Any], context: dict[str, Any], method: str,
                       repetition: int, batch_index: int) -> dict[str, Any]:
    prop = next(item for item in context["properties"]
                if item["property_id"] == raw["property_id"])
    return {**raw,
            "candidate_id": f"{method}-r{repetition}-b{batch_index}-{raw['candidate_id']}",
            "project": context["project"], "context": context,
            "property": prop["property"]}


def _repair_agent_b(context: dict[str, Any], candidate: dict[str, Any], budget: CallBudget,
                    fixed_prefix: list[dict[str, Any]] | None,
                    api_log: Path,
                    max_attempts: int = 2) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    feedback = None
    events: list[dict[str, Any]] = []
    for attempt in range(1, max_attempts + 1):
        try:
            concrete, event = instantiate_candidate(
                context, candidate, feedback=feedback, attempt=attempt,
                fixed_prefix_transactions=fixed_prefix,
                call_options={"budget": budget, "log_path": api_log})
            events.append(event)
            return concrete, events
        except DeepSeekCallError as exc:
            if exc.event:
                events.append(exc.event)
            if attempt >= max_attempts:
                raise
            feedback = ("上次返回未通过本地参数或交易结构校验；保持同一函数顺序，"
                        f"根据错误修正：{str(exc)}")[:1200]
    raise AssertionError("Agent B 的有限修正循环意外结束")


def _property_short_name(prop: dict[str, Any]) -> str:
    return prop["property"].rsplit(".", 1)[-1].split("(", 1)[0]


def _run_echidna_target(project: str, prop: dict[str, Any], campaign_root: Path,
                        seed: int, deadline: float) -> dict[str, Any]:
    campaign_root.parent.mkdir(parents=True, exist_ok=True)
    remaining = int(deadline - time.monotonic())
    if remaining <= 0:
        return {"status": "time_budget_exhausted", "property_id": prop["property_id"]}
    name = _property_short_name(prop)
    test_mode = "property" if name.startswith("echidna_") else "assertion"
    try:
        result = run_echidna(
            project, campaign_root, property_name=name,
            test_limit=ECHIDNA_TEST_LIMIT, timeout=min(45, remaining), seed=seed,
            test_mode=test_mode,
            property_prefix="echidna_" if test_mode == "assertion" else name,
            seq_len=ECHIDNA_SEQ_LEN, disable_slither=False)
        evidence = echidna_corpus_evidence(result.get("output", ""))
        return {
            "status": "completed", "property_id": prop["property_id"],
            "property": prop["property"], "test_mode": test_mode,
            "exit_code": result.get("exit_code"),
            "elapsed_seconds": result.get("elapsed_seconds"),
            "test_limit": ECHIDNA_TEST_LIMIT, "seq_len": ECHIDNA_SEQ_LEN,
            **evidence,
            "target_property_results": result.get("target_property_results", []),
            "property_failures": result.get("property_failures", []),
            "initial_state_failures": result.get("initial_state_failures", []),
            "output": result.get("output", "")[-9000:],
        }
    except Exception as exc:
        return {"status": "echidna_error", "property_id": prop["property_id"],
                "property": prop["property"],
                "error": f"{type(exc).__name__}: {str(exc)[:1000]}"}


def _run_agent_condition(project: str, property_ids: list[str], full_context: dict[str, Any],
                         associated: list[list[str]], method: str, repetition: int,
                         temp_root: Path, grouping_ms: float,
                         api_log: Path, seed_archive_root: Path) -> dict[str, Any]:
    started = time.monotonic()
    deadline = started + WALL_BUDGET_SECONDS
    budget = CallBudget(TOKEN_BUDGET, deadline_monotonic=deadline)
    batches = _partition(project, property_ids, method, associated, repetition)
    flattened = [pid for batch in batches for pid in batch]
    if sorted(flattened) != sorted(property_ids) or len(flattened) != len(set(flattened)):
        raise ValueError("方法分组没有完整且唯一覆盖固定属性集合")

    a_events: list[dict[str, Any]] = []
    b_events: list[dict[str, Any]] = []
    batch_contexts: dict[int, dict[str, Any]] = {}
    candidates: list[tuple[int, dict[str, Any]]] = []
    batch_rows = []
    use_prefix = method != "associated_no_prefix"
    execution_feedback = method != "associated_no_feedback"
    for batch_index, batch in enumerate(batches, start=1):
        if time.monotonic() >= deadline:
            batch_rows.append({"batch_index": batch_index, "property_ids": batch,
                               "status": "time_budget_exhausted"})
            continue
        try:
            batch_context = load_project_context(project, batch)
            batch_contexts[batch_index] = batch_context
            plan, event = generate_candidates(
                batch_context, max_candidates=1, max_steps=8, min_steps=1,
                use_shared_prefixes=use_prefix,
                tag=f"AgentA_{project}_{method}_r{repetition}_b{batch_index}",
                # 正式条件刻意不传人工属性约束、交易路径或预注册共享前缀。
                call_options={"budget": budget, "log_path": api_log})
            a_events.append(event)
            rows = plan.get("property_sequences", [])
            candidates.extend((batch_index, row) for row in rows)
            batch_rows.append({
                "batch_index": batch_index, "property_ids": batch,
                "candidate_property_ids": [row["property_id"] for row in rows],
                "candidate_count": len(rows),
                "planned_shared_prefixes": plan.get("shared_prefixes", []),
                "applied_shared_prefixes": plan.get("applied_shared_prefixes", []),
                "invalid_records": plan.get("invalid_records", []), "status": "completed"})
        except DeepSeekCallError as exc:
            if exc.event:
                a_events.append(exc.event)
            batch_rows.append({"batch_index": batch_index, "property_ids": batch,
                               "status": "agent_a_error", "error": str(exc)[:1200]})

    candidate_by_property = {row["property_id"]: (batch_index, row)
                             for batch_index, row in candidates}
    seed_rows: list[dict[str, Any]] = []
    prefix_transactions: dict[tuple[int, str], list[dict[str, Any]]] = {}
    seed_pack_root = temp_root / "seed-packs" / project / f"{method}-r{repetition}"
    seed_pack_root.mkdir(parents=True, exist_ok=True)

    try:
        anvil = AnvilSession()
        anvil.__enter__()
    except Exception as exc:
        anvil = None
        anvil_error = f"{type(exc).__name__}: {str(exc)[:800]}"
    else:
        anvil_error = None

    if anvil is not None:
        try:
            # 候选按属性集合中的固定顺序处理，使共享前缀的首个具体实例可复用。
            for property_id in property_ids:
                if time.monotonic() >= deadline:
                    seed_rows.append({"property_id": property_id, "status": "time_budget_exhausted"})
                    continue
                found = candidate_by_property.get(property_id)
                if not found:
                    seed_rows.append({"property_id": property_id, "status": "agent_a_no_candidate"})
                    continue
                batch_index, raw = found
                context = batch_contexts[batch_index]
                candidate = _candidate_context(raw, context, method, repetition, batch_index)
                prefix_id = candidate.get("shared_prefix_id")
                prefix_len = len(candidate.get("shared_prefix_steps", []))
                prefix_key = (batch_index, str(prefix_id)) if prefix_id and prefix_len else None
                fixed_prefix = prefix_transactions.get(prefix_key) if prefix_key else None
                attempts: list[dict[str, Any]] = []
                replay = None
                concrete = None
                status = "candidate_error"
                try:
                    concrete, events = _repair_agent_b(
                        context, candidate, budget, fixed_prefix, api_log,
                        # 所有方案都保留相同的本地 ABI/JSON 修复；消融只关闭
                        # 真实 EVM 回放失败后的参数/环境反馈调用。
                        max_attempts=2)
                    b_events.extend(events)
                    attempts.extend(events)
                    replay = replay_seed(project, candidate, concrete["transactions"], session=anvil)
                    if replay.get("replay_status") != "executable" and execution_feedback:
                        tx_errors = [item for item in replay.get("transactions", [])
                                     if item.get("status") != "success" or
                                     item.get("observed_effect_status") == "not_observed"]
                        feedback = "逐交易 EVM 回放失败；请只修正参数、sender、金额或延迟，保留既定函数顺序。证据：" + json.dumps(
                            tx_errors[:4], ensure_ascii=False)[:1800]
                        try:
                            repaired, event = instantiate_candidate(
                                context, candidate, feedback=feedback, attempt=3,
                                fixed_prefix_transactions=fixed_prefix,
                                call_options={"budget": budget, "log_path": api_log})
                            b_events.append(event)
                            attempts.append(event)
                            repaired_replay = replay_seed(
                                project, candidate, repaired["transactions"], session=anvil)
                            concrete, replay = repaired, repaired_replay
                        except DeepSeekCallError as exc:
                            if exc.event:
                                b_events.append(exc.event)
                            attempts.append(exc.event or {"ok": False, "error": str(exc)})
                    status = replay.get("replay_status", "replay_failed")
                    seed_id = None
                    corpus_file = None
                    if status == "executable":
                        seed_id = new_seed_id()
                        corpus_file = write_corpus(
                            project, candidate, concrete["transactions"], context,
                            seed_pack_root, replay=replay, seed_id=seed_id)
                    prefix_replay = None
                    if prefix_key and fixed_prefix is None and concrete and prefix_len <= len(concrete["transactions"]):
                        prefix_replay = replay_seed(
                            project, candidate, concrete["transactions"][:prefix_len], session=anvil)
                        if prefix_replay.get("replay_status") == "executable":
                            prefix_transactions[prefix_key] = concrete["transactions"][:prefix_len]
                    seed_rows.append({
                        "property_id": property_id, "property": candidate["property"],
                    "batch_index": batch_index,
                        "candidate_id": candidate["candidate_id"], "seed_id": seed_id,
                        "status": status, "plan": candidate["steps"],
                        "planned_step_count": len(candidate["steps"]),
                        "concrete_transactions": concrete.get("transactions") if concrete else None,
                        "replay": replay, "corpus_file": str(corpus_file) if corpus_file else None,
                        "shared_prefix_id": prefix_id,
                        "shared_prefix_transactions_reused": len(fixed_prefix or []),
                        "shared_prefix_replay": prefix_replay,
                        "agent_b_attempts": attempts,
                    })
                except Exception as exc:
                    if isinstance(exc, DeepSeekCallError) and exc.event:
                        b_events.append(exc.event)
                    seed_rows.append({"property_id": property_id,
                                      "property": candidate["property"],
                                      "batch_index": batch_index,
                                      "candidate_id": candidate["candidate_id"],
                                      "status": status,
                                      "error": f"{type(exc).__name__}: {str(exc)[:1200]}",
                                      "planned_step_count": len(candidate["steps"]),
                                      "plan": candidate["steps"],
                                      "concrete_transactions": (concrete.get("transactions")
                                                                if concrete else None),
                                      "agent_b_attempts": attempts})
        finally:
            anvil.__exit__(None, None, None)
    else:
        seed_rows = [{"property_id": pid, "status": "anvil_unavailable",
                      "error": anvil_error} for pid in property_ids]

    by_id = {prop["property_id"]: prop for prop in full_context["properties"]}
    echidna_rows = []
    for property_index, property_id in enumerate(property_ids, start=1):
        if time.monotonic() >= deadline:
            echidna_rows.append({"property_id": property_id, "status": "time_budget_exhausted"})
            continue
        prop = by_id[property_id]
        campaign_root = temp_root / "campaigns" / project / f"{method}-r{repetition}" / property_id
        coverage = campaign_root / "coverage"
        coverage.mkdir(parents=True, exist_ok=True)
        row = next((item for item in seed_rows if item.get("property_id") == property_id), {})
        if row.get("status") == "executable" and row.get("corpus_file"):
            archived_file = seed_archive_root / f"{row['seed_id']}.txt"
            archived_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(row["corpus_file"], archived_file)
            shutil.copy2(archived_file, coverage / f"{row['seed_id']}.txt")
            row["corpus_file"] = str(archived_file.relative_to(ROOT))
        elif row.get("concrete_transactions"):
            # Drips 的 Anvil harness 部署路径不兼容；保留错误归因，同时直接用
            # 完整 ABI 交易在 Echidna 2.3.2 中做原生语料回放验证。
            batch_context = batch_contexts[row["batch_index"]]
            candidate = {"candidate_id": row["candidate_id"],
                         "property_id": property_id, "steps": row["plan"]}
            sequence = to_echidna_sequence(candidate, row["concrete_transactions"], batch_context)
            seed_id = row.get("seed_id") or new_seed_id()
            row["seed_id"] = seed_id
            row["echidna_only_seed_submission"] = True
            archived_file = seed_archive_root / f"{seed_id}.txt"
            archived_file.parent.mkdir(parents=True, exist_ok=True)
            encoded = json.dumps(sequence, ensure_ascii=False)
            archived_file.write_text(encoded, encoding="utf-8")
            (coverage / f"{seed_id}.txt").write_text(encoded, encoding="utf-8")
            row["corpus_file"] = str(archived_file.relative_to(ROOT))
        result = _run_echidna_target(project, prop, campaign_root,
                                     BASE_SEED + repetition * 101 + property_index, deadline)
        result["input_seed_count"] = int(bool(
            row.get("status") == "executable" or row.get("echidna_only_seed_submission")))
        echidna_rows.append(result)

    elapsed = time.monotonic() - started
    return {
        "project": project, "method": method, "repetition": repetition,
        "property_ids": property_ids, "batches": batches, "batch_records": batch_rows,
        "model_prompt_policy": {"manual_task_constraints": False,
                                 "pre_registered_prefix_hint": False,
                                 "argument_templates": False,
                                 "max_candidates_per_property": 1},
        "budgets": {"model_tokens": TOKEN_BUDGET, "wall_seconds": WALL_BUDGET_SECONDS,
                    "seed_slots": len(property_ids), "echidna_test_limit_per_property": ECHIDNA_TEST_LIMIT,
                    "echidna_seq_len": ECHIDNA_SEQ_LEN},
        "budget_usage": {"spent_tokens": budget.spent_tokens, "calls": budget.calls,
                         "remaining_tokens": budget.max_tokens - budget.spent_tokens,
                         "wall_seconds_used": round(elapsed, 3),
                         "wall_seconds_remaining": max(0, round(WALL_BUDGET_SECONDS - elapsed, 3))},
        "grouping_preprocessing_median_ms_in_total_cost": round(grouping_ms, 6)
        if method.startswith("associated") or method == "random_batch" else 0,
        "agent_a": _event_summary(a_events), "agent_b": _event_summary(b_events),
        "seeds": seed_rows, "echidna": echidna_rows,
        "effective_successful_state_transitions": sum(
            tx.get("status") == "success" and tx.get("observed_view_state_changed")
            for row in seed_rows for tx in (row.get("replay") or {}).get("transactions", [])),
        "effective_slither_evidenced_transitions": sum(
            tx.get("status") == "success" and tx.get("observed_effect_status") == "observed"
            for row in seed_rows for tx in (row.get("replay") or {}).get("transactions", [])),
        "unknown_effect_transition_count": sum(
            tx.get("status") == "success" and tx.get("observed_effect_status") == "unknown"
            for row in seed_rows for tx in (row.get("replay") or {}).get("transactions", [])),
        "valid_evm_seed_count": sum(row.get("status") == "executable" for row in seed_rows),
        "agent_a_applied_shared_prefix_count": sum(
            len(batch.get("applied_shared_prefixes", [])) for batch in batch_rows),
        "shared_prefix_transactions_reused": sum(
            row.get("shared_prefix_transactions_reused", 0) for row in seed_rows),
        "shared_prefix_seed_reuse_count": sum(
            row.get("shared_prefix_transactions_reused", 0) > 0 for row in seed_rows),
        "echidna_only_seed_submission_count": sum(
            bool(row.get("echidna_only_seed_submission")) for row in seed_rows),
        "multi_transaction_seed_count": sum(
            row.get("status") == "executable" and
            len(row.get("concrete_transactions") or []) >= 2
            for row in seed_rows),
        "echidna_loaded_seed_count": sum(row.get("loaded_seed_count", 0) for row in echidna_rows),
        "echidna_replayed_seed_count": sum(row.get("replayed_sequence_count", 0) for row in echidna_rows),
        "echidna_replayed_multitransaction_seed_count": sum(
            row.get("replayed_sequence_count", 0) > 0 and
            len(next((seed.get("concrete_transactions") or [] for seed in seed_rows
                      if seed.get("property_id") == row["property_id"]), [])) >= 2
            for row in echidna_rows),
        "echidna_post_replay_mutation_count": sum(bool(row.get("mutation_evidence")) for row in echidna_rows),
        "echidna_fuzzing_ran_count": sum(row.get("fuzzing_transactions", 0) > 0 and
                                           not row.get("worker_crashes") for row in echidna_rows),
        "echidna_unique_instructions": {row["property_id"]: row.get("unique_instructions")
                                        for row in echidna_rows},
        "pre_fuzz_property_violations": [
            {"property_id": row["property_id"], "violation": row["replay"].get("target_property_violation")}
            for row in seed_rows if row.get("replay", {}).get("target_property_violation")],
        "echidna_property_failures": [
            {"property_id": row["property_id"], "initial_state_failures": row.get("initial_state_failures", []),
             "post_initial_failures": row.get("property_failures", []),
             "attribution": (
                 "initial_state" if row.get("initial_state_failures") else
                 "anvil_prevalidation_already_violated" if next((seed for seed in seed_rows
                     if seed.get("property_id") == row["property_id"] and
                     seed.get("replay", {}).get("target_property_violation")), None) else
                 "external_seed_replay_or_followup_fuzzing_unresolved" if row.get("input_seed_count") else
                 "fuzzing_without_external_seed")}
            for row in echidna_rows if row.get("property_failures")],
        "total_elapsed_seconds_including_grouping": round(
            elapsed + (grouping_ms / 1000
                       if method.startswith("associated") or method == "random_batch" else 0), 4),
    }


def _grouping_benchmark(project: str, property_ids: list[str], repeats: int) -> dict[str, Any]:
    from 属性关联分组 import analyze

    report = _selected_report(project, property_ids)
    stages: dict[str, list[float]] = {key: [] for key in
                                     ("feature_extraction_ms", "dependency_graph_ms", "property_merge_ms")}
    latest = None
    for trial in range(repeats):
        timings: dict[str, float] = {}
        latest = analyze(report, trials=1, seed=BASE_SEED + trial, timings=timings)
        for key in stages:
            stages[key].append(timings[key])
    assert latest is not None
    return {"groups": _groups_from_result(latest),
            "repetitions": repeats,
            "stage_timings": {key: {"median_ms": round(statistics.median(values), 6),
                                     "range_ms": [round(min(values), 6), round(max(values), 6)],
                                     "samples_ms": [round(value, 6) for value in values]}
                              for key, values in stages.items()},
            "partition_quality": latest["evaluation"],
            "method": latest["method"]}


def _context_benchmark(project: str, property_ids: list[str],
                       associated: list[list[str]], repeats: int) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / ".tools/tokenizer"))
    import tiktoken

    encoder = tiktoken.get_encoding("o200k_base")
    extraction_samples: list[float] = []
    dedup_samples: dict[str, list[float]] = {"independent": [], "associated": [],
                                             "global_deduplicated": []}
    encoding_samples: dict[str, list[float]] = {"independent": [], "associated": [],
                                                "global_deduplicated": []}
    counts: dict[str, list[int]] = {"independent": [], "associated": [], "global_deduplicated": []}
    audit_summary = {"property_count": len(property_ids), "predicates_preserved": True,
                     "candidate_action_relations_preserved": True,
                     "source_references_preserved": True, "unknown_relations_preserved": True,
                     "missing_evidence": []}
    for trial in range(repeats):
        tick = time.perf_counter_ns()
        full = load_project_context(project, property_ids)
        extraction_samples.append((time.perf_counter_ns() - tick) / 1_000_000)
        by_id = {prop["property_id"]: prop for prop in full["properties"]}
        layouts: dict[str, list[dict[str, Any]]] = {
            "independent": [{**full, "properties": [by_id[pid]]} for pid in property_ids],
            "associated": [{**full, "properties": [by_id[pid] for pid in group]}
                           for group in associated],
            "global_deduplicated": [full],
        }
        for name, contexts in layouts.items():
            payloads = []
            dedup_ms = 0.0
            for context in contexts:
                tick = time.perf_counter_ns()
                payload = compact_for_agent(context)
                dedup_ms += (time.perf_counter_ns() - tick) / 1_000_000
                payloads.append(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
                compact_by_id = {prop["property_id"]: prop for prop in payload.get("properties", [])}
                source_map = payload.get("shared_function_contexts", {})
                for pid in context["properties"]:
                    prop_id = pid["property_id"]
                    retained = compact_by_id.get(prop_id)
                    if not retained:
                        audit_summary["missing_evidence"].append({"property_id": prop_id,
                                                                  "evidence": "property"})
                        continue
                    for field, audit_key in (("property_predicate", "predicates_preserved"),
                                              ("property_source", "source_references_preserved"),
                                              ("unknowns", "unknown_relations_preserved"),
                                              ("prerequisite_state_closure",
                                               "unknown_relations_preserved")):
                        if retained.get(field) != pid.get(field):
                            audit_summary[audit_key] = False
                            audit_summary["missing_evidence"].append({"property_id": prop_id,
                                                                      "evidence": field})
                    retained_actions = retained.get("candidate_actions", [])
                    for action in pid.get("candidate_actions", []):
                        found = next((item for item in retained_actions
                                      if item.get("abi_signature") == action.get("abi_signature") and
                                      item.get("function") == action.get("function")), None)
                        if not found or found.get("matched_states") != action.get("matched_states") or \
                                found.get("effect_evidence") != action.get("effect_evidence"):
                            audit_summary["candidate_action_relations_preserved"] = False
                            audit_summary["missing_evidence"].append({"property_id": prop_id,
                                                                      "evidence": action.get("abi_signature")})
                        elif found.get("source_context_id") not in source_map:
                            audit_summary["source_references_preserved"] = False
                            audit_summary["missing_evidence"].append({"property_id": prop_id,
                                                                      "evidence": "action_source"})
            dedup_samples[name].append(dedup_ms)
            tick = time.perf_counter_ns()
            counts[name].append(sum(len(encoder.encode(value)) for value in payloads))
            encoding_samples[name].append((time.perf_counter_ns() - tick) / 1_000_000)
    summarize = lambda values: {"median_ms": round(statistics.median(values), 6),
                                "range_ms": [round(min(values), 6), round(max(values), 6)]}
    return {
        "repetitions": repeats, "local_tokenizer": "tiktoken o200k_base; 仅作布局比较，正式用量取 DeepSeek API usage",
        "timings": {
            "property_context_extraction": summarize(extraction_samples),
            "context_deduplication": {key: summarize(values)
                                      for key, values in dedup_samples.items()},
            "local_token_encoding": {key: summarize(values)
                                     for key, values in encoding_samples.items()},
        },
        "summed_context_tokens_median": {name: int(statistics.median(values))
                                         for name, values in counts.items()},
        "retention_audit": audit_summary,
    }


def _manual_drips_upper_bound(temp_root: Path, repetition: int) -> dict[str, Any]:
    seed_path = ROOT / "seeds/Drips/自主种子质量实验/公开基准正例.json"
    seed = read_json(seed_path)
    property_id = DATASETS["Drips"][0]
    context = load_project_context("Drips", [property_id])
    prop = context["properties"][0]
    campaign_root = temp_root / "manual-upper-bound" / f"r{repetition}" / property_id
    coverage = campaign_root / "coverage"
    coverage.mkdir(parents=True, exist_ok=True)
    (coverage / "known-counterexample.txt").write_text(
        json.dumps(seed["transactions"], ensure_ascii=False), encoding="utf-8")
    deadline = time.monotonic() + 120
    result = _run_echidna_target("Drips", prop, campaign_root,
                                 BASE_SEED + 9000 + repetition, deadline)
    return {"repetition": repetition, "property_id": property_id, "seed_id": seed["seed_id"],
            "origin": seed["origin"], "transaction_count": seed["transaction_count"],
            "manual_path_or_parameters_given_to_agents": False,
            "echidna": result}


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    keys = ("valid_evm_seed_count", "multi_transaction_seed_count",
            "agent_a_applied_shared_prefix_count", "shared_prefix_transactions_reused",
            "shared_prefix_seed_reuse_count",
            "effective_successful_state_transitions", "effective_slither_evidenced_transitions",
            "unknown_effect_transition_count", "echidna_replayed_multitransaction_seed_count",
            "echidna_loaded_seed_count", "echidna_replayed_seed_count",
            "echidna_post_replay_mutation_count", "echidna_fuzzing_ran_count",
            "total_elapsed_seconds_including_grouping")
    for project, method in sorted({(run["project"], run["method"]) for run in runs}):
        selected = [run for run in runs if run["project"] == project and run["method"] == method]
        result[f"{project}/{method}"] = {
            "repetitions": len(selected),
            **{key: {"median": statistics.median(run[key] for run in selected),
                     "range": [min(run[key] for run in selected), max(run[key] for run in selected)]}
               for key in keys},
            "model_tokens": {"median": statistics.median(run["budget_usage"]["spent_tokens"]
                                                          for run in selected),
                             "range": [min(run["budget_usage"]["spent_tokens"] for run in selected),
                                       max(run["budget_usage"]["spent_tokens"] for run in selected)]},
            "estimated_cost_usd_offpeak_total": round(sum(
                run["agent_a"]["estimated_cost_usd_offpeak"] +
                run["agent_b"]["estimated_cost_usd_offpeak"] for run in selected), 8),
            "median_unique_instructions": statistics.median(
                sum(value for value in run["echidna_unique_instructions"].values()
                    if value is not None) for run in selected),
        }
    return result


def _run_native_baselines(projects: list[str], repetitions: int,
                          temp_root: Path) -> list[dict[str, Any]]:
    baselines = []
    for project in projects:
        ids = DATASETS[project]
        context = load_project_context(project, ids)
        properties_by_id = {prop["property_id"]: prop for prop in context["properties"]}
        for repetition in range(1, repetitions + 1):
            native_started = time.monotonic()
            deadline = native_started + WALL_BUDGET_SECONDS
            rows = []
            for property_index, property_id in enumerate(ids, start=1):
                campaign_root = temp_root / "native" / project / f"r{repetition}" / property_id
                rows.append(_run_echidna_target(
                    project, properties_by_id[property_id], campaign_root,
                    BASE_SEED + repetition * 101 + property_index, deadline))
            baselines.append({
                "project": project, "repetition": repetition,
                "property_ids": ids, "echidna": rows,
                "elapsed_seconds": round(time.monotonic() - native_started, 4),
                "budgets": {"wall_seconds": WALL_BUDGET_SECONDS,
                            "test_limit_per_property": ECHIDNA_TEST_LIMIT,
                            "seq_len": ECHIDNA_SEQ_LEN},
            })
            print(f"原生基线完成 {project}/r{repetition}: "
                  f"目标运行={sum(row.get('status') == 'completed' for row in rows)}/{len(ids)}",
                  flush=True)
    return baselines


def _attach_coverage_comparisons(runs: list[dict[str, Any]],
                                 native_baselines: list[dict[str, Any]]) -> None:
    native_lookup = {(row["project"], row["repetition"], prop["property_id"]): prop
                     for row in native_baselines for prop in row["echidna"]}
    for run in runs:
        comparisons = {}
        for row in run.get("echidna", []):
            base = native_lookup.get((run["project"], run["repetition"], row["property_id"]))
            if base:
                current_cov = row.get("unique_instructions")
                baseline_cov = base.get("unique_instructions")
                comparisons[row["property_id"]] = {
                    "method_unique_instructions": current_cov,
                    "native_unique_instructions": baseline_cov,
                    "delta_instructions": (current_cov - baseline_cov
                                           if current_cov is not None and baseline_cov is not None else None),
                }
        run["coverage_vs_native"] = comparisons


def repair_existing_report(report_path: Path, *, repair_native: bool,
                           rerun_methods: list[str]) -> dict[str, Any]:
    repair_started = time.monotonic()
    report = read_json(report_path)
    experiment_id = report.get("experiment_id", uuid.uuid4().hex)
    temp_root = Path(tempfile.mkdtemp(prefix=f"v2-seed-quality-repair-{experiment_id}-"))
    corrections = []
    api_logs = []
    seed_archives = []
    try:
        if repair_native:
            report["native_echidna_baselines"] = _run_native_baselines(
                list(report["property_sets_fixed_before_calls"]),
                report["repetitions"], temp_root)
            corrections.append({"kind": "native_echidna_baselines",
                                "reason": "先前空语料 campaign 的父目录未创建，初次调用在启动前失败；已补跑。"})
            _attach_coverage_comparisons(report["runs"], report["native_echidna_baselines"])
            report["correction_runs"] = list(corrections)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        for method in rerun_methods:
            projects = sorted({run["project"] for run in report["runs"]
                               if run["method"] == method})
            if not projects:
                continue
            corrected_runs = []
            log_path = RESULT_DIR / f"自主种子质量实验-{experiment_id}-{method}-校正API调用.jsonl"
            archive_root = RESULT_DIR / f"种子语料-{experiment_id}-{method}-校正"
            for project in projects:
                ids = report["property_sets_fixed_before_calls"][project]
                groups = report["grouping_preprocessing"][project]["groups"]
                grouping = report["grouping_preprocessing"][project]["stage_timings"]
                grouping_ms = sum(grouping[key]["median_ms"] for key in
                                  ("feature_extraction_ms", "dependency_graph_ms", "property_merge_ms"))
                context = load_project_context(project, ids)
                for repetition in range(1, report["repetitions"] + 1):
                    run = _run_agent_condition(
                        project, ids, context, groups, method, repetition, temp_root,
                        grouping_ms, log_path, archive_root)
                    corrected_runs.append(run)
                    print(f"校正完成 {project}/{method}/r{repetition}: "
                          f"有效种子={run['valid_evm_seed_count']}/{len(ids)}, "
                          f"Token={run['budget_usage']['spent_tokens']}", flush=True)
            report["runs"] = [run for run in report["runs"] if run["method"] != method] + corrected_runs
            api_logs.append(str(log_path.relative_to(ROOT)))
            seed_archives.append(str(archive_root.relative_to(ROOT)))
            corrections.append({"kind": method,
                                "reason": "此前消融同时关闭了结构修复；按相同预算、保留 ABI/JSON 局部修复后重跑，并替换旧条件。"})
        for run in report["runs"]:
            seeds_by_id = {seed.get("property_id"): seed for seed in run.get("seeds", [])}
            for echidna_row in run.get("echidna", []):
                seed = seeds_by_id.get(echidna_row.get("property_id"), {})
                echidna_row["input_seed_count"] = int(bool(
                    seed.get("status") == "executable" or seed.get("echidna_only_seed_submission")))
            run["multi_transaction_seed_count"] = sum(
                seed.get("status") == "executable" and
                len(seed.get("concrete_transactions") or []) >= 2
                for seed in run.get("seeds", []))
            run["echidna_replayed_multitransaction_seed_count"] = sum(
                echidna_row.get("replayed_sequence_count", 0) > 0 and
                len((seeds_by_id.get(echidna_row.get("property_id"), {})
                     .get("concrete_transactions") or [])) >= 2
                for echidna_row in run.get("echidna", []))
            run["unknown_effect_transition_count"] = sum(
                tx.get("status") == "success" and tx.get("observed_effect_status") == "unknown"
                for seed in run.get("seeds", [])
                for tx in (seed.get("replay") or {}).get("transactions", []))
            run["echidna_property_failures"] = []
            for echidna_row in run.get("echidna", []):
                if not echidna_row.get("property_failures"):
                    continue
                seed = seeds_by_id.get(echidna_row.get("property_id"), {})
                attribution = ("initial_state" if echidna_row.get("initial_state_failures") else
                              "anvil_prevalidation_already_violated"
                              if seed.get("replay", {}).get("target_property_violation") else
                              "external_seed_replay_or_followup_fuzzing_unresolved"
                              if echidna_row.get("input_seed_count") else
                              "fuzzing_without_external_seed")
                run["echidna_property_failures"].append({
                    "property_id": echidna_row["property_id"],
                    "initial_state_failures": echidna_row.get("initial_state_failures", []),
                    "post_initial_failures": echidna_row.get("property_failures", []),
                    "attribution": attribution})
        _attach_coverage_comparisons(report["runs"], report.get("native_echidna_baselines", []))
        report["aggregates"] = _aggregate(report["runs"])
        report["correction_runs"] = corrections
        report["additional_api_logs"] = api_logs
        report["additional_seed_corpus_directories"] = seed_archives
        report["total_wall_seconds"] = round(
            report.get("total_wall_seconds", 0) + time.monotonic() - repair_started, 3)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)


def run_experiment(repetitions: int, projects: list[str]) -> dict[str, Any]:
    experiment_id = uuid.uuid4().hex
    temp_root = Path(tempfile.mkdtemp(prefix=f"v2-seed-quality-{experiment_id}-"))
    api_log = RESULT_DIR / f"自主种子质量实验-{experiment_id}-API调用.jsonl"
    seed_archive_root = RESULT_DIR / f"种子语料-{experiment_id}"
    started = time.monotonic()
    grouping: dict[str, Any] = {}
    contexts: dict[str, dict[str, Any]] = {}
    for project in projects:
        ids = DATASETS[project]
        grouping[project] = _grouping_benchmark(project, ids, GROUPING_REPETITIONS)
        grouping[project]["context_benchmark"] = _context_benchmark(
            project, ids, grouping[project]["groups"], GROUPING_REPETITIONS)
        contexts[project] = load_project_context(project, ids)

    runs = []
    native_baselines = _run_native_baselines(projects, repetitions, temp_root)
    manual_upper_bound = []
    try:
        for project in projects:
            ids = DATASETS[project]
            groups = grouping[project]["groups"]
            methods = list(MATRIX_METHODS) if project == "Immutable" else ["independent"]
            for method in methods:
                for repetition in range(1, repetitions + 1):
                    run = _run_agent_condition(
                        project, ids, contexts[project], groups, method, repetition,
                        temp_root, grouping[project]["stage_timings"]["feature_extraction_ms"]["median_ms"] +
                        grouping[project]["stage_timings"]["dependency_graph_ms"]["median_ms"] +
                        grouping[project]["stage_timings"]["property_merge_ms"]["median_ms"],
                        api_log, seed_archive_root)
                    runs.append(run)
                    RESULT_DIR.mkdir(parents=True, exist_ok=True)
                    checkpoint = {"schema_version": 1, "experiment_id": experiment_id,
                                  "repetitions_requested": repetitions,
                                  "grouping": grouping, "native_baselines": native_baselines,
                                  "runs": runs,
                                  "aggregate_so_far": _aggregate(runs)}
                    (RESULT_DIR / "自主种子质量实验-检查点.json").write_text(
                        json.dumps(checkpoint, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"完成 {project}/{method}/r{repetition}: "
                          f"有效种子={run['valid_evm_seed_count']}/{len(ids)}, "
                          f"Token={run['budget_usage']['spent_tokens']}, "
                          f"耗时={run['budget_usage']['wall_seconds_used']}s", flush=True)
            if project == "Drips":
                for repetition in range(1, repetitions + 1):
                    manual_upper_bound.append(_manual_drips_upper_bound(temp_root, repetition))
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

    _attach_coverage_comparisons(runs, native_baselines)
    return {
        "schema_version": 1, "experiment_id": experiment_id,
        "model": "deepseek-flash", "model_thinking": "disabled",
        "repetitions": repetitions, "property_sets_fixed_before_calls": DATASETS,
        "sample_rationale": {
            "Immutable": "Slither 可序列化候选覆盖 mint/approve/transfer/burn；固定集合包含授权清理、所有权更新、有界组操作及 tokenId/supply 边界。",
            "BeeStorage": "commit/reveal 两阶段交易依赖，并含 bytes32 参数和提交者身份/状态关联。",
            "Drips": "历史八笔可复现反例依赖流/拆分/接收/挤压状态和时间推进；该反例仅作上界，不给 Agent。",
        },
        "methods": {"Immutable": ["native_echidna", *MATRIX_METHODS],
                    "Drips": ["native_echidna", "independent_dual_agent", "manual_upper_bound"],
                    "BeeStorage": ["native_echidna", "independent_dual_agent"]},
        "budgets": {"tokens_per_agent_condition": TOKEN_BUDGET,
                    "wall_seconds_per_agent_condition": WALL_BUDGET_SECONDS,
                    "one_seed_slot_per_property": True,
                    "echidna_test_limit_per_property": ECHIDNA_TEST_LIMIT,
                    "echidna_sequence_length": ECHIDNA_SEQ_LEN},
        "grouping_preprocessing": grouping,
        "native_echidna_baselines": native_baselines,
        "runs": runs, "manual_upper_bound": manual_upper_bound,
        "aggregates": _aggregate(runs),
        "api_log": str(api_log.relative_to(ROOT)),
        "retained_seed_corpus_directory": str(seed_archive_root.relative_to(ROOT)),
        "total_wall_seconds": round(time.monotonic() - started, 3),
        "evidence_policy": {
            "agent_prompt_has_no_manual_paths_or_parameter_templates": True,
            "manual_drips_seed_is_upper_bound_only": True,
            "anvil_validity_and_echidna_native_replay_reported_separately": True,
            "only_loaded_and_replayed_corpus_without_worker_crash_counts_as_mutated_seed": True,
            "initial_state_failures_and_pre_fuzz_violations_reported_separately": True,
            "fuzzing_failures_are_not_counted_as_agent_discovered_if_replayed_seed_already_violated": True,
        },
        "limitations": [
            "Immutable 的属性函数部分会在检查体中执行内部操作；外部交易数与属性内部操作数分别记录。",
            "BeeStorage 与 Drips 在固定集合中各一个属性，适合检验跨合约类型/时间语义，不用于估计分组收益。",
            "原生 Echidna 基线按相同属性、相同 test-limit 和独立新语料目录运行；每个属性独立归因。",
            "Slither 静态依赖与公开 getter 的实际状态转移是代理指标，不等同于全面路径覆盖。",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--projects", nargs="+", choices=list(DATASETS),
                        default=list(DATASETS))
    parser.add_argument("--output", default="deepseek/结果/自主种子质量实验/自主种子质量实验.json")
    parser.add_argument("--repair-existing", type=Path,
                        help="修复已有实验报告中的原生基线或指定 Agent 条件，不重跑其他方法")
    parser.add_argument("--repair-native-baselines", action="store_true")
    parser.add_argument("--rerun-method", action="append", choices=list(MATRIX_METHODS), default=[])
    args = parser.parse_args()
    if args.repair_existing:
        if not args.repair_native_baselines and not args.rerun_method:
            parser.error("--repair-existing 需配合 --repair-native-baselines 或 --rerun-method")
        report_path = args.repair_existing
        if not report_path.is_absolute():
            report_path = ROOT / report_path
        report = repair_existing_report(
            report_path, repair_native=args.repair_native_baselines,
            rerun_methods=args.rerun_method)
        print(json.dumps({"report": str(report_path),
                          "corrections": report.get("correction_runs", []),
                          "aggregates": report.get("aggregates", {})},
                         ensure_ascii=False), flush=True)
        return
    if not 3 <= args.repetitions <= 5:
        parser.error("正式重复轮次应为 3–5")
    result = run_experiment(args.repetitions, args.projects)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    checkpoint = RESULT_DIR / "自主种子质量实验-检查点.json"
    if checkpoint.exists():
        checkpoint.unlink()
    print(json.dumps({"output": str(output), "runs": len(result["runs"]),
                      "aggregate_keys": list(result["aggregates"]),
                      "total_wall_seconds": result["total_wall_seconds"]}, ensure_ascii=False),
          flush=True)


if __name__ == "__main__":
    main()
