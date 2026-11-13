#!/usr/bin/env python3
"""固定属性集合比较独立、随机批处理、关联分组及受控组规模的 DeepSeek 闭环。"""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import statistics
import time
import uuid
import shutil
from pathlib import Path
from typing import Any

from web3 import Web3

from AgentA import generate_candidates
from AgentB import instantiate_candidate
from deepseek接口 import DeepSeekCallError
from 属性种子上下文 import (PROJECTS, compact_for_agent, load_project_context,
                           read_json)
from 种子验证 import (AnvilSession, echidna_corpus_evidence, replay_seed,
                     new_seed_id, run_echidna, write_corpus)


ROOT = Path(__file__).resolve().parents[2]
GROUP_FILE = ROOT / ".tools/results/属性关联分组.json"
DATASETS = {
    # Request group 2：共享 paymentRefCounter 和候选交易，但静态结果没有必需 setup。
    "Request": {"group_index": 2, "random_k": 2, "control_k": 2,
                "seed_properties": ["EchidnaERC20CommerceEscrowWrapper.echidna_escrow_state_consistent()"]},
    # Immutable group 2：18 个属性共享 totalMinted；抽取三个预先指定属性完成 B/EVM 样本。
    "Immutable": {"group_index": 2, "random_k": 3, "control_k": 3,
                  "seed_properties": ["echidna_group_occupancy", "echidna_approval_consistency",
                                      "echidna_minted_tokens_have_owner"]},
}
METHODS = ("independent", "random_batch", "associated", "controlled_size")
BASE_SEED = 20261113
MAX_GROUP_SIZE = 6


def _load_dataset(project: str) -> tuple[list[str], dict[str, Any]]:
    groups = read_json(GROUP_FILE)["projects"][project]["groups"]
    group = groups[DATASETS[project]["group_index"]]
    ids = [member["property_id"] for member in group["members"]]
    return ids, group


def _partition(project: str, ids: list[str], method: str, repetition: int) -> list[list[str]]:
    if method == "independent":
        return [[item] for item in ids]
    if method == "associated":
        return [ids[i:i + MAX_GROUP_SIZE] for i in range(0, len(ids), MAX_GROUP_SIZE)]
    size = DATASETS[project]["random_k" if method == "random_batch" else "control_k"]
    arranged = list(ids)
    if method == "random_batch":
        random.Random(BASE_SEED + repetition * 101 + sum(ord(c) for c in project)).shuffle(arranged)
    else:
        arranged.sort()
    return [arranged[i:i + size] for i in range(0, len(arranged), size)]


def _audit_partition(context: dict[str, Any], batches: list[list[str]], full_ids: list[str]):
    flattened = [item for batch in batches for item in batch]
    if sorted(flattened) != sorted(full_ids) or len(flattened) != len(set(flattened)):
        raise ValueError("分组条件未覆盖完全相同且唯一的属性集合")
    if len(context["properties"]) != len(set(full_ids)):
        raise ValueError("属性上下文丢失或重复")
    for prop in context["properties"]:
        if not prop.get("property_predicate"):
            raise ValueError(f"属性谓词源码不可用：{prop['property_id']}")
        for action in prop["candidate_actions"]:
            if action.get("abi_signature") and action.get("seed_compatible"):
                # The ABI is resolved later in compact_for_agent's one shared map.
                pass
    return {"input_property_ids": sorted(full_ids), "unique_property_count": len(set(full_ids)),
            "predicate_sources_available": sum(bool(p.get("property_predicate"))
                                                for p in context["properties"]),
            "candidate_action_count": sum(len(p["candidate_actions"])
                                           for p in context["properties"])}


def _candidate_for(context: dict[str, Any], raw: dict[str, Any], method: str,
                   repetition: int) -> dict[str, Any]:
    return {**raw,
            "candidate_id": f"{method}-r{repetition}-{raw['candidate_id']}",
            "project": context["project"], "context": context,
            "property": next(p["property"] for p in context["properties"]
                             if p["property_id"] == raw["property_id"])}


