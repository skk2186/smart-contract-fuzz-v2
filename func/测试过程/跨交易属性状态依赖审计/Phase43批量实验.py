#!/usr/bin/env python3
"""Phase43 单次冻结批处理：Olympia 100 样本、Phase42 Agent/E2/E3 与原生 Echidna。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入"),
                str(ROOT / "func/测试过程/跨交易属性状态依赖审计")]

import Phase41Drips端到端实验 as phase41
from AgentB import SENDERS, to_echidna_sequence
from deepseek接口 import CallBudget
from 属性种子上下文 import PROJECTS, load_project_context
from 项目配置 import register_project_profiles
from 状态反馈序列扩展 import (build_action_templates, feedback_vector,
                            propose_extensions, retain_diverse_prefixes,
                            sequence_fingerprint)
from 跨交易状态约束 import (bind_inserted_prerequisite,
                           cross_transaction_write_read_matches)


RESULT = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase43-20261123"
MANIFEST = RESULT / "dataset-manifest.json"
DATASET = RESULT / "dataset/olympia"
MAX_SEQUENCE_LENGTH = 8
E3_CANDIDATE_BUDGET = 24
ECHIDNA_ADDRESS = "0x00a329c0648769A73afAc7F9381E08FB43dBEA72"
ECHIDNA_DEPLOYER = "0x0000000000000000000000000000000000030000"
ECHIDNA_BIN = "/usr/local/bin/echidna"
SOLC = "/home/skk/smart-contract-fuzz-v2/.tools/olympia-solc/solc-v0.8.26"
SOLC_BIN = "/home/skk/smart-contract-fuzz-v2/.tools/phase43-solc-bin"
PYTHON_TARGET = "/home/skk/smart-contract-fuzz-v2/.tools/phase43-runtime-py311"
Z3_BIN = "/home/skk/smart-contract-fuzz-v2/.tools/phase43-z3-root/usr/bin"
PYTHON_BIN = "/usr/bin/python3.11"

CAMPAIGN_FIELDS = [
    "sample_id", "source", "dimension", "group", "phase", "seed", "status",
    "raw_sequence_count", "sequence_length", "transactions_succeeded",
    "complete_executable", "target_state_reached", "target_state_status",
    "property_value", "echidna_target_status", "native_counterexample",
    "time_to_first_native_counterexample_seconds", "seed_only_coverage",
    "new_coverage", "final_coverage", "unique_calls", "replayed_seed_count",
    "candidate_count", "extension_replay_count", "g2_binding_applicable", "g2_binding_success",
    "planning_seconds", "repair_seconds", "execution_seconds", "compile_seconds",
    "fuzz_seconds", "run_wall_seconds", "analysis_compile_prep_seconds", "static_analysis_seconds", "agent_total_seconds", "agent_a_seconds", "agent_b_seconds", "agent_tokens",
    "agent_cost_usd_offpeak", "agent_cost_usd_peak", "notes", "raw_dir"]
FAILURE_FIELDS = ["sample_id", "source", "dimension", "stage", "group", "seed",
                  "failure_class", "reason", "raw_log", "timestamp"]
ADMISSION_FIELDS = ["sample_id", "source", "dimension", "upstream_commit", "source_hash",
                    "native_property", "generator_reachability", "analysis_status",
                    "build_status", "native_admission", "v2_status", "blocking_reason"]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def append_csv(path: Path, fields: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.is_file() or path.stat().st_size == 0
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        writer.writerow({key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                         if isinstance(value, (dict, list)) else value
                         for key, value in row.items()})
        handle.flush()
        os.fsync(handle.fileno())


def replace_admission(sample_id: str, update: dict[str, Any]) -> None:
    path = RESULT / "admission.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline=""))) if path.is_file() else []
    for row in rows:
        if row.get("sample_id") == sample_id:
            row.update({k: str(v) for k, v in update.items()})
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ADMISSION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def record_failure(sample: dict[str, Any], stage: str, reason: str, *,
                   failure_class: str = "execution_failure", group: str = "",
                   seed: Any = "", raw_log: str = "") -> None:
    path = RESULT / "failures.csv"
    row = {
        "sample_id": sample.get("sample_id", ""), "source": sample.get("source", "Olympia"),
        "dimension": sample.get("dimension", ""), "stage": stage, "group": group,
        "seed": seed, "failure_class": failure_class, "reason": str(reason)[:2000],
        "raw_log": raw_log, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline=""))) if path.is_file() else []
    key = (row["sample_id"], stage, group, str(seed), failure_class)
    replacement = {key: str(value) for key, value in row.items()}
    for index, old in enumerate(rows):
        if (old.get("sample_id"), old.get("stage"), old.get("group", ""),
                old.get("seed", ""), old.get("failure_class")) == key:
            rows[index] = {**old, **replacement}
            break
    else:
        rows.append(replacement)
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FAILURE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def progress_update(sample_id: str, **fields: Any) -> None:
    path = RESULT / "progress.json"
    progress = read_json(path, {"schema_version": 1, "completed_samples": [],
                                "in_progress": None, "last_update": None})
    progress.update(fields)
    progress["last_update"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if sample_id and sample_id not in progress["completed_samples"] and fields.get("sample_complete"):
        progress["completed_samples"].append(sample_id)
    write_json(path, progress)


def campaign_row(sample: dict[str, Any], group: str, phase: str, *, seed: Any = "",
                 status: str = "", notes: str = "", raw_dir: str = "", **metrics: Any) -> None:
    path = RESULT / "campaign-results.csv"
    row = {
        "sample_id": sample["sample_id"], "source": "Olympia",
        "dimension": sample["dimension"], "group": group, "phase": phase,
        "seed": seed, "status": status, "notes": notes, "raw_dir": raw_dir,
        **metrics}
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline=""))) if path.is_file() else []
    key = (row["sample_id"], group, phase, str(seed))
    replacement = {field: json.dumps(value, ensure_ascii=False, sort_keys=True)
                   if isinstance(value, (dict, list)) else value for field, value in row.items()}
    for index, old in enumerate(rows):
        if (old.get("sample_id"), old.get("group"), old.get("phase"), old.get("seed", "")) == key:
            rows[index] = {**old, **{k: str(v) for k, v in replacement.items()}}
            break
    else:
        rows.append({k: str(v) for k, v in replacement.items()})
    temporary = path.with_suffix(".csv.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CAMPAIGN_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def runtime_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = ":".join([PYTHON_TARGET, str(ROOT / "deepseek"),
                                   str(ROOT / "func/功能"),
                                   env.get("PYTHONPATH", "")]).rstrip(":")
    env["SOLCX_BINARY_PATH"] = str(Path(SOLC).parent)
    env["PATH"] = ":".join([SOLC_BIN,
                            "/home/skk/smart-contract-fuzz-v2/.tools/olympia-venv/bin",
                            str(Path(PYTHON_BIN).parent), Z3_BIN,
                            "/usr/local/bin", "/usr/bin", env.get("PATH", "")])
    return env


def parse_echidna_log(log: str, elapsed: float, return_code: int | None,
                      timed_out: bool) -> dict[str, Any]:
    target_match = re.search(r"echidna_noBug:\s*(passing|falsified|failed)", log, re.I)
    status_text = target_match.group(1).lower() if target_match else "unknown"
    # Echidna 2.3.2 prints a worker-level "Test ... falsified!" marker and a
    # final "property: failed!" line for a real counterexample. Treating that
    # terminal word as an execution failure silently loses native findings.
    worker_falsification = re.search(
        r"\bTest\s+echidna_noBug\s+falsified!", log, re.IGNORECASE) is not None
    if status_text == "failed" and worker_falsification:
        status_text = "falsified"
    unique = re.findall(r"Unique instructions:\s*([0-9,]+)", log)
    corpus = re.findall(r"Corpus size:\s*([0-9,]+)", log)
    calls = re.findall(r"Total calls:\s*([0-9,]+)", log)
    loaded = [int(x.replace(",", "")) for x in
              re.findall(r"Loaded\s+([0-9,]+) transaction sequences from .*?/coverage", log)]
    replayed = len(re.findall(r"Sequence replayed from corpus file", log))
    compile_times = [float(x) for x in re.findall(r"Compiling .*? Done! \(([0-9.]+)s\)", log)]
    return {"status": ("timed_out" if timed_out else
                       "native_counterexample" if status_text == "falsified" else
                       "completed" if return_code == 0 and status_text == "passing" else
                       "failed"),
            "exit_code": return_code, "timed_out": timed_out,
            "target_property_status": status_text,
            "native_counterexample": status_text == "falsified",
            "elapsed_seconds": round(elapsed, 6),
            "time_to_first_native_counterexample_seconds": round(elapsed, 6)
                if status_text == "falsified" else None,
            "unique_instructions": int(unique[-1].replace(",", "")) if unique else None,
            "corpus_size": int(corpus[-1].replace(",", "")) if corpus else None,
            "unique_calls": int(calls[-1].replace(",", "")) if calls else None,
            "loaded_seed_sequences": sum(loaded), "replayed_seed_count": replayed,
            "echidna_compile_seconds": round(sum(compile_times), 6)}


def run_echidna(sample: dict[str, Any], source: Path, run_dir: Path, *,
                seed: int, timeout: int, test_limit: int,
                seed_sequences: list[list[dict[str, Any]]] | None = None,
                candidate: dict[str, Any] | None = None,
                context: dict[str, Any] | None = None,
                working_directory: Path | None = None) -> dict[str, Any]:
    if run_dir.exists():
        completed_result = read_json(run_dir / "result.json")
        retryable = (completed_result is not None and
                     (completed_result.get("status") == "timed_out" or
                      (completed_result.get("status") == "failed" and
                       completed_result.get("exit_code") not in (None, 0))))
        if completed_result is not None and not retryable:
            return completed_result
        prior_root = run_dir.parent / "prior-attempts"
        prior_root.mkdir(parents=True, exist_ok=True)
        index = 1
        while (prior_root / f"{run_dir.name}-{index:02d}").exists():
            index += 1
        run_dir.rename(prior_root / f"{run_dir.name}-{index:02d}")
    corpus = run_dir / "corpus"
    (corpus / "coverage").mkdir(parents=True, exist_ok=True)
    written = []
    for index, sequence in enumerate(seed_sequences or [], 1):
        payload = to_echidna_sequence(candidate or {}, sequence, context or {},
                                      contract_address=ECHIDNA_ADDRESS)
        digest = hashlib.sha256(json.dumps(sequence, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()[:16]
        path = corpus / "coverage" / f"seed-{index:02d}-{digest}.txt"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        written.append(str(path.relative_to(ROOT)))
    command = [ECHIDNA_BIN, str(source), "--contract", "Maze", "--test-mode", "property",
               "--workers", "1", "--seq-len", str(MAX_SEQUENCE_LENGTH),
               "--test-limit", str(test_limit), "--timeout", str(timeout), "--seed", str(seed),
               "--shrink-limit", "1", "--contract-addr", ECHIDNA_ADDRESS,
               "--deployer", ECHIDNA_DEPLOYER]
    for sender in SENDERS:
        command.extend(["--sender", sender])
    command.extend(["--corpus-dir", str(corpus), "--coverage-dir", str(corpus),
                    "--disable-onchain-sources", "--format", "text"])
    echidna_cwd = working_directory or ROOT
    echidna_cwd.mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "run-config.json", {
        "command": command, "seed": seed, "timeout_seconds": timeout,
        "test_limit": test_limit, "workers": 1, "sequence_length": MAX_SEQUENCE_LENGTH,
        "native_property": "echidna_noBug", "seed_files": written,
        "working_directory": str(echidna_cwd),
        "fresh_corpus": True})
    started = time.monotonic()
    try:
        completed = subprocess.run(command, cwd=echidna_cwd, env=runtime_env(),
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, timeout=timeout + 120, check=False)
        elapsed = time.monotonic() - started
        log = completed.stdout or ""
        rc, did_timeout = completed.returncode, False
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        log = (exc.stdout or "")
        if isinstance(log, bytes):
            log = log.decode("utf-8", errors="replace")
        rc, did_timeout = None, True
        log += "\nPHASE43_OUTER_TIMEOUT\n"
    (run_dir / "echidna.log").write_text(log, encoding="utf-8", errors="replace")
    metrics = parse_echidna_log(log, elapsed, rc, did_timeout)
    metrics.update({"command": command, "seed_files": written,
                    "raw_log": str((run_dir / "echidna.log").relative_to(ROOT))})
    write_json(run_dir / "result.json", metrics)
    return metrics


def compile_artifact(source: Path, artifact_path: Path) -> tuple[dict[str, Any], float]:
    import solcx
    start = time.monotonic()
    compiled = solcx.compile_source(source.read_text(encoding="utf-8"),
                                    output_values=["abi", "bin"],
                                    solc_binary=SOLC, via_ir=True,
                                    optimize_yul=True, optimize=True)
    _, artifact = next(iter(compiled.items()))
    result = {"abi": artifact["abi"], "bin": artifact["bin"],
              "compiler": {"version": "0.8.26", "via_ir": True,
                           "optimize_yul": True, "optimize": True}}
    write_json(artifact_path, result)
    return result, time.monotonic() - start


def property_replay(source: Path, artifact: dict[str, Any],
                    sequence: list[dict[str, Any]]) -> tuple[dict[str, Any], float]:
    """通用 ABI/PyEVM 执行入口；调用真实合约 getter，不读取 generator answers。"""
    start = time.monotonic()
    try:
        import eth.vm.forks.spurious_dragon.computation as spurious
        import eth.vm.forks.shanghai.computation as shanghai
        from web3 import Web3, EthereumTesterProvider
        from eth_abi import encode
        spurious.EIP170_CODE_SIZE_LIMIT = 100_000_000
        shanghai.MAX_INITCODE_SIZE = 100_000_000
        web3 = Web3(EthereumTesterProvider())
        accounts = list(web3.eth.accounts)
        if not web3.is_connected() or len(accounts) < len(SENDERS):
            raise RuntimeError("PyEVM provider is unavailable")
        web3.eth.default_account = accounts[0]
        factory = web3.eth.contract(abi=artifact["abi"], bytecode=artifact["bin"])
        deploy_hash = factory.constructor().transact({"from": accounts[0]})
        deploy_receipt = web3.eth.wait_for_transaction_receipt(deploy_hash)
        if deploy_receipt["status"] != 1:
            raise RuntimeError("constructor transaction reverted")
        contract = web3.eth.contract(address=deploy_receipt["contractAddress"], abi=artifact["abi"])
        sender_map = {str(sender).lower(): accounts[i] for i, sender in enumerate(SENDERS)}
        rows = []

        def observe() -> dict[str, Any]:
            values = {}
            for signature in ("bug()", "echidna_noBug()"):
                try:
                    value = contract.get_function_by_signature(signature)().call()
                    values[signature] = {"status": "observed", "value": value}
                except Exception as exc:
                    values[signature] = {"status": "unknown", "error": str(exc)[:300]}
            return values

        initial = observe()
        stopped = False
        for index, tx in enumerate(sequence, 1):
            signature = str(tx.get("function", ""))
            before = observe()
            row = {"index": index, "transaction_index": index, "function": signature,
                   "arguments": tx.get("arguments", []),
                   "logical_sender": tx.get("sender"), "status": "not_executed",
                   "state_before": before, "state_after": None,
                   "revert_reason": None, "outer_revert": False,
                   "target_property": None, "target_property_status": "unknown"}
            if stopped:
                rows.append(row)
                continue
            sender = sender_map.get(str(tx.get("sender", "")).lower())
            if sender is None:
                row.update({"status": "unsupported", "execution_class": "unsupported_sender",
                            "revert_reason": "sender is outside the configured Echidna pool"})
                stopped = True
            else:
                try:
                    delay_seconds = int(tx.get("delay_seconds", 0))
                    delay_blocks = int(tx.get("delay_blocks", 0))
                    if delay_seconds:
                        tester = web3.provider.ethereum_tester
                        current_time = int(tester.get_block_by_number("latest")["timestamp"])
                        tester.time_travel(current_time + delay_seconds)
                    if delay_blocks:
                        web3.provider.ethereum_tester.mine_blocks(delay_blocks)
                    function = contract.get_function_by_signature(signature)(*tx.get("arguments", []))
                    tx_hash = function.transact({"from": sender,
                                                 "value": int(tx.get("value_wei", 0))})
                    receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
                    success = int(receipt["status"]) == 1
                    row.update({"status": "success" if success else "failed",
                                "execution_class": "successful" if success else "outer_revert",
                                "transaction_hash": tx_hash.hex(),
                                "block_number": int(receipt["blockNumber"]),
                                "gas_used": int(receipt["gasUsed"]),
                                "actual_sender": sender})
                    if not success:
                        row["outer_revert"] = True
                        stopped = True
                except Exception as exc:
                    row.update({"status": "failed", "execution_class": "outer_revert",
                                "outer_revert": True,
                                "revert_reason": str(exc)[:1000]})
                    stopped = True
            after = observe()
            row["state_after"] = after
            bug = after.get("bug", {}).get("value")
            prop = after.get("echidna_noBug()", {}).get("value")
            if prop is not None:
                row["target_property"] = bool(prop)
                row["target_property_status"] = "passed" if prop else "failed"
            changed = [key for key in after
                       if after[key].get("status") == "observed" and
                       before.get(key, {}).get("value") != after[key].get("value")]
            row["predicate_getter_values"] = [
                {"signature": key, "arguments": [], "value": after[key]["value"],
                 "status": "observed"} for key in after
                if after[key].get("status") == "observed"]
            row["changed_predicate_getters"] = changed
            row["changed_effect_states"] = (["Maze.bug"] if "bug()" in changed else [])
            row["changed_states"] = row["changed_effect_states"]
            rows.append(row)
        final = observe()
        bug_value = final.get("bug", {}).get("value")
        prop_value = final.get("echidna_noBug()", {}).get("value")
        all_success = len(rows) == len(sequence) and all(row.get("status") == "success" for row in rows)
        feedback = {
            "replay_status": "executable" if all_success else "partial_or_failed",
            "deployment_status": "success", "contract_address": contract.address,
            "transactions": rows, "initial_property_values": {
                "Maze.echidna_noBug()": initial.get("echidna_noBug()", {}).get("value")},
            "initial_predicate_getters": [
                {"signature": signature, "arguments": [], **value}
                for signature, value in initial.items()],
            "final_predicate_getters": [
                {"signature": signature, "arguments": [], **value}
                for signature, value in final.items()],
            "target_property_state": {"property": "Maze.echidna_noBug()",
                "value": prop_value, "status": "observed" if prop_value is not None else "unknown",
                "counterexample_state_established": prop_value is False,
                "property_related_state_changed": any("echidna_noBug()" in row.get("changed_predicate_getters", []) for row in rows),
                "trajectory": [{"changed_predicate_getters": row.get("changed_predicate_getters", [])}
                               for row in rows]},
            "target_state": {"name": "Maze.bug()", "value": bug_value,
                             "status": "observed" if bug_value is not None else "unknown",
                             "reached": bug_value is True},
            "counterexample_state_established": prop_value is False,
            "engine": "PyEVM EthereumTesterProvider",
            "note": "本地执行反馈仅用于 V2 修复/扩展；漏洞发现只认原生 Echidna 属性结果。"}
        return feedback, time.monotonic() - start
    except Exception as exc:
        return {"replay_status": "deployment_failed", "deployment_status": "failed",
                "transactions": [], "error": f"{type(exc).__name__}: {exc}",
                "target_state": {"status": "unknown", "value": None}}, time.monotonic() - start


def seed_only_metrics(metrics: dict[str, Any] | None) -> tuple[bool, int | None]:
    if not metrics:
        return False, None
    return (metrics.get("loaded_seed_sequences", 0) > 0 and
            metrics.get("replayed_seed_count", 0) > 0), metrics.get("unique_instructions")


def e3_group(group: str, sample: dict[str, Any], base_sequence: list[dict[str, Any]],
             base_feedback: dict[str, Any], context: dict[str, Any],
             artifact: dict[str, Any], analysis: dict[str, Any], task_dir: Path,
             *, bind: bool, target_guided: bool = False) -> dict[str, Any]:
    prop = context["properties"][0]
    abi_by_signature = {entry["name"] + "(" + ",".join(
        arg["type"] for arg in entry.get("inputs", [])) + ")": entry
        for entry in artifact["abi"] if entry.get("type") == "function"}
    templates, decisions = build_action_templates(
        prop.get("candidate_actions", []), abi_by_signature, base_sequence, SENDERS)
    action_evidence = {}
    for action in prop.get("candidate_actions", []):
        signature = action.get("abi_signature")
        if not signature:
            continue
        writes = sorted({str(effect.get("state")) for effect in action.get("effect_evidence", [])
                         if effect.get("state")})
        action_evidence[signature] = {**action, "write_states": writes,
            "read_states": sorted({str(state) for effect in action.get("effect_evidence", [])
                for guard in effect.get("guards", []) for state in guard.get("state_reads", [])})}
    target_states = set(prop.get("read_states", [])) | set(prop.get("property_write_states", []))
    effect_catalog = analysis.get("effect_catalog", {})
    output = task_dir / group
    output.mkdir(parents=True, exist_ok=True)
    budget_left = E3_CANDIDATE_BUDGET
    seen = {sequence_fingerprint(base_sequence)}
    frontier = [{"sequence": base_sequence, "feedback": base_feedback}]
    records = []
    replay_seconds = 0.0
    while frontier and budget_left > 0:
        next_frontier = []
        for parent_index, parent in enumerate(frontier):
            if budget_left <= 0:
                break
            proposals = propose_extensions(
                parent["sequence"], templates, action_evidence, abi_by_signature,
                mode="state_feedback", replay=parent["feedback"], target_states=target_states,
                senders=SENDERS, max_sequence_length=MAX_SEQUENCE_LENGTH,
                max_proposals=min(E3_CANDIDATE_BUDGET, budget_left),
                random_seed=4100 + parent_index,
                allow_repeated_prerequisite=target_guided)
            parent_vector = feedback_vector(parent["feedback"],
                property_source=prop.get("property_predicate") or "",
                action_evidence=action_evidence, target_states=target_states)
            scored = []
            for proposal in proposals:
                sequence = proposal["sequence"]
                fp = sequence_fingerprint(sequence)
                if fp in seen:
                    continue
                seen.add(fp)
                binding, binding_matches = None, []
                binding_status = "disabled_in_G1" if not bind else "not_evaluated"
                if bind:
                    binding_matches = cross_transaction_write_read_matches(
                        parent["sequence"], sequence, effect_catalog)
                    if binding_matches:
                        binding = bind_inserted_prerequisite(
                            parent["sequence"], sequence, effect_catalog,
                            abi_by_signature, parent_replay=parent["feedback"])
                        binding_status = ("applied" if binding and binding.get("status") == "applied"
                                          else "matched_but_unresolved")
                        if binding:
                            sequence = binding["sequence"]
                            fp = sequence_fingerprint(sequence)
                            if fp in seen:
                                continue
                            seen.add(fp)
                    else:
                        binding_status = "not_applicable_no_matching_cross_transaction_constraint"
                index = E3_CANDIDATE_BUDGET - budget_left + 1
                feedback, elapsed = property_replay(
                    RESULT / next(row["files"]["source"]["path"] for row in read_json(MANIFEST)["dataset"]["samples"]
                                  if row["sample_id"] == sample["sample_id"]), artifact, sequence)
                replay_seconds += elapsed
                write_json(output / f"{group}-e3-{index:02d}.sequence.json", sequence)
                write_json(output / f"{group}-e3-{index:02d}.feedback.json", feedback)
                budget_left -= 1
                vector = feedback_vector(feedback, property_source=prop.get("property_predicate") or "",
                                         action_evidence=action_evidence,
                                         parent_vector=parent_vector,
                                         target_states=target_states)
                record = {"candidate_index": index, "operator": proposal.get("operator"),
                    "proposal_reason": proposal.get("proposal_reason"), "proposal_evidence": proposal.get("evidence"),
                    "phase37_binding": binding, "phase37_binding_status": binding_status,
                    "phase37_matching_constraints": binding_matches, "sequence": sequence,
                    "replay_status": feedback.get("replay_status"), "feedback": vector,
                    "parent_feedback": parent_vector,
                    "selection_mode": "target_state_progress" if target_guided else "legacy_feedback",
                    "raw_feedback_file": str((output / f"{group}-e3-{index:02d}.feedback.json").relative_to(ROOT))}
                records.append(record)
                scored.append({"sequence": sequence, "feedback": vector,
                               "replay_feedback": feedback, "record": record})
            if scored:
                for retained in retain_diverse_prefixes(scored, limit=4,
                                                        target_state_guided=target_guided):
                    row = retained["record"]
                    vector = retained.get("feedback", {})
                    has_successful_prefix = int(vector.get("transactions_succeeded", 0)) > 0
                    has_pending_guard = any(item.get("status") == "state_prerequisite_unmet"
                                            for item in vector.get("precondition_conditions", []))
                    keep_frontier = (row.get("replay_status") == "executable" or
                                     has_successful_prefix or has_pending_guard or
                                     bool(vector.get("precondition_progress")) or
                                     vector.get("target_progress", {}).get("status") == "directional_progress")
                    if (target_guided and keep_frontier and
                            len(retained["sequence"]) < MAX_SEQUENCE_LENGTH):
                        next_frontier.append({"sequence": retained["sequence"],
                                              "feedback": retained["replay_feedback"]})
                    elif (not target_guided and row.get("replay_status") != "executable" and
                            len(retained["sequence"]) < MAX_SEQUENCE_LENGTH):
                        next_frontier.append({"sequence": retained["sequence"],
                                              "feedback": retained["replay_feedback"]})
        frontier = next_frontier
    valid = [row["sequence"] for row in records if row.get("replay_status") == "executable"]
    summary = {"group": group, "phase37_binding_enabled": bind,
        "starting_sequence_fingerprint": sequence_fingerprint(base_sequence),
        "starting_sequence": base_sequence, "action_template_count": len(templates),
        "template_decisions": decisions, "candidate_budget": E3_CANDIDATE_BUDGET,
        "selection_mode": "target_state_progress" if target_guided else "legacy_feedback",
        "candidate_count": len(records), "candidates": records,
        "valid_sequence_count": len(valid), "valid_sequences": valid,
        "replay_seconds": round(replay_seconds, 6)}
    write_json(output / f"{group}-result.json", summary)
    return summary


def initialize_outputs(samples: list[dict[str, Any]]) -> None:
    for filename, fields in (("campaign-results.csv", CAMPAIGN_FIELDS),
                             ("failures.csv", FAILURE_FIELDS),
                             ("admission.csv", ADMISSION_FIELDS)):
        path = RESULT / filename
        if not path.exists():
            with path.open("w", encoding="utf-8", newline="") as handle:
                csv.DictWriter(handle, fieldnames=fields).writeheader()
    admission = list(csv.DictReader((RESULT / "admission.csv").open(encoding="utf-8", newline="")))
    known = {row["sample_id"] for row in admission}
    for sample in samples:
        if sample["sample_id"] not in known:
            source = Path(sample["files"]["source"]["path"])
            append_csv(RESULT / "admission.csv", ADMISSION_FIELDS, {
                "sample_id": sample["sample_id"], "source": "Olympia",
                "dimension": sample["dimension"], "upstream_commit": sample["upstream_commit"],
                "source_hash": sample["files"]["source"]["sha256"],
                "native_property": sample["native_property"],
                "generator_reachability": sample["generation_status"],
                "analysis_status": "pending", "build_status": "pending",
                "native_admission": "pending", "v2_status": "pending", "blocking_reason": ""})
    real_rows = [
        ("SCFUZZ-AaveV4", "AaveV4"), ("SCFUZZ-SuperformV2", "SuperformV2"),
        ("SCFUZZ-LiquityV2Governance", "LiquityV2Governance"),
        ("SCFUZZ-OriginDollar", "OriginDollar")]
    known = {row["sample_id"] for row in csv.DictReader((RESULT / "admission.csv").open(encoding="utf-8", newline=""))}
    for sample_id, project in real_rows:
        if sample_id not in known:
            append_csv(RESULT / "admission.csv", ADMISSION_FIELDS, {
                "sample_id": sample_id, "source": "SCFuzzBench", "dimension": "",
                "upstream_commit": "078af185f3fa416cc13edfe3678f94c01a38d561",
                "source_hash": "", "native_property": "pending target task selection",
                "generator_reachability": "not_applicable", "analysis_status": "pending",
                "build_status": "pending", "native_admission": "pending",
                "v2_status": "pending", "blocking_reason": ""})


def analyze_and_context(sample: dict[str, Any], task_dir: Path) -> tuple[dict[str, Any] | None,
        dict[str, Any] | None, dict[str, Any] | None, Path, float, str | None]:
    source = RESULT / sample["files"]["source"]["path"]
    analysis_dir = task_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    report_path = analysis_dir / "property-analysis.json"
    artifact_path = analysis_dir / "compiler-artifact.json"
    start = time.monotonic()
    # Reuse only the exact first-sample, read-only static-analysis preflight artifact.
    if sample["sample_id"] == "OLYMPIA-001":
        preflight_report = RESULT / "preflight/analysis/sample-001-mapped.json"
        preflight_artifact = RESULT / "preflight/analysis/sample-001.artifact.json"
        if preflight_report.is_file() and preflight_artifact.is_file():
            shutil.copy2(preflight_report, report_path)
            shutil.copy2(preflight_artifact, artifact_path)
    if not artifact_path.is_file():
        artifact, _ = compile_artifact(source, artifact_path)
    else:
        artifact = read_json(artifact_path)
    if not report_path.is_file():
        command = [sys.executable, str(ROOT / "func/功能/属性分析适配器.py"),
                   str(source), "--contract", "Maze", "--output", str(report_path),
                   "--solc", SOLC]
        (analysis_dir / "command.json").write_text(json.dumps(command, ensure_ascii=False, indent=2)+"\n",
                                                    encoding="utf-8")
        try:
            result = subprocess.run(command, cwd=ROOT, env=runtime_env(),
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=240, check=False)
            (analysis_dir / "property-analysis.log").write_text(result.stdout or "", encoding="utf-8")
            if result.returncode != 0 or not report_path.is_file():
                return (None, artifact, None, source, time.monotonic()-start,
                        f"property adapter exit={result.returncode}; {((result.stdout or '')[-1000:])}")
        except subprocess.TimeoutExpired as exc:
            text = exc.stdout or ""
            if isinstance(text, bytes): text = text.decode("utf-8", errors="replace")
            (analysis_dir / "property-analysis.log").write_text(text, encoding="utf-8")
            return None, artifact, None, source, time.monotonic()-start, "property analysis timed out after 240 seconds"
    report = read_json(report_path)
    if not report or report.get("status") not in {"complete", "partial"}:
        return (report, artifact, None, source, time.monotonic()-start,
                f"static analysis status={None if report is None else report.get('status')}")
    targets = [row for row in report.get("properties", [])
               if row.get("property", "").rsplit(".", 1)[-1] == "echidna_noBug()"]
    if len(targets) != 1:
        return (report, artifact, None, source, time.monotonic()-start,
                f"native property selection matched {len(targets)} echidna_noBug targets")
    property_id = targets[0]["property_id"]
    project_key = sample["sample_id"].replace("-", "_")
    PROJECTS[project_key] = {"report": str(report_path.relative_to(ROOT)),
                             "artifact": str(artifact_path.relative_to(ROOT)),
                             "source_root": str((RESULT / "dataset/olympia/src").relative_to(ROOT)),
                             "contract": "Maze"}
    register_project_profiles(PROJECTS)
    context = load_project_context(project_key, [property_id])
    context["sender_pool"] = SENDERS
    context["agent_environment"] = {
        "chain_id": 1, "initial_timestamp": 0, "initial_block_number": 0,
        "evm_revision": "shanghai", "harness_address": ECHIDNA_ADDRESS,
        "property_sender": SENDERS[0], "gas_price_wei": 0,
        "gas_limit_per_transaction": 12_500_000}
    write_json(task_dir / "agent" / "property-context.json", context)
    return report, artifact, context, source, time.monotonic()-start, None


def e1_e2_seed_row(sample: dict[str, Any], group: str, phase: str, *,
                   sequence: list[dict[str, Any]] | None, feedback: dict[str, Any] | None,
                   elapsed: float = 0, note: str = "") -> None:
    target = (feedback or {}).get("target_state", {})
    prop = (feedback or {}).get("target_property_state", {})
    campaign_row(sample, group, phase, seed="", status=(feedback or {}).get("replay_status", "N/A"),
        raw_sequence_count=1 if sequence else 0,
        sequence_length=len(sequence) if sequence else 0,
        transactions_succeeded=sum(row.get("status") == "success" for row in (feedback or {}).get("transactions", [])),
        complete_executable=(feedback or {}).get("replay_status") == "executable",
        target_state_reached=target.get("reached"), target_state_status=target.get("status", "unknown"),
        property_value=prop.get("value"), execution_seconds=round(elapsed, 6), notes=note)


def task_state_path(sample: dict[str, Any]) -> Path:
    return RESULT / "tasks" / sample["sample_id"] / "task-state.json"


def run_task(sample: dict[str, Any]) -> dict[str, Any]:
    task_dir = RESULT / "tasks" / sample["sample_id"]
    state_path = task_state_path(sample)
    prior = read_json(state_path, {})
    if prior.get("status") == "completed":
        return prior
    task_dir.mkdir(parents=True, exist_ok=True)
    write_json(state_path, {"sample_id": sample["sample_id"], "status": "in_progress",
                            "started_at": prior.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                            "agent_call_state": prior.get("agent_call_state", {})})
    progress_update(sample["sample_id"], in_progress=sample["sample_id"],
                    current_stage="fresh_corpus_G0")
    replace_admission(sample["sample_id"], {"build_status": "compiled_and_reachability_verified",
        "native_admission": "native echidna_noBug available", "analysis_status": "running",
        "v2_status": "running"})
    seed_values = [4301, 4302, 4303]
    g0_results = []
    source = RESULT / sample["files"]["source"]["path"]
    start = time.monotonic()
    # G0 is run before any Agent request; each random seed receives an empty corpus.
    for seed in seed_values:
        run_dir = task_dir / "echidna" / "G0" / f"seed-{seed}"
        try:
            result = run_echidna(sample, source, run_dir, seed=seed, timeout=60,
                                 test_limit=1_000_000_000)
        except Exception as exc:
            result = {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                      "unique_instructions": None, "elapsed_seconds": 0,
                      "native_counterexample": False}
            record_failure(sample, "echidna_fuzz_G0", result["error"], group="G0", seed=seed,
                           raw_log=str(run_dir / "echidna.log"))
        if result.get("status") == "failed":
            log_path = run_dir / "echidna.log"
            reason = log_path.read_text(encoding="utf-8", errors="replace")[:1500] if log_path.exists() else result.get("error", "Echidna failed")
            record_failure(sample, "echidna_fuzz_G0", reason, group="G0", seed=seed,
                           failure_class="echidna_invocation_error",
                           raw_log=str(log_path.relative_to(ROOT)) if log_path.exists() else "")
        g0_results.append(result)
        campaign_row(sample, "G0", "formal_fuzz", seed=seed,
            status=result.get("status"), native_counterexample=result.get("native_counterexample"),
            echidna_target_status=result.get("target_property_status"),
            time_to_first_native_counterexample_seconds=result.get("time_to_first_native_counterexample_seconds"),
            final_coverage=result.get("unique_instructions"), unique_calls=result.get("unique_calls"),
            fuzz_seconds=result.get("elapsed_seconds"), compile_seconds=result.get("echidna_compile_seconds"),
            notes="原生 Echidna G0，无注入种子；普通 assertion 不计作目标反例。",
            raw_dir=result.get("raw_log", ""))
        progress_update(sample["sample_id"], current_stage=f"G0 seed {seed}",
                        last_echidna_status=result.get("status"))

    report, artifact, context, source, analysis_seconds, analysis_error = analyze_and_context(sample, task_dir)
    if analysis_error:
        replace_admission(sample["sample_id"], {"analysis_status": "failed",
            "v2_status": "not_run", "blocking_reason": analysis_error})
        record_failure(sample, "attribute_analysis", analysis_error,
                       failure_class="property_or_analysis_admission",
                       raw_log=str(task_dir / "analysis/property-analysis.log"))
        state = {"sample_id": sample["sample_id"], "status": "completed",
                 "pipeline_status": "completed_with_v2_admission_failure",
                 "analysis_status": "failed", "analysis_error": analysis_error,
                 "g0_runs": g0_results, "agent_call_state": prior.get("agent_call_state", {}),
                 "elapsed_seconds": round(time.monotonic()-start, 6)}
        write_json(state_path, state)
        return state
    replace_admission(sample["sample_id"], {"analysis_status": "complete",
        "v2_status": "agent_and_replay_started", "blocking_reason": ""})
    prop = context["properties"][0]
    api_log = task_dir / "agent" / "API调用.jsonl"
    api_log.parent.mkdir(parents=True, exist_ok=True)
    call_state = prior.get("agent_call_state", {})
    call_options = {"budget": CallBudget(1_500_000, deadline_monotonic=time.monotonic()+1800),
                    "log_path": api_log, "record_request_body": True, "max_retries": 0}
    candidates, a_events, planning = [], [], {"status": "not_called"}
    prior_a_result = read_json(task_dir / "agent/agent-a-result.json")
    if prior_a_result is not None:
        candidates = prior_a_result.get("candidates", [])
        a_events = prior_a_result.get("events", [])
        planning = prior_a_result.get("planning", {})
    elif not call_state.get("agent_a_started"):
        call_state["agent_a_started"] = True
        write_json(state_path, {"sample_id": sample["sample_id"], "status": "in_progress",
            "started_at": prior.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "agent_call_state": call_state})
        try:
            candidates, a_events, planning = phase41._agent_a_for_property(
                context, prop["property_id"], max_candidates=1, max_steps=MAX_SEQUENCE_LENGTH,
                planning_repairs=0, tag=f"Phase43_{sample['sample_id']}_AgentA",
                call_options=call_options)
        except Exception as exc:
            planning = {"status": "agent_a_error", "error": f"{type(exc).__name__}: {exc}"}
    else:
        planning = {"status": "agent_a_attempt_recorded_before_resume; request not repeated"}
    write_json(task_dir / "agent/agent-a-result.json", {
        "events": a_events, "planning": planning, "candidates": candidates,
        "calls": len(a_events), "sequence_length_max": MAX_SEQUENCE_LENGTH})
    candidate = phase41._candidate_context(candidates[0], context) if candidates else None
    concrete, b_events, b_error = None, [], "not_called_no_valid_agent_a_candidate"
    prior_b_result = read_json(task_dir / "agent/agent-b-result.json")
    if prior_b_result is not None:
        concrete = prior_b_result.get("concrete_output")
        b_events = prior_b_result.get("events", [])
        b_error = prior_b_result.get("error")
    elif candidate and not call_state.get("agent_b_started"):
        call_state["agent_b_started"] = True
        write_json(state_path, {"sample_id": sample["sample_id"], "status": "in_progress",
            "started_at": prior.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "agent_call_state": call_state})
        try:
            concrete, b_events, b_error = phase41._agent_b_call(
                context, candidate, feedback=None, first_attempt=1, schema_repairs=0,
                call_options=call_options)
        except Exception as exc:
            b_error = f"{type(exc).__name__}: {exc}"
    elif candidate:
        b_error = "agent_b_attempt_recorded_before_resume; request not repeated"
    write_json(task_dir / "agent/agent-b-result.json", {
        "events": b_events, "error": b_error, "concrete_output": concrete,
        "calls": len(b_events), "schema_repairs": 0})
    write_json(task_dir / "agent/agent-run.json", {
        "sample_id": sample["sample_id"], "property_id": prop["property_id"],
        "property": prop["property"], "agent_a": {"events": a_events, "planning": planning},
        "agent_b": {"events": b_events, "error": b_error}, "plan": candidates[0] if candidates else None,
        "concrete_output": concrete, "api_usage": phase41._api_summary(api_log),
        "agent_a_calls": len(a_events), "agent_b_calls": len(b_events),
        "request_log": str(api_log.relative_to(ROOT)), "retries": 0})
    sequence = (concrete or {}).get("transactions") or []
    if len(sequence) > MAX_SEQUENCE_LENGTH:
        sequence = []
        b_error = "Agent B sequence exceeds frozen limit 8"
        record_failure(sample, "agent_b_validation", b_error,
                       failure_class="sequence_length_exceeded")
    if not candidates:
        record_failure(sample, "agent_a", planning.get("error", planning.get("status", "no valid candidate")),
                       failure_class="agent_no_candidate")
    elif not concrete:
        record_failure(sample, "agent_b", b_error or "no concrete sequence",
                       failure_class="agent_b_no_concrete_sequence")

    e1_feedback, e1_seconds = ({"replay_status": "not_run", "transactions": []}, 0.0)
    if sequence:
        e1_feedback, e1_seconds = property_replay(source, artifact, sequence)
        write_json(task_dir / "E1/sequence.json", sequence)
        write_json(task_dir / "E1/v2-feedback.json", e1_feedback)
    e1_e2_seed_row(sample, "E1", "agent_replay", sequence=sequence or None,
                   feedback=e1_feedback, elapsed=e1_seconds, note="Agent A/B 原始序列，本地 getter 仅作目标状态观察。")
    e1_seed = None
    if sequence and e1_feedback.get("replay_status") == "executable":
        seed_dir = task_dir / "echidna/E1-seed-only"
        e1_seed = run_echidna(sample, source, seed_dir, seed=4301, timeout=60,
            test_limit=0, seed_sequences=[sequence], candidate=candidate, context=context)
        if e1_seed.get("status") == "failed":
            log_path = seed_dir / "echidna.log"
            record_failure(sample, "seed_only_E1", log_path.read_text(encoding="utf-8", errors="replace")[:1500]
                           if log_path.exists() else "Echidna failed", group="E1", seed=4301,
                           failure_class="echidna_invocation_error",
                           raw_log=str(log_path.relative_to(ROOT)) if log_path.exists() else "")
        campaign_row(sample, "E1", "seed_only", seed=4301, status=e1_seed.get("status"),
            complete_executable=True, target_state_reached=e1_feedback.get("target_state", {}).get("reached"),
            target_state_status=e1_feedback.get("target_state", {}).get("status"),
            property_value=e1_feedback.get("target_property_state", {}).get("value"),
            echidna_target_status=e1_seed.get("target_property_status"),
            native_counterexample=e1_seed.get("native_counterexample"),
            time_to_first_native_counterexample_seconds=e1_seed.get("time_to_first_native_counterexample_seconds"),
            seed_only_coverage=e1_seed.get("unique_instructions"),
            replayed_seed_count=e1_seed.get("replayed_seed_count"),
            execution_seconds=e1_seconds, compile_seconds=e1_seed.get("echidna_compile_seconds"),
            notes="E1 seed-only；仅目标原生 echidna_noBug falsified 计为反例。",
            raw_dir=e1_seed.get("raw_log", ""))
    else:
        campaign_row(sample, "E1", "seed_only", seed=4301, status="N/A",
                     notes="没有完整可执行的 E1 序列，未生成 corpus。")

    e2_started = time.monotonic()
    e2_proposal = phase41._e2_repair(context, sequence, e1_feedback) if sequence else {
        "applied": False, "sequence": [], "proposals": [], "propagated_argument_updates": []}
    e2_seconds = time.monotonic() - e2_started
    e2_sequence = e2_proposal.get("sequence") or sequence
    write_json(task_dir / "E2/repair.json", {**e2_proposal,
        "status": "repair_applied" if e2_proposal.get("applied") else "no_evidence_supported_repair"})
    e2_feedback, e2_replay_seconds = ({"replay_status": "not_run", "transactions": []}, 0.0)
    if e2_sequence:
        e2_feedback, e2_replay_seconds = property_replay(source, artifact, e2_sequence)
        write_json(task_dir / "E2/sequence.json", e2_sequence)
        write_json(task_dir / "E2/v2-feedback.json", e2_feedback)
    e1_e2_seed_row(sample, "E2", "repair_and_replay", sequence=e2_sequence or None,
                   feedback=e2_feedback, elapsed=e2_replay_seconds,
                   note=f"repair_applied={bool(e2_proposal.get('applied'))}")
    e2_seed = None
    if e2_sequence and e2_feedback.get("replay_status") == "executable":
        e2_seed = run_echidna(sample, source, task_dir / "echidna/E2-seed-only",
            seed=4301, timeout=60, test_limit=0, seed_sequences=[e2_sequence],
            candidate=candidate, context=context)
        if e2_seed.get("status") == "failed":
            log_path = task_dir / "echidna/E2-seed-only/echidna.log"
            record_failure(sample, "seed_only_E2", log_path.read_text(encoding="utf-8", errors="replace")[:1500]
                           if log_path.exists() else "Echidna failed", group="E2", seed=4301,
                           failure_class="echidna_invocation_error",
                           raw_log=str(log_path.relative_to(ROOT)) if log_path.exists() else "")
        campaign_row(sample, "E2", "seed_only", seed=4301, status=e2_seed.get("status"),
            complete_executable=True,
            target_state_reached=e2_feedback.get("target_state", {}).get("reached"),
            target_state_status=e2_feedback.get("target_state", {}).get("status"),
            property_value=e2_feedback.get("target_property_state", {}).get("value"),
            echidna_target_status=e2_seed.get("target_property_status"),
            native_counterexample=e2_seed.get("native_counterexample"),
            time_to_first_native_counterexample_seconds=e2_seed.get("time_to_first_native_counterexample_seconds"),
            seed_only_coverage=e2_seed.get("unique_instructions"),
            replayed_seed_count=e2_seed.get("replayed_seed_count"),
            repair_seconds=round(e2_seconds, 6), execution_seconds=e2_replay_seconds,
            compile_seconds=e2_seed.get("echidna_compile_seconds"),
            notes="E2 修复后 seed-only；只核实原生 echidna_noBug。",
            raw_dir=e2_seed.get("raw_log", ""))
    else:
        campaign_row(sample, "E2", "seed_only", seed=4301, status="N/A",
                     notes="没有完整可执行的 E2 序列，未生成 corpus。")

    group_results = {}
    group_sequences = {}
    if e2_sequence:
        for group, bind in (("G1", False), ("G2", True)):
            result = e3_group(group, sample, e2_sequence, e2_feedback,
                              context, artifact, report, task_dir, bind=bind)
            group_results[group] = result
            valid = ([e2_sequence] if e2_feedback.get("replay_status") == "executable" else [])
            valid.extend(result.get("valid_sequences", []))
            group_sequences[group] = valid
            campaign_row(sample, group, "extension", seed="",
                status="completed" if result["candidate_count"] or result["template_decisions"] else "completed_no_candidates",
                raw_sequence_count=result["candidate_count"],
                sequence_length=len(e2_sequence), complete_executable=result["valid_sequence_count"]>0,
                candidate_count=result["candidate_count"],
                g2_binding_applicable=sum(bool(row.get("phase37_matching_constraints")) for row in result["candidates"]),
                g2_binding_success=sum(row.get("phase37_binding_status")=="applied" for row in result["candidates"]),
                execution_seconds=result.get("replay_seconds", 0),
                notes=f"templates={result['action_template_count']}; base_E2_seed_eligible={e2_feedback.get('replay_status')=='executable'}",
                raw_dir=str((task_dir/group/f"{group}-result.json").relative_to(ROOT)))
            if valid:
                seed_dir = task_dir / "echidna" / f"{group}-seed-only"
                seed_only = run_echidna(sample, source, seed_dir, seed=4301, timeout=60,
                    test_limit=0, seed_sequences=valid, candidate=candidate, context=context)
                if seed_only.get("status") == "failed":
                    log_path = seed_dir / "echidna.log"
                    record_failure(sample, f"seed_only_{group}", log_path.read_text(encoding="utf-8", errors="replace")[:1500]
                                   if log_path.exists() else "Echidna failed", group=group, seed=4301,
                                   failure_class="echidna_invocation_error",
                                   raw_log=str(log_path.relative_to(ROOT)) if log_path.exists() else "")
                loaded, seed_cov = seed_only_metrics(seed_only)
                campaign_row(sample, group, "seed_only", seed=4301,
                    status=seed_only.get("status") if loaded else "seed_not_loaded",
                    complete_executable=True, echidna_target_status=seed_only.get("target_property_status"),
                    native_counterexample=seed_only.get("native_counterexample"),
                    time_to_first_native_counterexample_seconds=seed_only.get("time_to_first_native_counterexample_seconds"),
                    seed_only_coverage=seed_cov, replayed_seed_count=seed_only.get("replayed_seed_count"),
                    compile_seconds=seed_only.get("echidna_compile_seconds"),
                    notes=f"初始 E2 + G1/G2 完整执行候选；loaded={seed_only.get('loaded_seed_sequences')}; replayed={seed_only.get('replayed_seed_count')}",
                    raw_dir=seed_only.get("raw_log", ""))
                if not loaded:
                    group_sequences[group] = []
            else:
                campaign_row(sample, group, "seed_only", seed=4301, status="N/A",
                    complete_executable=False,
                    notes="无完整可执行种子，按要求记 N/A，不运行 seeded fuzz。")
                group_sequences[group] = []
    else:
        for group in ("G1", "G2"):
            group_results[group] = {"candidate_count": 0, "valid_sequence_count": 0,
                                    "valid_sequences": [], "action_template_count": 0}
            group_sequences[group] = []
            campaign_row(sample, group, "extension", status="N/A",
                notes="没有 E2 起始序列，不能运行扩展。")
            campaign_row(sample, group, "seed_only", seed=4301, status="N/A",
                notes="没有合格种子，未运行 seed-only。")

    for group in ("G1", "G2"):
        sequences = group_sequences.get(group, [])
        seed_only_loaded = bool(sequences)
        for seed in seed_values:
            if not seed_only_loaded:
                campaign_row(sample, group, "formal_fuzz", seed=seed, status="N/A",
                    complete_executable=False,
                    notes="没有合格且被 Echidna 加载的种子；未运行，覆盖为 N/A。")
                continue
            run_dir = task_dir / "echidna" / group / f"seed-{seed}"
            progress_update(sample["sample_id"], current_stage=f"{group} seed {seed}")
            print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} FUZZ_START {sample['sample_id']} {group} {seed}", flush=True)
            result = run_echidna(sample, source, run_dir, seed=seed, timeout=60,
                test_limit=1_000_000_000, seed_sequences=sequences,
                candidate=candidate, context=context)
            if result.get("status") == "failed":
                log_path = run_dir / "echidna.log"
                record_failure(sample, f"echidna_fuzz_{group}", log_path.read_text(encoding="utf-8", errors="replace")[:1500]
                               if log_path.exists() else "Echidna failed", group=group, seed=seed,
                               failure_class="echidna_invocation_error",
                               raw_log=str(log_path.relative_to(ROOT)) if log_path.exists() else "")
            initial_seed_cov = (e2_seed or {}).get("unique_instructions")
            final_cov = result.get("unique_instructions")
            campaign_row(sample, group, "formal_fuzz", seed=seed, status=result.get("status"),
                complete_executable=True,
                target_state_reached=(True if result.get("native_counterexample") else None),
                target_state_status=("confirmed_by_native_property_false" if result.get("native_counterexample") else "unknown"),
                echidna_target_status=result.get("target_property_status"),
                native_counterexample=result.get("native_counterexample"),
                time_to_first_native_counterexample_seconds=result.get("time_to_first_native_counterexample_seconds"),
                seed_only_coverage=initial_seed_cov,
                new_coverage=(max(0, final_cov-initial_seed_cov)
                              if final_cov is not None and initial_seed_cov is not None else None),
                final_coverage=final_cov, unique_calls=result.get("unique_calls"),
                replayed_seed_count=result.get("replayed_seed_count"),
                fuzz_seconds=result.get("elapsed_seconds"), compile_seconds=result.get("echidna_compile_seconds"),
                candidate_count=group_results.get(group, {}).get("candidate_count", 0),
                g2_binding_applicable=sum(bool(row.get("phase37_matching_constraints"))
                    for row in group_results.get(group, {}).get("candidates", [])) if group == "G2" else 0,
                g2_binding_success=sum(row.get("phase37_binding_status")=="applied"
                    for row in group_results.get(group, {}).get("candidates", [])) if group == "G2" else 0,
                agent_tokens=phase41._api_summary(api_log).get("total_tokens", 0),
                agent_cost_usd_offpeak=phase41._api_summary(api_log).get("estimated_cost_usd_offpeak", "0"),
                agent_cost_usd_peak=phase41._api_summary(api_log).get("estimated_cost_usd_peak", "0"),
                notes="Echidna 原生目标属性结果；unknown state 不反推为到达。",
                raw_dir=result.get("raw_log", ""))
            progress_update(sample["sample_id"], current_stage=f"{group} seed {seed} complete",
                            last_echidna_status=result.get("status"))
            print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} FUZZ_DONE {sample['sample_id']} {group} {seed} {result.get('status')}", flush=True)
    api_usage = phase41._api_summary(api_log) if api_log.exists() else {}
    state = {"sample_id": sample["sample_id"], "status": "completed",
        "pipeline_status": "completed" if not analysis_error else "completed_with_errors",
        "analysis_status": report.get("status"), "property_id": prop["property_id"],
        "property": prop["property"], "g0_runs": g0_results,
        "agent_a_calls": len(a_events), "agent_b_calls": len(b_events),
        "agent_a_status": planning.get("status"), "agent_b_status": "ready" if concrete else "failed_or_not_called",
        "e1_replay_status": e1_feedback.get("replay_status"),
        "e2_repair_applied": bool(e2_proposal.get("applied")),
        "e2_replay_status": e2_feedback.get("replay_status"),
        "e1_seed_only": e1_seed, "e2_seed_only": e2_seed,
        "g1_candidates": group_results.get("G1", {}).get("candidate_count", 0),
        "g2_candidates": group_results.get("G2", {}).get("candidate_count", 0),
        "g2_binding_applicable": sum(bool(row.get("phase37_matching_constraints"))
             for row in group_results.get("G2", {}).get("candidates", [])),
        "g2_binding_success": sum(row.get("phase37_binding_status")=="applied"
             for row in group_results.get("G2", {}).get("candidates", [])),
        "api_usage": api_usage, "analysis_and_compile_seconds": round(analysis_seconds, 6),
        "elapsed_seconds": round(time.monotonic()-start, 6), "agent_call_state": call_state}
    write_json(state_path, state)
    replace_admission(sample["sample_id"], {"analysis_status": report.get("status"),
        "build_status": "compiled_and_reachability_verified", "native_admission": "passed",
        "v2_status": state["pipeline_status"], "blocking_reason": ""})
    progress_update(sample["sample_id"], sample_complete=True,
                    current_stage="completed", last_property=prop["property"])
    return state


def rebuild_metrics() -> None:
    path = RESULT / "campaign-results.csv"
    if not path.is_file():
        return
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("source", ""), row.get("dimension", ""), row.get("group", ""))].append(row)
    fields = ["source", "dimension", "group", "phase", "run_count", "completed_count",
              "native_counterexamples", "native_counterexample_rate", "mean_final_coverage",
              "mean_seed_only_coverage", "mean_new_coverage", "median_first_counterexample_seconds",
              "mean_fuzz_seconds", "mean_agent_tokens", "mean_agent_cost_usd_offpeak"]
    output = RESULT / "metrics-summary.csv"
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for (source, dimension, group), subset in sorted(groups.items()):
            for phase in sorted({row.get("phase", "") for row in subset}):
                selected = [row for row in subset if row.get("phase") == phase]
                completed = [row for row in selected if row.get("status") in {"completed", "native_counterexample"}]
                falsified = [row for row in selected if str(row.get("native_counterexample", "")).lower() == "true"]
                def numbers(key: str) -> list[float]:
                    values=[]
                    for row in selected:
                        try:
                            value=float(row[key])
                            if value == value: values.append(value)
                        except (KeyError, TypeError, ValueError): pass
                    return values
                def mean(key: str) -> float | str:
                    values=numbers(key)
                    return round(sum(values)/len(values), 6) if values else "N/A"
                first=numbers("time_to_first_native_counterexample_seconds")
                first.sort()
                median=(round(first[len(first)//2],6) if first and len(first)%2 else
                        round((first[len(first)//2-1]+first[len(first)//2])/2,6) if first else "N/A")
                writer.writerow({"source":source,"dimension":dimension,"group":group,"phase":phase,
                    "run_count":len(selected),"completed_count":len(completed),
                    "native_counterexamples":len(falsified),
                    "native_counterexample_rate":round(len(falsified)/len(selected),6) if selected else "N/A",
                    "mean_final_coverage":mean("final_coverage"),"mean_seed_only_coverage":mean("seed_only_coverage"),
                    "mean_new_coverage":mean("new_coverage"),"median_first_counterexample_seconds":median,
                    "mean_fuzz_seconds":mean("fuzz_seconds"),"mean_agent_tokens":mean("agent_tokens"),
                    "mean_agent_cost_usd_offpeak":mean("agent_cost_usd_offpeak")})
        handle.flush(); os.fsync(handle.fileno())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0,
                        help="工程调试上限；0 表示按冻结清单自动执行全部样本")
    parser.add_argument("--resume", action="store_true", help="恢复断点，默认也跳过已完成样本")
    args = parser.parse_args()
    manifest = read_json(MANIFEST)
    samples = manifest["dataset"]["samples"]
    initialize_outputs(samples)
    preflight = [row for row in samples if row.get("preflight")]
    remaining = [row for row in samples if not row.get("preflight")]
    ordered = [*preflight, *remaining]
    if args.limit:
        ordered = ordered[:args.limit]
    progress = read_json(RESULT / "progress.json", {})
    # The task checkpoint is authoritative; an old progress list may include
    # attempts that ended in retryable engineering errors.
    already_done = {row["sample_id"] for row in samples
                    if read_json(task_state_path(row), {}).get("status") == "completed"}
    progress["completed_samples"] = sorted(already_done)
    write_json(RESULT / "progress.json", progress)
    run_rows = []
    for sample in ordered:
        if sample["sample_id"] in already_done and args.resume:
            continue
        # Completed task-state is always authoritative for safe restart.
        if read_json(task_state_path(sample), {}).get("status") == "completed":
            already_done.add(sample["sample_id"])
            continue
        print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} START {sample['sample_id']}", flush=True)
        try:
            state = run_task(sample)
        except Exception as exc:
            task_dir = RESULT / "tasks" / sample["sample_id"]
            task_dir.mkdir(parents=True, exist_ok=True)
            error = {"type": type(exc).__name__, "message": str(exc),
                     "traceback": traceback.format_exc()}
            write_json(task_dir / "uncaught-error.json", error)
            record_failure(sample, "batch_runner", error["message"],
                           failure_class=error["type"], raw_log=str((task_dir/"uncaught-error.json").relative_to(ROOT)))
            state = {"sample_id": sample["sample_id"], "status": "retryable_error",
                     "pipeline_status": "completed_with_runner_error", "error": error,
                     "agent_call_state": read_json(task_state_path(sample), {}).get("agent_call_state", {})}
            write_json(task_state_path(sample), state)
            progress_update(sample["sample_id"], sample_complete=True,
                            current_stage="completed_with_runner_error")
        already_done.add(sample["sample_id"])
        run_rows.append(state)
        rebuild_metrics()
        print(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} DONE {sample['sample_id']} {state.get('pipeline_status')}", flush=True)
        # After the frozen 20-item preflight queue, proceed automatically unless the
        # generic compiler/Echidna accounting chain failed on every sample.
        if len(already_done.intersection({row["sample_id"] for row in preflight})) == len(preflight):
            all_campaign = list(csv.DictReader((RESULT/"campaign-results.csv").open(encoding="utf-8", newline="")))
            sample_states = [read_json(task_state_path(row), {}) for row in preflight]
            required_keys = {(sample_id, group, phase) for sample_id in [row["sample_id"] for row in preflight]
                             for group, phase in (("G0", "formal_fuzz"), ("E1", "agent_replay"),
                                 ("E2", "repair_and_replay"), ("G1", "extension"), ("G1", "seed_only"),
                                 ("G2", "extension"), ("G2", "seed_only"))}
            actual_keys = {(row.get("sample_id"), row.get("group"), row.get("phase")) for row in all_campaign}
            analysis_ready = all(state.get("analysis_status") in {"complete", "partial"}
                                 for state in sample_states)
            campaign_ready = required_keys.issubset(actual_keys)
            g0_rows = [row for row in all_campaign if row.get("group") == "G0" and row.get("phase") == "formal_fuzz"]
            passed = analysis_ready and campaign_ready and len(g0_rows) >= len(preflight) * 3
            preflight_record = {"status": "passed_engineering_pipeline" if passed else "blocked_pipeline_incomplete",
                "preflight_sample_ids": [row["sample_id"] for row in preflight],
                "g0_campaign_rows": len(g0_rows),
                "analysis_ready": analysis_ready, "campaign_ready": campaign_ready,
                "completed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "note": "V2 success did not control inclusion; all 20 frozen samples retained."}
            write_json(RESULT/"preflight/preflight-result.json", preflight_record)
            if preflight_record["status"] != "passed_engineering_pipeline":
                break
    rebuild_metrics()
    progress_update("", current_stage="batch_finished_or_paused",
                    queued_samples=[row["sample_id"] for row in samples
                                    if row["sample_id"] not in already_done])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
