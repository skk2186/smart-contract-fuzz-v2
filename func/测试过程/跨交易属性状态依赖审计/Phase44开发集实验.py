#!/usr/bin/env python3
"""Phase44 固定开发集配对实验。只读取 Phase43 原始数据，所有新输出写入 Phase44。"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import statistics
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/测试过程/跨交易属性状态依赖审计")]
phase = importlib.import_module("Phase43批量实验")

OUTPUT_BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase44-20261124"
ACTIVE_SPLIT = "dev"
OUTPUT = OUTPUT_BASE / ACTIVE_SPLIT
MAX_LENGTH = 64
CANDIDATE_TOTAL_BUDGET = 24
PER_GROUP_BUDGET = CANDIDATE_TOTAL_BUDGET // 2
FUZZ_SECONDS = 20
FUZZ_TEST_LIMIT = 100_000_000
SEED = 4301
FUZZ_SEEDS = [SEED]
FUZZ_VALID_STATUSES = {"completed", "native_counterexample"}
DEV_IDS = [
    "OLYMPIA-001", "OLYMPIA-002", "OLYMPIA-003", "OLYMPIA-004",
    "OLYMPIA-026", "OLYMPIA-027", "OLYMPIA-028", "OLYMPIA-029",
    "OLYMPIA-051", "OLYMPIA-052", "OLYMPIA-053", "OLYMPIA-054",
    "OLYMPIA-076", "OLYMPIA-077", "OLYMPIA-078", "OLYMPIA-079",
]
EVAL_IDS = [f"OLYMPIA-{i:03d}" for i in range(1, 101) if f"OLYMPIA-{i:03d}" not in set(DEV_IDS)]
ACTIVE_IDS = DEV_IDS
ALL_ACTIVE_IDS = DEV_IDS
ACTIVE_SHARD: dict[str, int] | None = None


def read(path: Path, default: Any = None) -> Any:
    return phase.read_json(path, default)


def write(path: Path, value: Any) -> None:
    phase.write_json(path, value)


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def covered_source_lines(run_dir: Path) -> set[str]:
    """Read exact Solidity source-line coverage from Echidna's LCOV output."""
    covered: set[str] = set()
    for path in sorted((run_dir / "corpus").glob("covered.*.lcov")):
        source = ""
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if raw.startswith("SF:"):
                source = raw[3:]
            elif raw.startswith("DA:") and source:
                parts = raw[3:].split(",", 1)
                if len(parts) == 2 and int(parts[1]) > 0:
                    covered.add(f"{source}#{parts[0]}")
    return covered


def find_sample(sample_id: str) -> dict[str, Any]:
    manifest = read(phase.MANIFEST)
    return next(item for item in manifest["dataset"]["samples"]
                if item["sample_id"] == sample_id)


def task_paths(sample_id: str) -> tuple[Path, Path]:
    return (phase.RESULT / "tasks" / sample_id,
            OUTPUT / "tasks" / sample_id)


def candidate_metadata(context: dict[str, Any]) -> dict[str, Any]:
    return {"property_id": context["properties"][0]["property_id"]}


def executable_feedback(feedback: dict[str, Any] | None) -> bool:
    return bool(feedback and feedback.get("replay_status") == "executable")


def candidate_coverage_replay(sample: dict[str, Any], source: Path,
                              output_dir: Path, sequence: list[dict[str, Any]],
                              context: dict[str, Any]) -> dict[str, Any]:
    return phase.run_echidna(
        sample, source, output_dir, seed=SEED, timeout=10, test_limit=0,
        seed_sequences=[sequence], candidate=candidate_metadata(context), context=context,
        working_directory=output_dir / "echidna-cwd")


