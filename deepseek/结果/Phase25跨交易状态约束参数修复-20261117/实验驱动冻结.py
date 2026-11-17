#!/usr/bin/env python3
"""Phase 25：固定跨交易状态依赖样本上的约束修复与持续探索对照。"""

from __future__ import annotations

import copy
import argparse
import hashlib
import json
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

import 种子验证 as verifier
from AgentB import HARNESS_ADDRESS, SENDERS, to_echidna_sequence
from 属性种子上下文 import PROJECTS, load_project_context


BASE_COMMIT = "462dabeb50ef1b9c08fe50623fb735759fad0dac"
OUTPUT = ROOT / "deepseek/结果/Phase25跨交易状态约束参数修复-20261117"
REQUEST_SOURCE = Path("deepseek/结果/Agent种子语料/Request/9c7edf27282f4ab59886d322da5845da/逐属性Agent种子流程.json")
IMMUTABLE_SOURCE = Path("deepseek/结果/逐属性原生对照实验/2253a6ce251e4d44aea57f6be6378ff3/seed-generation/Immutable/a9d9745dffe4118dcc3a/逐属性Agent种子流程.json")
OPENNFT_MINT_SOURCE = Path("deepseek/结果/Agent种子语料/OpenNFTs/28ede2b017fe45d58f2a41d7a06ad4b1/逐属性Agent种子流程.json")
OPENNFT_TRANSFER_SOURCE = Path("deepseek/结果/Agent种子语料/OpenNFTs/e0a8efee17ed4c9abc72cf4e96066f13/逐属性Agent种子流程.json")
BEE_REGRESSION_SOURCE = Path("deepseek/结果/逐属性原生对照实验/种子效用核验-20261115/状态依赖回归.json")
REPETITIONS = (1, 2, 3)
ECHIDNA_SEEDS = (20261125, 20261135, 20261145)
ECHIDNA_TEST_LIMIT = 500
ECHIDNA_TIMEOUT_SECONDS = 1800
SEQ_LEN = 8
SHRINK_LIMIT = 1


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _candidate(source: Path, project: str, property_id: str,
               predicate) -> tuple[dict[str, Any], dict[str, Any]]:
    data = json.loads((ROOT / source).read_text(encoding="utf-8"))
    if data.get("project") != project:
        raise RuntimeError(f"来源项目不匹配：{source}")
    for property_row in data.get("property_results", []):
        if property_row.get("property_id") != property_id:
            continue
        for candidate in property_row.get("candidate_results", []):
            if predicate(candidate):
                return data, candidate
    raise RuntimeError(f"未从历史来源找到样本：{source}, {property_id}")


def _context_candidate(project: str, property_id: str, candidate_id: str,
                       transactions: list[dict[str, Any]], steps: list[dict[str, Any]],
                       source_records: list[dict[str, Any]]) -> dict[str, Any]:
    context = load_project_context(project, [property_id])
    prop = context["properties"][0]
    return {"project": project, "property_id": property_id,
            "candidate_id": candidate_id, "property": prop["property"],
            "steps": steps, "transactions": transactions,
            "context": context, "_source_records": source_records}


def _steps_from_transactions(transactions: list[dict[str, Any]],
                             rationale: str) -> list[dict[str, str]]:
    return [{"function": tx["function"], "rationale": rationale}
            for tx in transactions]


