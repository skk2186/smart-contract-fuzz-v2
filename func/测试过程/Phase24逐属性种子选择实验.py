#!/usr/bin/env python3
"""Phase 24：冻结并比较 Request 逐属性有效种子的合并、贪心与随机子集。"""

from __future__ import annotations

import hashlib
import json
import random
import re
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

import 种子验证 as verifier
from AgentB import HARNESS_ADDRESS, SENDERS, to_echidna_sequence
from 属性种子上下文 import load_project_context


SOURCE_REPORT = Path("deepseek/结果/DeepSeek分组可信度修复实验.json")
SOURCE_EXPERIMENT_ID = "2860da9f9d884d24898287128b95d0b0"
SOURCE_METHOD = "independent_dual"
SOURCE_REPETITIONS = (1, 2)
OUTPUT_ROOT = Path("deepseek/结果/Phase24逐属性种子选择与持续探索验证-20261117")
HARNESS_PATH = Path("sol/真实项目/Request/src/contracts/test/EchidnaERC20CommerceEscrowWrapper.sol")
WRAPPER_PATH = Path("sol/真实项目/Request/src/contracts/ERC20CommerceEscrowWrapper.sol")
PAIRED_RANDOM_SEEDS = (20261118, 20261128, 20261208, 20261218, 20261228)
SELECTION_RANDOM_SEED = 242417
ZERO_REPLAY_RANDOM_SEED = 20261117
TEST_LIMIT = 500
SEQ_LEN = 8
SHRINK_LIMIT = 1
RUN_TIMEOUT_SECONDS = 86400
REPLAY_TIMEOUT_SECONDS = 600


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalized_transactions(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """忽略种子 ID、属性说明和 JSON 排版，按实际交易语义去重。"""
    return [{
        "function": str(tx["function"]),
        "arguments": [normalize_scalar(value) for value in tx.get("arguments", [])],
        "sender": str(tx["sender"]).lower(),
        "value_wei": str(int(tx.get("value_wei", "0"))),
        "delay_seconds": int(tx.get("delay_seconds", 0)),
        "delay_blocks": int(tx.get("delay_blocks", 0)),
    } for tx in transactions]


def sequence_fingerprint(transactions: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    normalized = normalized_transactions(transactions)
    encoded = json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return sha256_bytes(encoded), normalized


def source_inventory(source_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_data = json.loads(source_path.read_text(encoding="utf-8"))
    if source_data.get("experiment_id") != SOURCE_EXPERIMENT_ID:
        raise RuntimeError("Phase 10 原始报告 experiment_id 与预登记值不符")
    raw_candidates: list[dict[str, Any]] = []
    for run in sorted(
        (row for row in source_data.get("runs", [])
         if row.get("method") == SOURCE_METHOD and row.get("repetition") in SOURCE_REPETITIONS),
        key=lambda row: row["repetition"],
    ):
        for candidate in run.get("seed_candidates", []):
            seed = candidate.get("seed") or {}
            transactions = seed.get("transactions") or []
            corpus_file = candidate.get("corpus_file")
            corpus_path = ROOT / corpus_file if corpus_file else None
            corpus_bytes = corpus_path.read_bytes() if corpus_path and corpus_path.is_file() else None
            sequence_hash, normalized = sequence_fingerprint(transactions) if transactions else (None, [])
            corpus_sequence = json.loads(corpus_bytes.decode("utf-8")) if corpus_bytes else None
            prop_id = candidate.get("property_id", "")
            context = load_project_context("Request", [prop_id]) if prop_id else None
            candidate_for_encoder = {
                "property_id": prop_id,
                "candidate_id": seed.get("candidate_id", candidate.get("candidate_id", "")),
                "steps": candidate.get("plan", []),
            }
            expected_sequence = (to_echidna_sequence(
                candidate_for_encoder, transactions, context,
                contract_address=HARNESS_ADDRESS) if context and transactions else None)
            serialized_match = bool(corpus_sequence is not None and expected_sequence == corpus_sequence)
            raw_candidates.append({
                "source_method": run["method"],
                "source_repetition": run["repetition"],
                "property_id": prop_id,
                "property": candidate.get("property"),
                "source_status": candidate.get("status"),
                "source_seed_id": candidate.get("seed_id"),
                "candidate_id": seed.get("candidate_id", candidate.get("candidate_id")),
                "source_report": source_path.relative_to(ROOT).as_posix(),
                "source_corpus_file": corpus_file,
                "source_corpus_exists": corpus_bytes is not None,
                "source_corpus_sha256": sha256_bytes(corpus_bytes) if corpus_bytes is not None else None,
                "sequence_sha256": sequence_hash,
                "normalized_transactions": normalized,
                "source_corpus_matches_agent_transactions": serialized_match,
                "source_plan": candidate.get("plan", []),
                "source_assumptions": seed.get("assumptions", []),
                "transactions": transactions,
                "replay_status_phase10": (candidate.get("replay") or {}).get("replay_status"),
            })

    if len(raw_candidates) != 8:
        raise RuntimeError(f"预登记来源应含 8 条 independent_dual 候选，实际为 {len(raw_candidates)}")

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for candidate in raw_candidates:
        if candidate.get("sequence_sha256"):
            groups[candidate["sequence_sha256"]].append(candidate)
    for sequence_hash, rows in groups.items():
        rows.sort(key=lambda row: (row["source_repetition"], row["property_id"], row["source_seed_id"] or ""))
        for index, row in enumerate(rows):
            row["duplicate_of"] = None if index == 0 else rows[0]["source_seed_id"]
            row["duplicate_group_size"] = len(rows)
            row["duplicate_sequence_sha256"] = sequence_hash
    for candidate in raw_candidates:
        if not candidate.get("sequence_sha256"):
            candidate["duplicate_of"] = None
            candidate["duplicate_group_size"] = 0
            candidate["duplicate_sequence_sha256"] = None

    inventory = {
        "source_report": source_path.relative_to(ROOT).as_posix(),
        "source_report_sha256": sha256_file(source_path),
        "source_experiment_id": source_data["experiment_id"],
        "source_method": SOURCE_METHOD,
        "source_repetitions": list(SOURCE_REPETITIONS),
        "source_candidate_count": len(raw_candidates),
        "raw_transaction_sequence_count_after_dedup": len(groups),
        "candidate_records": raw_candidates,
        "dedup_groups": [{
            "sequence_sha256": sequence_hash,
            "source_seed_ids": [row["source_seed_id"] for row in rows],
            "property_ids": sorted({row["property_id"] for row in rows}),
            "source_corpus_sha256_values": sorted({row["source_corpus_sha256"] for row in rows}),
            "all_source_corpus_files_match_agent_transactions": all(
                row["source_corpus_matches_agent_transactions"] for row in rows),
        } for sequence_hash, rows in sorted(groups.items())],
    }
    return inventory, raw_candidates


def discover_harness_properties() -> list[str]:
    source = (ROOT / HARNESS_PATH).read_text(encoding="utf-8")
    return sorted(set(re.findall(r"\bfunction\s+(echidna_[A-Za-z0-9_]+)\s*\(", source)))


def function_line(source_path: Path, function_name: str) -> int:
    source = (ROOT / source_path).read_text(encoding="utf-8")
    matches = [index for index, line in enumerate(source.splitlines(), start=1)
               if re.search(r"\bfunction\s+" + re.escape(function_name) + r"\s*\(", line)]
    if len(matches) != 1:
        raise RuntimeError(f"無法唯一定位函數 {function_name}：{source_path} {matches}")
    return matches[0]


def target_path_ranges() -> list[dict[str, Any]]:
    groups = [
        (HARNESS_PATH, "Harness.driver_authorizePayment", "driver_authorizePayment", "driver_capturePayment"),
        (HARNESS_PATH, "Harness.driver_capturePayment", "driver_capturePayment", "driver_voidPayment"),
        (HARNESS_PATH, "Harness.driver_chargePayment", "driver_chargePayment", "driver_reclaimPayment"),
        (WRAPPER_PATH, "Wrapper.authorize_path", "authorizePayment", "capturePayment"),
        (WRAPPER_PATH, "Wrapper.capturePayment", "capturePayment", "voidPayment"),
        (WRAPPER_PATH, "Wrapper.charge_path", "chargePayment", "reclaimPayment"),
    ]
    ranges = []
    for path, label, start_name, stop_name in groups:
        start = function_line(path, start_name)
        stop = function_line(path, stop_name)
        ranges.append({"label": label, "source": path.as_posix(), "first_line": start,
                       "last_line": stop - 1})
    return ranges


def freeze_plan(inventory: dict[str, Any], property_names: list[str],
                ranges: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
    try:
        base_commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                     capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        base_commit = None
    plan = {
        "phase": 24,
        "created_at_utc": utc_now(),
        "experiment_status": "pre-registered-before-replay-and-fuzzing",
        "base_commit": base_commit,
        "source_report": inventory["source_report"],
        "source_report_sha256": inventory["source_report_sha256"],
        "source_experiment_id": inventory["source_experiment_id"],
        "seed_source": "Phase 10 Request independent_dual, repetitions 1 and 2 only; no new DeepSeek calls",
        "source_candidate_count": inventory["source_candidate_count"],
        "deduplication": "SHA-256 of normalized ordered transactions (function, arguments, sender, value, delays); retain every alias and invalid source record",
        "seed_validity_rule": [
            "Phase 10 corpus serialization must exactly match its Agent transaction record under the current Request ABI encoder.",
            "Fresh Anvil replay must deploy the same Request Harness; all 16 initial echidna_* properties must evaluate true.",
            "Every planned transaction must have a successful outer receipt, an available callTracer and prestateTracer result, no unexpected internal call revert, at least one persistent storage slot change, and an observed public-view state change.",
            "Property violations are recorded as outcomes and do not by themselves invalidate an otherwise effective executable seed.",
            "All source candidate records, failed replays and duplicate aliases remain in the audit ledger.",
        ],
        "gate": "Run formal campaigns only if at least 3 unique valid transaction sequences represent at least 3 distinct source property IDs on this exact Harness.",
        "harness": {
            "project": "Request",
            "contract": "EchidnaERC20CommerceEscrowWrapper",
            "source": HARNESS_PATH.as_posix(),
            "source_sha256": sha256_file(ROOT / HARNESS_PATH),
            "property_names": property_names,
            "property_count": len(property_names),
            "contract_source_sha256": sha256_file(ROOT / WRAPPER_PATH),
            "contract_address": HARNESS_ADDRESS,
        },
        "environment": {
            "echidna_version": "2.3.2",
            "anvil_version": "1.9.0-dev",
            "solidity": "0.8.20",
            "chain_id": verifier.CHAIN_ID,
            "initial_timestamp": verifier.INITIAL_TIMESTAMP,
            "initial_block_number": verifier.INITIAL_BLOCK_NUMBER,
            "evm_hardfork": "shanghai",
            "deployer": verifier.DEPLOYER,
            "property_sender": verifier.PROPERTY_SENDER,
            "sender_pool": list(SENDERS),
            "account_balance_wei": verifier.INITIAL_BALANCE,
            "gas_price_wei": 0,
            "gas_limit_per_transaction": verifier.MAX_TX_GAS,
        },
        "echidna_configuration": {
            "test_mode": "property",
            "prefix": "echidna_",
            "workers": 1,
            "seq_len": SEQ_LEN,
            "shrink_limit": SHRINK_LIMIT,
            "stop_on_fail": False,
            "disable_slither": True,
            "coverage": True,
            "max_time_delay_seconds": 86400,
            "max_block_delay": 86400,
            "max_gas_price": 0,
            "balance_addr": verifier.INITIAL_BALANCE,
            "balance_contract": 0,
            "test_max_gas": verifier.MAX_TX_GAS,
            "property_max_gas": verifier.MAX_TX_GAS,
            "formal_test_limit": TEST_LIMIT,
            "formal_campaign_timeout_seconds": RUN_TIMEOUT_SECONDS,
        },
        "paired_random_seeds": list(PAIRED_RANDOM_SEEDS),
        "groups": {
            "G0": "native Echidna, empty external corpus",
            "G1": "all unique valid Phase 10 seeds",
            "G2": "greedy half-ceiling by marginal LCOV source lines from independent, test-limit=0 seed replays only; stable tie-break by property ID then sequence SHA-256",
            "G3": f"random sample of the same size from sorted valid seeds using Python random.Random({SELECTION_RANDOM_SEED}); selected before any formal result is read",
        },
        "coverage_separation": {
            "replay": "separate Echidna test-limit=0 campaign with only the fixed seed bundle (or an empty corpus for G0)",
            "post_replay_fuzzing": "exact set difference of final campaign LCOV covered source lines minus that group's independent replay LCOV covered source lines",
            "unique_instruction_limit": "Echidna exposes a scalar unique-instruction total but no instruction-PC bitmap; report final totals and replay-only totals separately, and do not claim exact new unique instructions by scalar subtraction.",
        },
        "target_related_path_ranges": ranges,
        "pre_registered_decision_rule": {
            "stable_pair_wins_required": 4,
            "minimum_relative_mean_gain_percent": 5.0,
            "minimum_absolute_mean_gain_source_lines": 5,
            "G1_meaningful_later_exploration": "G1 must beat G0 in at least 4/5 paired runs on exact post-replay new LCOV source lines and its mean gain must be at least max(5 lines, 5% of G0 mean); otherwise recommend stopping this direction.",
            "G2_versus_G3_stable": "G2 must beat G3 in at least 4/5 paired runs on exact post-replay new LCOV source lines and its mean gain must be at least max(5 lines, 5% of G3 mean); otherwise recommend stopping this direction.",
            "no_posthoc_adjustment": "Do not alter the frozen candidate pool, selection metric, tie-break, random rule or thresholds after any G0-G3 formal campaign begins.",
        },
        "candidate_inventory": [{
            "repetition": row["source_repetition"],
            "property_id": row["property_id"],
            "source_seed_id": row["source_seed_id"],
            "source_status": row["source_status"],
            "sequence_sha256": row["sequence_sha256"],
            "source_corpus_sha256": row["source_corpus_sha256"],
            "source_corpus_matches_agent_transactions": row["source_corpus_matches_agent_transactions"],
            "duplicate_of": row["duplicate_of"],
        } for row in inventory["candidate_records"]],
    }
    plan_path = output_root / "实验方案冻结.json"
    write_json(plan_path, plan)
    (output_root / "实验方案冻结.sha256").write_text(sha256_file(plan_path) + "  实验方案冻结.json\n", encoding="utf-8")
    return plan


def view_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    left, right = before.get("view_values", {}), after.get("view_values", {})
    return [{"getter": key, "before": left.get(key), "after": right.get(key)}
            for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)]


def replay_candidate(candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    original_snapshot = verifier._state_view_snapshot

    def capture(*args: Any, **kwargs: Any) -> dict[str, Any]:
        snapshot = original_snapshot(*args, **kwargs)
        snapshots.append(snapshot)
        return snapshot

    candidate_info = {
        "candidate_id": candidate.get("candidate_id") or candidate.get("source_seed_id"),
        "property_id": candidate["property_id"],
        "property": candidate.get("property", ""),
        "context": context,
    }
    verifier._state_view_snapshot = capture
    try:
        replay = verifier.replay_seed("Request", candidate_info, candidate["transactions"])
    finally:
        verifier._state_view_snapshot = original_snapshot
    if len(snapshots) == len(replay.get("transactions", [])) + 1:
        replay["view_changes_by_transaction"] = [
            view_changes(snapshots[index], snapshots[index + 1])
            for index in range(len(snapshots) - 1)]
        replay["initial_to_final_view_changes"] = view_changes(snapshots[0], snapshots[-1])
    else:
        replay["view_snapshot_error"] = {
            "snapshot_count": len(snapshots),
            "transaction_count": len(replay.get("transactions", [])),
        }
    records = replay.get("transactions", [])
    failed_reasons = []
    if replay.get("replay_status") != "executable":
        failed_reasons.append("verifier_replay_status_not_executable")
    if len(records) != len(candidate["transactions"]):
        failed_reasons.append("incomplete_transaction_sequence")
    if any(row.get("status") != "success" for row in records):
        failed_reasons.append("outer_transaction_reverted_or_failed")
    if any(row.get("trace_error") for row in records):
        failed_reasons.append("internal_trace_unavailable")
    if any(row.get("internal_errors") for row in records):
        failed_reasons.append("unexpected_internal_call_revert")
    if any(row.get("changed_storage_slot_count") in (None, 0) for row in records):
        failed_reasons.append("persistent_storage_change_not_observed")
    if any(row.get("observed_view_state_changed") is not True for row in records):
        failed_reasons.append("public_view_state_change_not_observed")
    initial_values = replay.get("initial_property_values", {})
    if len(initial_values) != 16 or any(value is not True for value in initial_values.values()):
        failed_reasons.append("one_or_more_initial_harness_properties_not_true")
    if any(row.get("all_property_errors") for row in records):
        failed_reasons.append("one_or_more_harness_properties_could_not_be_evaluated")
    replay["phase24_effective_seed"] = not failed_reasons
    replay["phase24_invalid_reasons"] = failed_reasons
    return replay


def read_lcov(path: Path) -> set[tuple[str, int]]:
    source_name = ""
    covered: set[tuple[str, int]] = set()
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw_line.startswith("SF:"):
            source_name = raw_line[3:].replace("\\", "/")
            marker = "/home/skk/smart-contract-fuzz-v2/"
            if marker in source_name:
                source_name = source_name.split(marker, 1)[1]
            elif source_name.startswith("smart-contract-fuzz-v2/"):
                source_name = source_name[len("smart-contract-fuzz-v2/"):]
            source_name = source_name.lstrip("./")
        elif raw_line.startswith("DA:"):
            pieces = raw_line[3:].split(",", 2)
            if len(pieces) >= 2 and int(pieces[1]) > 0:
                covered.add((source_name, int(pieces[0])))
    return covered


def lcov_for_root(corpus_root: Path) -> tuple[Path | None, set[tuple[str, int]]]:
    files = sorted(corpus_root.glob("covered.*.lcov"), key=lambda path: path.stat().st_mtime_ns)
    if not files:
        return None, set()
    selected = files[-1]
    return selected, read_lcov(selected)


def property_outcomes(log: str) -> tuple[dict[str, str], list[str]]:
    outcomes: dict[str, str] = {}
    violations: set[str] = set()
    for line in log.splitlines():
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        match = re.match(r"^(echidna_[A-Za-z0-9_]+)\s*:\s*(.+)$", clean, re.IGNORECASE)
        if match:
            name, status = match.group(1), match.group(2).strip()
            outcomes[name] = status
            if any(word in status.lower() for word in ("falsified", "failed", "💥")):
                violations.add(name)
        for found in re.findall(r"\bTest\s+(echidna_[A-Za-z0-9_]+)\s+falsified\b", clean,
                                re.IGNORECASE):
            violations.add(found)
    return outcomes, sorted(violations)


def run_echidna(root: Path, random_seed: int, seed_inputs: list[dict[str, Any]],
                test_limit: int, timeout_seconds: int) -> dict[str, Any]:
    if root.exists():
        raise FileExistsError(f"實驗 campaign 目錄已存在，拒絕覆蓋：{root}")
    coverage_dir = root / "coverage"
    coverage_dir.mkdir(parents=True)
    copied: dict[str, str] = {}
    for item in seed_inputs:
        destination = coverage_dir / item["corpus_filename"]
        destination.write_bytes((ROOT / item["frozen_corpus_file"]).read_bytes())
        copied[destination.name] = sha256_file(destination)

    started_at = utc_now()
    result = verifier.run_echidna(
        "Request", root, property_name="echidna_", test_limit=test_limit,
        timeout=timeout_seconds, seed=random_seed, test_mode="property",
        property_prefix="echidna_", seq_len=SEQ_LEN, shrink_limit=SHRINK_LIMIT,
        stop_on_fail=False, disable_slither=True, sender_pool=list(SENDERS))
    log_path = ROOT / result["full_log_path"]
    log = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else ""
    lcov_path, covered_lines = lcov_for_root(root)
    property_statuses, violations = property_outcomes(log)
    progress = [(int(left), int(right)) for left, right in
                re.findall(r"\bfuzzing\s*:\s*(\d+)\s*/\s*(\d+)", log, re.IGNORECASE)]
    test_limit_reached = "Test limit reached" in log
    campaign_completed = bool(
        test_limit > 0 and result.get("status") == "completed" and result.get("exit_code") == 0
        and test_limit_reached and (not progress or max(right for _, right in progress) >= test_limit)
    )
    post_run_seed_hashes = {
        path.name: sha256_file(path) for path in sorted(coverage_dir.glob("*.txt"))
        if path.name in copied
    }
    expected_loaded = len(seed_inputs)
    replay_checks = {
        "expected_seed_count": expected_loaded,
        "echidna_loaded_seed_count": result.get("loaded_seed_count"),
        "echidna_replayed_sequence_count": result.get("replayed_sequence_count"),
        "loaded_count_matches": result.get("loaded_seed_count") == expected_loaded,
        "all_input_seed_files_remained_unchanged": post_run_seed_hashes == copied,
    }
    return {
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "random_seed": random_seed,
        "test_limit": test_limit,
        "campaign_status": "completed_at_test_limit" if campaign_completed else result.get("status"),
        "campaign_completed_at_test_limit": campaign_completed,
        "exit_code": result.get("exit_code"),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "fuzzing_progress": [{"transactions": left, "test_cases_limit": right} for left, right in progress],
        "test_limit_reached_log_evidence": test_limit_reached,
        "unique_instructions_total": result.get("unique_instructions"),
        "unique_instruction_coverage_source": result.get("coverage_source"),
        "replay_only_unique_instructions": None,
        "exact_new_unique_instruction_count_after_replay": None,
        "loaded_seed_count": result.get("loaded_seed_count"),
        "replayed_sequence_count": result.get("replayed_sequence_count"),
        "mutation_evidence": result.get("mutation_evidence"),
        "property_statuses_observed": property_statuses,
        "property_violations": violations,
        "property_violation_count": len(violations),
        "source_lcov_file": lcov_path.relative_to(ROOT).as_posix() if lcov_path else None,
        "source_lcov_sha256": sha256_file(lcov_path) if lcov_path else None,
        "covered_source_line_count": len(covered_lines),
        "covered_source_lines": [f"{path}:{line}" for path, line in sorted(covered_lines)],
        "full_log_file": log_path.relative_to(ROOT).as_posix() if log_path.is_file() else None,
        "replay_evidence": replay_checks,
        "input_corpus_files": copied,
        "corpus_files_after_run": sorted(path.name for path in coverage_dir.glob("*.txt")),
        "raw_result": result,
    }


def region_lines(lines: set[tuple[str, int]], ranges: list[dict[str, Any]]) -> dict[str, int]:
    return {region["label"]: sum(
        1 for source, line in lines
        if source == region["source"] and region["first_line"] <= line <= region["last_line"])
        for region in ranges}


def stats(values: list[float | int | None]) -> dict[str, Any]:
    numbers = [float(value) for value in values if value is not None]
    if not numbers:
        return {"n": 0, "mean": None, "median": None, "sample_sd": None, "min": None, "max": None}
    return {
        "n": len(numbers),
        "mean": statistics.mean(numbers),
        "median": statistics.median(numbers),
        "sample_sd": statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
        "min": min(numbers),
        "max": max(numbers),
    }


def refresh_saved_summary() -> None:
    """只重建逐次汇总字段，不执行或改写任何 Echidna campaign 原始证据。"""
    output_root = ROOT / OUTPUT_ROOT
    summary_path = output_root / "Phase24结果汇总.json"
    raw_path = output_root / "正式實驗逐次結果.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    for group_name in ("G0", "G1", "G2", "G3"):
        replay_instructions = raw["group_seed_replays"][group_name].get("replay_only_unique_instructions")
        per_run = []
        for row in raw["groups"][group_name]:
            result = row.get("result", {})
            per_run.append({
                "pair_index": row.get("pair_index"),
                "random_seed": row.get("random_seed"),
                "test_limit": result.get("test_limit"),
                "campaign_status": result.get("campaign_status", row.get("campaign_status")),
                "completed_at_test_limit": result.get("campaign_completed_at_test_limit",
                                                        row.get("campaign_completed_at_test_limit", False)),
                "exit_code": result.get("exit_code"),
                "elapsed_seconds": result.get("elapsed_seconds"),
                "total_unique_instructions": result.get("unique_instructions_total"),
                "replay_only_unique_instructions": replay_instructions,
                "final_covered_source_lines": row.get("final_covered_source_line_count"),
                "replay_covered_source_lines": row.get("replay_covered_source_line_count"),
                "post_replay_new_source_lines": row.get("post_replay_new_source_line_count"),
                "property_violations": row.get("property_violations", []),
                "property_status_count": len(result.get("property_statuses_observed", {})),
                "corpus_file_count_after_run": len(result.get("corpus_files_after_run", [])),
                "result_directory": row.get("result_directory"),
                "log_file": result.get("full_log_file"),
                "lcov_file": row.get("final_lcov_file"),
            })
        summary["groups"][group_name]["per_run"] = per_run
    summary["per_run_detail_source"] = raw_path.relative_to(ROOT).as_posix()
    write_json(summary_path, summary)


def main() -> None:
    output_root = ROOT / OUTPUT_ROOT
    source_path = ROOT / SOURCE_REPORT
    inventory, candidates = source_inventory(source_path)
    property_names = discover_harness_properties()
    ranges = target_path_ranges()
    if len(property_names) != 16:
        raise RuntimeError(f"Phase 24 預登記要求 16 個原生安全屬性，源碼枚舉得到 {len(property_names)}")
    plan_path = output_root / "实验方案冻结.json"
    inventory_matches = list(output_root.glob("Phase10*.json"))
    if len(inventory_matches) > 1:
        raise RuntimeError("Phase 10 来源清单副本不唯一，拒绝选择其中之一")
    inventory_path = inventory_matches[0] if inventory_matches else output_root / "Phase10来源候选与去重清单.json"
    replay_path = output_root / "Anvil候选逐笔回放.json"
    if output_root.exists():
        if not plan_path.is_file() or not replay_path.is_file():
            raise FileExistsError(f"已有 Phase 24 目录不是可安全续跑的预登记阶段：{output_root}")
        if (output_root / "正式运行开始记录.json").exists() or (output_root / "正式模糊测试").exists():
            raise FileExistsError(f"正式 campaign 已开始，拒绝再次执行以免覆盖：{output_root}")
        existing_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        existing_inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        if (existing_plan.get("source_report_sha256") != inventory["source_report_sha256"]
                or existing_inventory.get("source_report_sha256") != inventory["source_report_sha256"]):
            raise RuntimeError("续跑时 Phase 10 输入哈希与原冻结方案不一致")
        plan = existing_plan
        prior_replays = json.loads(replay_path.read_text(encoding="utf-8"))
        candidate_replays = prior_replays.get("records", [])
        if [row.get("source_candidate", {}).get("source_seed_id") for row in candidate_replays] != [
            row["source_seed_id"] for row in candidates
        ]:
            raise RuntimeError("已有 Anvil 回放记录与冻结来源候选次序不一致")
        print("发现未启动正式实验的 Phase 24 预登记运行；复用既有 Anvil 原始证据继续。", flush=True)
    else:
        output_root.mkdir(parents=True)
        write_json(inventory_path, inventory)
        plan = freeze_plan(inventory, property_names, ranges, output_root)
        candidate_replays = []
    print(f"方案已冻结；来源候选 {len(candidates)} 条，规范化序列 {inventory['raw_transaction_sequence_count_after_dedup']} 条。", flush=True)

    context_cache: dict[str, dict[str, Any]] = {}
    completed_ids = {row["source_candidate"]["source_seed_id"] for row in candidate_replays}
    for index, candidate in enumerate(candidates, start=1):
        if candidate["source_seed_id"] in completed_ids:
            continue
        if not candidate["source_corpus_exists"] or not candidate["source_corpus_matches_agent_transactions"]:
            replay = {
                "phase24_effective_seed": False,
                "phase24_invalid_reasons": ["source_corpus_missing_or_does_not_match_agent_transactions"],
                "replay_status": "not_replayed_source_mismatch",
            }
        else:
            prop_id = candidate["property_id"]
            if prop_id not in context_cache:
                context_cache[prop_id] = load_project_context("Request", [prop_id])
            try:
                replay = replay_candidate(candidate, context_cache[prop_id])
            except Exception as exc:
                replay = {
                    "phase24_effective_seed": False,
                    "phase24_invalid_reasons": [f"anvil_replay_exception:{type(exc).__name__}:{str(exc)[:300]}"],
                    "replay_status": "replay_exception",
                }
        record = {
            "source_candidate": candidate,
            "anvil_replay": replay,
            "phase24_effective_seed": replay.get("phase24_effective_seed", False),
            "invalid_reasons": replay.get("phase24_invalid_reasons", []),
        }
        candidate_replays.append(record)
        write_json(replay_path, {
            "source_report": inventory["source_report"],
            "candidate_records_processed": index,
            "candidate_count": len(candidates),
            "records": candidate_replays,
        })
        tx_statuses = [row.get("execution_class") or row.get("status")
                       for row in replay.get("transactions", [])]
        print(f"Anvil {index}/{len(candidates)}: {candidate['source_seed_id']} "
              f"{replay.get('replay_status')} {tx_statuses}", flush=True)

    by_sequence: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in candidate_replays:
        sequence_hash = record["source_candidate"].get("sequence_sha256")
        if sequence_hash:
            by_sequence[sequence_hash].append(record)
    valid_unique_seeds = []
    for sequence_hash, records in sorted(by_sequence.items()):
        valid_records = [row for row in records if row["phase24_effective_seed"]]
        if not valid_records:
            continue
        valid_records.sort(key=lambda row: (
            row["source_candidate"]["source_repetition"],
            row["source_candidate"]["property_id"],
            row["source_candidate"]["source_seed_id"] or ""))
        representative = valid_records[0]["source_candidate"]
        source_ids = sorted({row["source_candidate"]["property_id"] for row in valid_records})
        frozen_name = f"phase24-{sequence_hash[:20]}.txt"
        frozen_path = output_root / "冻结种子" / frozen_name
        frozen_path.parent.mkdir(parents=True, exist_ok=True)
        frozen_path.write_bytes((ROOT / representative["source_corpus_file"]).read_bytes())
        valid_unique_seeds.append({
            "sequence_sha256": sequence_hash,
            "frozen_corpus_file": frozen_path.relative_to(ROOT).as_posix(),
            "frozen_corpus_sha256": sha256_file(frozen_path),
            "corpus_filename": frozen_name,
            "representative_source_seed_id": representative["source_seed_id"],
            "representative_property_id": representative["property_id"],
            "valid_source_property_ids": source_ids,
            "source_seed_ids": sorted({row["source_candidate"]["source_seed_id"] for row in records}),
            "source_repetitions": sorted({row["source_candidate"]["source_repetition"] for row in records}),
            "transactions": representative["transactions"],
            "normalized_transactions": representative["normalized_transactions"],
            "source_record_count": len(records),
            "valid_source_record_count": len(valid_records),
            "source_records": [{
                "seed_id": row["source_candidate"]["source_seed_id"],
                "property_id": row["source_candidate"]["property_id"],
                "repetition": row["source_candidate"]["source_repetition"],
                "valid": row["phase24_effective_seed"],
                "invalid_reasons": row["invalid_reasons"],
            } for row in records],
        })

    represented_properties = sorted({
        property_id for seed in valid_unique_seeds for property_id in seed["valid_source_property_ids"]
    })
    collection_path = output_root / "种子集合冻结.json"
    collection_freeze = {
        "frozen_at_utc": utc_now(),
        "pre_registered_plan_sha256": sha256_file(plan_path),
        "source_candidate_count": len(candidates),
        "candidate_records_with_effective_anvil_replay": sum(row["phase24_effective_seed"] for row in candidate_replays),
        "unique_valid_seed_count": len(valid_unique_seeds),
        "distinct_valid_source_property_count": len(represented_properties),
        "distinct_valid_source_property_ids": represented_properties,
        "valid_unique_seeds": valid_unique_seeds,
        "invalid_and_duplicate_records_preserved_at": "Anvil候选逐笔回放.json",
    }
    if collection_path.is_file():
        previous_collection = json.loads(collection_path.read_text(encoding="utf-8"))
        if ([row["sequence_sha256"] for row in previous_collection.get("valid_unique_seeds", [])]
                != [row["sequence_sha256"] for row in valid_unique_seeds]):
            raise RuntimeError("续跑时有效种子集合与既有冻结记录不一致")
        valid_unique_seeds = previous_collection["valid_unique_seeds"]
        collection_freeze = previous_collection
        for seed in valid_unique_seeds:
            frozen_path = ROOT / seed["frozen_corpus_file"]
            if not frozen_path.is_file() or sha256_file(frozen_path) != seed["frozen_corpus_sha256"]:
                raise RuntimeError(f"冻结种子文件缺失或哈希变化：{frozen_path}")
    else:
        write_json(collection_path, collection_freeze)
        (output_root / "种子集合冻结.sha256").write_text(
            sha256_file(collection_path) + "  种子集合冻结.json\n", encoding="utf-8")

    if len(valid_unique_seeds) < 3 or len(represented_properties) < 3:
        blocker = {
            "phase": 24,
            "status": "stopped_before_formal_fuzzing",
            "reason": "deduplicated_effective_seed_gate_not_met",
            "unique_valid_seed_count": len(valid_unique_seeds),
            "distinct_valid_source_property_count": len(represented_properties),
            "required_unique_seeds": 3,
            "required_distinct_source_properties": 3,
            "candidate_replays": "Anvil候选逐笔回放.json",
        }
        write_json(output_root / "正式模糊测试阻断记录.json", blocker)
        write_json(output_root / "正式实验逐次结果.json", {"status": blocker["status"], "groups": {}})
        print("有效种子门槛未通过；已保留核验记录并按方案停止正式模糊测试。", flush=True)
        return

    valid_unique_seeds.sort(key=lambda seed: (seed["representative_property_id"], seed["sequence_sha256"]))
    seed_count = len(valid_unique_seeds)
    selected_count = (seed_count + 1) // 2
    baseline_root = output_root / "獨立回放" / "G0-empty"
    baseline_saved_path = output_root / "獨立回放" / "基线回放结果.json"
    if baseline_saved_path.is_file() and lcov_for_root(baseline_root)[0] is not None:
        baseline = json.loads(baseline_saved_path.read_text(encoding="utf-8"))
    else:
        baseline = run_echidna(baseline_root, ZERO_REPLAY_RANDOM_SEED, [], 0, REPLAY_TIMEOUT_SECONDS)
        write_json(baseline_saved_path, baseline)
    baseline_lcov, baseline_lines = lcov_for_root(baseline_root)
    if baseline_lcov is None:
        raise RuntimeError("空语料 test-limit=0 未生成 LCOV，无法按冻结方案计算回放增量")
    print(f"独立回放基线完成：{len(baseline_lines)} 行源码覆盖。", flush=True)

    single_replays: dict[str, dict[str, Any]] = {}
    single_lines: dict[str, set[tuple[str, int]]] = {}
    single_replay_path = output_root / "独立种子回放覆盖.json"
    saved_single_replays: dict[str, dict[str, Any]] = {}
    if single_replay_path.is_file():
        previous_singles = json.loads(single_replay_path.read_text(encoding="utf-8"))
        saved_single_replays = {row["sequence_sha256"]: row["result"]
                                for row in previous_singles.get("seeds", [])}
    for index, seed in enumerate(valid_unique_seeds, start=1):
        replay_root = output_root / "獨立回放" / f"seed-{seed['sequence_sha256'][:20]}"
        if seed["sequence_sha256"] in saved_single_replays and replay_root.exists():
            result = saved_single_replays[seed["sequence_sha256"]]
        else:
            result = run_echidna(replay_root, ZERO_REPLAY_RANDOM_SEED, [seed], 0, REPLAY_TIMEOUT_SECONDS)
        lcov_path, lines = lcov_for_root(replay_root)
        if lcov_path is None:
            raise RuntimeError(f"种子 {seed['sequence_sha256']} 的纯回放未生成 LCOV")
        single_replays[seed["sequence_sha256"]] = result
        single_lines[seed["sequence_sha256"]] = lines
        seed["independent_replay"] = {
            "result_directory": replay_root.relative_to(ROOT).as_posix(),
            "lcov_file": lcov_path.relative_to(ROOT).as_posix(),
            "lcov_sha256": sha256_file(lcov_path),
            "covered_source_line_count": len(lines),
            "new_source_lines_over_empty_baseline": len(lines - baseline_lines),
            "new_source_lines_over_empty_baseline_detail": [
                f"{path}:{line}" for path, line in sorted(lines - baseline_lines)],
            "replay_only_unique_instructions": result.get("unique_instructions_total"),
            "loaded_seed_count": result.get("loaded_seed_count"),
            "replayed_sequence_count": result.get("replayed_sequence_count"),
        }
        write_json(single_replay_path, {
            "baseline": baseline,
            "seeds": [{"sequence_sha256": key, "result": value}
                      for key, value in single_replays.items()],
        })
        print(f"独立回放 {index}/{seed_count}: {seed['sequence_sha256'][:12]} "
              f"+{len(lines - baseline_lines)} 源码行。", flush=True)

    selection_path = output_root / "组别选择冻结.json"
    existing_selection = json.loads(selection_path.read_text(encoding="utf-8")) if selection_path.is_file() else None
    greedy_order = list(valid_unique_seeds)
    greedy_order.sort(key=lambda seed: (seed["representative_property_id"], seed["sequence_sha256"]))
    greedy_selected: list[dict[str, Any]] = []
    greedy_covered = set(baseline_lines)
    greedy_steps = []
    for step in range(selected_count):
        remaining = [seed for seed in greedy_order if seed not in greedy_selected]
        scored = [(len(single_lines[seed["sequence_sha256"]] - greedy_covered), seed)
                  for seed in remaining]
        best_score = max(score for score, _ in scored)
        best_seed = next(seed for score, seed in scored if score == best_score)
        newly_covered = single_lines[best_seed["sequence_sha256"]] - greedy_covered
        greedy_selected.append(best_seed)
        greedy_covered.update(newly_covered)
        greedy_steps.append({
            "step": step + 1,
            "selected_sequence_sha256": best_seed["sequence_sha256"],
            "representative_source_seed_id": best_seed["representative_source_seed_id"],
            "representative_property_id": best_seed["representative_property_id"],
            "marginal_new_source_line_count": len(newly_covered),
            "marginal_new_source_lines": [f"{path}:{line}" for path, line in sorted(newly_covered)],
        })

    ordered_hashes = [seed["sequence_sha256"] for seed in greedy_order]
    random_pool = [next(seed for seed in valid_unique_seeds if seed["sequence_sha256"] == sequence_hash)
                   for sequence_hash in ordered_hashes]
    random_selected = random.Random(SELECTION_RANDOM_SEED).sample(random_pool, selected_count)
    random_selected.sort(key=lambda seed: (seed["representative_property_id"], seed["sequence_sha256"]))
    groups = {"G0": [], "G1": list(valid_unique_seeds), "G2": greedy_selected, "G3": random_selected}
    selection_freeze = {
        "frozen_at_utc": utc_now(),
        "seed_collection_freeze_sha256": sha256_file(output_root / "种子集合冻结.json"),
        "selection_metric": "marginal covered source lines from each individual test-limit=0 Echidna LCOV replay, relative to the empty-corpus replay; greedily maximize marginal set coverage",
        "selection_tie_break": "representative property ID then canonical transaction sequence SHA-256",
        "valid_seed_pool_order": ordered_hashes,
        "valid_seed_count": seed_count,
        "subset_size": selected_count,
        "greedy_steps_G2": greedy_steps,
        "random_rule_G3": {
            "algorithm": "Python random.Random(seed).sample(sorted_pool, k)",
            "seed": SELECTION_RANDOM_SEED,
            "sorted_pool_sequence_sha256": ordered_hashes,
            "selected_sequence_sha256": [seed["sequence_sha256"] for seed in random_selected],
        },
        "groups": {name: [seed["sequence_sha256"] for seed in selected]
                   for name, selected in groups.items()},
        "formal_results_read_before_freeze": False,
        "formal_paired_random_seeds": list(PAIRED_RANDOM_SEEDS),
    }
    if existing_selection is not None:
        if existing_selection.get("valid_seed_pool_order") != ordered_hashes:
            raise RuntimeError("续跑时有效种子池与已冻结 G2/G3 选择不一致")
        selection_freeze = existing_selection
        groups = {name: [next(seed for seed in valid_unique_seeds if seed["sequence_sha256"] == sequence_hash)
                         for sequence_hash in existing_selection["groups"][name]]
                  for name in ("G0", "G1", "G2", "G3")}
    else:
        write_json(selection_path, selection_freeze)
        (output_root / "组别选择冻结.sha256").write_text(
            sha256_file(selection_path) + "  组别选择冻结.json\n", encoding="utf-8")

    group_replay_results: dict[str, dict[str, Any]] = {"G0": baseline}
    group_replay_lines: dict[str, set[tuple[str, int]]] = {"G0": baseline_lines}
    group_replay_paths = {"G0": baseline_root}
    group_replay_records_path = next(iter(output_root.glob("*纯回放结果.json")), None)
    if group_replay_records_path is not None:
        group_replay_records = json.loads(group_replay_records_path.read_text(encoding="utf-8"))
        if set(group_replay_records) != {"G0", "G1", "G2", "G3"}:
            raise RuntimeError("已有组别纯回放记录不完整，拒绝覆盖")
        for group_name, record in group_replay_records.items():
            replay_root = ROOT / record["result_directory"]
            lcov_path, lines = lcov_for_root(replay_root)
            if lcov_path is None:
                raise RuntimeError(f"已有 {group_name} 纯回放结果没有 LCOV")
            group_replay_results[group_name] = record["result"]
            group_replay_lines[group_name] = lines
            group_replay_paths[group_name] = replay_root
    else:
        for group_name in ("G1", "G2", "G3"):
            replay_root = output_root / "组别种子纯回放" / group_name
            result = run_echidna(replay_root, ZERO_REPLAY_RANDOM_SEED, groups[group_name], 0,
                                 REPLAY_TIMEOUT_SECONDS)
            lcov_path, lines = lcov_for_root(replay_root)
            if lcov_path is None:
                raise RuntimeError(f"{group_name} 纯种子回放未生成 LCOV")
            group_replay_results[group_name] = result
            group_replay_lines[group_name] = lines
            group_replay_paths[group_name] = replay_root
            print(f"{group_name} 种子纯回放完成：{len(lines)} 行源码覆盖。", flush=True)
        group_replay_records = {}
        for group_name, result in group_replay_results.items():
            replay_root = group_replay_paths[group_name]
            lcov_path, lines = lcov_for_root(replay_root)
            group_replay_records[group_name] = {
                "result_directory": replay_root.relative_to(ROOT).as_posix(),
                "result": result,
                "lcov_file": lcov_path.relative_to(ROOT).as_posix() if lcov_path else None,
                "covered_source_line_count": len(lines),
                "replay_only_unique_instructions": result.get("unique_instructions_total"),
                "target_path_replay_coverage": region_lines(lines, ranges),
            }
        group_replay_records_path = output_root / "组别种子纯回放结果.json"
        write_json(group_replay_records_path, group_replay_records)

    formal_start = {
        "formal_started_at_utc": utc_now(),
        "plan_sha256": sha256_file(plan_path),
        "seed_collection_freeze_sha256": sha256_file(collection_path),
        "group_selection_freeze_sha256": sha256_file(output_root / "组别选择冻结.json"),
        "formal_results_read_before_start": False,
        "groups": selection_freeze["groups"],
        "paired_random_seeds": list(PAIRED_RANDOM_SEEDS),
        "test_limit": TEST_LIMIT,
        "stop_on_fail": False,
    }
    write_json(output_root / "正式運行開始記錄.json", formal_start)
    formal_records: dict[str, list[dict[str, Any]]] = {name: [] for name in groups}
    formal_line_sets: dict[str, dict[int, set[tuple[str, int]]]] = {name: {} for name in groups}
    for pair_index, random_seed in enumerate(PAIRED_RANDOM_SEEDS, start=1):
        for group_name in ("G0", "G1", "G2", "G3"):
            campaign_root = output_root / "正式模糊測試" / group_name / f"pair-{pair_index:02d}-seed-{random_seed}"
            try:
                result = run_echidna(campaign_root, random_seed, groups[group_name], TEST_LIMIT,
                                     RUN_TIMEOUT_SECONDS)
                lcov_path, final_lines = lcov_for_root(campaign_root)
                baseline_group_lines = group_replay_lines[group_name]
                newly_covered = final_lines - baseline_group_lines
                run_record = {
                    "group": group_name,
                    "pair_index": pair_index,
                    "random_seed": random_seed,
                    "result_directory": campaign_root.relative_to(ROOT).as_posix(),
                    "result": result,
                    "final_lcov_file": lcov_path.relative_to(ROOT).as_posix() if lcov_path else None,
                    "final_covered_source_line_count": len(final_lines),
                    "replay_covered_source_line_count": len(baseline_group_lines),
                    "post_replay_new_source_line_count": len(newly_covered),
                    "post_replay_new_source_lines": [f"{path}:{line}" for path, line in sorted(newly_covered)],
                    "target_path_replay_coverage": region_lines(baseline_group_lines, ranges),
                    "target_path_post_replay_new_coverage": region_lines(newly_covered, ranges),
                    "campaign_completed_at_test_limit": result.get("campaign_completed_at_test_limit", False),
                    "property_violations": result.get("property_violations", []),
                }
                formal_line_sets[group_name][random_seed] = final_lines
            except Exception as exc:
                run_record = {
                    "group": group_name,
                    "pair_index": pair_index,
                    "random_seed": random_seed,
                    "result_directory": campaign_root.relative_to(ROOT).as_posix(),
                    "campaign_status": "exception",
                    "error": f"{type(exc).__name__}: {str(exc)[:1000]}",
                    "post_replay_new_source_line_count": None,
                    "property_violations": [],
                }
            formal_records[group_name].append(run_record)
            write_json(output_root / "正式實驗逐次結果.json", {
                "status": "running",
                "groups": formal_records,
                "group_seed_replays": group_replay_records,
            })
            print(f"正式 {group_name} pair {pair_index}/5 seed={random_seed}: "
                  f"{run_record.get('campaign_status', run_record.get('result', {}).get('campaign_status'))}; "
                  f"new_lines={run_record.get('post_replay_new_source_line_count')}; "
                  f"instructions={run_record.get('result', {}).get('unique_instructions_total')}", flush=True)

    summaries: dict[str, Any] = {}
    for group_name, rows in formal_records.items():
        for row in rows:
            result = row.get("result", {})
            if "result" in row and row.get("post_replay_new_source_line_count") is not None:
                row["_replay_unique_instructions"] = group_replay_records[group_name]["replay_only_unique_instructions"]
        completed_count = sum(bool(row.get("campaign_completed_at_test_limit")) for row in rows)
        failed_count = len(rows) - completed_count
        summaries[group_name] = {
            "per_run": [{
                "pair_index": row.get("pair_index"),
                "random_seed": row.get("random_seed"),
                "campaign_status": row.get("result", {}).get("campaign_status", row.get("campaign_status")),
                "campaign_completed_at_test_limit": row.get("campaign_completed_at_test_limit", False),
                "result_directory": row.get("result_directory"),
                "elapsed_seconds": row.get("result", {}).get("elapsed_seconds"),
                "unique_instructions_total": row.get("result", {}).get("unique_instructions_total"),
                "replay_only_unique_instructions": group_replay_records[group_name]["replay_only_unique_instructions"],
                "final_covered_source_line_count": row.get("final_covered_source_line_count"),
                "replay_covered_source_line_count": row.get("replay_covered_source_line_count"),
                "post_replay_new_source_line_count": row.get("post_replay_new_source_line_count"),
                "target_path_post_replay_new_coverage": row.get("target_path_post_replay_new_coverage"),
                "property_violations": row.get("property_violations", []),
                "error": row.get("error"),
            } for row in rows],
            "campaign_success_count": completed_count,
            "campaign_failure_count": failed_count,
            "mean_elapsed_seconds": stats([row.get("result", {}).get("elapsed_seconds") for row in rows]),
            "mean_total_unique_instructions": stats([row.get("result", {}).get("unique_instructions_total") for row in rows]),
            "mean_replay_only_unique_instructions": group_replay_records[group_name]["replay_only_unique_instructions"],
            "mean_final_covered_source_lines": stats([row.get("final_covered_source_line_count") for row in rows]),
            "mean_post_replay_new_source_lines": stats([row.get("post_replay_new_source_line_count") for row in rows]),
            "property_violation_runs": sum(bool(row.get("property_violations")) for row in rows),
            "property_violation_occurrences": sorted({
                name for row in rows for name in row.get("property_violations", [])
            }),
            "replay_only_covered_source_lines": group_replay_records[group_name]["covered_source_line_count"],
            "target_path_replay_coverage": group_replay_records[group_name]["target_path_replay_coverage"],
            "target_path_post_replay_new_coverage_mean": {
                label: stats([row.get("target_path_post_replay_new_coverage", {}).get(label)
                              for row in rows if row.get("target_path_post_replay_new_coverage") is not None])
                for label in (region["label"] for region in ranges)
            },
        }

    paired_comparisons = {}
    for left, right, label in (("G1", "G0", "G1_minus_G0"), ("G2", "G3", "G2_minus_G3")):
        pairs = []
        for random_seed in PAIRED_RANDOM_SEEDS:
            left_row = next(row for row in formal_records[left] if row["random_seed"] == random_seed)
            right_row = next(row for row in formal_records[right] if row["random_seed"] == random_seed)
            left_lines = left_row.get("post_replay_new_source_line_count")
            right_lines = right_row.get("post_replay_new_source_line_count")
            pairs.append({
                "random_seed": random_seed,
                "left_group": left,
                "right_group": right,
                "left_new_source_lines": left_lines,
                "right_new_source_lines": right_lines,
                "new_source_line_difference": (left_lines - right_lines)
                    if left_lines is not None and right_lines is not None else None,
                "left_instructions": left_row.get("result", {}).get("unique_instructions_total"),
                "right_instructions": right_row.get("result", {}).get("unique_instructions_total"),
            })
        differences = [row["new_source_line_difference"] for row in pairs
                       if row["new_source_line_difference"] is not None]
        positive_wins = sum(value > 0 for value in differences)
        left_mean = summaries[left]["mean_post_replay_new_source_lines"]["mean"]
        right_mean = summaries[right]["mean_post_replay_new_source_lines"]["mean"]
        mean_gain = (left_mean - right_mean) if left_mean is not None and right_mean is not None else None
        threshold = max(5.0, (right_mean or 0.0) * 0.05)
        paired_comparisons[label] = {
            "pairs": pairs,
            "positive_pair_wins": positive_wins,
            "mean_new_source_line_gain": mean_gain,
            "minimum_mean_gain_required": threshold,
            "stable_advantage": bool(len(differences) == len(PAIRED_RANDOM_SEEDS)
                                     and positive_wins >= 4 and mean_gain is not None
                                     and mean_gain >= threshold),
        }

    overall = {
        "phase": 24,
        "status": "completed",
        "completed_at_utc": utc_now(),
        "source_candidate_count": len(candidates),
        "source_candidate_records_effective": sum(row["phase24_effective_seed"] for row in candidate_replays),
        "unique_valid_seed_count": len(valid_unique_seeds),
        "distinct_valid_property_ids": represented_properties,
        "group_seed_counts": {name: len(rows) for name, rows in groups.items()},
        "paired_random_seeds": list(PAIRED_RANDOM_SEEDS),
        "formal_campaign_count": sum(len(rows) for rows in formal_records.values()),
        "formal_campaign_success_count": sum(row.get("campaign_completed_at_test_limit", False)
                                              for rows in formal_records.values() for row in rows),
        "formal_campaign_failure_count": sum(not row.get("campaign_completed_at_test_limit", False)
                                             for rows in formal_records.values() for row in rows),
        "groups": summaries,
        "paired_comparisons": paired_comparisons,
        "coverage_interpretation": "Echidna unique instructions are exact final scalar totals; replay-only unique instructions come from separate test-limit=0 runs; post-replay new source lines are exact LCOV set differences. The new unique-instruction count is not exactly recoverable because Echidna provides no instruction-PC bitmap.",
        "raw_evidence_directory": OUTPUT_ROOT.as_posix(),
        "no_deepseek_calls": True,
    }
    write_json(output_root / "Phase24结果汇总.json", overall)
    write_json(output_root / "正式實驗逐次結果.json", {
        "status": "completed",
        "groups": formal_records,
        "group_seed_replays": group_replay_records,
        "summary_file": (output_root / "Phase24结果汇总.json").relative_to(ROOT).as_posix(),
    })
    print("Phase 24 正式运行完成。", flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--refresh-summary"]:
        refresh_saved_summary()
    else:
        main()
