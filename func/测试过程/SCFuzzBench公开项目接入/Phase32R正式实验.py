#!/usr/bin/env python3
"""Phase32-R: 复用 Pigfox RWA 冻结候选与既有状态反馈扩展，运行正式最小对照。"""

from __future__ import annotations

import copy
import argparse
from decimal import Decimal
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入")]

from 属性种子上下文 import PROJECTS, load_project_context, read_json  # noqa: E402
import 种子验证 as seed_verifier  # noqa: E402
import Phase32有限扩展与对照 as phase32  # noqa: E402


PROJECT = "Phase32PigfoxRWADemo"
PROPERTY_ID = "2e998090c7de1e70f195"
SEEDS = [20261125, 20261135, 20261145]
RESULTS = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-R-20261120"
COMPAT = RESULTS / "CompatibilityHarness"
ARTIFACT = COMPAT / "RWA-Properties-compat-artifact.json"
NATIVE_COPY = Path("/tmp/phase32-r-native-copy-20261120")
AGENT_FILE = (ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase32-20261120"
              / "AgentAB/Phase32PigfoxRWADemo/Agent种子流程.json")
ECHIDNA = Path("/usr/local/bin/echidna")


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_native_copy() -> None:
    """重建或验证隔离 solc 工作树；不改写仓库内上游 Solidity 文件。"""
    upstream = ROOT / "sol/真实项目/PigfoxRWATokenDemo"
    source_pairs = [(path, NATIVE_COPY / path.relative_to(upstream))
                    for folder in (upstream / "src",)
                    for path in folder.rglob("*.sol")]
    source_pairs.extend([
        (upstream / "lib/solidity-pipeline/src/PigfoxProperties.sol",
         NATIVE_COPY / "pipeline/PigfoxProperties.sol"),
        (upstream / "test/Actor.sol", NATIVE_COPY / "test/Actor.sol"),
        (COMPAT / "Properties.sol", NATIVE_COPY / "test/Properties.sol"),
    ])
    if not NATIVE_COPY.exists():
        for source, destination in source_pairs:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
    mismatches = [str(destination) for source, destination in source_pairs
                  if not destination.is_file() or sha256(source) != sha256(destination)]
    if mismatches:
        raise RuntimeError("隔离运行树缺少文件或哈希与冻结输入不符：" + ", ".join(mismatches))
    if (NATIVE_COPY / "foundry.toml").exists():
        raise RuntimeError("隔离运行树不应包含 foundry.toml；拒绝意外启用 Foundry 编译路径。")


def configure_compatibility_artifact() -> None:
    if not ARTIFACT.is_file():
        raise FileNotFoundError(f"缺少适配 Harness Anvil artifact: {ARTIFACT}")
    prepare_native_copy()
    config = PROJECTS[PROJECT]
    config["artifact"] = str(ARTIFACT)
    config["fuzzer_target"] = str(NATIVE_COPY)
    config["foundry"] = False
    config["solc_version"] = "0.8.28"
    config["solc"] = "/home/skk/.solc-select/artifacts/solc-0.8.28/solc-0.8.28"
    config["solc_args"] = "--base-path . --optimize --optimize-runs 200 --evm-version cancun"


def make_candidate() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    agent = read_json(AGENT_FILE)
    result = next(item for item in agent["property_results"]
                  if item["property_id"] == PROPERTY_ID)
    concrete = result["candidate_results"][0]["raw_concrete_seed"]
    context = load_project_context(PROJECT, [PROPERTY_ID])
    prop = context["properties"][0]
    one_context = {**context, "properties": [prop]}
    candidate = {**concrete, "project": PROJECT, "property": prop["property"],
                 "context": one_context}
    sequence = copy.deepcopy(concrete["transactions"])
    write_json(RESULTS / "Inputs" / "E1-AgentAB-raw-seed.json", {
        "source": str(AGENT_FILE.relative_to(ROOT)), "candidate_id": concrete["candidate_id"],
        "agent_generated_at_phase": 32, "sequence": sequence,
        "note": "沿用 Phase32 原始 A/B 候选；本轮不调用 Agent，不使用参数修复后的 E2 候选。"})
    return candidate, prop, sequence