def _load_samples() -> list[dict[str, Any]]:
    request_data, request = _candidate(
        REQUEST_SOURCE, "Request", "c451c42790194538cf50",
        lambda row: row.get("status") == "replay_failed" and
        len((row.get("concrete_seed") or {}).get("transactions", [])) == 3)
    request_seed = request["concrete_seed"]
    request_transactions = copy.deepcopy(request_seed["transactions"])
    request_steps = copy.deepcopy(request.get("plan") or
                                  _steps_from_transactions(request_transactions,
                                                          "Phase 18 原有逐属性计划"))
    request_fixture = _context_candidate(
        "Request", request_seed["property_id"], request_seed["candidate_id"],
        request_transactions, request_steps,
        [{"report": REQUEST_SOURCE.as_posix(),
          "report_sha256": sha256_file(ROOT / REQUEST_SOURCE),
          "candidate_id": request.get("candidate_id"),
          "source_status": request.get("status"),
          "seed_id": request.get("seed_id"),
          "original_transactions": request_transactions}])
    request_fixture.update({"sample_id": "request_refund_quota",
                            "target_function": request_transactions[-1]["function"],
                            "dependency_hints": []})

    immutable_data, immutable = _candidate(
        IMMUTABLE_SOURCE, "Immutable", "a9d9745dffe4118dcc3a",
        lambda row: row.get("concrete_seed") and
        row.get("status") == "replay_failed" and
        len(row["concrete_seed"].get("transactions", [])) >= 3)
    immutable_seed = immutable["concrete_seed"]
    immutable_transactions = copy.deepcopy(immutable_seed["transactions"])
    immutable_fixture = _context_candidate(
        "Immutable", immutable_seed["property_id"], immutable_seed["candidate_id"],
        immutable_transactions,
        copy.deepcopy(immutable.get("plan") or
                      _steps_from_transactions(immutable_transactions,
                                              "Phase 21 原有 mint/authorization/transfer 计划")),
        [{"report": IMMUTABLE_SOURCE.as_posix(),
          "report_sha256": sha256_file(ROOT / IMMUTABLE_SOURCE),
          "candidate_id": immutable.get("candidate_id"),
          "source_status": immutable.get("status"),
          "seed_id": immutable.get("seed_id"),
          "original_transactions": immutable_transactions}])
    immutable_fixture.update({"sample_id": "immutable_mint_then_approve",
                              "target_function": immutable_transactions[1]["function"],
                              "dependency_hints": []})

    bee_data = json.loads((ROOT / BEE_REGRESSION_SOURCE).read_text(encoding="utf-8"))
    bee_record = next(row for row in bee_data["records"]
                      if row.get("project") == "BeeStorage" and
                      row.get("property_id") == "2c68514fc72b1303d6e8")
    bee_transactions = []
    for row in bee_record["original"]["resolved_transactions"]:
        bee_transactions.append({key: copy.deepcopy(row[key]) for key in
                                 ("function", "arguments", "sender", "value_wei",
                                  "delay_seconds", "delay_blocks") if key in row})
    bee_steps = _steps_from_transactions(bee_transactions,
                                         "Phase 17 原有 createBatch/topUp/expire 序列")
    bee_fixture = _context_candidate(
        "BeeStorage", bee_record["property_id"], bee_record["seed_id"],
        bee_transactions, bee_steps,
        [{"report": BEE_REGRESSION_SOURCE.as_posix(),
          "report_sha256": sha256_file(ROOT / BEE_REGRESSION_SOURCE),
          "seed_id": bee_record["seed_id"],
          "original_replay_status": bee_record["original"]["replay_status"],
          "historical_hint_replay_status":
              bee_record["with_historical_dependency_hints"]["replay_status"],
          "original_transactions": bee_transactions}])
    bee_fixture.update({"sample_id": "beestorage_batch_id_no_hint",
                        "target_function": bee_transactions[1]["function"],
                        "dependency_hints": []})
    bee_compatibility_fixture = copy.deepcopy(bee_fixture)
    bee_compatibility_fixture["sample_id"] = "beestorage_batch_id_explicit_hint_compatibility"
    bee_compatibility_fixture["dependency_hints"] = [{
        "transaction_index": 1, "field": "batchId", "depends_on_index": 0,
        "source": "Phase 15/17 existing explicit event binding",
    }]

    _, mint_candidate = _candidate(
        OPENNFT_MINT_SOURCE, "OpenNFTs", "50cc31144be4bad9bc9d",
        lambda row: row.get("status") == "executable" and row.get("concrete_seed") and
        len(row["concrete_seed"].get("transactions", [])) == 1)
    _, failed_transfer = _candidate(
        OPENNFT_TRANSFER_SOURCE, "OpenNFTs", "50cc31144be4bad9bc9d",
        lambda row: row.get("concrete_seed") and
        len(row["concrete_seed"].get("transactions", [])) == 1)
    open_context = load_project_context("OpenNFTs", ["50cc31144be4bad9bc9d"])
    open_property = open_context["properties"][0]
    harness_source = ROOT / "sol/真实项目/OpenNFTs/tests/echidna/OpenAutoMarketEx.e.sol"
    source_text = harness_source.read_text(encoding="utf-8")
    other_match = re.search(r"_other\s*=\s*address\(([^)]*)\)", source_text)
    if not other_match:
        raise RuntimeError("OpenNFTs Harness 中无法从属性源码解析 _other")
    other_literal = other_match.group(1).strip()
    other_integer = int(other_literal, 0)
    other_address = f"0x{other_integer:040x}"
    mint_transactions = copy.deepcopy(mint_candidate["concrete_seed"]["transactions"])
    transfer_source_transactions = copy.deepcopy(failed_transfer["concrete_seed"]["transactions"])
    transfer_transactions = copy.deepcopy(transfer_source_transactions)
    transfer = transfer_transactions[0]
    if len(transfer.get("arguments", [])) != 3:
        raise RuntimeError("OpenNFTs 历史 transferFrom 样本 ABI 参数数量不符")
    transfer["arguments"][1] = other_address
    open_transactions = mint_transactions + transfer_transactions
    open_fixture = _context_candidate(
        "OpenNFTs", "50cc31144be4bad9bc9d",
        "phase25-derived-mint-transfer-to-property-target",
        open_transactions,
        _steps_from_transactions(open_transactions,
                                 "历史 mint 与 transfer 样本拼接；接收地址由目标属性源码读取"),
        [{"report": OPENNFT_MINT_SOURCE.as_posix(),
          "report_sha256": sha256_file(ROOT / OPENNFT_MINT_SOURCE),
          "candidate_id": mint_candidate.get("candidate_id"),
          "source_status": mint_candidate.get("status"),
          "original_transactions": mint_transactions},
         {"report": OPENNFT_TRANSFER_SOURCE.as_posix(),
          "report_sha256": sha256_file(ROOT / OPENNFT_TRANSFER_SOURCE),
          "candidate_id": failed_transfer.get("candidate_id"),
          "source_status": failed_transfer.get("status"),
          "original_transactions": transfer_source_transactions,
          "fixture_change": {"argument": "to", "from": "historical recipient",
                             "to": other_address,
                             "basis": "_other constant parsed from requested balance property source"}}])
    open_fixture.update({"sample_id": "opennfts_reach_other_balance",
                         "target_function": open_transactions[-1]["function"],
                         "property_target_address": other_address,
                         "dependency_hints": []})
    return [request_fixture, immutable_fixture, bee_fixture,
            bee_compatibility_fixture, open_fixture]


