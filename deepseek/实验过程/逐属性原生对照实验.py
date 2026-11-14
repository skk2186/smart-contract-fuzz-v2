#!/usr/bin/env python3
"""对逐属性 Agent 种子注入与空语料原生 Echidna 做小规模配对比较。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/功能")]

from AgentB import to_echidna_sequence
from 属性种子上下文 import PROJECTS, load_project_context
from 种子验证 import new_seed_id, run_echidna
from 运行Agent种子流程 import run_project


def _parse_property(specification: str) -> tuple[str, str]:
    try:
        project, property_id = specification.split(":", 1)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("属性格式应为 PROJECT:PROPERTY_ID") from exc
    if project not in PROJECTS or not property_id:
        raise argparse.ArgumentTypeError(f"无效属性标识：{specification}")
    return project, property_id


def _campaign(project: str, prop: dict[str, Any], root: Path, *,
              treatment: str, seed: int, test_limit: int, timeout: int,
              stop_on_fail: bool, input_seed: Path | None) -> dict[str, Any]:
    coverage = root / "coverage"
    coverage.mkdir(parents=True, exist_ok=True)
    if input_seed is not None:
        shutil.copy2(input_seed, coverage / input_seed.name)
    initial_files = sorted(path.name for path in coverage.glob("*.txt"))
    property_name = prop["property"].rsplit(".", 1)[-1].split("(", 1)[0]
    try:
        result = run_echidna(
            project, root, property_name=property_name,
            test_limit=test_limit, timeout=max(1, timeout), seed=seed,
            test_mode="property" if property_name.startswith("echidna_") else "assertion",
            property_prefix=property_name,
            seq_len=8, shrink_limit=1, stop_on_fail=stop_on_fail,
            disable_slither=True)
        result.update({"treatment": treatment, "property_id": prop["property_id"],
                       "expected_external_seed_count": int(input_seed is not None),
                       "initial_corpus_files": initial_files,
                       "initial_corpus_empty": not initial_files,
                       "specific_input_seed_replay_verified": bool(
                           input_seed is not None and any(
                               input_seed.name in line
                               for line in result.get("replayed_lines", []))),
                       "external_seed_loaded_and_replayed": bool(
                           input_seed is not None and
                           result.get("loaded_seed_count", 0) >= 1 and
                           any(input_seed.name in line
                               for line in result.get("replayed_lines", [])) and
                           not result.get("worker_crashes")),
                       "native_empty_corpus_verified": bool(
                           treatment == "native_echidna" and not initial_files and
                           result.get("initial_corpus_file_count") == 0)})
        return result
    except Exception as exc:
        return {"treatment": treatment, "property_id": prop["property_id"],
                "status": "echidna_error", "timed_out": False,
                "error": f"{type(exc).__name__}: {str(exc)[:1200]}",
                "expected_external_seed_count": int(input_seed is not None),
                "initial_corpus_files": initial_files,
                "initial_corpus_empty": not initial_files}


def _seed_violations(seed_result: dict[str, Any]) -> list[dict[str, Any]]:
    found = []
    for candidate in seed_result.get("candidate_results", []):
        for replay in candidate.get("replay_attempts", []):
            if replay.get("target_property_violation"):
                found.append({"candidate_id": candidate.get("candidate_id"),
                              "seed_id": candidate.get("seed_id"),
                              "elapsed_from_run_start_seconds": replay.get(
                                  "elapsed_from_run_start_seconds"),
                              "violation": replay["target_property_violation"]})
    return found


def _discovery(campaign: dict[str, Any], *, seed_result: dict[str, Any] | None,
               preparation_seconds: float) -> dict[str, Any]:
    seed_findings = _seed_violations(seed_result or {})
    initial_failures = campaign.get("initial_state_failures", [])
    noninitial_failures = [line for line in campaign.get("property_failures", [])
                           if line not in initial_failures]
    if seed_findings:
        first_seed = min((item["elapsed_from_run_start_seconds"] for item in seed_findings
                          if item.get("elapsed_from_run_start_seconds") is not None),
                         default=preparation_seconds)
        return {"property_violation_discovered": True,
                "discovery_source": "anvil_verified_seed_prevalidation",
                "first_discovery_time_seconds": first_seed,
                "first_discovery_time_basis": "V2 启动至 Anvil 首次观察到目标属性为假的墙钟时间",
                "seed_prevalidation_violation_count": len(seed_findings),
                "echidna_initial_state_failures": initial_failures,
                "echidna_noninitial_failures": noninitial_failures}
    if noninitial_failures:
        observed = campaign.get("first_property_failure_observed_seconds")
        return {"property_violation_discovered": True,
                "discovery_source": "echidna_campaign",
                "first_discovery_time_seconds": (preparation_seconds + observed
                                                   if seed_result is not None and observed is not None
                                                   else observed),
                "first_discovery_time_basis": (
                    "V2 种子准备时间加 Echidna 首次输出失败时的 campaign 墙钟时间"
                    if seed_result is not None else
                    "Native Echidna 首次输出失败时的 campaign 墙钟时间"),
                "first_discovery_time_is_upper_bound": campaign.get(
                    "property_failure_time_is_upper_bound", False),
                "seed_prevalidation_violation_count": 0,
                "echidna_initial_state_failures": initial_failures,
                "echidna_noninitial_failures": noninitial_failures}
    return {"property_violation_discovered": False,
            "discovery_source": "initial_state_failure_only" if initial_failures else "none_observed",
            "first_discovery_time_seconds": None,
            "first_discovery_time_is_right_censored": True,
            "echidna_initial_state_failures": initial_failures,
            "echidna_noninitial_failures": []}


def _prepare_diagnostic(project: str, property_id: str, property_row: dict[str, Any],
                        context: dict[str, Any], root: Path, seed: int) -> dict[str, Any] | None:
    candidate_row = next((row for row in property_row.get("candidate_results", [])
                          if row.get("seed_class") == "echidna_only_diagnostic_candidate"
                          and row.get("concrete_seed")), None)
    if candidate_row is None:
        return None
    prop_context = next(item for item in context["properties"]
                       if item["property_id"] == property_id)
    candidate = {"candidate_id": candidate_row["candidate_id"],
                 "property_id": property_id, "steps": candidate_row["plan"]}
    sequence = to_echidna_sequence(candidate,
                                   candidate_row["concrete_seed"]["transactions"], context)
    root.mkdir(parents=True, exist_ok=True)
    coverage = root / "coverage"
    coverage.mkdir(parents=True, exist_ok=True)
    diagnostic_id = new_seed_id()
    source_root = root.parent / "diagnostic-seeds"
    source_root.mkdir(parents=True, exist_ok=True)
    path = source_root / f"{diagnostic_id}.txt"
    path.write_text(json.dumps(sequence, ensure_ascii=False), encoding="utf-8")
    result = _campaign(project, prop_context, root, treatment="echidna_only_diagnostic",
                       seed=seed, test_limit=20, timeout=30,
                       stop_on_fail=True, input_seed=path)
    return {"seed_class": "echidna_only_diagnostic_not_evm_valid",
            "diagnostic_seed_id": diagnostic_id,
            "source_candidate_id": candidate_row["candidate_id"],
            "excluded_from_v2_comparison": True,
            "campaign": result}


def _run_property(project: str, property_id: str, *, experiment_root: Path,
                  test_limit: int, time_budget: int, base_seed: int,
                  token_budget: int, diagnostic: bool,
                  generation_override: dict[str, Any] | None = None,
                  preparation_seconds_override: float | None = None) -> dict[str, Any]:
    context = load_project_context(project, [property_id])
    prop = context["properties"][0]
    generation_root = experiment_root / "seed-generation" / project / property_id
    generation_root.mkdir(parents=True, exist_ok=True)
    if generation_override is None:
        generation_started = time.monotonic()
        generation = run_project(
            project, [property_id], max_candidates=1, max_steps=8,
            repairs=1, planning_repairs=1, echidna_limit=test_limit,
            echidna_timeout=max(1, time_budget), echidna_seed=base_seed,
            token_budget=token_budget, wall_budget=max(1, time_budget),
            run_fuzzer=False, run_root=generation_root)
        preparation_seconds = round(time.monotonic() - generation_started, 3)
    else:
        generation = generation_override
        preparation_seconds = float(preparation_seconds_override or
                                    generation.get("total_elapsed_seconds", 0))
    generation_path = generation_root / "逐属性Agent种子流程.json"
    generation_path.write_text(json.dumps(generation, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    property_row = generation["property_results"][0]
    valid_seed = next((row for row in property_row.get("candidate_results", [])
                       if row.get("status") == "executable" and row.get("corpus_file")), None)
    concrete_candidate = next((row for row in property_row.get("candidate_results", [])
                               if row.get("concrete_seed")), None)
    archived_seed = ROOT / valid_seed["corpus_file"] if valid_seed else None

    pair_seed = base_seed
    test_runs: dict[str, dict[str, Any]] = {}
    for treatment in ("native_echidna", "v2_seeded"):
        campaign_root = (experiment_root / "campaigns" / "same_test_budget" /
                         treatment / project / property_id)
        test_runs[treatment] = _campaign(
            project, prop, campaign_root, treatment=treatment, seed=pair_seed,
            test_limit=test_limit, timeout=max(30, time_budget), stop_on_fail=False,
            input_seed=archived_seed if treatment == "v2_seeded" else None)

    # 以 Agent A 开始至 V2 Echidna 结束作为 V2 端到端时间；种子生成阶段已经计入。
    v2_remaining = max(0, int(time_budget - preparation_seconds))
    time_runs: dict[str, dict[str, Any]] = {}
    native_root = (experiment_root / "campaigns" / "same_end_to_end_time" /
                   "native_echidna" / project / property_id)
    time_runs["native_echidna"] = _campaign(
        project, prop, native_root, treatment="native_echidna", seed=pair_seed,
        test_limit=10_000_000, timeout=time_budget, stop_on_fail=True, input_seed=None)
    v2_root = (experiment_root / "campaigns" / "same_end_to_end_time" /
               "v2_seeded" / project / property_id)
    if v2_remaining > 0:
        time_runs["v2_seeded"] = _campaign(
            project, prop, v2_root, treatment="v2_seeded", seed=pair_seed,
            test_limit=10_000_000, timeout=v2_remaining, stop_on_fail=True,
            input_seed=archived_seed)
    else:
        time_runs["v2_seeded"] = {"treatment": "v2_seeded", "property_id": property_id,
                                  "status": "time_budget_exhausted_before_echidna",
                                  "timed_out": False, "elapsed_seconds": 0,
                                  "initial_corpus_file_count": 0,
                                  "expected_external_seed_count": int(archived_seed is not None)}

    comparisons = {}
    for budget_name, runs in (("same_test_budget", test_runs),
                              ("same_end_to_end_time", time_runs)):
        baseline, treatment = runs["native_echidna"], runs["v2_seeded"]
        baseline_cov = baseline.get("unique_instructions")
        treatment_cov = treatment.get("unique_instructions")
        baseline_find = _discovery(baseline, seed_result=None, preparation_seconds=0)
        treatment_find = _discovery(treatment, seed_result=property_row,
                                    preparation_seconds=preparation_seconds)
        comparisons[budget_name] = {
            "paired_property_id": property_id,
            "same_random_seed": baseline.get("seed") == treatment.get("seed"),
            "echidna_parameters_match_except_campaign_timeout_and_corpus_path": True,
            "baseline": {"elapsed_seconds": baseline.get("elapsed_seconds"),
                         "end_to_end_elapsed_seconds": baseline.get("elapsed_seconds"),
                         "status": baseline.get("status"),
                         "exit_code": baseline.get("exit_code"),
                         "timed_out": baseline.get("timed_out", False),
                         "test_limit": baseline.get("test_limit"),
                         "stop_on_fail": baseline.get("stop_on_fail"),
                         "unique_instructions": baseline_cov,
                         "coverage_source": baseline.get("coverage_source"),
                         "initial_corpus_file_count": baseline.get("initial_corpus_file_count"),
                         "initial_corpus_files": baseline.get("initial_corpus_files", []),
                         "loaded_seed_count": baseline.get("loaded_seed_count", 0),
                         "replayed_seed_count": baseline.get("replayed_sequence_count", 0),
                         "fuzzing_transactions": baseline.get("fuzzing_transactions", 0),
                         "fuzzing_cases": baseline.get("fuzzing_cases", 0),
                         "fuzzing_progress_count": baseline.get("fuzzing_progress_count", 0),
                         "fuzzing_progress_limit": baseline.get("fuzzing_progress_limit", 0),
                         "worker_crashes": baseline.get("worker_crashes", []),
                         "mutation_evidence": baseline.get("mutation_evidence", False),
                         "property_discovery": baseline_find,
                         "target_property_results": baseline.get("target_property_results", []),
                         "property_failures": baseline.get("property_failures", []),
                         "initial_state_failures": baseline.get("initial_state_failures", []),
                         "campaign_output_excerpt": baseline.get("output", ""),
                         "external_seed_loaded": baseline.get("loaded_seed_count", 0) > 0,
                         "native_empty_corpus_verified": baseline.get("native_empty_corpus_verified", False),
                         "timed_out": baseline.get("timed_out", False)},
            "v2": {"seed_preparation_seconds": preparation_seconds,
                   "campaign_elapsed_seconds": treatment.get("elapsed_seconds"),
                   "end_to_end_elapsed_seconds": (preparation_seconds +
                                                    (treatment.get("elapsed_seconds") or 0)),
                   "status": treatment.get("status"),
                   "exit_code": treatment.get("exit_code"),
                   "timed_out": treatment.get("timed_out", False),
                   "test_limit": treatment.get("test_limit"),
                   "stop_on_fail": treatment.get("stop_on_fail"),
                   "unique_instructions": treatment_cov,
                   "coverage_source": treatment.get("coverage_source"),
                   "fuzzing_transactions": treatment.get("fuzzing_transactions", 0),
                   "fuzzing_cases": treatment.get("fuzzing_cases", 0),
                   "fuzzing_progress_count": treatment.get("fuzzing_progress_count", 0),
                   "fuzzing_progress_limit": treatment.get("fuzzing_progress_limit", 0),
                   "worker_crashes": treatment.get("worker_crashes", []),
                   "initial_corpus_files": treatment.get("initial_corpus_files", []),
                   "property_discovery": treatment_find,
                   "target_property_results": treatment.get("target_property_results", []),
                   "property_failures": treatment.get("property_failures", []),
                   "initial_state_failures": treatment.get("initial_state_failures", []),
                   "campaign_output_excerpt": treatment.get("output", ""),
                   "input_seed_id": valid_seed.get("seed_id") if valid_seed else None,
                   "input_seed_count": treatment.get("initial_corpus_file_count", 0),
                   "loaded_seed_count": treatment.get("loaded_seed_count", 0),
                   "replayed_seed_count": treatment.get("replayed_sequence_count", 0),
                   "specific_input_seed_replay_verified": treatment.get(
                       "specific_input_seed_replay_verified", False),
                   "seed_load_replay_verified": treatment.get(
                       "external_seed_loaded_and_replayed", False),
                   "mutation_evidence": treatment.get("mutation_evidence", False),
                   "timed_out": treatment.get("timed_out", False),
                   "seed_generation_status": property_row.get("status")},
            "coverage_delta_unique_instructions": (
                treatment_cov - baseline_cov
                if treatment_cov is not None and baseline_cov is not None else None),
            "violation_discovery_delta": (
                int(treatment_find["property_violation_discovered"]) -
                int(baseline_find["property_violation_discovered"])),
        }

    diagnosis = None
    if diagnostic:
        diagnosis = _prepare_diagnostic(
            project, property_id, property_row, context,
            experiment_root / "diagnostics" / project / property_id,
            seed=pair_seed)

    return {"project": project, "property_id": property_id,
            "property": prop["property"],
            "property_kind": "assertion" if not prop["property"].split(".")[-1].startswith("echidna_") else "echidna_property",
            "dependency_status": prop.get("dependency_status"),
            "seed_generation": property_row,
            "seed_generation_success": bool(concrete_candidate),
            "candidate_plan_success": bool(property_row.get("candidate_results")),
            "evm_executable": bool(valid_seed),
            "evm_valid_seed_id": valid_seed.get("seed_id") if valid_seed else None,
            "candidate_seed_class": valid_seed.get("seed_class") if valid_seed else
                                    next((row.get("seed_class") for row in property_row.get("candidate_results", [])), "none"),
            "agent_api_usage": generation.get("api_usage"),
            "seed_preparation_seconds": preparation_seconds,
            "comparisons": comparisons,
            "echidna_only_diagnostic": diagnosis}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--property", dest="properties", action="append", type=_parse_property,
                        required=True, help="重复指定 PROJECT:PROPERTY_ID")
    parser.add_argument("--test-limit", type=int, default=80)
    parser.add_argument("--time-budget-seconds", type=int, default=120,
                        help="每条属性的相同端到端墙钟预算")
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--token-budget-per-property", type=int, default=120_000)
    parser.add_argument("--reuse-generated-seeds-from", type=Path,
                        help="重跑 Echidna 配对条件时复用既有报告中的逐属性 Agent/EVM 种子，不再调用 API")
    parser.add_argument("--skip-echidna-only-diagnostic", action="store_true")
    args = parser.parse_args()
    if args.test_limit < 1 or args.time_budget_seconds < 1 or args.token_budget_per_property < 1:
        parser.error("预算参数必须为正数")
    deduplicated = list(dict.fromkeys(args.properties))
    experiment_started = time.monotonic()
    started_at_utc = datetime.now(timezone.utc).isoformat()
    experiment_id = uuid.uuid4().hex
    experiment_root = ROOT / "deepseek/结果/逐属性原生对照实验" / experiment_id
    experiment_root.mkdir(parents=True, exist_ok=False)
    previous_report = None
    previous_root = None
    previous_properties: dict[tuple[str, str], dict[str, Any]] = {}
    if args.reuse_generated_seeds_from:
        previous_path = args.reuse_generated_seeds_from.resolve()
        previous_report = json.loads(previous_path.read_text(encoding="utf-8"))
        previous_root = previous_path.parent
        previous_properties = {(row["project"], row["property_id"]): row
                              for row in previous_report.get("properties", [])}
        missing = [f"{project}/{property_id}" for project, property_id in deduplicated
                   if (project, property_id) not in previous_properties]
        if missing:
            parser.error(f"复用报告没有这些属性：{missing}")
    sample_set = [{"project": project, "property_id": property_id}
                  for project, property_id in deduplicated]
    report: dict[str, Any] = {
        "schema_version": 1, "experiment_id": experiment_id,
        "started_at_utc": started_at_utc,
        "sample_set_fixed_before_agent_calls": sample_set,
        "experimental_conditions": {
            "baseline": "Native Echidna 从空 coverage 目录启动，不注入外部语料",
            "v2": "逐属性 Agent A/B；仅 Anvil 成功的 EVM 有效种子进入主比较语料",
            "echidna_parameters": {"workers": 1, "seq_len": 8, "shrink_limit": 1,
                                   "disable_slither": True},
            "same_test_budget": {"test_limit": args.test_limit,
                                 "stop_on_fail": False},
            "same_end_to_end_time": {"seconds_per_property": args.time_budget_seconds,
                                     "test_limit": 10_000_000,
                                     "stop_on_fail": True,
                                     "v2_echidna_time_is_remaining_after_seed_preparation": True},
            "random_seed": args.seed,
            "slither_reports_precomputed": True,
            "excluded_from_end_to_end_time": ["Slither 首次编译/静态分析，使用仓库既有报告"],
            "diagnostic_corpus_excluded_from_v2_comparison": True,
        },
        "properties": [],
    }
    if previous_report:
        report["seed_generation_reuse"] = {
            "source_report": str(args.reuse_generated_seeds_from.resolve().relative_to(ROOT)),
            "additional_agent_api_calls": 0,
            "original_actual_token_usage_and_cost_retained": True,
            "correction_reason": "仅重新运行 Echidna 条件，不改变已有 Agent 响应、种子或成本记录",
        }
    print(f"实验 {experiment_id}：固定属性 {len(sample_set)} 条", flush=True)
    for index, (project, property_id) in enumerate(deduplicated, start=1):
        print(f"[{index}/{len(deduplicated)}] {project}/{property_id}: 生成单属性种子并配对回放", flush=True)
        generation_override = None
        preparation_override = None
        if previous_root is not None:
            prior = previous_properties[(project, property_id)]
            generation_path = (previous_root / "seed-generation" / project /
                               property_id / "逐属性Agent种子流程.json")
            generation_override = json.loads(generation_path.read_text(encoding="utf-8"))
            preparation_override = prior.get("seed_preparation_seconds")
        result = _run_property(
            project, property_id, experiment_root=experiment_root,
            test_limit=args.test_limit, time_budget=args.time_budget_seconds,
            base_seed=args.seed + index - 1,
            token_budget=args.token_budget_per_property,
            diagnostic=not args.skip_echidna_only_diagnostic,
            generation_override=generation_override,
            preparation_seconds_override=preparation_override)
        report["properties"].append(result)
        output = experiment_root / "逐属性原生对照实验.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"project": project, "property_id": property_id,
                          "evm_executable": result["evm_executable"],
                          "same_test_budget_delta": result["comparisons"]["same_test_budget"][
                              "coverage_delta_unique_instructions"],
                          "same_time_budget_delta": result["comparisons"]["same_end_to_end_time"][
                              "coverage_delta_unique_instructions"],
                          "api_tokens": (result.get("agent_api_usage") or {}).get("total_tokens")},
                         ensure_ascii=False), flush=True)
    api_totals = [row.get("agent_api_usage") or {} for row in report["properties"]]
    report["aggregate"] = {
        "property_count": len(report["properties"]),
        "candidate_generation_success_count": sum(row.get("seed_generation_success", False)
                                                   for row in report["properties"]),
        "candidate_plan_success_count": sum(row.get("candidate_plan_success", False)
                                            for row in report["properties"]),
        "evm_executable_seed_count": sum(row.get("evm_executable", False)
                                         for row in report["properties"]),
        "external_seed_load_replay_verified_count": sum(
            row["comparisons"]["same_test_budget"]["v2"]["seed_load_replay_verified"]
            for row in report["properties"]),
        "actual_api_tokens": sum(row.get("total_tokens", 0) for row in api_totals),
        "estimated_api_cost_usd_offpeak": str(sum(
            (float(row.get("estimated_cost_usd_offpeak", 0)) for row in api_totals), 0.0)),
        "estimated_api_cost_usd_peak": str(sum(
            (float(row.get("estimated_cost_usd_peak", 0)) for row in api_totals), 0.0)),
        "api_request_attempts": sum(row.get("request_attempts", 0) for row in api_totals),
        "failed_api_request_attempts": sum(row.get("failed_request_attempts", 0) for row in api_totals),
        "unmetered_api_attempts": sum(row.get("unmetered_attempts", 0) for row in api_totals),
        "seed_generation_success_rate": (sum(row.get("seed_generation_success", False)
                                             for row in report["properties"]) /
                                         max(1, len(report["properties"]))),
        "evm_executable_rate": (sum(row.get("evm_executable", False)
                                   for row in report["properties"]) /
                               max(1, len(report["properties"]))),
        "same_test_budget_coverage_deltas": {
            f"{row['project']}/{row['property_id']}": row["comparisons"]["same_test_budget"][
                "coverage_delta_unique_instructions"] for row in report["properties"]},
        "same_end_to_end_time_coverage_deltas": {
            f"{row['project']}/{row['property_id']}": row["comparisons"]["same_end_to_end_time"][
                "coverage_delta_unique_instructions"] for row in report["properties"]},
        "summed_per_property_elapsed_seconds": {
            "same_test_budget": {
                "native_echidna_campaigns": sum(
                    row["comparisons"]["same_test_budget"]["baseline"]["end_to_end_elapsed_seconds"]
                    for row in report["properties"]),
                "v2_including_seed_preparation": sum(
                    row["comparisons"]["same_test_budget"]["v2"]["end_to_end_elapsed_seconds"]
                    for row in report["properties"]),
            },
            "same_end_to_end_time": {
                "native_echidna_campaigns": sum(
                    row["comparisons"]["same_end_to_end_time"]["baseline"]["end_to_end_elapsed_seconds"]
                    for row in report["properties"]),
                "v2_including_seed_preparation": sum(
                    row["comparisons"]["same_end_to_end_time"]["v2"]["end_to_end_elapsed_seconds"]
                    for row in report["properties"]),
            },
        },
        "property_violation_discovery_counts": {
            budget: {
                "native_echidna": sum(
                    row["comparisons"][budget]["baseline"]["property_discovery"][
                        "property_violation_discovered"] for row in report["properties"]),
                "v2": sum(
                    row["comparisons"][budget]["v2"]["property_discovery"][
                        "property_violation_discovered"] for row in report["properties"]),
            }
            for budget in ("same_test_budget", "same_end_to_end_time")
        },
    }
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["total_experiment_elapsed_seconds"] = round(
        time.monotonic() - experiment_started, 3)
    output = experiment_root / "逐属性原生对照实验.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"结果：{output.relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