def run_candidates() -> dict[str, Any]:
    phase.MAX_SEQUENCE_LENGTH = MAX_LENGTH
    phase.E3_CANDIDATE_BUDGET = PER_GROUP_BUDGET
    phase.MANIFEST = phase.RESULT / "dataset-manifest.json"
    OUTPUT.mkdir(parents=True, exist_ok=True)
    configuration = {
        "phase": f"Phase44-{ACTIVE_SPLIT}",
        "split_rule": "For each dimension, the first four samples in frozen Phase43 manifest order are development tasks.",
        "development_sample_ids": DEV_IDS,
        "evaluation_sample_ids": EVAL_IDS,
        "active_split": ACTIVE_SPLIT,
        "split_sample_ids": ALL_ACTIVE_IDS,
        "worker_sample_ids": ALL_ACTIVE_IDS,
        "sequence_length_all_groups": MAX_LENGTH,
        "candidate_replay_seed": SEED,
        "fuzz_seeds_all_groups": FUZZ_SEEDS,
        "fuzz_seconds_per_group_all_groups": FUZZ_SECONDS,
        "fuzz_test_limit": FUZZ_TEST_LIMIT,
        "extension_candidate_budget_per_task": CANDIDATE_TOTAL_BUDGET,
        "extension_candidate_budget_G1": PER_GROUP_BUDGET,
        "extension_candidate_budget_G2": PER_GROUP_BUDGET,
        "candidate_replay_engines": ["PyEVM feedback replay", "Echidna native corpus replay"],
        "echidna_working_directory_policy": "unique per-run directory to isolate crytic-export/combined_solc.json",
        "official_answers_used_by_generator": False,
        "official_answers_use": "separate reachability diagnostic only",
        "source_commit": "6cc891129640546e014c84eb11ec84e8c96cf1f7",
        "echidna_version": "2.3.2",
    }
    if ACTIVE_SHARD:
        worker_dir = OUTPUT / "workers" / f"shard-{ACTIVE_SHARD['index']}-of-{ACTIVE_SHARD['count']}"
        write(worker_dir / "experiment-config.json", configuration)
        write(worker_dir / "shard-info.json",
              {"worker_shard": ACTIVE_SHARD, "worker_sample_ids": ACTIVE_IDS})
        progress_path = OUTPUT / "progress" / f"candidate-stage-progress-shard-{ACTIVE_SHARD['index']}.json"
        summary_path = OUTPUT / f"candidate-stage-summary-shard-{ACTIVE_SHARD['index']}.json"
    else:
        write(OUTPUT / "experiment-config.json", configuration)
        progress_path = OUTPUT / "candidate-stage-progress.json"
        summary_path = OUTPUT / "candidate-stage-summary.json"
    summary: dict[str, Any] = {"configuration": configuration, "tasks": {}}

    for sample_id in ACTIVE_IDS:
        baseline_dir, task_out = task_paths(sample_id)
        task_out.mkdir(parents=True, exist_ok=True)
        saved_ledger = read(task_out / "candidate-ledger.json")
        if saved_ledger is not None:
            summary["tasks"][sample_id] = saved_ledger
            write(progress_path, summary)
            continue
        sample = find_sample(sample_id)
        source = phase.RESULT / sample["files"]["source"]["path"]
        context = read(baseline_dir / "agent/property-context.json")
        artifact = read(baseline_dir / "analysis/compiler-artifact.json")
        analysis = read(baseline_dir / "analysis/property-analysis.json")
        e1_path = baseline_dir / "E1/sequence.json"
        e2_path = baseline_dir / "E2/sequence.json"
        e1 = read(e1_path, []) or []
        e2 = read(e2_path, []) or []
        e1_feedback = read(baseline_dir / "E1/v2-feedback.json")
        e2_feedback = read(baseline_dir / "E2/v2-feedback.json")
        if context is None or artifact is None or analysis is None:
            summary["tasks"][sample_id] = {"status": "missing_frozen_input"}
            continue

        # Empty E1 tasks remain in the fixed set; the extension begins from an
        # empty sequence and may use only ABI/action evidence and runtime state.
        base_sequence = e1
        if not e1_feedback or not executable_feedback(e1_feedback):
            e1_feedback, _ = phase.property_replay(source, artifact, e1)
        write(task_out / "inputs.json", {
            "sample_id": sample_id,
            "source_sha256": sha256(source),
            "E1_sequence_sha256": sha256(e1_path),
            "E2_sequence_sha256": sha256(e2_path),
            "E1_sequence": e1,
            "E2_sequence": e2,
            "E1_feedback": e1_feedback,
            "E2_feedback": e2_feedback,
            "E1_sequence_present": bool(e1),
            "E2_sequence_present": bool(e2),
        })

        e1_seed_only = None
        e2_seed_only = None
        if e1:
            e1_seed_only = candidate_coverage_replay(
                sample, source, task_out / "E1-seed-only", e1, context)
        if e2:
            e2_seed_only = candidate_coverage_replay(
                sample, source, task_out / "E2-seed-only", e2, context)
        baseline_coverage = ((e1_seed_only or {}).get("unique_instructions")
                             if e1 else 0)
        baseline_source_lines = (covered_source_lines(task_out / "E1-seed-only")
                                 if e1 else set())

        group_results = {}
        for group, bind in (("G1", False), ("G2", True)):
            result = phase.e3_group(
                group, sample, base_sequence, e1_feedback, context, artifact, analysis,
                task_out, bind=bind)
            group_results[group] = result

        candidate_rows = []
        coverage_gain_count = 0
        for group in ("G1", "G2"):
            for row in group_results[group]["candidates"]:
                feedback = row.get("feedback") or {}
                sequence = row["sequence"]
                index = row["candidate_index"]
                native = candidate_coverage_replay(
                    sample, source,
                    task_out / group / "candidate-native" / f"candidate-{index:02d}",
                    sequence, context)
                candidate_coverage = native.get("unique_instructions")
                coverage_delta = (candidate_coverage - baseline_coverage
                                  if candidate_coverage is not None and baseline_coverage is not None
                                  else None)
                candidate_source_lines = covered_source_lines(
                    task_out / group / "candidate-native" / f"candidate-{index:02d}")
                new_source_lines = sorted(candidate_source_lines - baseline_source_lines)
                new_coverage = bool(new_source_lines)
                coverage_gain_count += int(new_coverage)
                candidate_rows.append({
                    "group": group,
                    "candidate_index": index,
                    "operator": row.get("operator"),
                    "proposal_reason": row.get("proposal_reason"),
                    "proposal_evidence": row.get("proposal_evidence"),
                    "phase37_binding_status": row.get("phase37_binding_status"),
                    "phase37_matching_constraints": row.get("phase37_matching_constraints"),
                    "sequence": sequence,
                    "sequence_fingerprint": phase.sequence_fingerprint(sequence),
                    "pyevm_replay_status": row.get("replay_status"),
                    "pyevm_execution_succeeded": row.get("replay_status") == "executable",
                    "pyevm_target_property": feedback.get("property_value"),
                    "pyevm_counterexample_reached": feedback.get("counterexample_reached"),
                    "echidna_replayed_seed_count": native.get("replayed_seed_count"),
                    "echidna_target_status": native.get("target_property_status"),
                    "echidna_native_counterexample": native.get("native_counterexample"),
                    "echidna_unique_instructions": candidate_coverage,
                    "coverage_reference_unique_instructions": baseline_coverage,
                    "coverage_delta_proxy": coverage_delta,
                    "new_coverage_relative_to_E1_seed": new_coverage,
                    "covered_source_lines": sorted(candidate_source_lines),
                    "new_covered_source_lines": new_source_lines,
                    "raw_feedback_file": row.get("raw_feedback_file"),
                    "echidna_raw_log": native.get("raw_log"),
                })

        task_record = {
            "sample_id": sample_id,
            "dimension": sample["dimension"],
            "E1_agent_sequence_present": bool(e1),
            "E1_replay_status": e1_feedback.get("replay_status"),
            "E2_repair_sequence_present": bool(e2),
            "E2_repair_applied": bool(read(baseline_dir / "E2/repair.json", {}).get("applied")),
            "E2_replay_status": e2_feedback.get("replay_status") if e2_feedback else None,
            "E1_seed_only_coverage": (e1_seed_only or {}).get("unique_instructions"),
            "E2_seed_only_coverage": (e2_seed_only or {}).get("unique_instructions"),
            "G1_candidate_count": group_results["G1"]["candidate_count"],
            "G1_valid_sequence_count": group_results["G1"]["valid_sequence_count"],
            "G2_candidate_count": group_results["G2"]["candidate_count"],
            "G2_valid_sequence_count": group_results["G2"]["valid_sequence_count"],
            "extension_candidate_total": len(candidate_rows),
            "extension_candidate_budget_respected": len(candidate_rows) <= CANDIDATE_TOTAL_BUDGET,
            "extension_successful_execution_count": sum(
                bool(row["pyevm_execution_succeeded"]) for row in candidate_rows),
            "extension_new_coverage_candidate_count": coverage_gain_count,
            "extension_successful_new_coverage_candidate_count": sum(
                bool(row["pyevm_execution_succeeded"] and
                     row["new_coverage_relative_to_E1_seed"])
                for row in candidate_rows),
            "phase37_binding_status_counts": {
                status: sum(row.get("phase37_binding_status") == status for row in candidate_rows)
                for status in sorted({str(row.get("phase37_binding_status"))
                                      for row in candidate_rows})
            },
            "candidates": candidate_rows,
        }
        write(task_out / "candidate-ledger.json", task_record)
        summary["tasks"][sample_id] = task_record
        write(progress_path, summary)

    completed = list(summary["tasks"].values())
    candidate_count = sum(item.get("extension_candidate_total", 0) for item in completed)
    successful = sum(item.get("extension_successful_execution_count", 0) for item in completed)
    coverage_gains = sum(item.get("extension_new_coverage_candidate_count", 0) for item in completed)
    successful_coverage_gains = sum(
        item.get("extension_successful_new_coverage_candidate_count", 0) for item in completed)
    summary["candidate_stage_totals"] = {
        "task_count": len(summary["tasks"]),
        "candidate_count": candidate_count,
        "successful_execution_count": successful,
        "candidate_count_with_new_source_lines": coverage_gains,
        "successful_candidates_with_new_source_lines": successful_coverage_gains,
        "development_gate_passed": successful_coverage_gains > 0,
        "gate_rule": "At least one individual extension candidate must execute successfully in PyEVM and cover at least one new Solidity source line in its independent Echidna corpus replay compared with the same task's E1 seed-only replay (empty baseline only when E1 is absent).",
    }
    write(summary_path, summary)
    return summary