def _source_hashes(samples: list[dict[str, Any]]) -> dict[str, str]:
    paths = {REQUEST_SOURCE, IMMUTABLE_SOURCE, OPENNFT_MINT_SOURCE,
             OPENNFT_TRANSFER_SOURCE, BEE_REGRESSION_SOURCE,
             Path("func/功能/种子验证.py"), Path("func/功能/跨交易状态约束.py"),
             Path("deepseek/实验过程/运行Agent种子流程.py"),
             Path("func/测试过程/Phase25跨交易状态约束实验.py")}
    out = {path.as_posix(): sha256_file(ROOT / path) for path in sorted(paths)}
    for sample in samples:
        project = sample["project"]
        artifact = PROJECTS[project]["artifact"]
        path = Path(artifact)
        out[path.as_posix()] = sha256_file(ROOT / path)
    return out


def _version(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                timeout=15, check=False)
        return (result.stdout + result.stderr).strip()[:600]
    except Exception as exc:
        return f"{type(exc).__name__}: {str(exc)[:200]}"


def _freeze(samples: list[dict[str, Any]]) -> tuple[dict[str, Any], Any]:
    if OUTPUT.exists():
        raise FileExistsError(f"拒绝覆盖已有 Phase 25 结果：{OUTPUT}")
    OUTPUT.mkdir(parents=True)
    frozen_dir = OUTPUT / "冻结V2"
    frozen_dir.mkdir()
    baseline = subprocess.run(
        ["git", "show", f"{BASE_COMMIT}:func/功能/种子验证.py"],
        cwd=ROOT, capture_output=True, check=True).stdout
    baseline_path = frozen_dir / "种子验证.py"
    baseline_path.write_bytes(baseline)
    frozen = _load_frozen_module(baseline_path)
    sample_rows = []
    for sample in samples:
        context = sample["context"]
        prop = context["properties"][0]
        artifact = json.loads((ROOT / PROJECTS[sample["project"]]["artifact"]).read_text(
            encoding="utf-8"))
        harness_path = Path(artifact["source"])
        sample_rows.append({
            "sample_id": sample["sample_id"], "project": sample["project"],
            "property_id": sample["property_id"], "property": prop.get("property"),
            "target_function": sample["target_function"],
            "property_target_address": sample.get("property_target_address"),
            "harness_path": harness_path.as_posix(),
            "harness_sha256": sha256_file(ROOT / harness_path),
            "contract_source_sha256s": _source_hashes([sample]),
            "source_records": sample["_source_records"],
            "transactions": sample["transactions"],
            "dependency_hints": sample["dependency_hints"],
        })
    plan = {
        "phase": 25,
        "experiment_status": "frozen-before-first-anvil-replay",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_commit": BASE_COMMIT,
        "baseline_source_sha256": sha256_bytes(baseline),
        "current_source_sha256s": _source_hashes(samples),
        "samples": sample_rows,
        "groups": {
            "G0": "冻结 commit 的原始种子验证器；不启用 Phase 25 约束修复",
            "G1": "当前 V2 回放器，启用唯一前序对象事件绑定、匹配事件键的单参数 view getter 观察及最多一次有界数值修复；修复后完整重新部署并回放",
            "G2": "与 G1 相同源码和配置，runtime_constraints=False；既有显式 dependency_hints 功能保留",
        },
        "selection_rule": "所有诊断交易在第一次回放前从指定历史记录冻结；OpenNFTs 仅把已有失败转账样本的接收地址替换为目标属性源码解析出的 _other，使其能检验目标余额可达性；不基于 G0-G2 结果改变种子或规则。",
        "repetitions": list(REPETITIONS),
        "anvil_configuration": {
            "chain_id": verifier.CHAIN_ID,
            "initial_timestamp": verifier.INITIAL_TIMESTAMP,
            "initial_block_number": verifier.INITIAL_BLOCK_NUMBER,
            "evm_revision": "shanghai", "gas_price_wei": 0,
            "gas_limit_per_transaction": verifier.MAX_TX_GAS,
            "anvil_version": _version([str(verifier.ANVIL_BIN), "--version"]),
            "same_project_session_per_pair": True,
        },
        "echidna_configuration": {
            "test_limit": ECHIDNA_TEST_LIMIT,
            "seeds": list(ECHIDNA_SEEDS), "seq_len": SEQ_LEN,
            "shrink_limit": SHRINK_LIMIT, "workers": 1,
            "stop_on_fail": False, "disable_slither": True,
            "timeout_seconds": ECHIDNA_TIMEOUT_SECONDS,
            "echidna_version": _version([str(verifier.ECHIDNA_BIN), "--version"]),
            "runs": "仅对 G1 完整回放有效的种子执行；每个种子与空语料原生组做 3 组配对 500-testLimit 对照。",
        },
        "api_calls": 0,
        "api_cost_usd": 0,
        "metrics": ["逐交易外层结果", "内部调用回滚与 callTracer", "持久 storage slot 变化",
                    "view getter 状态差异", "目标操作路径到达", "目标属性违反/状态",
                    "运行时间", "Echidna unique instructions", "最终 LCOV 命中行"],
        "coverage_separation": "Anvil 回放和 Echidna 模糊测试分开记录；Echidna 的最终 LCOV 是回放与后续变异的累计结果，不能从单份 LCOV 精确拆分，日志会保留种子回放和 fuzzing 计数证据。",
    }
    write_json(OUTPUT / "实验方案.json", plan)
    return plan, frozen