def _retry_agent_b(context: dict[str, Any], candidate: dict[str, Any], repair_limit: int):
    feedback = None
    events = []
    for attempt in range(1, repair_limit + 2):
        try:
            data, event = instantiate_candidate(context, candidate,
                                                feedback=feedback, attempt=attempt)
            events.append(event)
            return data, events
        except DeepSeekCallError as exc:
            if exc.event:
                events.append(exc.event)
            else:
                events.append({"ok": False, "error": str(exc), "error_kind": exc.kind})
            feedback = ("本地 ABI/结构校验未通过，按原序列修正。错误：" + str(exc))[:1200]
            if attempt > repair_limit:
                raise
    raise AssertionError("unreachable")


def _events_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [event for event in events if event.get("usage")]
    failed = [event for event in events if not event.get("ok")]
    compact_events = [{key: event.get(key) for key in
                       ("tag", "request_sha256", "model_requested", "model_returned", "ok",
                        "error_kind", "error", "usage", "elapsed_seconds",
                        "local_context_dedup_seconds")}
                      for event in events]
    return {
        "calls": len(events),
        "failed_calls": len(failed),
        "prompt_tokens": sum(event["usage"].get("prompt_tokens", 0) for event in measured),
        "cache_hit_tokens": sum(event["usage"].get("prompt_cache_hit_tokens", 0)
                                 for event in measured),
        "cache_miss_tokens": sum(event["usage"].get("prompt_cache_miss_tokens", 0)
                                  for event in measured),
        "completion_tokens": sum(event["usage"].get("completion_tokens", 0)
                                  for event in measured),
        "total_tokens": sum(event["usage"].get("total_tokens", 0) for event in measured),
        "estimated_cost_usd_offpeak": sum(float(event["usage"]["estimated_cost_usd"]["offpeak"])
                                           for event in measured),
        "estimated_cost_usd_peak": sum(float(event["usage"]["estimated_cost_usd"]["peak"])
                                        for event in measured),
        "elapsed_seconds": sum(event.get("elapsed_seconds", 0) for event in events),
        "local_context_dedup_seconds": sum(event.get("local_context_dedup_seconds", 0)
                                            for event in events),
        "events": compact_events,
    }