def summarize_candidates() -> dict[str, Any]:
    progress = read(OUTPUT / "candidate-stage-progress.json", {})
    configuration = read(OUTPUT / "experiment-config.json",
                         progress.get("configuration"))
    if configuration is None:
        worker_configs = sorted((OUTPUT / "workers").glob("shard-*/experiment-config.json"))
        configuration = read(worker_configs[0], {}) if worker_configs else {}
    if configuration:
        configuration["echidna_working_directory_policy"] = (
            "unique per-run directory to isolate crytic-export/combined_solc.json")
        write(OUTPUT / "experiment-config.json", configuration)
    summary: dict[str, Any] = {"configuration": configuration, "tasks": {}}
    for sample_id in ALL_ACTIVE_IDS:
        ledger = read(OUTPUT / "tasks" / sample_id / "candidate-ledger.json")
        if ledger:
            summary["tasks"][sample_id] = ledger
    rows = list(summary["tasks"].values())
    for row in rows:
        candidates = row.get("candidates", [])
        sample_id = row["sample_id"]
        _, task_out = task_paths(sample_id)
        baseline_lines = (covered_source_lines(task_out / "E1-seed-only")
                          if row.get("E1_agent_sequence_present") else set())
        row["E1_seed_only_covered_source_lines"] = sorted(baseline_lines)
        row["E1_seed_only_covered_source_line_count"] = len(baseline_lines)
        for candidate in candidates:
            native_result = read(
                task_out / candidate["group"] / "candidate-native" /
                f"candidate-{candidate['candidate_index']:02d}" / "result.json")
            if native_result:
                candidate["echidna_replayed_seed_count"] = native_result.get("replayed_seed_count")
                candidate["echidna_target_status"] = native_result.get("target_property_status")
                candidate["echidna_native_counterexample"] = native_result.get("native_counterexample")
                candidate["echidna_unique_instructions"] = native_result.get("unique_instructions")
                candidate["echidna_raw_log"] = native_result.get("raw_log")
            raw_log = candidate.get("echidna_raw_log")
            candidate_run_dir = (ROOT / raw_log).parent if raw_log else Path("/")
            candidate_lines = covered_source_lines(candidate_run_dir)
            candidate["covered_source_lines"] = sorted(candidate_lines)
            candidate["new_covered_source_lines"] = sorted(candidate_lines - baseline_lines)
            candidate["new_coverage_relative_to_E1_seed"] = bool(
                candidate["new_covered_source_lines"])
        row["extension_new_coverage_candidate_count"] = sum(
            bool(candidate.get("new_coverage_relative_to_E1_seed"))
            for candidate in candidates)
        row["extension_successful_new_coverage_candidate_count"] = sum(
            bool(candidate.get("pyevm_execution_succeeded") and
                 candidate.get("new_coverage_relative_to_E1_seed"))
            for candidate in candidates)
        write(task_out / "candidate-ledger.json", row)
    successful = sum(row.get("extension_successful_execution_count", 0) for row in rows)
    gains = sum(row.get("extension_new_coverage_candidate_count", 0) for row in rows)
    both = sum(row.get("extension_successful_new_coverage_candidate_count", 0) for row in rows)
    total = sum(row.get("extension_candidate_total", 0) for row in rows)
    summary["candidate_stage_totals"] = {
        "task_count": len(rows),
        "candidate_count": total,
        "successful_execution_count": successful,
        "candidate_count_with_new_source_lines": gains,
        "successful_candidates_with_new_source_lines": both,
        "development_gate_passed": both > 0,
        "gate_rule": "At least one individual extension candidate must execute successfully in PyEVM and cover at least one new Solidity source line in its independent Echidna corpus replay compared with the same task's E1 seed-only replay (empty baseline only when E1 is absent).",
    }
    write(OUTPUT / "candidate-stage-summary.json", summary)
    return summary