def _load_frozen_module(baseline_path: Path):
    import importlib.util
    sys.path.insert(0, str(ROOT / "deepseek"))
    spec = importlib.util.spec_from_file_location("phase25_frozen_v2", baseline_path)
    frozen = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(frozen)
    frozen.ROOT = ROOT
    frozen.ANVIL_BIN = verifier.ANVIL_BIN
    frozen.ECHIDNA_BIN = verifier.ECHIDNA_BIN
    return frozen


def _target_record(replay: dict[str, Any], target_function: str) -> dict[str, Any] | None:
    return next((row for row in replay.get("transactions", [])
                 if row.get("function") == target_function), None)


def _collect_paths(node: dict[str, Any] | None, prefix: tuple[str, ...] = ()) -> list[list[str]]:
    if not isinstance(node, dict):
        return []
    label = ":".join(str(node.get(key, "")) for key in ("type", "to") if node.get(key))
    here = (*prefix, label) if label else prefix
    paths = [list(here)] if here else []
    for child in node.get("calls", []) or []:
        paths.extend(_collect_paths(child, here))
    return paths


def _run_replay_arm(sample: dict[str, Any], arm: str, repetition: int,
                    session: Any, frozen: Any) -> dict[str, Any]:
    candidate = {key: value for key, value in sample.items()
                 if key not in {"transactions", "dependency_hints", "sample_id",
                                "target_function", "property_target_address", "_source_records"}}
    original = copy.deepcopy(sample["transactions"])
    transactions = copy.deepcopy(original)
    started = time.monotonic()
    attempts = []
    repair_history = []
    applied = False
    while True:
        replay_started = time.monotonic()
        options = {"session": session,
                   "dependency_hints": copy.deepcopy(sample.get("dependency_hints", []))}
        if arm == "G0":
            result = frozen.replay_seed(sample["project"], candidate, transactions, **options)
        else:
            result = verifier.replay_seed(sample["project"], candidate, transactions,
                                          runtime_constraints=(arm == "G1"), **options)
        result["attempt_elapsed_seconds"] = round(time.monotonic() - replay_started, 6)
        attempt_path = (OUTPUT / "Anvil原始" / sample["sample_id"] /
                        str(repetition) / arm / f"attempt-{len(attempts) + 1}.json")
        write_json(attempt_path, result)
        attempts.append({"path": attempt_path.relative_to(ROOT).as_posix(),
                         "sha256": sha256_file(attempt_path),
                         "replay_status": result.get("replay_status"),
                         "elapsed_seconds": result["attempt_elapsed_seconds"],
                         "repair_proposal": result.get("transactions", [{}])[-1].get(
                             "constraint_repair_proposal") if result.get("transactions") else None})
        proposal = next((row.get("constraint_repair_proposal") for row in result.get("transactions", [])
                         if row.get("constraint_repair_proposal")), None)
        if arm == "G1" and proposal and not applied:
            tx_index, argument_index = int(proposal["transaction_index"]) - 1, int(proposal["argument_index"])
            if 0 <= tx_index < len(transactions):
                tx = transactions[tx_index]
                old_arguments = list(tx.get("arguments", []))
                new_arguments = list(old_arguments)
                if 0 <= argument_index < len(new_arguments):
                    new_arguments[argument_index] = proposal["repaired_value"]
                    tx["arguments"] = new_arguments
                    repair_history.append({"transaction_index": tx_index + 1,
                                           "function": tx.get("function"),
                                           "argument_index": argument_index,
                                           "argument_name": proposal.get("argument_name"),
                                           "original_value": old_arguments[argument_index],
                                           "repaired_value": proposal["repaired_value"],
                                           "evidence": proposal,
                                           "replay_after_repair_required": True})
                    applied = True
                    continue
        break
    total_seconds = round(time.monotonic() - started, 6)
    target = _target_record(result, sample["target_function"])
    target_path = _collect_paths((target or {}).get("internal_call_trace"))
    target_success = bool(target and target.get("status") == "success" and
                          target.get("execution_class") not in
                          {"unexpected_internal_revert", "trace_unavailable"} and
                          not target.get("internal_errors"))
    property_signature = sample["property"].rsplit(".", 1)[-1]
    target_property_false = bool(target and target.get("all_property_values", {}).get(
        property_signature) is False)
    return {
        "sample_id": sample["sample_id"], "project": sample["project"],
        "property_id": sample["property_id"], "arm": arm,
        "repetition": repetition, "replay_status": result.get("replay_status"),
        "target_function": sample["target_function"],
        "target_operation_success": target_success,
        "target_execution_class": target.get("execution_class") if target else None,
        "target_transaction_record": target,
        "target_internal_call_paths": target_path,
        "target_property_false_after_operation": target_property_false,
        "target_property_violation": result.get("target_property_violation"),
        "initial_property_violations": result.get("initial_property_violations", []),
        "internal_revert_count": sum(len(row.get("internal_errors", []))
                                      for row in result.get("transactions", [])),
        "outer_revert_count": sum(row.get("status") == "reverted"
                                   for row in result.get("transactions", [])),
        "unique_instruction_count": None,
        "elapsed_seconds": total_seconds,
        "automatic_constraint_repair_applied": applied,
        "automatic_constraint_repairs": repair_history,
        "attempts": attempts,
        "resolved_transactions": result.get("resolved_transactions", []),
        "raw_result_path": attempts[-1]["path"],
    }


