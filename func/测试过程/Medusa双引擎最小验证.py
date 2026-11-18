#!/usr/bin/env python3
"""Phase 28 的可复现实验驱动；默认仅准备，不会启动模糊测试。"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from eth_utils import to_checksum_address


ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "func/测试过程/Medusa双引擎最小验证/结果"
MEDUSA = ROOT / ".tools/medusa/linux/medusa"
REPLAY_CHECKER = ROOT / ".tools/medusa/linux/replay-checker"
SOLC = ROOT / ".tools/olympia-venv/bin/solc"
SOLC_SELECT = ROOT / ".tools/olympia-venv/bin/solc-select"
PHASE25 = ROOT / "deepseek/结果/Phase25跨交易状态约束参数修复-20261117/Anvil原始"
OZ4 = ROOT / "sol/真实项目/DripsSCFuzzBench/lib/openzeppelin-contracts"
OZ5 = ROOT / "sol/真实项目/依赖/OpenZeppelin561"
FROZEN_SHA256 = {
    "BeeStorage": {
        "harness": "ac863a20587871404c449ef6fee36496736d495bba80f639880f0c262a2b4332",
        "abi": "b52571c9ec58da207d46ded4f569bcd578f09014c3431c315ffa450a03a33982",
    },
    "Immutable": {
        "harness": "5b96814001c3c523c768d76a48a3ce5ac429513a1b8af91e8500405ebc18d1dd",
        "abi": "b9e8dbc601775b13743d60a8186893f5cc55877cf34ec5dd2c02411fce916a02",
    },
}

CASES: dict[str, dict[str, Any]] = {
    "BeeStorage": {
        "seed": PHASE25 / "beestorage_batch_id_no_hint/1/G1/attempt-1.json",
        "abi": ROOT / "deepseek/结果/自主种子质量实验/BeeStorage-Harness编译.json",
        "harness": ROOT / "sol/真实项目/BeeStorage/src/echidna/EchidnaSystemHarness.sol",
        "contract": "EchidnaSystemHarness",
        "imports": ROOT / ".tools/medusa/imports/beestorage",
        "target_function": "act_actor_topUp(uint8,bytes32,uint256)",
        "property": "echidna_stamp_internal_pot_not_above_contract_balance()",
        "source_roots": [ROOT / "sol/真实项目/BeeStorage", OZ4],
        "property_checks": ["BatchTopUp event", "PostageStamp.batchTopUp return value"],
    },
    "Immutable": {
        "seed": PHASE25 / "immutable_mint_then_approve/1/G1/attempt-1.json",
        "abi": ROOT / ".tools/results/Immutable-Harness编译.json",
        "harness": ROOT / "sol/真实项目/Immutable/test/token/erc721/fuzz/ERC721PsiV2.Echidna.sol",
        "contract": "ERC721PsiV2Echidna",
        "imports": ROOT / ".tools/medusa/imports/immutable",
        "target_function": "approve(address,uint256)",
        "property": "echidna_complex_transfer_sequence()",
        "source_roots": [ROOT / "sol/真实项目/Immutable", OZ4, OZ5],
        "property_checks": ["Approval event", "ownerOf/getApproved getters if exposed by trace"],
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def stable_json_hash(obj: Any) -> str:
    return sha256_bytes(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())


def ensure_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        if link.resolve() != target.resolve():
            raise RuntimeError(f"已存在但指向不同依赖的本地链接：{link}")
        return
    if link.exists():
        raise RuntimeError(f"拒绝覆盖已有非链接路径：{link}")
    link.symlink_to(target.resolve(), target_is_directory=True)


def prepare_imports(case_name: str) -> None:
    case = CASES[case_name]
    ensure_link(case["imports"] / "sol", ROOT / "sol")
    if case_name == "BeeStorage":
        ensure_link(case["imports"] / "@openzeppelin/contracts", OZ4 / "contracts")
    else:
        ensure_link(case["imports"] / "openzeppelin-contracts-4", OZ4 / "contracts")
        ensure_link(case["imports"] / "openzeppelin-contracts-5", OZ5 / "contracts")


def medusa_compile_target(case: dict[str, Any]) -> Path:
	return case["imports"] / case["harness"].relative_to(ROOT)


def solidity_source_snapshot(case: dict[str, Any]) -> dict[str, str]:
    """按 import 图递归哈希 Harness 编译闭包，避免把整仓库无关源码算进来。"""
    aliases = [case["harness"].parent, ROOT, case["imports"]]
    queue = [case["harness"].resolve()]
    seen: dict[str, str] = {}
    import_pattern = re.compile(r"\bimport\s+(?:[^\"']*?\s+from\s+)?[\"']([^\"']+)[\"']\s*;")
    while queue:
        source = queue.pop().resolve()
        rel = source.as_posix()
        if rel in seen:
            continue
        if not source.is_file() or source.suffix != ".sol":
            continue
        seen[rel] = sha256_file(source)
        content = source.read_text(encoding="utf-8", errors="replace")
        for imported in import_pattern.findall(content):
            options = [source.parent / imported] + [root / imported for root in aliases]
            dependency = next((item.resolve() for item in options if item.exists() and item.is_file()), None)
            if dependency is None:
                raise RuntimeError(f"无法冻结导入依赖：{imported}（来自 {source}）")
            queue.append(dependency)
    return dict(sorted(seen.items()))


def write_plan(case_name: str) -> tuple[Path, Path]:
    case = CASES[case_name]
    prepare_imports(case_name)
    seed = json.loads(case["seed"].read_text(encoding="utf-8"))
    if sha256_file(case["harness"]) != FROZEN_SHA256[case_name]["harness"]:
        raise RuntimeError("当前 Harness 哈希与 Phase 25 冻结值不一致")
    if sha256_file(case["abi"]) != FROZEN_SHA256[case_name]["abi"]:
        raise RuntimeError("当前 ABI artifact 哈希与 Phase 25 冻结值不一致")
    env = seed["environment"]
    deployer = to_checksum_address(env["deployer"]).lower()
    source_address = to_checksum_address(seed["contract_address"]).lower()
    medusa_target = source_address
    case_root = RESULTS / "实验" / case_name
    case_root.mkdir(parents=True, exist_ok=True)
    deployment_map = {
        "source_to_medusa": {source_address: medusa_target},
        "deployer": deployer,
        "deployment_address_override": "Medusa fuzzing.predeployedContracts 将目标 Harness 固定在 Phase 25 部署地址，避免静默替换并保持内部 CREATE 地址可复现",
        "runtime_address_verified": False,
        "sender_addresses": env["sender_pool"],
        "source_initial_block_number": env.get("initial_block_number"),
        "source_initial_timestamp": env.get("initial_timestamp"),
        "source_chain_id": env.get("chain_id"),
        "absolute_initial_block_and_timestamp_supported_by_medusa_1_5_1": False,
    }
    deployment_path = case_root / "deployment-map.json"
    deployment_path.write_text(json.dumps(deployment_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sources = solidity_source_snapshot(case)
    compile_settings = {
        "platform": "crytic-compile",
        "target": str(medusa_compile_target(case)),
        "solc_version": "0.8.20",
        "working_directory": str(case["imports"]),
        "solc_args": f"--base-path {case['imports']} --allow-paths {ROOT},{case['imports']}",
        "optimizer": False,
        "evm_version": "shanghai",
    }
    plan = {
        "phase": 28,
        "case": case_name,
        "source_repository_baseline": "eb51e6de464ad73f1d32a2cbdd9fdeb20bc460cd",
        "seed_file": str(case["seed"]),
        "seed_sha256": sha256_file(case["seed"]),
        "seed_replay_status": seed.get("replay_status"),
        "harness": str(case["harness"]),
        "harness_sha256": sha256_file(case["harness"]),
        "solidity_source_closure": sources,
        "solidity_source_closure_sha256": stable_json_hash(sources),
        "abi_artifact": str(case["abi"]),
        "abi_artifact_sha256": sha256_file(case["abi"]),
        "abi_canonical_sha256": stable_json_hash(json.loads(case["abi"].read_text(encoding="utf-8"))["abi"]),
        "contract": case["contract"],
        "target_function": case["target_function"],
        "target_property": case["property"],
        "compile_settings": compile_settings,
        "compile_settings_sha256": stable_json_hash(compile_settings),
        "phase25_initial_environment": env,
        "deployment_map": str(deployment_path),
        "deployment_map_sha256": sha256_file(deployment_path),
        "medusa_contract_address_configured": medusa_target,
        "note": "地址映射必须经运行日志核验；Medusa v1.5.1 没有配置绝对起始区块号/时间戳，需按案例语义评估影响。",
    }
    plan_path = case_root / "frozen-inputs.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return case_root, deployment_path


def load_adapter():
    path = ROOT / "func/功能/Medusa种子适配.py"
    spec = importlib.util.spec_from_file_location("medusa_seed_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法导入 Medusa 种子适配器")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(case_name: str, corpus_dir: Path, log_dir: Path, timeout: int, test_limit: int) -> dict[str, Any]:
    case = CASES[case_name]
    solc_args = f"--base-path {case['imports']} --allow-paths {ROOT},{case['imports']}"
    return {
        "fuzzing": {
            "workers": 1,
            "workerResetLimit": 50,
            "timeout": timeout,
            "testLimit": test_limit,
            "shrinkLimit": 5000,
            "callSequenceLength": 8,
            "pruneFrequency": 5,
            "corpusDirectory": str(corpus_dir),
            "coverageEnabled": True,
            "coverageFormats": ["html", "lcov"],
            "coverageExclusions": [],
            "revertReporterEnabled": False,
            "targetContracts": [case["contract"]],
            "predeployedContracts": {case["contract"]: to_checksum_address(json.loads(case["seed"].read_text())["contract_address"])},
            "targetContractsBalances": [],
            "constructorArgs": {},
            "deployerAddress": to_checksum_address(json.loads(case["seed"].read_text())["environment"]["deployer"]),
            "senderAddresses": [to_checksum_address(item) for item in json.loads(case["seed"].read_text())["environment"]["sender_pool"]],
            "blockNumberDelayMax": 60480,
            "blockTimestampDelayMax": 604800,
            "transactionGasLimit": 12500000,
            "testing": {
                "stopOnFailedTest": False,
                "stopOnFailedContractMatching": True,
                "stopOnNoTests": True,
                "testAllContracts": False,
                "testViewMethods": True,
                "verbosity": 1,
                "assertionTesting": {"enabled": False},
                "propertyTesting": {"enabled": True, "testPrefixes": ["echidna_"]},
                "optimizationTesting": {"enabled": False, "testPrefixes": ["optimize_"]},
                "targetFunctionSignatures": [],
                "excludeFunctionSignatures": [],
            },
            "chainConfig": {
                "codeSizeCheckDisabled": True,
                "cheatCodes": {"cheatCodesEnabled": True, "enableFFI": False},
                "skipAccountChecks": True,
                "forkConfig": {"forkModeEnabled": False, "rpcUrl": "", "rpcBlock": 1, "poolSize": 20},
            },
        },
        "compilation": {
            "platform": "crytic-compile",
            "platformConfig": {
                "target": str(medusa_compile_target(case)),
                "solcVersion": "0.8.20",
                "exportDirectory": str(log_dir / "compiled"),
                "args": ["--compile-force-framework", "solc", "--solc-working-dir", str(case["imports"]), "--solc-args", solc_args],
            },
        },
        "slither": {"useSlither": False, "cachePath": str(log_dir / "slither-cache.json"), "args": []},
        "logging": {"level": "info", "logDirectory": str(log_dir / "medusa-log"), "noColor": True},
    }


def _prepare_campaigns(
    case_name: str,
    case_root: Path,
    corpus_source: Path,
    replay_only: bool = False,
    recovery: bool = False,
    selected_arm: str | None = None,
    selected_repeat: int | None = None,
) -> list[Path]:
    arms = ["M1"] if replay_only else [selected_arm] if selected_arm else ["M0", "M1"]
    repetitions = [1] if replay_only else [selected_repeat] if selected_repeat else [1, 2, 3]
    configs: list[Path] = []
    for arm in arms:
        for repetition in repetitions:
            run_name = f"repeat-{repetition}-recovery" if recovery and not replay_only else f"repeat-{repetition}"
            run_root = case_root / "replay-validation" if replay_only else case_root / "runs" / arm / run_name
            corpus_dir = run_root / "corpus"
            log_dir = run_root / "output"
            call_sequences = corpus_dir / "call_sequences"
            call_sequences.mkdir(parents=True, exist_ok=True)
            (log_dir / "compiled").mkdir(parents=True, exist_ok=True)
            if arm == "M1":
                seed_file = corpus_source / "call_sequences/v2_seed.json"
                if not seed_file.is_file():
                    raise RuntimeError("M1 需要已转换的 V2 corpus")
                shutil.copy2(seed_file, call_sequences / seed_file.name)
                shutil.copy2(corpus_source / "metadata/seed_manifest.json", corpus_dir / "seed_manifest.json")
            cfg = _config(case_name, corpus_dir, log_dir, 2 if replay_only else 60, 100 if replay_only else 100000)
            config_path = run_root / "medusa.json"
            config_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            configs.append(config_path)
    return configs


def run_seed_validation(case_name: str, case_root: Path, config_path: Path, corpus_source: Path) -> dict[str, Any]:
    if not REPLAY_CHECKER.is_file():
        raise RuntimeError(f"缺少 Medusa 逐笔回放核验程序：{REPLAY_CHECKER}")
    run_root = config_path.parent
    seed_json = corpus_source / "call_sequences/v2_seed.json"
    manifest = json.loads((corpus_source / "metadata/seed_manifest.json").read_text(encoding="utf-8"))
    target_address = manifest["medusa_contract_address"]
    target_index = next(
        i for i, tx in enumerate(manifest["transactions"]) if tx["function"] == CASES[case_name]["target_function"]
    )
    helper_json = run_root / "replay-check.json"
    helper_log = run_root / "replay-check.stdout.log"
    helper_started = time.monotonic()
    helper = subprocess.run(
        [str(REPLAY_CHECKER), "--case", case_name, "--config", str(config_path), "--corpus", str(seed_json),
         "--target", target_address, "--target-index", str(target_index), "--out", str(helper_json)],
        cwd=ROOT,
        env=medusa_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=180,
    )
    helper_elapsed = time.monotonic() - helper_started
    helper_log.write_text(helper.stdout, encoding="utf-8", errors="replace")
    helper_result: dict[str, Any] = {}
    if helper_json.is_file():
        helper_result = json.loads(helper_json.read_text(encoding="utf-8"))

    original_corpus_hash = sha256_file(seed_json)
    clean_log_path = run_root / "medusa-corpus-clean.log"
    clean_started = time.monotonic()
    clean = subprocess.run(
        [str(MEDUSA), "corpus", "clean", "--config", str(config_path)],
        cwd=ROOT,
        env=medusa_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=180,
    )
    clean_elapsed = time.monotonic() - clean_started
    clean_log_path.write_text(clean.stdout, encoding="utf-8", errors="replace")
    clean_match = re.search(r"Results:\s*(\d+) valid,\s*(\d+) invalid out of\s*(\d+) total sequences", clean.stdout)
    valid_count, invalid_count, total_count = (map(int, clean_match.groups()) if clean_match else (None, None, None))
    corpus_after_clean = run_root / "corpus/call_sequences/v2_seed.json"
    clean_valid = clean.returncode == 0 and valid_count == 1 and invalid_count == 0 and total_count == 1 and corpus_after_clean.is_file()
    source_hash_after = sha256_file(seed_json) if seed_json.is_file() else None
    original_seed_hash_now = sha256_file(CASES[case_name]["seed"])
    seed_replayed = helper_result.get("all_transactions_replayed") is True and helper_result.get("all_outer_transactions_succeeded") is True
    target_state = helper_result.get("target_state_established") is True
    target_tx = helper_result.get("target_transaction_succeeded") is True
    property_detected = helper_result.get("medusa_property_detected") is True
    summary = {
        "status": "passed" if all([helper.returncode == 0, clean_valid, seed_replayed, target_tx, target_state, property_detected]) else "failed",
        "case": case_name,
        "source_seed_sha256": manifest["source_seed_sha256"],
        "source_seed_unchanged_after_validation": original_seed_hash_now == manifest["source_seed_sha256"],
        "converted_corpus_sha256_before_clean": original_corpus_hash,
        "converted_corpus_sha256_after_clean": source_hash_after,
        "helper_exit_code": helper.returncode,
        "helper_elapsed_seconds": round(helper_elapsed, 3),
        "helper_log": str(helper_log),
        "helper_log_sha256": sha256_file(helper_log),
        "helper_result": helper_result,
        "medusa_corpus_clean_exit_code": clean.returncode,
        "medusa_corpus_clean_elapsed_seconds": round(clean_elapsed, 3),
        "medusa_corpus_clean_log": str(clean_log_path),
        "medusa_corpus_clean_log_sha256": sha256_file(clean_log_path),
        "corpus_clean_counts": {"valid": valid_count, "invalid": invalid_count, "total": total_count},
        "corpus_clean_only_touched_temporary_copy": True,
        "seed_loaded": clean_valid,
        "seed_replayed_completely": seed_replayed,
        "target_transaction_succeeded": target_tx,
        "target_state_established": target_state,
        "target_property_detected": property_detected,
    }
    summary_path = run_root / "seed-verification.json"
    summary["result_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def _parse_counts(log: str) -> dict[str, Any]:
    call_counts = [int(x.replace(",", "")) for x in re.findall(r"calls:\s*([0-9,]+)", log)]
    sequence_counts = [int(x.replace(",", "")) for x in re.findall(r"sequences:\s*([0-9,]+)", log)]
    pc_counts = [int(x.replace(",", "")) for x in re.findall(r"total PCs hit:\s*([0-9,]+)", log)]
    branch_counts = [int(x.replace(",", "")) for x in re.findall(r"branches:\s*([0-9,]+)", log)]
    return {
        "actual_calls_reported": max(call_counts) if call_counts else None,
        "actual_sequences_reported": max(sequence_counts) if sequence_counts else None,
        "total_pcs_hit_reported": max(pc_counts) if pc_counts else None,
        "branches_reported": max(branch_counts) if branch_counts else None,
    }


def _parse_lcov(path: Path | None, target_function: str | None = None) -> dict[str, Any]:
    if not path or not path.is_file():
        return {"available": False, "path": str(path) if path else None}
    line_hits: dict[tuple[str, int], int] = {}
    function_hits: list[dict[str, Any]] = []
    branch_records: list[bool] = []
    source = ""
    target_name = target_function.split("(", 1)[0] if target_function else None
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if raw_line.startswith("SF:"):
            source = raw_line[3:]
        elif raw_line.startswith("DA:"):
            fields = raw_line[3:].split(",", 2)
            if len(fields) >= 2:
                try:
                    line_hits[(source, int(fields[0]))] = int(fields[1])
                except ValueError:
                    pass
        elif raw_line.startswith("FNDA:"):
            fields = raw_line[5:].split(",", 1)
            if len(fields) == 2:
                try:
                    function_hits.append({"source": source, "name": fields[1], "executions": int(fields[0])})
                except ValueError:
                    pass
        elif raw_line.startswith("BRDA:"):
            fields = raw_line[5:].split(",", 3)
            if len(fields) == 4:
                branch_records.append(fields[3] != "-" and fields[3] != "0")
    target_hits = [item for item in function_hits if target_name and item["name"] == target_name]
    return {
        "available": True,
        "path": str(path),
        "sha256": sha256_file(path),
        "source_files": len({source for source, _ in line_hits}),
        "executable_lines": len(line_hits),
        "covered_lines": sum(hits > 0 for hits in line_hits.values()),
        "line_hits_total": sum(line_hits.values()),
        "branches": len(branch_records) if branch_records else None,
        "covered_branches": sum(branch_records) if branch_records else None,
        "functions": len(function_hits),
        "covered_functions": sum(item["executions"] > 0 for item in function_hits),
        "target_function_name": target_name,
        "target_function_covered": any(item["executions"] > 0 for item in target_hits),
        "target_function_lcov_records": target_hits,
    }


def summarize_case(case_name: str, case_root: Path) -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    incomplete_attempts: list[dict[str, Any]] = []
    target_function = CASES[case_name]["target_function"]
    for arm in ("M0", "M1"):
        for repeat in (1, 2, 3):
            run_root = case_root / "runs" / arm / f"repeat-{repeat}"
            result_path = run_root / "result.json"
            log_path = run_root / "medusa.stdout.log"
            recovery_root = case_root / "runs" / arm / f"repeat-{repeat}-recovery"
            recovery_lcov = recovery_root / "corpus" / "coverage" / "lcov.info"
            recovered = False
            if arm == "M1" and not (run_root / "corpus/coverage/lcov.info").is_file() and recovery_lcov.is_file():
                initial_result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
                initial_log = run_root / "medusa.stdout.log"
                incomplete_attempts.append({
                    "arm": arm,
                    "repeat": repeat,
                    "result": str(result_path),
                    "log": str(initial_log),
                    "log_sha256": sha256_file(initial_log) if initial_log.is_file() else None,
                    "exit_code": initial_result.get("exit_code"),
                    "reason": f"原始 M1 repeat-{repeat} 在 Medusa campaign 中断且未生成 LCOV；使用同配置独立目录重跑。",
                })
                run_root = recovery_root
                result_path = run_root / "result.json"
                log_path = run_root / "medusa.stdout.log"
                recovered = True
            if not log_path.is_file():
                continue
            log = log_path.read_text(encoding="utf-8", errors="replace")
            old = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
            config_path = run_root / "medusa.json"
            config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
            corpus_dir = Path(config["fuzzing"]["corpusDirectory"]) if config.get("fuzzing", {}).get("corpusDirectory") else run_root / "corpus"
            coverage_path = corpus_dir / "coverage" / "lcov.info"
            if not coverage_path.is_file():
                incomplete_attempts.append({
                    "arm": arm,
                    "repeat": repeat,
                    "result": str(result_path),
                    "log": str(log_path),
                    "log_sha256": sha256_file(log_path),
                    "exit_code": old.get("exit_code"),
                    "reason": "campaign 未生成最终 LCOV，未计入有效覆盖重复。",
                })
                continue
            counts = _parse_counts(log)
            timeout = config.get("fuzzing", {}).get("timeout")
            test_limit = config.get("fuzzing", {}).get("testLimit")
            fuzz_elapsed = [int(value) for value in re.findall(r"fuzz: elapsed:\s*([0-9]+)s", log)]
            compile_elapsed = re.search(r"Finished compiling targets in ([0-9.]+)s", log)
            passed = list(dict.fromkeys(re.findall(r"\[PASSED\] Property Test:\s*([^\r\n]+)", log)))
            failed = list(dict.fromkeys(re.findall(r"\[FAILED\] Property Test:\s*([^\r\n]+)", log)))
            target_property = CASES[case_name]["property"]
            target_property = target_property.removesuffix("()")
            target_passed = any(name.split(".")[-1].split("(", 1)[0] == target_property for name in passed)
            target_failed = any(name.split(".")[-1].split("(", 1)[0] == target_property for name in failed)
            timed_out = "Fuzzer stopped, test results follow below" in log and "Test summary:" in log
            stop_reason = "test_limit" if "transaction test limit reached" in log.lower() else "timeout" if timed_out else "external_timeout" if old.get("external_timeout") else "process_exit"
            record = {
                "arm": arm,
                "repeat": repeat,
                "recovery_run": recovered,
                "initial_failed_attempt": str(case_root / "runs" / arm / f"repeat-{repeat}" / "result.json") if recovered else None,
                "config": str(config_path),
                "config_sha256": sha256_file(config_path) if config_path.is_file() else None,
                "stdout_log": str(log_path),
                "stdout_log_sha256": sha256_file(log_path),
                "exit_code": old.get("exit_code"),
                "elapsed_seconds": old.get("elapsed_seconds"),
                "compile_elapsed_seconds_reported": float(compile_elapsed.group(1)) if compile_elapsed else None,
                "fuzz_elapsed_seconds_reported": max(fuzz_elapsed) if fuzz_elapsed else None,
                "campaign_timeout_seconds": timeout,
                "test_limit_safety_cap_transactions": test_limit,
                "stop_reason": stop_reason,
                "counts": counts,
                "property_tests_passed": passed,
                "property_tests_failed": failed,
                "target_property": target_property,
                "target_property_detected": target_passed or target_failed,
                "target_property_passed": target_passed,
                "target_property_failed": target_failed,
                "coverage_lcov": str(coverage_path),
                "coverage": _parse_lcov(coverage_path, target_function),
            }
            record["property_failures_reported"] = failed
            result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            runs.append(record)

    def metrics_for(arm: str) -> dict[str, Any]:
        selected = [record for record in runs if record["arm"] == arm]
        metrics = {
            "actual_calls_reported": [record["counts"]["actual_calls_reported"] for record in selected],
            "medusa_branches_reported": [record["counts"]["branches_reported"] for record in selected],
            "lcov_covered_lines": [record["coverage"].get("covered_lines") for record in selected],
            "lcov_covered_branches": [record["coverage"].get("covered_branches") for record in selected],
            "target_function_covered": [record["coverage"].get("target_function_covered") for record in selected],
            "elapsed_seconds": [record.get("elapsed_seconds") for record in selected],
            "property_failure_count": [len(record["property_tests_failed"]) for record in selected],
            "target_property_failed": [record["target_property_failed"] for record in selected],
        }
        summaries: dict[str, Any] = {"repeats": len(selected), "runs": selected}
        for name, values in metrics.items():
            present = [value for value in values if isinstance(value, (int, float))]
            summaries[name] = {
                "values": values,
                "mean": round(statistics.mean(present), 3) if present else None,
                "median": statistics.median(present) if present else None,
            }
        return summaries

    groups = {arm: metrics_for(arm) for arm in ("M0", "M1")}
    paired_deltas: dict[str, list[dict[str, Any]]] = {}
    count_metric_names = {
        "medusa_branches_reported": "branches_reported",
        "actual_calls_reported": "actual_calls_reported",
    }
    coverage_metric_names = {
        "lcov_covered_lines": "covered_lines",
        "lcov_covered_branches": "covered_branches",
        "target_function_covered": "target_function_covered",
    }
    for metric in ("medusa_branches_reported", "lcov_covered_lines", "lcov_covered_branches", "target_function_covered", "actual_calls_reported"):
        field = count_metric_names.get(metric)
        m0 = {
            record["repeat"]: record["counts"].get(field) if field else record["coverage"].get(coverage_metric_names[metric])
            for record in groups["M0"]["runs"]
        }
        m1 = {
            record["repeat"]: record["counts"].get(field) if field else record["coverage"].get(coverage_metric_names[metric])
            for record in groups["M1"]["runs"]
        }
        paired_deltas[metric] = [
            {"repeat": repeat, "M0": m0.get(repeat), "M1": m1.get(repeat), "delta_M1_minus_M0": (int(m1[repeat]) - int(m0[repeat])) if isinstance(m0.get(repeat), (bool, int, float)) and isinstance(m1.get(repeat), (bool, int, float)) else None}
            for repeat in (1, 2, 3)
        ]
    summary = {
        "case": case_name,
        "comparison": "M1_minus_M0_by_repeat_number",
        "random_seed_fixed": False,
        "seed_only_incremental_coverage": {
            "status": "not_measured",
            "reason": "本阶段没有独立的 replay-only LCOV 快照；最终 LCOV 混合种子回放与后续变异。",
        },
        "incomplete_attempts": incomplete_attempts,
        "groups": groups,
        "paired_deltas": paired_deltas,
    }
    summary_path = case_root / "summary.json"
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def medusa_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(SOLC.parent) + os.pathsep + env.get("PATH", "")
    env["SOLC_VERSION"] = "0.8.20"
    return env


def run_configs(config_paths: list[Path], timeout_padding: int = 90) -> list[dict[str, Any]]:
    if not MEDUSA.is_file():
        raise RuntimeError(f"缺少 Medusa 可执行文件：{MEDUSA}")
    records = []
    for config_path in config_paths:
        run_root = config_path.parent
        log_path = run_root / "medusa.stdout.log"
        started = time.monotonic()
        print(json.dumps({"run_starting": str(config_path)}, ensure_ascii=False), flush=True)
        try:
            proc = subprocess.run(
                [str(MEDUSA), "fuzz", "--config", str(config_path), "-vvv"],
                cwd=ROOT,
                env=medusa_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=max(timeout_padding, int(json.loads(config_path.read_text())["fuzzing"]["timeout"]) + 90),
                check=False,
            )
            output = proc.stdout
            exit_code = proc.returncode
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or "") + "\n[driver: external process timeout]\n"
            if isinstance(output, bytes):
                output = output.decode(errors="replace")
            exit_code = None
            timed_out = True
        elapsed = time.monotonic() - started
        log_path.write_text(output, encoding="utf-8", errors="replace")
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            campaign_timeout = cfg["fuzzing"]["timeout"]
            test_limit = cfg["fuzzing"]["testLimit"]
            corpus_dir = Path(cfg["fuzzing"]["corpusDirectory"])
        except Exception:
            campaign_timeout, test_limit, corpus_dir = None, None, None
        record = {
            "config": str(config_path),
            "config_sha256": sha256_file(config_path),
            "stdout_log": str(log_path),
            "stdout_log_sha256": sha256_file(log_path),
            "exit_code": exit_code,
            "external_timeout": timed_out,
            "elapsed_seconds": round(elapsed, 3),
            "campaign_timeout_seconds": campaign_timeout,
            "test_limit_safety_cap_transactions": test_limit,
            "counts": _parse_counts(output),
            "property_tests_passed": re.findall(r"\[PASSED\] Property Test:\s*([^\r\n]+)", output),
            "property_tests_failed": re.findall(r"\[FAILED\] Property Test:\s*([^\r\n]+)", output),
            "property_failures_reported": re.findall(r"\[FAILED\] Property Test:\s*([^\r\n]+)", output),
            "corpus_directory": str(corpus_dir) if corpus_dir else None,
            "coverage_html": str(corpus_dir / "coverage/coverage_report.html") if corpus_dir else None,
            "coverage_lcov": str(corpus_dir / "coverage/lcov.info") if corpus_dir else None,
            "stop_reason": "test_limit" if "transaction test limit reached" in output.lower() else "timeout_budget_elapsed" if campaign_timeout and elapsed >= campaign_timeout else "process_exit",
        }
        result_path = run_root / "result.json"
        result_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", choices=CASES)
    parser.add_argument("--mode", choices=["prepare", "replay", "campaign", "summary"], default="prepare")
    parser.add_argument("--confirm-replay-evidence", type=Path, help="campaign 必须提供人工核验的 seed-verification.json")
    parser.add_argument("--arm", choices=["M0", "M1"], help="campaign 仅运行指定组")
    parser.add_argument("--repeat", type=int, choices=[1, 2, 3], help="campaign 仅运行指定重复编号")
    parser.add_argument("--recovery", action="store_true", help="将一次技术失败的重复运行放到独立 recovery 目录，保留原始失败证据")
    args = parser.parse_args()
    try:
        if args.recovery and (args.arm != "M1" or args.repeat is None):
            raise RuntimeError("--recovery 仅用于指定 M1 重复编号，例如 --recovery --arm M1 --repeat 2")
        if args.mode == "summary":
            case_root = RESULTS / "实验" / args.case
            summary = summarize_case(args.case, case_root)
            print(json.dumps({"status": "summarized", "case": args.case, "summary_path": summary["summary_path"]}, ensure_ascii=False))
            return 0
        case_root, deployment_path = write_plan(args.case)
        adapter = load_adapter()
        source_corpus = case_root / "converted-seed-corpus"
        conversion_started = time.monotonic()
        conversion = adapter.convert_seed(CASES[args.case]["seed"], CASES[args.case]["abi"], deployment_path, source_corpus)
        conversion_elapsed = time.monotonic() - conversion_started
        conversion_timing_path = case_root / "conversion-timing.json"
        if not conversion_timing_path.is_file():
            conversion_timing_path.write_text(json.dumps({
                "case": args.case,
                "status": conversion.get("status"),
                "elapsed_seconds": round(conversion_elapsed, 6),
                "source_seed_sha256": sha256_file(CASES[args.case]["seed"]),
                "converted_corpus_sha256": sha256_file(source_corpus / "call_sequences/v2_seed.json") if (source_corpus / "call_sequences/v2_seed.json").is_file() else None,
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if conversion["status"] != "supported":
            print(json.dumps({"status": "unsupported", "case": args.case, "manifest": str(source_corpus / "metadata/seed_manifest.json")}, ensure_ascii=False))
            return 2
        if args.mode == "prepare":
            print(json.dumps({"status": "prepared", "case_root": str(case_root), "converted_corpus": str(source_corpus)}, ensure_ascii=False))
            return 0
        if args.mode == "campaign":
            evidence_path = args.confirm_replay_evidence or (case_root / "replay-validation/seed-verification.json")
            if not evidence_path.is_file():
                raise RuntimeError("找不到已完成的 replay-validation/seed-verification.json，先完成真实回放核验")
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            if evidence.get("seed_loaded") is not True or evidence.get("seed_replayed_completely") is not True or evidence.get("target_state_established") is not True:
                raise RuntimeError("回放证据未确认完整加载、完整执行和目标状态建立，停止 fuzz campaign")
            configs = _prepare_campaigns(
                args.case,
                case_root,
                source_corpus,
                recovery=args.recovery,
                selected_arm=args.arm,
                selected_repeat=args.repeat,
            )
        else:
            configs = _prepare_campaigns(args.case, case_root, source_corpus, replay_only=True)
        if args.mode == "replay":
            summary = run_seed_validation(args.case, case_root, configs[0], source_corpus)
            print(json.dumps(summary, ensure_ascii=False))
            return 0 if summary["status"] == "passed" else 2
        if args.mode == "campaign" and args.arm:
            configs = [path for path in configs if path.parent.parent.name == args.arm]
        if args.mode == "campaign" and args.repeat:
            wanted = {f"repeat-{args.repeat}", f"repeat-{args.repeat}-recovery"}
            configs = [path for path in configs if path.parent.name in wanted]
        records = run_configs(configs, 150)
        summary = summarize_case(args.case, case_root)
        print(json.dumps({"status": "completed", "case": args.case, "runs_completed": len(records), "summary_path": summary["summary_path"]}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "case": args.case, "reason": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