def replay_all_candidate_replays_isolated() -> dict[str, Any]:
    """Re-run every frozen seed and extension candidate in a private compile directory."""
    phase.MAX_SEQUENCE_LENGTH = MAX_LENGTH
    records: list[dict[str, Any]] = []
    for sample_id in ACTIVE_IDS:
        baseline_dir, task_out = task_paths(sample_id)
        ledger = read(task_out / "candidate-ledger.json")
        if not ledger:
            continue
        sample = find_sample(sample_id)
        source = phase.RESULT / sample["files"]["source"]["path"]
        context = read(baseline_dir / "agent/property-context.json")
        if context is None:
            continue
        e1 = read(baseline_dir / "E1/sequence.json", []) or []
        e2 = read(baseline_dir / "E2/sequence.json", []) or []
        if e1:
            e1_native = candidate_coverage_replay(
                sample, source, task_out / "E1-seed-only-isolated", e1, context)
            baseline_coverage = e1_native.get("unique_instructions")
            baseline_lines = covered_source_lines(task_out / "E1-seed-only-isolated")
            ledger["E1_seed_only_coverage"] = baseline_coverage
            ledger["E1_seed_only_covered_source_lines"] = sorted(baseline_lines)
            ledger["E1_seed_only_covered_source_line_count"] = len(baseline_lines)
            ledger["E1_seed_only_isolated_raw_log"] = e1_native.get("raw_log")
            records.append({
                "sample_id": sample_id, "kind": "seed_only", "group": "E1",
                "status": e1_native.get("status"), "native_counterexample": e1_native.get("native_counterexample"),
                "raw_log": e1_native.get("raw_log"),
            })
        else:
            baseline_coverage, baseline_lines = 0, set()
            ledger["E1_seed_only_coverage"] = 0
            ledger["E1_seed_only_covered_source_lines"] = []
            ledger["E1_seed_only_covered_source_line_count"] = 0
        if e2:
            e2_native = candidate_coverage_replay(
                sample, source, task_out / "E2-seed-only-isolated", e2, context)
            ledger["E2_seed_only_coverage"] = e2_native.get("unique_instructions")
            ledger["E2_seed_only_isolated_raw_log"] = e2_native.get("raw_log")
            records.append({
                "sample_id": sample_id, "kind": "seed_only", "group": "E2",
                "status": e2_native.get("status"), "native_counterexample": e2_native.get("native_counterexample"),
                "raw_log": e2_native.get("raw_log"),
            })
        write(task_out / "candidate-ledger.json", ledger)
        for row in ledger.get("candidates", []):
            run_dir = (task_out / row["group"] / "candidate-native-isolated" /
                       f"candidate-{int(row['candidate_index']):02d}")
            native = candidate_coverage_replay(
                sample, source, run_dir, row["sequence"], context)
            candidate_coverage = native.get("unique_instructions")
            candidate_lines = covered_source_lines(run_dir)
            new_lines = sorted(candidate_lines - baseline_lines)
            row.update({
                "echidna_replayed_seed_count": native.get("replayed_seed_count"),
                "echidna_target_status": native.get("target_property_status"),
                "echidna_native_counterexample": native.get("native_counterexample"),
                "echidna_unique_instructions": candidate_coverage,
                "coverage_reference_unique_instructions": baseline_coverage,
                "coverage_delta_proxy": (
                    candidate_coverage - baseline_coverage
                    if candidate_coverage is not None and baseline_coverage is not None else None),
                "new_coverage_relative_to_E1_seed": bool(new_lines),
                "covered_source_lines": sorted(candidate_lines),
                "new_covered_source_lines": new_lines,
                "echidna_raw_log": native.get("raw_log"),
                "echidna_working_directory": str(run_dir / "echidna-cwd"),
            })
            records.append({
                "sample_id": sample_id, "kind": "extension_candidate",
                "group": row["group"], "candidate_index": row["candidate_index"],
                "status": native.get("status"),
                "native_counterexample": native.get("native_counterexample"),
                "new_source_line_count": len(new_lines), "raw_log": native.get("raw_log"),
            })
            ledger["extension_new_coverage_candidate_count"] = sum(
                bool(item.get("new_coverage_relative_to_E1_seed"))
                for item in ledger["candidates"])
            ledger["extension_successful_new_coverage_candidate_count"] = sum(
                bool(item.get("pyevm_execution_succeeded") and
                     item.get("new_coverage_relative_to_E1_seed"))
                for item in ledger["candidates"])
            write(task_out / "candidate-ledger.json", ledger)
        write(OUTPUT / "progress" / f"isolated-candidate-replay-progress-{ACTIVE_SHARD['index'] if ACTIVE_SHARD else 0}.json",
              {"completed_tasks": sample_id, "replay_records": len(records)})
    report = {
        "phase": "Phase44", "working_directory_policy": "one private Echidna compile directory per run",
        "sample_ids": ACTIVE_IDS, "replay_record_count": len(records), "replays": records,
    }
    suffix = (f"-shard-{ACTIVE_SHARD['index']}-of-{ACTIVE_SHARD['count']}"
              if ACTIVE_SHARD else "")
    write(OUTPUT / f"isolated-candidate-replay{suffix}.json", report)
    return report