def _lcov_hits(campaign: Path) -> list[str]:
    files = list(campaign.glob("covered.*.lcov"))
    if len(files) != 1:
        return []
    source = ""
    hits = set()
    for line in files[0].read_text(encoding="utf-8").splitlines():
        if line.startswith("SF:"):
            raw = Path(line[3:])
            try:
                source = raw.relative_to(ROOT).as_posix()
            except ValueError:
                source = str(raw)
        elif line.startswith("DA:"):
            line_number, count, *_ = line[3:].split(",")
            if int(count) > 0:
                hits.add(f"{source}:{int(line_number)}")
    return sorted(hits)


def _echidna_campaign(sample: dict[str, Any], root: Path, random_seed: int,
                      seed_file: Path | None) -> dict[str, Any]:
    root.mkdir(parents=True, exist_ok=False)
    coverage = root / "coverage"
    coverage.mkdir()
    if seed_file:
        shutil.copy2(seed_file, coverage / seed_file.name)
    property_name = sample["property"].rsplit(".", 1)[-1].split("(", 1)[0]
    started = time.monotonic()
    result = verifier.run_echidna(
        sample["project"], root, property_name=property_name,
        test_limit=ECHIDNA_TEST_LIMIT, timeout=ECHIDNA_TIMEOUT_SECONDS,
        seed=random_seed, seq_len=SEQ_LEN, shrink_limit=SHRINK_LIMIT,
        stop_on_fail=False, disable_slither=True,
        test_mode="property" if property_name.startswith("echidna_") else "assertion",
        property_prefix=property_name, sender_pool=SENDERS)
    hits = _lcov_hits(root)
    if seed_file:
        replayed = any(seed_file.name in line for line in result.get("replayed_lines", []))
        loaded = result.get("loaded_seed_count", 0) >= 1
    else:
        replayed = False
        loaded = result.get("loaded_seed_count", 0) == 0
    summary = {
        "sample_id": sample["sample_id"],
        "treatment": "G1_valid_seed" if seed_file else "native_empty_corpus",
        "random_seed": random_seed, "test_limit": ECHIDNA_TEST_LIMIT,
        "status": result.get("status"), "exit_code": result.get("exit_code"),
        "loaded_seed_count": result.get("loaded_seed_count"),
        "external_seed_replayed": replayed,
        "corpus_load_expectation_met": loaded and (replayed if seed_file else True),
        "mutation_evidence": result.get("mutation_evidence"),
        "fuzzing_transactions": result.get("fuzzing_transactions"),
        "fuzzing_cases": result.get("fuzzing_cases"),
        "unique_instructions": result.get("unique_instructions"),
        "coverage_source": result.get("coverage_source"),
        "lcov_hit_line_count": len(hits), "lcov_hit_lines": hits,
        "target_property_results": result.get("target_property_results"),
        "property_failures": result.get("property_failures"),
        "elapsed_seconds": result.get("elapsed_seconds", round(time.monotonic() - started, 6)),
        "log_path": result.get("full_log_path"),
        "lcov_path": (next(root.glob("covered.*.lcov")).relative_to(ROOT).as_posix()
                      if list(root.glob("covered.*.lcov")) else None),
        "seed_file": seed_file.relative_to(ROOT).as_posix() if seed_file else None,
    }
    write_json(root / "campaign-summary.json", summary)
    write_json(root / "campaign-raw-result.json", result)
    return summary