def seed_preparation_costs(e3_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    agent = read_json(AGENT_FILE)
    property_row = next(row for row in agent["property_results"]
                        if row["property_id"] == PROPERTY_ID)
    api_rows = [json.loads(line) for line in (AGENT_FILE.parent / "API调用.jsonl")
                .read_text(encoding="utf-8").splitlines() if line.strip()]
    selected = [row for row in api_rows if
                PROPERTY_ID in row.get("tag", "") or
                "supply_sum_balances_mint_holder" in row.get("tag", "")]
    return {
        "E1": {
            "source": "Phase32 原始 A/B 结果；本轮复用，不重新调用 Agent",
            "new_agent_api_calls_this_phase": 0,
            "historical_agent_api_calls": len(selected),
            "historical_prompt_tokens": sum(int(row["usage"]["prompt_tokens"])
                                             for row in selected),
            "historical_completion_tokens": sum(int(row["usage"]["completion_tokens"])
                                                  for row in selected),
            "historical_total_tokens": sum(int(row["usage"]["total_tokens"])
                                            for row in selected),
            "historical_estimated_cost_usd_offpeak": str(sum(
                (Decimal(row["usage"]["estimated_cost_usd"]["offpeak"])
                 for row in selected), Decimal(0))),
            "historical_estimated_cost_usd_peak": str(sum(
                (Decimal(row["usage"]["estimated_cost_usd"]["peak"])
                 for row in selected), Decimal(0))),
            "historical_property_pipeline_elapsed_seconds": property_row.get("elapsed_seconds"),
            "phase32r_anvil_validation_elapsed_seconds": (
                read_json(RESULTS / "Observer/validation-summary.json").get("elapsed_seconds")),
            "seed_file": str(next((RESULTS / "E1/seed-pack/E1/coverage").glob("*.txt"))
                             .relative_to(ROOT)),
        },
        "E3": {
            "source": "既有 Phase31 状态反馈扩展、Phase25 一次参数修复规则；不调用 Agent",
            "new_agent_api_calls": 0,
            "candidate_executions": (e3_summary or {}).get("candidate_executions"),
            "total_anvil_replays": (e3_summary or {}).get("total_anvil_replays"),
            "parameter_repair_replays": (e3_summary or {}).get("parameter_repair_replays"),
            "elapsed_seconds": (e3_summary or {}).get("elapsed_seconds"),
            "seed_file": (e3_summary or {}).get("seed_path"),
        },
    }


def validate_observer(candidate: dict[str, Any], prop: dict[str, Any],
                      sequence: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.monotonic()
    with seed_verifier.AnvilSession(project=PROJECT) as session:
        replay = seed_verifier.replay_seed(PROJECT, candidate, sequence,
                                           session=session, runtime_constraints=True)
    destination = RESULTS / "Observer" / "E1逐笔属性状态对照.json"
    write_json(destination, replay)
    property_state = replay.get("target_property_state", {})
    initial = replay.get("initial_predicate_getters", [])
    transaction = replay.get("transactions", [{}])[0]
    final = transaction.get("predicate_getter_values", [])
    observed_names = sorted({item.get("signature") for item in initial + final
                             if item.get("status") == "observed"})
    changed = transaction.get("changed_predicate_getters", [])
    result = {"replay_status": replay.get("replay_status"),
              "initial_target_property": replay.get("initial_property_values", {}).get(
                  "echidna_supply_equals_sum_of_balances()"),
              "final_target_property": transaction.get("target_property"),
              "observed_predicate_getter_signatures": observed_names,
              "property_related_getter_changes": changed,
              "property_related_state_status": property_state.get("status"),
              "elapsed_seconds": round(time.monotonic() - started, 6),
              "full_replay_path": str(destination.relative_to(ROOT))}
    write_json(RESULTS / "Observer" / "validation-summary.json", result)
    if replay.get("replay_status") != "executable" or not changed:
        raise RuntimeError("适配 Harness 上 E1 回放或属性相关 getter 变化未被可靠观察；停止 Echidna 种子对照。")
    needed = {"totalSupply()", "balanceOf(address)"}
    if not needed.issubset(set(observed_names)):
        raise RuntimeError(f"供给求和属性操作数 getter 未完整观察：{observed_names}")
    return replay


def generate_e3(candidate: dict[str, Any], prop: dict[str, Any],
                sequence: list[dict[str, Any]], replay: dict[str, Any]
                ) -> tuple[list[dict[str, Any]] | None, Path | None, dict[str, Any]]:
    artifact = read_json(ARTIFACT)
    abi_by_signature = {
        entry["name"] + "(" + ",".join(arg["type"] for arg in entry.get("inputs", [])) + ")": entry
        for entry in artifact["abi"] if entry.get("type") == "function"}
    senders = list(PROJECTS[PROJECT].get("senders") or [])
    # Phase32 的既有驱动函数实现同一 Phase31 扩展和一次性参数修复规则；
    # 将模式收窄为 E3，明确不执行 R/S 探索。
    phase32.MODE_GROUPS = {"state_feedback": "E3"}
    extension_root = RESULTS / "E3" / "Extension"
    started = time.monotonic()
    expansion = phase32._expand(PROJECT, candidate, prop, abi_by_signature,
                                sequence, senders, extension_root)
    mode = expansion["modes"]["state_feedback"]
    choice = mode.get("target_candidate") or next(
        (row for row in mode.get("eligible_candidates", [])
         if row.get("origin") != "frozen_base_replay"), None)
    summary = {"status": mode.get("status"),
               "candidate_executions": mode.get("candidate_executions"),
               "total_anvil_replays": mode.get("total_anvil_replays"),
               "parameter_repair_replays": mode.get("parameter_repair_replays"),
               "elapsed_seconds": round(time.monotonic() - started, 6),
               "candidate_origin": choice.get("origin") if choice else None,
               "candidate_sequence": choice.get("sequence") if choice else None,
               "target_property_violation": bool(
                   choice and choice.get("replay", {}).get("target_property_violation")),
               "property_related_state_changed": bool(
                   choice and choice.get("feedback", {}).get("property_related_state_changed")),
               "extension_log": str((extension_root / "E3-扩展回放.json").relative_to(ROOT))}
    write_json(RESULTS / "E3" / "extension-summary.json", summary)
    if choice is None:
        return None, None, summary
    e3_sequence = copy.deepcopy(choice["sequence"])
    seed_path = phase32._prepare_seed(PROJECT, candidate, e3_sequence,
                                      candidate["context"], choice["replay"],
                                      RESULTS / "E3", "E3")
    summary["seed_path"] = str(seed_path.relative_to(ROOT)) if seed_path else None
    write_json(RESULTS / "E3" / "extension-summary.json", summary)
    return e3_sequence, seed_path, summary


def lcov_lines(root: Path) -> set[tuple[str, int]]:
    lines: set[tuple[str, int]] = set()
    for path in root.rglob("*.lcov"):
        source = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("SF:"):
                source = line[3:]
            elif line.startswith("DA:"):
                columns = line[3:].split(",")
                if len(columns) >= 2 and int(columns[1]) > 0:
                    lines.add((source, int(columns[0])))
    return lines


def run_case(group: str, seed: int, stage: str, test_limit: int,
             external_seed: Path | None, yaml_template: str) -> dict[str, Any]:
    case_root = RESULTS / "Echidna" / group / f"seed-{seed}" / stage
    corpus = case_root / "corpus"
    corpus.mkdir(parents=True, exist_ok=True)
    if external_seed is not None:
        destination = corpus / "coverage" / external_seed.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(external_seed, destination)
    yaml_path = case_root / "echidna.yaml"
    yaml = re.sub(r"(?m)^testLimit:.*$", f"testLimit: {test_limit}", yaml_template)
    yaml = re.sub(r"(?m)^seed:.*$", f"seed: {seed}", yaml)
    yaml = re.sub(r"(?m)^corpusDir:.*$", f'corpusDir: "{corpus}"', yaml)
    yaml_path.write_text(yaml, encoding="utf-8")
    config = PROJECTS[PROJECT]
    runtime = seed_verifier._project_runtime(PROJECT)
    command = [str(ECHIDNA), "test/Properties.sol", "--contract", "Properties",
               "--config", str(yaml_path), "--test-limit", str(test_limit),
               "--seq-len", "8", "--shrink-limit", "1", "--seed", str(seed),
               "--workers", "1", "--format", "text", "--deployer", runtime["deployer"],
               "--contract-addr", runtime["contract_address"]]
    command.extend(sum((["--sender", sender] for sender in config["senders"]), []))
    command.append("--disable-slither")
    env = {**os.environ,
           "PATH": str(ROOT / ".tools/olympia-venv/bin") + os.pathsep +
                   str(ROOT / ".tools/foundry/bin") + os.pathsep +
                   "/home/skk/miniconda3/envs/contract-fuzz/bin:" + os.environ.get("PATH", ""),
           "SOLC_VERSION": "0.8.28"}
    started = time.monotonic()
    result = subprocess.run(command, cwd=NATIVE_COPY, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180, check=False)
    elapsed = round(time.monotonic() - started, 6)
    output = result.stdout or ""
    (case_root / "echidna.log").write_text(output, encoding="utf-8")
    evidence = seed_verifier.echidna_corpus_evidence(output)
    metric = {"group": group, "seed": seed, "stage": stage,
              "test_limit": test_limit, "exit_code": result.returncode,
              "status": "completed" if result.returncode == 0 else "failed",
              "elapsed_seconds": elapsed,
              "external_seed_used": external_seed is not None,
              "external_seed_path": str(external_seed.relative_to(ROOT)) if external_seed else None,
              "loaded_seed_count": evidence["loaded_seed_count"],
              "replayed_sequence_count": evidence["replayed_sequence_count"],
              "property_failure_reported": evidence["property_failure_reported"],
              "tests_status_snapshots": evidence["tests_status_snapshots"],
              "fuzzing_progress_count": evidence["fuzzing_progress_count"],
              "fuzzing_progress_limit": evidence["fuzzing_progress_limit"],
              "test_limit_reached": "Test limit reached. Stopping." in output,
              "unique_instructions": evidence["unique_instructions"],
              "corpus_after_count": len(list((corpus / "coverage").glob("*.txt")))
                  if (corpus / "coverage").is_dir() else 0,
              "lcov_files": [str(path.relative_to(ROOT)) for path in case_root.rglob("*.lcov")],
              "lcov_executed_line_count": len(lcov_lines(case_root)),
              "command": command,
              "cwd": str(NATIVE_COPY),
              "environment": {"echidna_version": subprocess.run(
                  [str(ECHIDNA), "--version"], text=True, capture_output=True).stdout.strip(),
                  "crytic_compile_version": subprocess.run(
                      ["crytic-compile", "--version"], env=env, text=True,
                      capture_output=True).stdout.strip(),
                  "solc_version": subprocess.run(
                      [config["solc"], "--version"], text=True,
                      capture_output=True).stdout.strip().splitlines()[-1]}}
    write_json(case_root / "run-meta.json", metric)
    return metric


def echidna_matrix(seeds_by_group: dict[str, Path | None]) -> dict[str, Any]:
    template_path = RESULTS / "E0/seed-20261125-attempt3/echidna.yaml"
    yaml_template = template_path.read_text(encoding="utf-8")
    runs = []
    for group in ("E0", "E1", "E3"):
        seed_path = seeds_by_group.get(group)
        if group != "E0" and seed_path is None:
            runs.append({"group": group, "status": "not_run_no_valid_group_seed",
                         "reason": "该组没有由自身流程产生的可执行种子；未用其他组种子替代。"})
            continue
        for seed in SEEDS:
            for stage, limit in (("seed-only", 0), ("fuzz-500", 500)):
                run = run_case(group, seed, stage, limit,
                               seed_path if group != "E0" else None, yaml_template)
                runs.append(run)
                if run["exit_code"] != 0:
                    write_json(RESULTS / "Echidna" / "matrix.json", {
                        "status": "stopped_after_failed_run", "runs": runs})
                    raise RuntimeError(f"{group}/{seed}/{stage} Echidna 执行失败，停止本轮。")
    coverages = {}
    for group in ("E0", "E1", "E3"):
        for seed in SEEDS:
            seed_dir = RESULTS / "Echidna" / group / f"seed-{seed}"
            seed_only = lcov_lines(seed_dir / "seed-only")
            final = lcov_lines(seed_dir / "fuzz-500")
            fuzz_run = next((row for row in runs if row.get("group") == group and
                             row.get("seed") == seed and row.get("stage") == "fuzz-500"), None)
            if fuzz_run is None:
                continue
            coverages[f"{group}/{seed}"] = {
                "seed_only_lines": len(seed_only),
                "fuzz_added_lines": len(final - seed_only),
                "final_lines": len(final),
                "seed_only_lcov_present": any((seed_dir / "seed-only").rglob("*.lcov")),
                "final_lcov_present": any((seed_dir / "fuzz-500").rglob("*.lcov")),
                "fuzz_500_budget_reached": fuzz_run["test_limit_reached"] and
                    fuzz_run["fuzzing_progress_count"] >= 500}
    result = {"status": "completed", "seeds": SEEDS, "runs": runs,
              "coverage_by_group_seed": coverages}
    write_json(RESULTS / "Echidna" / "matrix.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("observer", "cost-summary", "full"), default="full")
    args = parser.parse_args()
    configure_compatibility_artifact()
    candidate, prop, sequence = make_candidate()
    if args.stage == "cost-summary":
        costs = seed_preparation_costs(
            read_json(RESULTS / "E3/extension-summary.json"))
        write_json(RESULTS / "seed-preparation-costs.json", costs)
        summary_path = RESULTS / "experiment-summary.json"
        if summary_path.is_file():
            summary = read_json(summary_path)
            summary["seed_preparation_costs"] = costs
            write_json(summary_path, summary)
        print(json.dumps(costs, ensure_ascii=False, indent=2))
        return
    replay = validate_observer(candidate, prop, sequence)
    existing_e1 = sorted((RESULTS / "E1/seed-pack/E1/coverage").glob("*.txt"))
    e1_seed = (existing_e1[0] if len(existing_e1) == 1 else
               phase32._prepare_seed(PROJECT, candidate, sequence,
                                     candidate["context"], replay,
                                     RESULTS / "E1", "E1"))
    if args.stage == "observer":
        print(json.dumps({"observer_status": replay.get("target_property_state", {}).get("status"),
                          "e1_seed_path": str(e1_seed.relative_to(ROOT)) if e1_seed else None,
                          "property_related_getter_changes": replay["transactions"][0].get(
                              "changed_predicate_getters", [])}, ensure_ascii=False, indent=2))
        return
    e3_sequence, e3_seed, e3_summary = generate_e3(candidate, prop, sequence, replay)
    result = echidna_matrix({"E0": None, "E1": e1_seed, "E3": e3_seed})
    final = {"status": "completed", "property_id": PROPERTY_ID,
             "upstream_commit": "2a6c4b0cfad46d1f84cbd6aaf3a2e0881660b03d",
             "compatibility_harness_sha256": sha256(COMPAT / "Properties.sol"),
             "adapter_artifact_sha256": sha256(ARTIFACT),
             "observer_status": replay.get("target_property_state", {}).get("status"),
             "e1_seed_path": str(e1_seed.relative_to(ROOT)) if e1_seed else None,
             "e3_seed_path": str(e3_seed.relative_to(ROOT)) if e3_seed else None,
             "e3": e3_summary, "echidna_matrix": str(
                 (RESULTS / "Echidna" / "matrix.json").relative_to(ROOT))}
    costs = seed_preparation_costs(e3_summary)
    write_json(RESULTS / "seed-preparation-costs.json", costs)
    final["seed_preparation_costs"] = costs
    write_json(RESULTS / "experiment-summary.json", final)
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