def replay_failed_candidate_replays() -> dict[str, Any]:
    """Retry candidate corpus replays that collided on shared crytic-export output."""
    phase.MAX_SEQUENCE_LENGTH = MAX_LENGTH
    repaired: list[dict[str, Any]] = []
    marker = "Failed to parse combined JSON file"
    secondary_marker = "unable to parse CombinedJSON project JSON"
    for sample_id in ACTIVE_IDS:
        baseline_dir, task_out = task_paths(sample_id)
        ledger = read(task_out / "candidate-ledger.json")
        if not ledger:
            continue
        sample = find_sample(sample_id)
        source = phase.RESULT / sample["files"]["source"]["path"]
        context = read(baseline_dir / "agent/property-context.json")
        if context is None:
            continue
        task_repaired = False
        for group in ("E1", "E2"):
            seed_dir = task_out / f"{group}-seed-only"
            old_log = seed_dir / "echidna.log"
            if not old_log.is_file():
                continue
            prior_log = old_log.read_text(encoding="utf-8", errors="replace")
            if marker not in prior_log and secondary_marker not in prior_log:
                continue
            sequence = read(baseline_dir / group / "sequence.json", []) or []
            if not sequence:
                continue
            native = candidate_coverage_replay(sample, source, seed_dir, sequence, context)
            if group == "E1":
                ledger["E1_seed_only_coverage"] = native.get("unique_instructions")
                baseline_lines = covered_source_lines(seed_dir)
                ledger["E1_seed_only_covered_source_lines"] = sorted(baseline_lines)
                ledger["E1_seed_only_covered_source_line_count"] = len(baseline_lines)
            else:
                ledger["E2_seed_only_coverage"] = native.get("unique_instructions")
            repaired.append({
                "sample_id": sample_id, "group": group, "kind": "seed_only",
                "prior_error": "shared crytic-export/combined_solc.json parse collision",
                "retry_status": native.get("status"), "retry_raw_log": native.get("raw_log"),
            })
            task_repaired = True
        baseline_coverage = ledger.get("E1_seed_only_coverage")
        baseline_lines = set(ledger.get("E1_seed_only_covered_source_lines", []))
        for row in ledger.get("candidates", []):
            if not row.get("echidna_raw_log"):
                continue
            raw_log = ROOT / row["echidna_raw_log"]
            try:
                prior_log = raw_log.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if marker not in prior_log and secondary_marker not in prior_log:
                continue
            run_dir = (task_out / row["group"] / "candidate-native" /
                       f"candidate-{int(row['candidate_index']):02d}")
            native = candidate_coverage_replay(
                sample, source, run_dir, row["sequence"], context)
            candidate_coverage = native.get("unique_instructions")
            candidate_lines = covered_source_lines(run_dir)
            new_lines = sorted(candidate_lines - baseline_lines)
            row.update({
                "echidna_replayed_seed_count": native.get("replayed_seed_count"),
                "echidna_target_status": native.get("target_property_status"),
                "echidna_native_counterexample": native.get("native_counterexample"),
                "echidna_unique_instructions": candidate_coverage,
                "coverage_reference_unique_instructions": baseline_coverage,
                "coverage_delta_proxy": (
                    candidate_coverage - baseline_coverage
                    if candidate_coverage is not None and baseline_coverage is not None else None),
                "new_coverage_relative_to_E1_seed": bool(new_lines),
                "covered_source_lines": sorted(candidate_lines),
                "new_covered_source_lines": new_lines,
                "echidna_raw_log": native.get("raw_log"),
            })
            repaired.append({
                "sample_id": sample_id, "group": row["group"],
                "kind": "extension_candidate",
                "candidate_index": row["candidate_index"],
                "prior_error": "shared crytic-export/combined_solc.json parse collision",
                "retry_status": native.get("status"),
                "retry_raw_log": native.get("raw_log"),
            })
            task_repaired = True
        for row in ledger.get("candidates", []):
            candidate_lines = set(row.get("covered_source_lines", []))
            new_lines = sorted(candidate_lines - baseline_lines)
            candidate_coverage = row.get("echidna_unique_instructions")
            row["coverage_reference_unique_instructions"] = baseline_coverage
            row["coverage_delta_proxy"] = (
                candidate_coverage - baseline_coverage
                if candidate_coverage is not None and baseline_coverage is not None else None)
            row["new_coverage_relative_to_E1_seed"] = bool(new_lines)
            row["new_covered_source_lines"] = new_lines
        ledger["extension_new_coverage_candidate_count"] = sum(
            bool(row.get("new_coverage_relative_to_E1_seed")) for row in ledger.get("candidates", []))
        ledger["extension_successful_new_coverage_candidate_count"] = sum(
            bool(row.get("pyevm_execution_succeeded") and
                 row.get("new_coverage_relative_to_E1_seed"))
            for row in ledger.get("candidates", []))
        if task_repaired:
            write(task_out / "candidate-ledger.json", ledger)
    report = {
        "phase": "Phase44", "reason": "isolate per-run Echidna compile working directories",
        "replayed_candidate_count": len(repaired), "replays": repaired,
    }
    write(OUTPUT / "candidate-replay-recovery.json", report)
    return summarize_candidates()


