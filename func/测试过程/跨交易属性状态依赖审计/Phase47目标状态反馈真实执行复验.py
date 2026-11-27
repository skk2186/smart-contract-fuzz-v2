#!/usr/bin/env python3
"""Recheck Phase46 target-state feedback under one pinned Python runtime."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计"
P36 = BASE / "结果/Phase36-20261120"
P43 = BASE / "结果/Phase43-20261123"
P44 = BASE / "结果/Phase44-20261124"
P46 = BASE / "结果/Phase46-20261127"
OUT = BASE / "结果/Phase47-20261127"
PHASE46_DRIVER = BASE / "Phase46目标状态反馈配对实验.py"
FROZEN_PHASE46 = P46 / "phase46-frozen-config.json"
FROZEN_PHASE36 = P36 / "00-Phase36冻结.json"
FROZEN_INPUT_DALLOWANCE = P36 / "00-缺失前置步骤删减输入.json"
FROZEN_INPUT_WALLET = P36 / "00-Phase36冻结.json"
TARGET_SITE = ROOT / ".tools/phase43-runtime-py311"
PYTHON = ROOT / ".tools/uv/python/cpython-3.11-linux-x86_64-gnu/bin/python"
MAX_LENGTH = 64
CANDIDATES_PER_ARM = 12
RETAINED_PREFIXES = 4
ALGORITHM_SEED = 4701
ECHIDNA_SEED = 4702
FUZZ_SECONDS = 15
RUN_LOG = OUT / "phase47-run.log"
FREEZE = OUT / "phase47-frozen-config.json"
RUNTIME_RECORD = OUT / "phase47-runtime.json"
SMOKE_RECORD = OUT / "phase47-smoke.json"
SUMMARY = OUT / "phase47-paired-summary.json"
CODE_PATHS = (
    "func/功能/状态反馈序列扩展.py",
    "func/功能/种子验证.py",
    "func/功能/跨交易状态约束.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase36自适应扩展.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase37前置约束绑定验证.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase43批量实验.py",
    "func/测试过程/跨交易属性状态依赖审计/Phase46目标状态反馈配对实验.py",
)
CHILD_PROBE = r"""
import importlib.metadata as m, importlib.util, json, sys
import web3, eth_account
import eth_account._utils.typed_transactions as tx
names = ['web3','eth-account','eth-utils','eth-keys','eth-tester','py-evm']
versions = {}
for name in names:
    try: versions[name] = m.version(name)
    except m.PackageNotFoundError: versions[name] = None
print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'versions':versions,
 'web3_file':web3.__file__,'eth_account_file':eth_account.__file__,'typed_transactions_file':tx.__file__}))