def _aggregate_replays(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault((row["sample_id"], row["arm"]), []).append(row)
    summaries = []
    for (sample_id, arm), group in sorted(grouped.items()):
        summaries.append({"sample_id": sample_id, "arm": arm,
                          "runs": len(group),
                          "replay_successes": sum(row["replay_status"] == "executable" for row in group),
                          "replay_failures": sum(row["replay_status"] != "executable" for row in group),
                          "target_operation_successes": sum(row["target_operation_success"] for row in group),
                          "internal_reverts": sum(row["internal_revert_count"] for row in group),
                          "target_property_false_count": sum(
                              row["target_property_false_after_operation"] for row in group),
                          "mean_elapsed_seconds": statistics.mean(row["elapsed_seconds"] for row in group),
                          "mean_unique_instruction_count": None,
                          "api_calls": 0, "api_cost_usd": 0})
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-only", action="store_true",
                        help="只保存不可覆盖的实验方案与 G0 源码快照，不启动 Anvil")
    parser.add_argument("--run-frozen", action="store_true",
                        help="只运行已冻结方案；会校验当前代码和输入来源 SHA-256")
    args = parser.parse_args()
    samples = _load_samples()
    if args.run_frozen:
        plan_path = OUTPUT / "实验方案.json"
        if not plan_path.is_file():
            raise FileNotFoundError(f"未找到冻结方案：{plan_path}")
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("current_source_sha256s") != _source_hashes(samples):
            raise RuntimeError("冻结后生产代码或输入来源发生变化；拒绝在旧方案上继续实验")
        frozen_path = OUTPUT / "冻结V2/种子验证.py"
        if sha256_file(frozen_path) != plan.get("baseline_source_sha256"):
            raise RuntimeError("冻结的 G0 验证器哈希不匹配")
        frozen = _load_frozen_module(frozen_path)
    else:
        plan, frozen = _freeze(samples)
        print(f"冻结完成：{(OUTPUT / '实验方案.json').relative_to(ROOT)}", flush=True)
        if args.freeze_only:
            return

    replay_rows = []
    valid_g1: dict[str, dict[str, Any]] = {}
    for project in dict.fromkeys(row["project"] for row in samples):
        with verifier.AnvilSession() as session:
            for sample in (row for row in samples if row["project"] == project):
                for repetition in REPETITIONS:
                    for arm in ("G0", "G1", "G2"):
                        row = _run_replay_arm(sample, arm, repetition, session, frozen)
                        replay_rows.append(row)
                        write_json(OUTPUT / "Anvil汇总" / sample["sample_id"] /
                                   f"{arm}-重复{repetition}.json", row)
                        print(sample["sample_id"], arm, repetition,
                              row["replay_status"], row["target_operation_success"],
                              row["automatic_constraint_repair_applied"], flush=True)
                        if arm == "G1" and repetition == 1:
                            valid_g1[sample["sample_id"]] = row

    # 仅使用运行前冻结的有效性规则；所有有效 G1 种子进入等预算原生 Echidna 对照。
    echidna_rows = []
    echidna_seed_files: dict[str, Path] = {}
    for sample in samples:
        g1 = valid_g1.get(sample["sample_id"])
        if not g1 or g1["replay_status"] != "executable":
            continue
        context = sample["context"]
        sequence = to_echidna_sequence(
            {"candidate_id": sample["candidate_id"],
             "property_id": sample["property_id"], "steps": sample["steps"]},
            g1["resolved_transactions"], context, contract_address=HARNESS_ADDRESS)
        seed_root = OUTPUT / "Echidna输入种子" / sample["sample_id"]
        seed_root.mkdir(parents=True, exist_ok=True)
        seed_path = seed_root / "coverage-seed.txt"
        seed_path.write_text(json.dumps(sequence, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
        echidna_seed_files[sample["sample_id"]] = seed_path
        for random_seed in ECHIDNA_SEEDS:
            for treatment, input_seed in (("native_empty_corpus", None),
                                          ("G1_valid_seed", seed_path)):
                result = _echidna_campaign(
                    sample,
                    OUTPUT / "Echidna" / sample["sample_id"] / str(random_seed) / treatment,
                    random_seed, input_seed)
                echidna_rows.append(result)
                print("Echidna", sample["sample_id"], random_seed, treatment,
                      result["unique_instructions"], result["external_seed_replayed"],
                      flush=True)

    summary = {"plan": plan,
               "replay_runs": replay_rows,
               "replay_summary": _aggregate_replays(replay_rows),
               "echidna_runs": echidna_rows,
               "echidna_summary": []}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in echidna_rows:
        grouped.setdefault((row["sample_id"], row["treatment"]), []).append(row)
    for (sample_id, treatment), group in sorted(grouped.items()):
        instructions = [row["unique_instructions"] for row in group
                        if isinstance(row["unique_instructions"], (int, float))]
        lines = [row["lcov_hit_line_count"] for row in group]
        failures = sum(bool(row.get("property_failures")) for row in group)
        summary["echidna_summary"].append({
            "sample_id": sample_id, "treatment": treatment, "runs": len(group),
            "completed_runs": sum(row["status"] == "completed" for row in group),
            "successful_corpus_replay_runs": sum(row["external_seed_replayed"] for row in group),
            "property_failure_runs": failures,
            "mean_unique_instructions": statistics.mean(instructions) if instructions else None,
            "mean_lcov_hit_line_count": statistics.mean(lines) if lines else None,
            "mean_elapsed_seconds": statistics.mean(row["elapsed_seconds"] for row in group),
            "api_calls": 0, "api_cost_usd": 0,
        })
    write_json(OUTPUT / "Phase25原始汇总.json", summary)
    print(f"结果：{(OUTPUT / 'Phase25原始汇总.json').relative_to(ROOT)}", flush=True)


if __name__ == "__main__":
    main()