def run_fuzz_campaigns() -> dict[str, Any]:
    phase.MAX_SEQUENCE_LENGTH = MAX_LENGTH
    phase.E3_CANDIDATE_BUDGET = PER_GROUP_BUDGET
    stage = read(OUTPUT / "candidate-stage-summary.json")
    if not stage:
        raise SystemExit("run the candidate stage first")
    campaign: dict[str, Any] = {
        "configuration": stage["configuration"],
        "fuzz_seconds_per_group": FUZZ_SECONDS,
        "test_limit": FUZZ_TEST_LIMIT,
        "seeds": FUZZ_SEEDS,
        "groups": {},
    }
    if ACTIVE_SHARD:
        progress_path = OUTPUT / "progress" / f"fuzz-stage-progress-shard-{ACTIVE_SHARD['index']}.json"
        summary_path = OUTPUT / f"fuzz-stage-summary-shard-{ACTIVE_SHARD['index']}.json"
    else:
        progress_path = OUTPUT / "fuzz-stage-progress.json"
        summary_path = OUTPUT / "fuzz-stage-summary.json"
    for sample_id in ACTIVE_IDS:
        baseline_dir, task_out = task_paths(sample_id)
        fuzz_root = task_out / "fuzz-isolated-final"
        sample = find_sample(sample_id)
        source = phase.RESULT / sample["files"]["source"]["path"]
        context = read(baseline_dir / "agent/property-context.json")
        if context is None:
            continue
        candidate = candidate_metadata(context)
        sequences: dict[str, list[list[dict[str, Any]]]] = {
            "G0": [],
            "E1": [read(baseline_dir / "E1/sequence.json", []) or []],
            "E2": [read(baseline_dir / "E2/sequence.json", []) or []],
        }
        for group in ("G1", "G2"):
            result = read(task_out / group / f"{group}-result.json", {})
            sequences[group] = [row["sequence"] for row in result.get("candidates", [])
                                if row.get("replay_status") == "executable"]
        sequences = {group: seqs for group, seqs in sequences.items()
                     if group in {"G0", "G1", "G2"} or seqs[0]}
        task_campaign = {}
        for group in ("G0", "E1", "E2", "G1", "G2"):
            group_sequences = sequences.get(group)
            if group_sequences is None:
                task_campaign[group] = {"status": "no_frozen_agent_sequence"}
                continue
            group_out = fuzz_root / group
            seed_only = None
            if group_sequences:
                seed_only = phase.run_echidna(
                    sample, source, group_out / "seed-only", seed=SEED,
                    timeout=10, test_limit=0, seed_sequences=group_sequences,
                    candidate=candidate, context=context,
                    working_directory=group_out / "seed-only" / "echidna-cwd")
            fuzz_runs = []
            for fuzz_seed in FUZZ_SEEDS:
                fuzz_runs.append(phase.run_echidna(
                    sample, source, group_out / f"seed-{fuzz_seed}", seed=fuzz_seed,
                    timeout=FUZZ_SECONDS, test_limit=FUZZ_TEST_LIMIT,
                    seed_sequences=group_sequences, candidate=candidate, context=context,
                    working_directory=group_out / f"seed-{fuzz_seed}" / "echidna-cwd"))
            baseline_coverage = (seed_only or {}).get("unique_instructions", 0)
            final_coverages = [row.get("unique_instructions") for row in fuzz_runs]
            final_coverage = mean(final_coverages)
            counterexample_runs = [row for row in fuzz_runs if row.get("native_counterexample")]
            first_times = [row.get("time_to_first_native_counterexample_seconds")
                           for row in counterexample_runs
                           if row.get("time_to_first_native_counterexample_seconds") is not None]
            task_campaign[group] = {
                "status": "completed" if all(row.get("status") in FUZZ_VALID_STATUSES
                                                for row in fuzz_runs) else "failed",
                "seed_sequence_count": len(group_sequences),
                "seed_only_coverage": baseline_coverage,
                "final_coverage": final_coverage,
                "new_coverage": (max(0, final_coverage - baseline_coverage)
                                 if final_coverage is not None and baseline_coverage is not None
                                 else None),
                "native_counterexample": bool(counterexample_runs),
                "echidna_target_status_by_seed": {
                    str(seed): row.get("target_property_status")
                    for seed, row in zip(FUZZ_SEEDS, fuzz_runs)},
                "time_to_first_native_counterexample_seconds": min(first_times)
                    if first_times else None,
                "fuzz_elapsed_seconds": mean(row.get("elapsed_seconds") for row in fuzz_runs),
                "replayed_seed_count_by_seed": {
                    str(seed): row.get("replayed_seed_count")
                    for seed, row in zip(FUZZ_SEEDS, fuzz_runs)},
                "loaded_seed_sequences_by_seed": {
                    str(seed): row.get("loaded_seed_sequences")
                    for seed, row in zip(FUZZ_SEEDS, fuzz_runs)},
                "unique_calls_mean": mean(row.get("unique_calls") for row in fuzz_runs),
                "seed_only_status": seed_only.get("status") if seed_only else "no_seed_sequence",
                "seed_only_native_counterexample": bool(
                    seed_only and seed_only.get("native_counterexample")),
                "seed_only_target_status": (seed_only or {}).get("target_property_status"),
                "raw_logs_by_seed": {str(seed): row.get("raw_log")
                                     for seed, row in zip(FUZZ_SEEDS, fuzz_runs)},
                "per_seed": {
                    str(seed): {
                        "status": row.get("status"),
                        "native_counterexample": row.get("native_counterexample"),
                        "target_property_status": row.get("target_property_status"),
                        "time_to_first_native_counterexample_seconds":
                            row.get("time_to_first_native_counterexample_seconds"),
                        "final_coverage": row.get("unique_instructions"),
                        "new_coverage": (max(0, row["unique_instructions"] - baseline_coverage)
                                         if row.get("unique_instructions") is not None and
                                         baseline_coverage is not None else None),
                        "elapsed_seconds": row.get("elapsed_seconds"),
                        "unique_calls": row.get("unique_calls"),
                        "raw_log": row.get("raw_log"),
                    } for seed, row in zip(FUZZ_SEEDS, fuzz_runs)},
                "seed_only_raw_log": seed_only.get("raw_log") if seed_only else None,
            }
            write(task_out / "fuzz-summary.json", task_campaign)
        campaign["groups"][sample_id] = task_campaign
        write(progress_path, campaign)

    aggregate: dict[str, Any] = {}
    for group in ("G0", "E1", "E2", "G1", "G2"):
        records = [task.get(group) for task in campaign["groups"].values()
                   if task.get(group, {}).get("status") != "no_frozen_agent_sequence"]
        comparable = [row for row in records if row]
        aggregate[group] = {
            "task_count": len(comparable),
            "native_counterexample_tasks": sum(bool(row.get("native_counterexample"))
                                                for row in comparable),
            "mean_final_coverage": mean(row.get("final_coverage") for row in comparable),
            "mean_new_coverage": mean(row.get("new_coverage") for row in comparable),
            "mean_first_counterexample_seconds": mean(
                row.get("time_to_first_native_counterexample_seconds") for row in comparable),
        }
    campaign["aggregate"] = aggregate
    write(summary_path, campaign)
    return campaign