"""


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def log(message: str) -> None:
    row = f"{datetime.now(timezone.utc).isoformat()} {message}"
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")
        handle.flush()
    print(row, flush=True)


def pinned_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("VIRTUAL_ENV", None)
    env["PYTHONPATH"] = os.pathsep.join((str(TARGET_SITE), str(ROOT / "deepseek"),
                                         str(ROOT / "func/功能")))
    return env


def probe_runtime() -> dict[str, Any]:
    if not PYTHON.is_file() or not TARGET_SITE.is_dir():
        raise RuntimeError("Pinned interpreter or Phase43 dependency directory is missing")
    child = subprocess.run([str(PYTHON), "-c", CHILD_PROBE], cwd=ROOT,
        env=pinned_env(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, timeout=20, check=False)
    if child.returncode != 0:
        raise RuntimeError(f"child runtime probe failed ({child.returncode}): {child.stdout[-2000:]}")
    result = json.loads(child.stdout.strip().splitlines()[-1])
    expected_root = str(TARGET_SITE.resolve()) + os.sep
    for field in ("web3_file", "eth_account_file", "typed_transactions_file"):
        if not str(Path(result[field]).resolve()).startswith(expected_root):
            raise RuntimeError(f"unexpected import origin for {field}: {result[field]}")
    if result["versions"].get("web3") != "6.19.0" or result["versions"].get("eth-account") != "0.11.2":
        raise RuntimeError(f"pinned package version mismatch: {result['versions']}")
    import web3
    import eth_account
    import eth_account._utils.typed_transactions as typed_transactions
    parent = {"executable": sys.executable, "web3_file": web3.__file__,
              "eth_account_file": eth_account.__file__,
              "typed_transactions_file": typed_transactions.__file__}
    for field in ("web3_file", "eth_account_file", "typed_transactions_file"):
        if not str(Path(parent[field]).resolve()).startswith(expected_root):
            raise RuntimeError(f"parent imported outside pinned environment for {field}: {parent[field]}")
    result.update({"target_site": str(TARGET_SITE), "pythonpath": pinned_env()["PYTHONPATH"],
                   "parent": parent, "child_returncode": child.returncode,
                   "child_stdout": child.stdout})
    return result


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def make_freeze(phase46, contexts: dict[str, Any], runtime: dict[str, Any]) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    phase46_cfg = read(FROZEN_PHASE46)
    cases: dict[str, Any] = {}
    for case_id in ("DAllowance", "Wallet02Refund"):
        row = contexts[case_id]
        cases[case_id] = {"project": row["project"],
            "sequence_sha256": phase46.seq_digest(row["sequence"]),
            "sequence": row["sequence"], "input_artifact_sha256": sha(FROZEN_INPUT_WALLET if case_id == "Wallet02Refund" else FROZEN_INPUT_DALLOWANCE)}
    olympia_cfg = phase46_cfg["cases"]["OLYMPIA-001"]
    cases["OLYMPIA-001"] = {"input_path": "func/测试过程/跨交易属性状态依赖审计/结果/Phase44-20261124/dev/tasks/OLYMPIA-001/inputs.json",
        "input_sha256": olympia_cfg["input_sha256"],
        "sequence_sha256": olympia_cfg["sequence_sha256"],
        "source_sha256": sha(P43 / next(row["files"]["source"]["path"] for row in read(P43 / "dataset-manifest.json")["dataset"]["samples"] if row["sample_id"] == "OLYMPIA-001"))}
    return {"phase": "Phase47", "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "baseline_head": head, "phase46_freeze_sha256": sha(FROZEN_PHASE46),
        "case_order": ["DAllowance", "Wallet02Refund", "OLYMPIA-001"],
        "cases": cases, "controls": {"max_sequence_length": MAX_LENGTH,
            "candidate_budget_per_arm": CANDIDATES_PER_ARM, "retained_prefixes": RETAINED_PREFIXES,
            "algorithm_seed": ALGORITHM_SEED, "echidna_seed": ECHIDNA_SEED,
            "phase37_binding_both_arms": True, "parameter_repair_both_arms": True,
            "agent_calls": 0, "oracle_or_reference_route_passed_to_generator": False},
        "runtime": runtime,
        "code_sha256": {path: sha(ROOT / path) for path in CODE_PATHS},
        "driver_sha256": sha(Path(__file__))}


def load_context(phase46):
    phase37, phase36, gate, contexts = phase46.load_phase37_cases()
    return phase37, phase36, gate, contexts


def run_smoke(phase46, phase37, phase36, gate, contexts):
    row = contexts["Wallet02Refund"]
    phase36.MAX_LENGTH = MAX_LENGTH
    phase36.MAX_EXECUTIONS = 0
    phase36.RETAINED_PREFIXES = RETAINED_PREFIXES
    phase36.SEED_BASE = ALGORITHM_SEED
    profile = __import__("属性种子上下文").PROJECTS[row["project"]]
    report_path, artifact_path = Path(profile["report"]), Path(profile["artifact"])
    if not report_path.is_absolute(): report_path = ROOT / report_path
    if not artifact_path.is_absolute(): artifact_path = ROOT / artifact_path
    report = read(report_path)
    abi = phase37._abi_map(artifact_path)
    result = phase36._run_g2(row["project"], row["candidate"], row["prop"], abi,
        row["sequence"], row["senders"], OUT / "smoke" / "Wallet02Refund", gate,
        binding_enabled=True, effect_catalog=report.get("effect_catalog", {}),
        target_guided=False)
    replay = result.get("base_replay") or {}
    txs = replay.get("transactions") or []
    ok = replay.get("deployment_status") == "success" and replay.get("replay_status") == "executable" and bool(txs) and all(tx.get("status") == "success" for tx in txs)
    summary = {"status": "passed" if ok else "failed", "deployment_status": replay.get("deployment_status"),
        "replay_status": replay.get("replay_status"), "transaction_count": len(txs),
        "transaction_statuses": [tx.get("status") for tx in txs],
        "property_value": replay.get("target_property_state"),
        "elapsed_seconds": result.get("elapsed_seconds"), "replay": replay}
    write(SMOKE_RECORD, summary)
    log(f"SMOKE Wallet02Refund status={summary['status']} deploy={summary['deployment_status']} replay={summary['replay_status']} tx={len(txs)}")
    return summary


def validate_freeze(freeze: dict[str, Any], runtime: dict[str, Any], phase46) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != freeze["baseline_head"]:
        raise RuntimeError(f"HEAD changed after freeze: {head}")
    if phase46.seq_digest(freeze["cases"]["Wallet02Refund"]["sequence"]) != freeze["cases"]["Wallet02Refund"]["sequence_sha256"]:
        raise RuntimeError("Wallet input hash mismatch")
    if runtime["executable"] != freeze["runtime"]["executable"] or runtime["versions"] != freeze["runtime"]["versions"]:
        raise RuntimeError("runtime differs from the smoke environment")
    for path, digest in freeze["code_sha256"].items():
        if sha(ROOT / path) != digest:
            raise RuntimeError(f"code changed after freeze: {path}")


def run_paired(phase46, phase36, gate, contexts, freeze: dict[str, Any]) -> dict[str, Any]:
    phase46.OUT = OUT
    phase46.RUN_LOG = RUN_LOG
    phase46.MAX_LENGTH = MAX_LENGTH
    phase46.CANDIDATES_PER_ARM = CANDIDATES_PER_ARM
    phase46.RETAINED_PREFIXES = RETAINED_PREFIXES
    phase46.ALGORITHM_SEED = ALGORITHM_SEED
    phase46.ECHIDNA_SEED = ECHIDNA_SEED
    phase46.FUZZ_SECONDS = FUZZ_SECONDS
    phase36.MAX_LENGTH = MAX_LENGTH
    phase36.MAX_EXECUTIONS = CANDIDATES_PER_ARM
    phase36.RETAINED_PREFIXES = RETAINED_PREFIXES
    phase36.SEED_BASE = ALGORITHM_SEED
    results = {}
    phase37, _phase36_again, _gate_again, _contexts = load_context(phase46)
    for case_id in freeze["case_order"]:
        if case_id == "OLYMPIA-001":
            case = phase46.run_olympia_case(case_id, read(P46 / "phase46-frozen-config.json"))
        else:
            case = phase46.run_phase37_case(case_id, read(P46 / "phase46-frozen-config.json"),
                                             (phase37, phase36, gate, contexts))
        results[case_id] = case
    summaries = {case_id: phase46.progress_summary(case) for case_id, case in results.items()}
    positive_cases = [case_id for case_id, summary in summaries.items()
        if summary["guided_independent_progress"]]
    output = {"phase": "Phase47", "cases": results, "progress_summary": summaries,
        "echidna_gate_open": bool(positive_cases), "gate_cases": positive_cases,
        "echidna_status": "not_run_candidate_gate_closed" if not positive_cases else "eligible_for_bounded_followup",
        "agent_calls": 0}
    write(SUMMARY, output)
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "paired", "fuzz"), required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True) if args.mode == "smoke" else None
    if args.mode == "smoke" and (FREEZE.exists() or SMOKE_RECORD.exists()):
        raise FileExistsError(f"Phase47 already initialized: {OUT}")
    if args.mode == "smoke":
        (OUT / "phase47-setup-attempts.log").write_text(
            "Attempt 1 stopped before runtime probe or contract deployment: the mode was initially declared as a positional argparse value beginning with '--', so argparse rejected the invocation. Generic correction: use required '--mode' option. No candidate budget or replay was consumed.\n",
            encoding="utf-8")
    phase46 = load_module("phase47_phase46", PHASE46_DRIVER)
    runtime = probe_runtime()
    write(RUNTIME_RECORD, runtime)
    phase37, phase36, gate, contexts = load_context(phase46)
    if args.mode == "smoke":
        freeze = make_freeze(phase46, contexts, runtime)
        write(FREEZE, freeze)
        smoke = run_smoke(phase46, phase37, phase36, gate, contexts)
        return 0 if smoke["status"] == "passed" else 2
    freeze = read(FREEZE)
    validate_freeze(freeze, runtime, phase46)
    if args.mode == "paired":
        if read(SMOKE_RECORD).get("status") != "passed":
            raise RuntimeError("Wallet deployment/replay smoke test did not pass")
        result = run_paired(phase46, phase36, gate, contexts, freeze)
        log(f"PAIRED done cases={len(result['cases'])} echidna_gate={result['echidna_gate_open']}")
        return 0
    summary = read(SUMMARY)
    if not summary.get("echidna_gate_open"):
        log("FUZZ skipped: no independently verified guided progress")
        return 0
    fuzz_results = {}
    for case_id in summary["gate_cases"]:
        fuzz_results[case_id] = phase46.run_fuzz_for_case(case_id, summary["cases"][case_id],
                                                          (phase37, phase36, gate, contexts))
    write(OUT / "phase47-echidna-summary.json", fuzz_results)
    log(f"FUZZ done cases={len(fuzz_results)} seed={ECHIDNA_SEED} seconds={FUZZ_SECONDS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