def run_condition(project: str, full_context: dict[str, Any], ids: list[str],
                  method: str, repetition: int, *, repair_limit: int,
                  test_limit: int, process_timeout: int, run_echidna_campaign: bool,
                  run_root: Path) -> dict[str, Any]:
    condition_start = time.perf_counter()
    batches = _partition(project, ids, method, repetition)
    audit = _audit_partition(full_context, batches, ids)
    by_id = {prop["property_id"]: prop for prop in full_context["properties"]}
    a_events: list[dict[str, Any]] = []
    b_events: list[dict[str, Any]] = []
    candidates_by_property: dict[str, dict[str, Any]] = {}
    batch_rows = []
    cache_probe = None
    cache_target_names = DATASETS[project]["seed_properties"]
    cache_target = next((prop["property_id"] for prop in full_context["properties"]
                         if any(name in prop["property"] for name in cache_target_names)), None)

    for batch_index, batch_ids in enumerate(batches, start=1):
        batch_context = load_project_context(project, batch_ids)
        tag = f"AgentA_{project}_{method}_r{repetition}_b{batch_index}"
        try:
            output, event = generate_candidates(batch_context, max_candidates=1, max_steps=5, tag=tag)
            a_events.append(event)
            rows = output.get("property_sequences", [])
            for row in rows:
                row["batch_id"] = batch_index
                # Keep first valid plan if a future model schema duplicates an ID across batches.
                candidates_by_property.setdefault(row["property_id"], row)
            batch_rows.append({"batch_index": batch_index, "property_ids": batch_ids,
                               "candidate_properties": [row["property_id"] for row in rows],
                               "candidate_count": len(rows), "status": "ok"})
            if method == "independent" and len(batch_ids) == 1 and batch_ids[0] == cache_target and cache_probe is None:
                probe, probe_event = generate_candidates(
                    batch_context, max_candidates=1, max_steps=5,
                    tag=f"AgentA_{project}_cache_probe_r{repetition}")
                cache_probe = {"property_id": cache_target, "output_used_for_quality": False,
                               "output_candidate_count": len(probe.get("property_sequences", [])),
                               "event": _events_summary([probe_event])["events"][0]}
        except DeepSeekCallError as exc:
            if exc.event:
                a_events.append(exc.event)
            batch_rows.append({"batch_index": batch_index, "property_ids": batch_ids,
                               "status": "agent_a_error", "error": str(exc)[:1000]})

    selected_seed_properties = {}
    for fragment in DATASETS[project]["seed_properties"]:
        prop = next((p for p in full_context["properties"] if fragment in p["property"]), None)
        if prop:
            selected_seed_properties[prop["property_id"]] = prop["property"]

    seed_rows = []
    corpus_root = run_root / project / f"{method}-r{repetition}"
    corpus_root.mkdir(parents=True, exist_ok=True)
    (corpus_root / "coverage").mkdir(exist_ok=True)
    with AnvilSession() as session:
        for property_id, property_signature in selected_seed_properties.items():
            raw = candidates_by_property.get(property_id)
            if not raw:
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "status": "agent_a_no_candidate"})
                continue
            candidate = _candidate_for(full_context, raw, method, repetition)
            try:
                concrete, events = _retry_agent_b(full_context, candidate, repair_limit)
                b_events.extend(events)
                replay = replay_seed(project, candidate, concrete["transactions"], session=session)
                corpus_file = None
                seed_id = None
                if replay["replay_status"] == "executable":
                    seed_id = new_seed_id()
                    corpus_file = write_corpus(project, candidate, concrete["transactions"],
                                               full_context, corpus_root,
                                               replay=replay, seed_id=seed_id)
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "candidate_id": candidate["candidate_id"], "seed_id": seed_id,
                                  "plan": raw["steps"],
                                  "seed": concrete, "replay": replay,
                                  "corpus_file": str(corpus_file.relative_to(ROOT)) if corpus_file else None,
                                  "status": replay["replay_status"]})
            except DeepSeekCallError as exc:
                if exc.event:
                    b_events.append(exc.event)
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "candidate_id": candidate["candidate_id"],
                                  "status": "agent_b_failed", "error": str(exc)[:1000]})
            except Exception as exc:
                seed_rows.append({"property_id": property_id, "property": property_signature,
                                  "candidate_id": candidate["candidate_id"],
                                  "status": "replay_or_abi_failed",
                                  "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})

    echidna = None
    if run_echidna_campaign:
        echidna = run_echidna(project, corpus_root, property_name="echidna_",
                              test_limit=test_limit, timeout=process_timeout,
                              seed=BASE_SEED + repetition)

    compact_bytes = len(json.dumps(compact_for_agent(full_context), ensure_ascii=False).encode("utf-8"))
    expanded_bytes = len(json.dumps(full_context, ensure_ascii=False).encode("utf-8"))
    prevalidation_violations = [
        {"property_id": row.get("property_id"), "violations": [
            {"transaction_index": tx["index"],
             "properties": tx.get("other_property_violations_during_prevalidation", []) +
                          ([row["property"].rsplit(".", 1)[-1].split("(", 1)[0]]
                           if tx.get("target_property") is False else [])}
            for tx in row.get("replay", {}).get("transactions", [])
            if tx.get("target_property") is False or
            tx.get("other_property_violations_during_prevalidation")]
         } for row in seed_rows
         if any(tx.get("target_property") is False or
                tx.get("other_property_violations_during_prevalidation")
                for tx in row.get("replay", {}).get("transactions", []))]
    prevalidated_names = {name.rsplit(".", 1)[-1].split("(", 1)[0]
                          for row in prevalidation_violations for tx in row["violations"]
                          for name in tx["properties"]}
    if echidna:
        failed_names = _property_failure_names(echidna)
        echidna["pre_fuzz_property_failure_overlap"] = sorted(failed_names & prevalidated_names)
        echidna["property_failures_not_prevalidated"] = sorted(failed_names - prevalidated_names)
    return {
        "project": project, "method": method, "repetition": repetition,
        "property_ids": ids, "batch_sizes": [len(batch) for batch in batches],
        "partition_audit": audit, "batches": batch_rows,
        "agent_a_output_properties": len(candidates_by_property),
        "agent_a_output_property_ids": sorted(candidates_by_property),
        "agent_a": _events_summary(a_events), "cache_probe": cache_probe,
        "agent_b": _events_summary(b_events), "seed_candidates": seed_rows,
        "prevalidation_violations": prevalidation_violations,
        "echidna": echidna, "corpus_root": str(corpus_root.relative_to(ROOT)),
        "context_size_bytes_for_reference": {"expanded": expanded_bytes, "deduplicated": compact_bytes},
        "context_dedup_seconds": _events_summary(a_events)["local_context_dedup_seconds"],
        "elapsed_seconds": round(time.perf_counter() - condition_start, 3),
    }


def run_experiment(*, repetitions: int, repair_limit: int, test_limit: int,
                   process_timeout: int, run_echidna_campaign: bool,
                   projects: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    experiment_id = uuid.uuid4().hex
    group_data = read_json(GROUP_FILE)
    results = []
    preprocessing = {}
    omitted = []
    for project in projects:
        ids, group = _load_dataset(project)
        feature_start = time.perf_counter()
        context = load_project_context(project, ids)
        feature_seconds = time.perf_counter() - feature_start
        compact_start = time.perf_counter()
        compact = compact_for_agent(context)
        compact_seconds = time.perf_counter() - compact_start
        preprocessing[project] = {
            "attribute_feature_extraction_and_source_resolution_seconds": feature_seconds,
            "context_deduplication_seconds": compact_seconds,
            "property_count": len(ids),
            "association_group_index": DATASETS[project]["group_index"],
            "association_group_size": len(ids),
            "shared_core": group.get("shared_core", {}),
            "shared_context_reduction_bytes": len(json.dumps(context, ensure_ascii=False).encode("utf-8")) -
                                              len(json.dumps(compact, ensure_ascii=False).encode("utf-8")),
        }
        for method in METHODS:
            for repetition in range(1, repetitions + 1):
                try:
                    result = run_condition(
                        project, context, ids, method, repetition,
                        repair_limit=repair_limit, test_limit=test_limit,
                        process_timeout=process_timeout,
                        run_echidna_campaign=run_echidna_campaign,
                        run_root=ROOT / "deepseek/结果/分组闭环实验/语料" / experiment_id)
                    results.append(result)
                    print(f"完成 {project}/{method}/r{repetition}: "
                          f"A={result['agent_a']['calls']} calls, "
                          f"B={result['agent_b']['calls']} calls, "
                          f"replay={sum(x.get('status') == 'executable' for x in result['seed_candidates'])}",
                          flush=True)
                except Exception as exc:
                    results.append({"project": project, "method": method,
                                    "repetition": repetition, "status": "condition_failed",
                                    "error": f"{type(exc).__name__}: {str(exc)[:1500]}"})
                    print(f"失败 {project}/{method}/r{repetition}: {type(exc).__name__}", flush=True)

    # Hokusai 的属性关联组 8 来源于 AMM Harness，但当前 sol 快照没有该 Harness/源码/编译产物。
    hokusai_amm_source = ROOT / "sol/真实项目/Hokusai/contracts/echidna/EchidnaAMMGraduation.sol"
    if not hokusai_amm_source.is_file():
        omitted.append({"project": "Hokusai", "group_index": 8,
                        "properties": [m["property_id"] for m in
                                       group_data["projects"]["Hokusai"]["groups"][8]["members"]],
                        "reason": "当前 Hokusai 源码快照缺少 EchidnaAMMGraduation.sol 及其编译 Harness；不以 JSON 摘要代替真实 ABI/源码验证。"})

    return {"schema_version": 1, "experiment_id": experiment_id,
            "model": "deepseek-flash", "model_thinking": "disabled",
            "base_seed": BASE_SEED, "repetitions": repetitions,
            "same_attribute_sets_per_project": {project: _load_dataset(project)[0] for project in projects},
            "methods": list(METHODS), "preprocessing": preprocessing,
            "excluded_cases": omitted, "runs": results,
            "total_elapsed_seconds": round(time.perf_counter() - started, 3),
            "limitations": [
                "每个属性最多生成并实例化一个候选序列，以固定 Agent 输出预算。",
                "Request 使用 3 属性组；Immutable 使用 18 属性大组；Anvil/Agent B 对预注册的 1/3 条属性做闭环样本。",
                "Echidna 原生运行使用同一 Harness 中全部 echidna_* 属性；Agent 分组不改变测试属性集合。",
                "费用来自 API 返回 Token 与官方单价估算，价格按峰/非峰给范围；本地 Token 编码耗时不由 API 暴露。",
                "当前 Hokusai AMM 共享前置动作组因本地源码快照不完整而未纳入分组效益对照。",
            ]}


def _random_argument(kind: str, rng: random.Random):
    if kind == "address":
        return Web3.to_checksum_address("0x" + f"{rng.getrandbits(160):040x}")
    if kind == "bool":
        return bool(rng.getrandbits(1))
    match = re.fullmatch(r"(u?int)([0-9]*)", kind)
    if not match:
        raise ValueError(f"匹配随机基线暂不支持 ABI 类型 {kind}")
    bits = int(match.group(2) or "256")
    value = rng.getrandbits(bits)
    if match.group(1) == "int" and value >= (1 << (bits - 1)):
        value -= 1 << bits
    return value


def _randomize_agent_seed(context: dict[str, Any], candidate: dict[str, Any],
                          seed: dict[str, Any], rng: random.Random):
    property_context = next(p for p in context["properties"]
                            if p["property_id"] == candidate["property_id"])
    actions = {action["abi_signature"]: action for action in property_context["candidate_actions"]
               if action.get("seed_compatible") and action.get("abi_signature")}
    transactions = []
    for tx in seed["transactions"]:
        action = actions[tx["function"]]
        arguments = [_random_argument(item["type"], rng) for item in action["abi_inputs"]]
        transactions.append({**tx, "arguments": arguments,
                             "sender": rng.choice(__import__("AgentB").SENDERS)})
    return transactions


def _property_failure_names(echidna: dict[str, Any] | None) -> set[str]:
    if not echidna:
        return set()
    return {line.split(":", 1)[0].strip().rsplit(".", 1)[-1].split("(", 1)[0]
            for line in echidna.get("property_failures", [])}


def _prevalidated_property_names(run: dict[str, Any]) -> set[str]:
    return {name.rsplit(".", 1)[-1].split("(", 1)[0]
            for row in run.get("prevalidation_violations", [])
            for tx in row.get("violations", []) for name in tx.get("properties", [])}


def _classify_echidna_failures(echidna: dict[str, Any], prevalidated: set[str]) -> None:
    failures = echidna.get("property_failures", [])
    all_failed = _property_failure_names(echidna)
    initial = {line.split(":", 1)[0].strip().rsplit(".", 1)[-1].split("(", 1)[0]
               for line in failures if "no transactions made" in line.lower()}
    post_initial = {line.split(":", 1)[0].strip().rsplit(".", 1)[-1].split("(", 1)[0]
                    for line in failures if "no transactions made" not in line.lower()}
    echidna["pre_fuzz_property_failure_overlap"] = sorted(all_failed & prevalidated)
    echidna["property_failures_not_prevalidated"] = sorted(all_failed - prevalidated)
    echidna["initial_state_failures"] = sorted(initial)
    echidna["non_initial_failures_not_prevalidated"] = sorted(post_initial - prevalidated)


def _timing_summary(samples: list[float]) -> dict[str, Any]:
    values = [round(value, 4) for value in samples]
    return {"median_ms": round(statistics.median(samples), 4),
            "range_ms": [round(min(samples), 4), round(max(samples), 4)],
            "samples_ms": values}


def benchmark_preprocessing(repetitions: int = 10) -> dict[str, Any]:
    """重复计时 Slither JSON 特征、依赖分组、上下文去重与本地 Token 编码。"""
    import sys
    sys.path.insert(0, str(ROOT / ".tools/tokenizer"))
    import tiktoken
    from 属性关联分组 import analyze
    from 属性上下文压缩 import build, compact as compact_json

    grouping_all = read_json(GROUP_FILE)
    encoder = tiktoken.get_encoding("o200k_base")
    result = {"repetitions": repetitions,
              "local_tokenizer": "tiktoken 0.14.0 / o200k_base; 本地布局比较参考，DeepSeek 实际 Token 取 API usage",
              "projects": {}}
    for project in ("Hokusai", "Request", "Immutable"):
        grouping = grouping_all["projects"][project]
        input_path = Path(grouping["input_file"])
        source = read_json(input_path if input_path.is_absolute() else ROOT / input_path)
        feature, graph, merge, projection, dedup = [], [], [], [], []
        token_times = {"independent": [], "global_shared": [], "associated_grouped": []}
        token_counts, audit = {}, None
        for iteration in range(repetitions):
            timings: dict[str, float] = {}
            computed_grouping = analyze(source, trials=1, seed=BASE_SEED + iteration,
                                        timings=timings)
            normalize_groups = lambda groups: sorted(
                tuple(sorted(member["property_id"] for member in group["members"]))
                for group in groups)
            if normalize_groups(computed_grouping["groups"]) != normalize_groups(grouping["groups"]):
                raise ValueError(f"{project} 计时使用的分组与正式输入不一致")
            feature.append(timings["feature_extraction_ms"])
            graph.append(timings["dependency_graph_ms"])
            merge.append(timings["property_merge_ms"])

            context_timings: dict[str, float] = {}
            layouts = build(source, grouping, timings=context_timings)
            projection.append(context_timings["context_projection_ms"])
            dedup.append(context_timings["context_dedup_ms"])
            audit = layouts["audit"]
            payloads = {"independent": layouts["independent"],
                        "global_shared": [layouts["global_shared"]],
                        "associated_grouped": layouts["grouped"]}
            for name, values in payloads.items():
                tick = time.perf_counter_ns()
                counts = [len(encoder.encode(compact_json(value))) for value in values]
                token_times[name].append((time.perf_counter_ns() - tick) / 1_000_000)
                token_counts[name] = sum(counts)

        result["projects"][project] = {
            "input_properties": audit["properties"],
            "repeated_stage_timings": {
                "attribute_feature_extraction": _timing_summary(feature),
                "dependency_graph_construction": _timing_summary(graph),
                "property_group_merge": _timing_summary(merge),
                "context_projection": _timing_summary(projection),
                "context_deduplication": _timing_summary(dedup),
                "local_token_encoding": {name: _timing_summary(values)
                                         for name, values in token_times.items()},
            },
            "local_token_counts_last_repeat": token_counts,
            "context_retention_audit": audit,
        }
    return result


def augment_baselines(report: dict[str, Any], *, test_limit: int = 100,
                      process_timeout: int = 45,
                      preprocessing_repetitions: int = 10) -> dict[str, Any]:
    """为已完成的 Agent 矩阵补同预算原生 Echidna 与配对随机参数基线。"""
    report["native_echidna_baselines"] = {}
    baseline_batch = f"补测-{time.time_ns()}"
    report["additional_baseline_batch"] = baseline_batch
    native_root = ROOT / "deepseek/结果/分组闭环实验/语料/原生Echidna" / baseline_batch
    for project in sorted({run["project"] for run in report["runs"] if run.get("property_ids")}):
        report["native_echidna_baselines"][project] = []
        repetitions = sorted({run["repetition"] for run in report["runs"]
                              if run.get("project") == project and run.get("property_ids")})
        for repetition in repetitions:
            corpus_root = native_root / project / f"r{repetition}"
            (corpus_root / "coverage").mkdir(parents=True, exist_ok=True)
            result = run_echidna(project, corpus_root, property_name="echidna_",
                                 test_limit=test_limit, timeout=process_timeout,
                                 seed=BASE_SEED + repetition)
            report["native_echidna_baselines"][project].append({
                "repetition": repetition, "status": "no_external_seed",
                "echidna": result,
            })
            print(f"完成 native Echidna/{project}/r{repetition}", flush=True)

    for run in report["runs"]:
        if not run.get("property_ids"):
            continue
        project, repetition, method = run["project"], run["repetition"], run["method"]
        # Older matrix records with no campaign are resumed as empty-corpus Echidna runs.
        if run.get("echidna") is None:
            corpus_root = ROOT / run.get("corpus_root",
                                        f"deepseek/结果/分组闭环实验/语料/{project}/{method}-r{repetition}")
            (corpus_root / "coverage").mkdir(parents=True, exist_ok=True)
            run["echidna"] = run_echidna(project, corpus_root, property_name="echidna_",
                                         test_limit=test_limit, timeout=process_timeout,
                                         seed=BASE_SEED + repetition)
            run["echidna"]["campaign_kind"] = "empty_corpus_after_no_candidate"
            print(f"补测空语料 Echidna/{project}/{method}/r{repetition}", flush=True)
        prevalidated = _prevalidated_property_names(run)
        failed = _property_failure_names(run.get("echidna"))
        run["echidna"]["pre_fuzz_property_failure_overlap"] = sorted(failed & prevalidated)
        run["echidna"]["property_failures_not_prevalidated"] = sorted(failed - prevalidated)

        context = load_project_context(project, run["property_ids"])
        seed_root = (ROOT / "deepseek/结果/分组闭环实验/语料/匹配随机种子" /
                     baseline_batch / project / f"{method}-r{repetition}")
        (seed_root / "coverage").mkdir(parents=True, exist_ok=True)
        random_rows = []
        seeds = [row for row in run.get("seed_candidates", []) if row.get("seed") and row.get("plan")]
        if seeds:
            rng_seed = BASE_SEED * 97 + repetition * 1009 + sum(ord(c) for c in project + method)
            rng = random.Random(rng_seed)
            with AnvilSession() as session:
                for row in seeds:
                    candidate = {"candidate_id": f"random-{row['candidate_id']}",
                                 "property_id": row["property_id"], "steps": row["plan"],
                                 "project": project, "context": context,
                                 "property": row["property"]}
                    try:
                        randomized = _randomize_agent_seed(context, candidate, row["seed"], rng)
                        replay = replay_seed(project, candidate, randomized, session=session)
                        if replay["replay_status"] != "executable":
                            random_rows.append({"property_id": row["property_id"],
                                                "candidate_id": candidate["candidate_id"],
                                                "status": "replay_failed", "replay": replay})
                            continue
                        seed_id = new_seed_id()
                        corpus_file = write_corpus(project, candidate, randomized, context, seed_root,
                                                   replay=replay, seed_id=seed_id)
                        random_rows.append({"property_id": row["property_id"],
                                            "candidate_id": candidate["candidate_id"],
                                            "seed_id": seed_id,
                                            "matched_function_sequence": [tx["function"] for tx in randomized],
                                            "transactions": randomized, "replay": replay,
                                            "corpus_file": str(corpus_file.relative_to(ROOT)),
                                            "status": replay["replay_status"]})
                    except Exception as exc:
                        random_rows.append({"property_id": row["property_id"],
                                            "candidate_id": candidate["candidate_id"],
                                            "status": "random_seed_failed",
                                            "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
        random_echidna = None
        campaign_root = ROOT / "deepseek/结果/分组闭环实验/语料/匹配随机种子Echidna" / baseline_batch / project / f"{method}-r{repetition}"
        if any(row.get("status") == "executable" for row in random_rows):
            campaign_coverage = campaign_root / "coverage"
            campaign_coverage.mkdir(parents=True, exist_ok=True)
            # 仅复制本轮 Agent 配对随机种子，排除同目录上一次 Echidna 变异生成的语料。
            for row in random_rows:
                corpus_file = row.get("corpus_file")
                if corpus_file:
                    source_file = ROOT / corpus_file
                    if source_file.is_file():
                        shutil.copy2(source_file, campaign_coverage / source_file.name)
            random_echidna = run_echidna(project, campaign_root, property_name="echidna_",
                                         test_limit=test_limit, timeout=process_timeout,
                                         seed=BASE_SEED + repetition)
            random_prevalidated = {
                name.rsplit(".", 1)[-1].split("(", 1)[0]
                for row in random_rows
                for tx in row.get("replay", {}).get("transactions", [])
                for name in (tx.get("all_property_values") or {})
                if tx["all_property_values"].get(name) is False
            }
            random_failed = _property_failure_names(random_echidna)
            random_echidna["pre_fuzz_property_failure_overlap"] = sorted(random_failed & random_prevalidated)
            random_echidna["property_failures_not_prevalidated"] = sorted(random_failed - random_prevalidated)
        run["matched_random_parameter_baseline"] = {
            "random_seed": rng_seed if seeds else None,
            "same_function_sequence_as_agent_a": True,
            "randomized_fields": ["ABI arguments", "sender"],
            "preserved_fields": ["function sequence", "value", "delay", "transaction count"],
            "seed_candidates": random_rows,
            "executable_seed_count": sum(row.get("status") == "executable" for row in random_rows),
            "echidna_input_corpus_root": str(campaign_root.relative_to(ROOT)) if random_rows else None,
            "echidna": random_echidna,
        }
        print(f"完成 matched-random/{project}/{method}/r{repetition}: "
              f"replay={sum(row.get('status') == 'executable' for row in random_rows)}", flush=True)
    for run in report["runs"]:
        echidna = run.get("echidna")
        if echidna and isinstance(echidna.get("output"), str):
            echidna.update(echidna_corpus_evidence(echidna["output"]))
            _classify_echidna_failures(echidna, _prevalidated_property_names(run))
        random_baseline = run.get("matched_random_parameter_baseline", {})
        random_echidna = random_baseline.get("echidna")
        if random_echidna and isinstance(random_echidna.get("output"), str):
            random_echidna.update(echidna_corpus_evidence(random_echidna["output"]))
            random_prevalidated = {
                name.rsplit(".", 1)[-1].split("(", 1)[0]
                for row in random_baseline.get("seed_candidates", [])
                for tx in row.get("replay", {}).get("transactions", [])
                for name in (tx.get("all_property_values") or {})
                if tx["all_property_values"].get(name) is False
            }
            _classify_echidna_failures(random_echidna, random_prevalidated)
    for baseline_rows in report.get("native_echidna_baselines", {}).values():
        for item in baseline_rows:
            echidna = item.get("echidna")
            if echidna and isinstance(echidna.get("output"), str):
                echidna.update(echidna_corpus_evidence(echidna["output"]))
                _classify_echidna_failures(echidna, set())
    report["preprocessing_benchmark"] = benchmark_preprocessing(preprocessing_repetitions)
    report["additional_baselines"] = {
        "native_echidna": "每项目每重复从空语料开始，测试预算/属性集与 Agent 配置一致。",
        "matched_random_parameter": "沿用 Agent A 的函数序列与交易数，仅随机化 ABI 参数和 sender；对照 Agent B 的实例化质量。",
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--repair-limit", type=int, default=1)
    parser.add_argument("--test-limit", type=int, default=100)
    parser.add_argument("--process-timeout", type=int, default=45)
    parser.add_argument("--projects", nargs="+", choices=list(DATASETS), default=list(DATASETS))
    parser.add_argument("--skip-echidna", action="store_true")
    parser.add_argument("--augment-existing", action="store_true",
                        help="不重新调用 Agent；为现有矩阵补同预算原生 Echidna 与匹配随机种子基线")
    parser.add_argument("--preprocess-repetitions", type=int, default=10,
                        help="预处理与本地 Token 编码的重复计时次数")
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 5:
        parser.error("repetitions 应在 1–5 之间")
    output = ROOT / "deepseek/结果/DeepSeek分组闭环实验.json"
    if args.augment_existing:
        report = json.loads(output.read_text(encoding="utf-8"))
        report = augment_baselines(report, test_limit=args.test_limit,
                                   process_timeout=args.process_timeout,
                                   preprocessing_repetitions=args.preprocess_repetitions)
    else:
        report = run_experiment(repetitions=args.repetitions, repair_limit=args.repair_limit,
                                test_limit=args.test_limit, process_timeout=args.process_timeout,
                                run_echidna_campaign=not args.skip_echidna,
                                projects=args.projects)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "runs": len(report["runs"]),
                      "total_elapsed_seconds": report["total_elapsed_seconds"]}, ensure_ascii=False),
          flush=True)


if __name__ == "__main__":
    main()