def summarize_fuzz() -> dict[str, Any]:
    candidate_stage = read(OUTPUT / "candidate-stage-summary.json", {})
    campaign: dict[str, Any] = {
        "configuration": candidate_stage.get("configuration", {}),
        "fuzz_seconds_per_group": FUZZ_SECONDS,
        "test_limit": FUZZ_TEST_LIMIT,
        "seeds": FUZZ_SEEDS,
        "groups": {},
    }
    for sample_id in ALL_ACTIVE_IDS:
        task_summary = read(OUTPUT / "tasks" / sample_id / "fuzz-summary.json")
        if task_summary is not None:
            campaign["groups"][sample_id] = task_summary
    aggregate: dict[str, Any] = {}
    for group in ("G0", "E1", "E2", "G1", "G2"):
        records = [task.get(group) for task in campaign["groups"].values()
                   if task.get(group, {}).get("status") != "no_frozen_agent_sequence"]
        comparable = [row for row in records if row]
        aggregate[group] = {
            "task_count": len(comparable),
            "native_counterexample_tasks": sum(bool(row.get("native_counterexample"))
                                                for row in comparable),
            "mean_final_coverage": mean(row.get("final_coverage") for row in comparable),
            "mean_new_coverage": mean(row.get("new_coverage") for row in comparable),
            "mean_first_counterexample_seconds": mean(
                row.get("time_to_first_native_counterexample_seconds") for row in comparable),
        }
    campaign["aggregate"] = aggregate
    paired: dict[str, Any] = {}
    for group in ("E1", "E2", "G1", "G2"):
        pairs = []
        for sample_id, task in campaign["groups"].items():
            baseline = task.get("G0", {})
            treatment = task.get(group, {})
            if (baseline.get("status") in FUZZ_VALID_STATUSES and
                    treatment.get("status") in FUZZ_VALID_STATUSES and
                    baseline.get("final_coverage") is not None and
                    treatment.get("final_coverage") is not None):
                pairs.append((sample_id, baseline, treatment))
        coverage_deltas = [treatment["final_coverage"] - baseline["final_coverage"]
                           for _, baseline, treatment in pairs]
        new_coverage_deltas = [treatment["new_coverage"] - baseline["new_coverage"]
                               for _, baseline, treatment in pairs
                               if treatment.get("new_coverage") is not None and
                               baseline.get("new_coverage") is not None]
        baseline_mean = mean(row[1]["final_coverage"] for row in pairs)
        treatment_mean = mean(row[2]["final_coverage"] for row in pairs)
        baseline_counterexamples = sum(bool(base.get("native_counterexample"))
                                       for _, base, _ in pairs)
        treatment_counterexamples = sum(bool(item.get("native_counterexample"))
                                        for _, _, item in pairs)
        baseline_times = [base.get("time_to_first_native_counterexample_seconds")
                          for _, base, _ in pairs
                          if base.get("time_to_first_native_counterexample_seconds") is not None]
        treatment_times = [item.get("time_to_first_native_counterexample_seconds")
                           for _, _, item in pairs
                           if item.get("time_to_first_native_counterexample_seconds") is not None]
        paired[group] = {
            "paired_task_count": len(pairs),
            "baseline_G0_final_coverage_mean": baseline_mean,
            "treatment_final_coverage_mean": treatment_mean,
            "mean_final_coverage_delta": mean(coverage_deltas),
            "relative_final_coverage_change_percent": (
                round((treatment_mean - baseline_mean) / baseline_mean * 100, 6)
                if baseline_mean not in (None, 0) and treatment_mean is not None else None),
            "tasks_with_higher_final_coverage": sum(delta > 0 for delta in coverage_deltas),
            "tasks_with_equal_final_coverage": sum(delta == 0 for delta in coverage_deltas),
            "tasks_with_lower_final_coverage": sum(delta < 0 for delta in coverage_deltas),
            "mean_new_coverage_delta": mean(new_coverage_deltas),
            "G0_native_counterexample_tasks": baseline_counterexamples,
            "treatment_native_counterexample_tasks": treatment_counterexamples,
            "native_counterexample_rate_delta_percentage_points": round(
                (treatment_counterexamples - baseline_counterexamples) / len(pairs) * 100, 6)
                if pairs else None,
            "G0_mean_first_counterexample_seconds": mean(baseline_times),
            "treatment_mean_first_counterexample_seconds": mean(treatment_times),
            "G0_median_first_counterexample_seconds": (
                round(statistics.median(baseline_times), 6) if baseline_times else None),
            "treatment_median_first_counterexample_seconds": (
                round(statistics.median(treatment_times), 6) if treatment_times else None),
        }
    campaign["paired_vs_G0"] = paired
    write(OUTPUT / "fuzz-stage-summary.json", campaign)
    return campaign


def reclassify_saved_echidna_runs() -> dict[str, Any]:
    """Reparse saved Phase44 logs after the Echidna 2.3.2 falsification fix."""
    global ACTIVE_SPLIT, OUTPUT, ACTIVE_IDS, ALL_ACTIVE_IDS, FUZZ_SECONDS, FUZZ_SEEDS
    report: dict[str, Any] = {"parser_fix": "worker-level falsified marker overrides final failed line",
                              "splits": {}}
    original_split, original_output = ACTIVE_SPLIT, OUTPUT
    original_ids, original_all_ids = ACTIVE_IDS, ALL_ACTIVE_IDS
    original_seconds, original_seeds = FUZZ_SECONDS, FUZZ_SEEDS
    for split, split_ids, seconds, seeds in (
            ("dev", DEV_IDS, 20, [4301]), ("eval", EVAL_IDS, 60, [4301, 4302, 4303])):
        split_dir = OUTPUT_BASE / split
        if not split_dir.is_dir():
            continue
        changed = 0
        scanned = 0
        ACTIVE_SPLIT, OUTPUT = split, split_dir
        ACTIVE_IDS = ALL_ACTIVE_IDS = split_ids
        FUZZ_SECONDS, FUZZ_SEEDS = seconds, seeds
        for result_path in split_dir.rglob("result.json"):
            if "prior-attempts" in result_path.parts:
                continue
            result = read(result_path)
            raw_log = result.get("raw_log") if result else None
            if not raw_log:
                continue
            log_path = Path(raw_log)
            if not log_path.is_absolute():
                log_path = ROOT / log_path
            if not log_path.is_file():
                continue
            log = log_path.read_text(encoding="utf-8", errors="replace")
            parsed = phase.parse_echidna_log(
                log, float(result.get("elapsed_seconds") or 0),
                result.get("exit_code"), bool(result.get("timed_out")))
            scanned += 1
            changed += int(bool(parsed.get("native_counterexample")) and
                           not bool(result.get("native_counterexample")))
            result.update(parsed)
            write(result_path, result)

        # Refresh candidate ledgers from their now-correct native result files.
        if (split_dir / "candidate-stage-progress.json").is_file():
            summarize_candidates()

        # Refresh each task's per-group fuzz summaries, retaining every seed result.
        for sample_id in split_ids:
            _, task_out = task_paths(sample_id)
            task_summary_path = task_out / "fuzz-summary.json"
            task_summary = read(task_summary_path)
            if task_summary is None:
                continue
            for group in ("G0", "E1", "E2", "G1", "G2"):
                group_row = task_summary.get(group)
                if not isinstance(group_row, dict) or group_row.get("status") == "no_frozen_agent_sequence":
                    continue
                group_dir = task_out / "fuzz" / group
                seed_only = read(group_dir / "seed-only/result.json")
                group_row["seed_only_status"] = (seed_only or {}).get("status", "no_seed_sequence")
                group_row["seed_only_native_counterexample"] = bool(
                    seed_only and seed_only.get("native_counterexample"))
                group_row["seed_only_target_status"] = (seed_only or {}).get("target_property_status")
                per_seed = {}
                for run_dir in sorted(group_dir.glob("seed-[0-9]*")):
                    seed_match = re.fullmatch(r"seed-(\d+)", run_dir.name)
                    result = read(run_dir / "result.json")
                    if not seed_match or result is None:
                        continue
                    seed = seed_match.group(1)
                    per_seed[seed] = {
                        "status": result.get("status"),
                        "native_counterexample": result.get("native_counterexample"),
                        "target_property_status": result.get("target_property_status"),
                        "time_to_first_native_counterexample_seconds":
                            result.get("time_to_first_native_counterexample_seconds"),
                        "final_coverage": result.get("unique_instructions"),
                        "new_coverage": (
                            max(0, result["unique_instructions"] -
                                (seed_only or {}).get("unique_instructions", 0))
                            if result.get("unique_instructions") is not None else None),
                        "elapsed_seconds": result.get("elapsed_seconds"),
                        "unique_calls": result.get("unique_calls"),
                        "raw_log": result.get("raw_log"),
                    }
                if not per_seed:
                    continue
                results = [read(group_dir / f"seed-{seed}" / "result.json")
                           for seed in per_seed]
                results = [result for result in results if result]
                counterexamples = [result for result in results
                                   if result.get("native_counterexample")]
                times = [result.get("time_to_first_native_counterexample_seconds")
                         for result in counterexamples
                         if result.get("time_to_first_native_counterexample_seconds") is not None]
                finals = [result.get("unique_instructions") for result in results
                          if result.get("unique_instructions") is not None]
                baseline = (seed_only or {}).get("unique_instructions", 0)
                group_row.update({
                    "status": "completed" if all(result.get("status") in FUZZ_VALID_STATUSES
                                                  for result in results) else "failed",
                    "native_counterexample": bool(counterexamples),
                    "echidna_target_status_by_seed": {
                        seed: entry.get("target_property_status")
                        for seed, entry in per_seed.items()},
                    "time_to_first_native_counterexample_seconds": min(times) if times else None,
                    "fuzz_elapsed_seconds": mean(result.get("elapsed_seconds")
                                                  for result in results),
                    "final_coverage": mean(finals),
                    "new_coverage": mean(max(0, value - baseline) for value in finals),
                    "replayed_seed_count_by_seed": {
                        seed: result.get("replayed_seed_count")
                        for seed, result in zip(per_seed, results)},
                    "loaded_seed_sequences_by_seed": {
                        seed: result.get("loaded_seed_sequences")
                        for seed, result in zip(per_seed, results)},
                    "unique_calls_mean": mean(result.get("unique_calls") for result in results),
                    "raw_logs_by_seed": {seed: entry.get("raw_log")
                                         for seed, entry in per_seed.items()},
                    "per_seed": per_seed,
                })
            write(task_summary_path, task_summary)

        if (split_dir / "candidate-stage-summary.json").is_file():
            summarize_fuzz()
        report["splits"][split] = {"run_results_scanned": scanned,
                                    "new_native_counterexamples_recognized": changed,
                                    "fuzz_task_count": len(read(split_dir / "fuzz-stage-summary.json", {})
                                                            .get("groups", {}))}
    ACTIVE_SPLIT, OUTPUT = original_split, original_output
    ACTIVE_IDS, ALL_ACTIVE_IDS = original_ids, original_all_ids
    FUZZ_SECONDS, FUZZ_SEEDS = original_seconds, original_seeds
    write(OUTPUT_BASE / "reclassification-summary.json", report)
    return report


def mean(values: Any) -> float | None:
    data = [float(value) for value in values if value is not None]
    return round(sum(data) / len(data), 6) if data else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("candidates", "replay-all-isolated",
                                          "replay-failed-candidates", "fuzz",
                                          "summarize", "summarize-fuzz", "reclassify"))
    parser.add_argument("--split", choices=("dev", "eval"), default="dev")
    parser.add_argument("--shard", help="optional zero-based shard in INDEX/TOTAL form")
    args = parser.parse_args()
    global ACTIVE_SPLIT, OUTPUT, ACTIVE_IDS, ALL_ACTIVE_IDS, ACTIVE_SHARD, FUZZ_SECONDS, FUZZ_SEEDS
    ACTIVE_SPLIT = args.split
    OUTPUT = OUTPUT_BASE / ACTIVE_SPLIT
    ALL_ACTIVE_IDS = DEV_IDS if ACTIVE_SPLIT == "dev" else EVAL_IDS
    ACTIVE_IDS = ALL_ACTIVE_IDS
    ACTIVE_SHARD = None
    if args.shard:
        try:
            shard_index, shard_count = (int(piece) for piece in args.shard.split("/", 1))
        except (ValueError, TypeError):
            raise SystemExit("--shard must use INDEX/TOTAL, for example 0/4")
        if shard_count < 1 or not 0 <= shard_index < shard_count:
            raise SystemExit("--shard index must satisfy 0 <= INDEX < TOTAL")
        ACTIVE_SHARD = {"index": shard_index, "count": shard_count}
        ACTIVE_IDS = [sample_id for index, sample_id in enumerate(ALL_ACTIVE_IDS)
                      if index % shard_count == shard_index]
    FUZZ_SECONDS = 20 if ACTIVE_SPLIT == "dev" else 60
    FUZZ_SEEDS = [SEED] if ACTIVE_SPLIT == "dev" else [4301, 4302, 4303]
    if args.stage == "candidates":
        run_candidates()
    elif args.stage == "replay-all-isolated":
        replay_all_candidate_replays_isolated()
    elif args.stage == "replay-failed-candidates":
        replay_failed_candidate_replays()
    elif args.stage == "fuzz":
        run_fuzz_campaigns()
    elif args.stage == "summarize-fuzz":
        ACTIVE_IDS = ALL_ACTIVE_IDS
        summarize_fuzz()
    elif args.stage == "reclassify":
        reclassify_saved_echidna_runs()
    else:
        ACTIVE_IDS = ALL_ACTIVE_IDS
        summarize_candidates()


if __name__ == "__main__":
    main()
