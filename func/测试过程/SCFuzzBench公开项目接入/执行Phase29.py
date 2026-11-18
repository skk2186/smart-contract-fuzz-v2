#!/usr/bin/env python3
"""运行固定配置的新公开项目接入与小规模 Echidna 配对实验。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "deepseek/实验过程"), str(ROOT / "func/测试过程")]

from 属性种子上下文 import PROJECTS, load_project_context
from 编译测试环境 import compile_project
from 种子验证 import (AnvilSession, inspect_initial_state, new_seed_id,
                    echidna_corpus_evidence, run_echidna, write_corpus)
from 运行Agent种子流程 import run_project


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    excluded = {".git", "out", "cache", "crytic-export", "broadcast", "node_modules"}
    for path in sorted(item for item in root.rglob("*")
                       if item.is_file() and not any(part in excluded for part in item.parts)):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        content_hash = bytes.fromhex(_sha256(path))
        digest.update(content_hash)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _analysis_command(project: str, profile: dict[str, Any], *, python: str) -> list[str]:
    raw = profile["_raw"]
    compiler = raw["compiler"]
    source_root = ROOT / raw["source"]["root"]
    command = [python, str(ROOT / "func/功能/属性分析适配器.py"),
               str(ROOT / profile["target"]), "--contract", profile["contract"],
               "--project-root", str(source_root), "--output",
               str(ROOT / profile["report"]), "--property-prefix",
               str(raw.get("property", {}).get("engine_prefix", "echidna_"))]
    if profile.get("solc"):
        command.extend(["--solc", profile["solc"]])
    if profile.get("remaps"):
        command.extend(["--solc-remaps", profile["remaps"]])
    for selector in raw.get("analysis", {}).get("property_functions", []):
        command.extend(["--property-function", selector])
    options = compiler.get("compile_options", {})
    for key, value in options.items():
        command.extend(["--compile-option", f"{key}={str(value).lower() if isinstance(value, bool) else value}"])
    return command


def _run_native_groups(project: str, profile: dict[str, Any], context: dict[str, Any],
                       property_context: dict[str, Any], experiment_root: Path,
                       seed_corpora: dict[str, Path], *, repeats: int,
                       timeout: int, test_limit: int, python_seed: int,
                       no_seed_status: str = "not_run_no_valid_replay") -> dict[str, Any]:
    rows = []
    property_name = property_context["property_abi"].split("(", 1)[0]
    mode = "property" if property_context["property_kind"] == "boolean_property" else "assertion"
    property_config = profile.get("property", {})
    prefix = property_config.get("engine_prefix", "echidna_")
    senders = profile.get("senders") or None
    for arm in ("G0", "G1", "G2"):
        corpus_seed = seed_corpora.get(arm)
        if arm != "G0" and corpus_seed is None:
            rows.append({"arm": arm, "status": no_seed_status})
            continue
        for repeat in range(1, repeats + 1):
            seed = python_seed + repeat - 1
            run_root = experiment_root / "fuzz" / arm / f"repeat-{repeat}"
            corpus = run_root / "corpus"
            (corpus / "coverage").mkdir(parents=True, exist_ok=True)
            if corpus_seed is not None:
                (corpus / "coverage" / corpus_seed.name).write_bytes(corpus_seed.read_bytes())
            started = time.monotonic()
            try:
                result = run_echidna(
                    project, corpus, property_name=property_name,
                    test_limit=test_limit, timeout=timeout, seed=seed,
                    test_mode=mode, property_prefix=prefix, seq_len=8,
                    stop_on_fail=False, disable_slither=True, sender_pool=senders,
                    working_directory=ROOT)
                result.update({"arm": arm, "repeat": repeat,
                               "input_seed": corpus_seed.name if corpus_seed else None})
            except Exception as exc:
                result = {"arm": arm, "repeat": repeat, "status": "engine_error",
                          "error": f"{type(exc).__name__}: {str(exc)[:1600]}",
                          "input_seed": corpus_seed.name if corpus_seed else None}
            result["wall_seconds"] = round(time.monotonic() - started, 3)
            rows.append(result)
    return {"engine": "Echidna", "test_mode": mode, "target_property": property_name,
            "property_prefix": prefix, "test_limit": test_limit, "timeout_seconds": timeout,
            "seq_len": 8, "workers": 1, "runs": rows}


def _target_lcov_evidence(lcov_path: Path, profile: dict[str, Any],
                          property_context: dict[str, Any]) -> dict[str, Any]:
    raw_source = property_context.get("property_source", "").split("#", 1)[0]
    source_path = ROOT / raw_source
    if not source_path.is_file():
        source_path = ROOT / profile["source_root"] / raw_source
    if not source_path.is_file():
        return {"status": "source_unavailable", "source": raw_source}
    function_name = property_context["property_abi"].split("(", 1)[0]
    source_lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
    pattern = re.compile(r"\bfunction\s+" + re.escape(function_name) + r"\s*\(")
    start = next((i for i, line in enumerate(source_lines) if pattern.search(line)), None)
    if start is None:
        return {"status": "function_source_not_found", "source": str(source_path)}
    depth = 0
    opened = False
    end = start
    for index in range(start, len(source_lines)):
        depth += source_lines[index].count("{") - source_lines[index].count("}")
        opened |= "{" in source_lines[index]
        if opened and depth <= 0:
            end = index + 1
            break
    relative_fragment = source_path.relative_to(ROOT / profile["source_root"]).as_posix()
    active_file = None
    hits: dict[int, int] = {}
    for line in lcov_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("SF:"):
            active_file = line[3:]
        elif line == "end_of_record":
            active_file = None
        elif active_file and active_file.endswith(relative_fragment) and line.startswith("DA:"):
            line_number, count = line[3:].split(",", 1)
            hits[int(line_number)] = int(count)
    selected = {line: count for line, count in hits.items()
                if start + 1 <= line <= end}
    assertion_lines = []
    for site in property_context.get("assertion_sites", []):
        match = re.search(r"#(\d+)", site.get("source", ""))
        if match:
            line_number = int(match.group(1))
            assertion_lines.append({"line": line_number,
                                    "hits": hits.get(line_number, 0)})
    return {"status": "measured", "source": str(source_path.relative_to(ROOT)),
            "function_line_range": [start + 1, end],
            "covered_executable_lines": sum(count > 0 for count in selected.values()),
            "executable_lines": len(selected),
            "line_hit_counts": {str(line): count for line, count in selected.items()},
            "assertion_sites": assertion_lines}


def _collect_existing_native_groups(project: str, profile: dict[str, Any],
                                    property_context: dict[str, Any],
                                    experiment_root: Path, *, repeats: int,
                                    timeout: int, test_limit: int,
                                    python_seed: int,
                                    no_seed_status: str) -> dict[str, Any]:
    target_name = property_context["property_abi"].split("(", 1)[0]
    runs = []
    for repeat in range(1, repeats + 1):
        run_root = experiment_root / "fuzz" / "G0" / f"repeat-{repeat}"
        corpus_root = run_root / "corpus"
        log_path = corpus_root / "echidna.log"
        if not log_path.is_file():
            runs.append({"arm": "G0", "repeat": repeat, "status": "missing_log"})
            continue
        output = log_path.read_text(encoding="utf-8", errors="replace")
        evidence = echidna_corpus_evidence(output)
        target_results = [line.strip() for line in output.splitlines()
                          if target_name in line and ":" in line and
                          any(token in line.lower() for token in
                              ("passing", "failed", "falsified", "💥"))]
        falsified = [match.group(1).strip() for match in re.finditer(
            r"\bTest\s+(.+?)\s+falsified!?", output, re.IGNORECASE)]
        total_calls = [int(value) for value in re.findall(r"Total calls:\s*(\d+)", output)]
        coverage_matches = [int(value.replace(",", "")) for value in re.findall(
            r"\bcov:\s*([\d,]+)", output, re.IGNORECASE)]
        lcov_paths = sorted(corpus_root.glob("covered.*.lcov"), key=lambda path: path.stat().st_mtime)
        seed_marker = corpus_root / ".echidna-run-started"
        marker = json.loads(seed_marker.read_text(encoding="utf-8")) if seed_marker.is_file() else {}
        run = {"arm": "G0", "repeat": repeat,
               "status": "completed",
               "seed": marker.get("seed", python_seed + repeat - 1),
               "test_limit": test_limit, "timeout_seconds": timeout,
               "test_mode": "assertion", "seq_len": 8, "workers": 1,
               "initial_corpus_file_count": 0,
               "total_calls": max(total_calls, default=None),
               "status_cov_snapshot": max(coverage_matches, default=None),
               "coverage_source": "Echidna cov status snapshot",
               "target_property_results": target_results,
               "target_property_falsified": any("failed" in line.lower() or
                                                "falsified" in line.lower()
                                                for line in target_results),
               "all_falsified_tests": sorted(set(falsified)),
               "canary_output_present": any("canary" in line.lower()
                                             for line in output.splitlines()),
               "elapsed_seconds": (round(log_path.stat().st_mtime - marker.get("started_at", log_path.stat().st_mtime), 3)
                                   if marker else None),
               "log": str(log_path.relative_to(ROOT)),
               "coverage_file": str(lcov_paths[-1].relative_to(ROOT)) if lcov_paths else None,
               **evidence}
        if lcov_paths:
            run["target_operation_coverage"] = _target_lcov_evidence(
                lcov_paths[-1], profile, property_context)
            run["coverage_file_sha256"] = _sha256(lcov_paths[-1])
        runs.append(run)
    for arm in ("G1", "G2"):
        runs.append({"arm": arm, "status": no_seed_status})
    return {"engine": "Echidna", "test_mode": "assertion",
            "target_property": target_name, "property_prefix":
            profile.get("property", {}).get("engine_prefix", "echidna_"),
            "test_limit": test_limit, "timeout_seconds": timeout,
            "seq_len": 8, "workers": 1, "runs": runs}


def run_one(project: str, *, repeats: int = 3, timeout: int = 60,
            test_limit: int = 5000, python_seed: int = 20261129,
            token_budget: int = 400000, wall_budget: int = 600,
            run_agents: bool = True, collect_existing: bool = False) -> dict[str, Any]:
    config = PROJECTS[project]
    raw = config["_raw"]
    os.environ["SOLC_VERSION"] = config["solc_version"]
    output_root = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果" / project
    output_root.mkdir(parents=True, exist_ok=True)
    stages: list[dict[str, Any]] = []

    started = time.monotonic()
    artifact = compile_project(project)
    artifact_path = ROOT / config["artifact"]
    _write_json(artifact_path, artifact)
    stages.append({"stage": 1, "name": "原生 Harness 编译", "status": "passed",
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "artifact": str(artifact_path.relative_to(ROOT))})

    analyzer_python = os.environ.get("PHASE29_PYTHON", sys.executable)
    command = _analysis_command(project, config, python=analyzer_python)
    analyzer_env = os.environ.copy()
    analyzer_env["SOLC_VERSION"] = config["solc_version"]
    analyzer_log = output_root / "04-slither.log"
    started = time.monotonic()
    analysis_run = subprocess.run(command, cwd=ROOT, env=analyzer_env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    analyzer_log.write_text(analysis_run.stdout, encoding="utf-8")
    report_path = ROOT / config["report"]
    analysis = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
    stages.append({"stage": 2, "name": "原生测试属性识别", "status":
                   "passed" if analysis.get("status") == "complete" else "failed",
                   "exit_code": analysis_run.returncode,
                   "elapsed_seconds": round(time.monotonic() - started, 3),
                   "report": str(report_path.relative_to(ROOT)) if report_path.is_file() else None,
                   "log": str(analyzer_log.relative_to(ROOT)),
                   "property_count": len(analysis.get("properties", []))})
    if analysis.get("status") != "complete":
        record = {"schema_version": 1, "project": project, "stages": stages,
                  "overall_status": "blocked_before_v2_analysis",
                  "analysis": analysis, "elapsed_seconds": round(time.monotonic() - started, 3)}
        _write_json(output_root / "phase29-result.json", record)
        return record

    target_id = raw.get("property", {}).get("target_property_id")
    if not target_id:
        raise ValueError(f"{project}: 缺少预先冻结的目标属性 ID")
    context = load_project_context(project, [target_id])
    property_context = context["properties"][0]
    expected_name = raw.get("property", {}).get("target_property")
    if expected_name and property_context.get("property") != expected_name:
        raise ValueError(f"冻结目标属性与分析报告不一致：{expected_name} != {property_context.get('property')}")
    if property_context.get("property_kind") not in {"boolean_property", "assertion_test"}:
        raise ValueError("目标函数未被识别为原生 Boolean 属性或 assert 测试")
    v2_dependency_complete = property_context.get("dependency_status") == "complete"
    stages.append({"stage": 3, "name": "V2 属性与状态依赖分析",
                   "status": "passed" if v2_dependency_complete else "partial",
                   "property_id": target_id,
                   "property": property_context.get("property"),
                   "property_kind": property_context.get("property_kind"),
                   "assertion_sites": property_context.get("assertion_sites", []),
                   "candidate_action_count": len(property_context.get("candidate_actions", [])),
                   "seed_compatible_action_count": sum(
                       bool(item.get("seed_compatible"))
                       for item in property_context.get("candidate_actions", [])),
                   "dependency_status": property_context.get("dependency_status")})

    deploy_session = None
    deployment_probe: dict[str, Any] = {}
    try:
        deploy_session = AnvilSession(project=project).__enter__()
        deployment_probe = inspect_initial_state(project, property_context,
                                                 session=deploy_session)
    except Exception as exc:
        deployment_probe = {"status": "failed",
                            "error": f"{type(exc).__name__}: {str(exc)[:8000]}",
                            "traceback": traceback.format_exc()}
    finally:
        if deploy_session is not None:
            deploy_session.__exit__(None, None, None)
    _write_json(output_root / "05-anvil-deploy-probe.json", deployment_probe)
    stages.append({"stage": 1.5, "name": "Anvil Harness 部署与初始状态", "status":
                   "passed" if deployment_probe.get("status") == "observed" else "blocked",
                   "evidence": str((output_root / "05-anvil-deploy-probe.json").relative_to(ROOT)),
                   "error": deployment_probe.get("error")})

    agent_root = output_root / "agent"
    started = time.monotonic()
    agent_error = None
    if run_agents and v2_dependency_complete:
        try:
            agent = run_project(
                project, [target_id], max_candidates=1, max_steps=8, repairs=0,
                planning_repairs=0, execution_replans=0, schema_repairs=0,
                echidna_limit=test_limit, echidna_timeout=timeout,
                echidna_seed=python_seed, token_budget=token_budget,
                wall_budget=wall_budget, run_fuzzer=False, runtime_constraints=True,
                run_root=agent_root, api_log_path=agent_root / "API调用.jsonl")
            _write_json(agent_root / "agent-output.json", agent)
        except Exception as exc:
            agent = None
            agent_error = f"{type(exc).__name__}: {str(exc)[:1600]}"
    elif not run_agents:
        agent = None
        agent_error = ("auto_review_external_data_egress_blocked: 本机执行器拒绝将项目源码、" +
                       "属性上下文和候选生成提示发送到 DeepSeek API；本轮未发出 API 请求。")
    else:
        agent = None
        agent_error = "V2 静态依赖状态为 incomplete，未达到运行 Agent A/B 的门槛。"
    stages.append({"stage": 4, "name": "Agent A/B 原始候选生成", "status":
                   "passed" if agent else
                   "blocked_v2_analysis_gate" if not v2_dependency_complete else
                   "blocked_external_api_approval_required" if not run_agents else "failed",
                   "api_request_sent": run_agents and v2_dependency_complete,
                   "elapsed_seconds":
                   round(time.monotonic() - started, 3), "error": agent_error})
    candidate_rows = []
    if agent:
        property_row = next((item for item in agent.get("property_results", [])
                             if item.get("property_id") == target_id), {})
        candidate_rows = property_row.get("candidate_results", [])
    candidate = candidate_rows[0] if candidate_rows else None
    raw_seed = candidate.get("raw_concrete_seed") if candidate else None
    raw_replay = candidate.get("raw_replay") if candidate else None
    replay_attempts = candidate.get("replay_attempts", []) if candidate else []
    final_replay = replay_attempts[-1] if replay_attempts else None
    repair_attempt = next((item for item in replay_attempts[1:]
                           if item.get("runtime_constraint_repairs")), None)
    stages.append({"stage": 5, "name": "Anvil 候选真实回放", "status":
                   "passed" if raw_replay and raw_replay.get("replay_status") == "executable"
                   else "failed" if candidate else
                   "not_reached_v2_analysis_gate" if not v2_dependency_complete else
                   "not_reached_external_api_blocked" if not run_agents else "not_reached",
                   "raw_replay_status": raw_replay.get("replay_status") if raw_replay else None,
                   "raw_replay_error": (raw_replay.get("error") if raw_replay else
                                         candidate.get("error") if candidate else None),
                   "target_state": raw_replay.get("target_property_state") if raw_replay else None,
                   "failure_class": candidate.get("failure_class") if candidate else None})
    stages.append({"stage": 6, "name": "现有跨交易参数修复", "status":
                   "attempted" if candidate and candidate.get("runtime_constraint_repairs") else
                   "no_repairable_constraint" if candidate and candidate.get("replay_attempts") else
                   "not_reached_due_to_deployment" if candidate and not candidate.get("replay_attempts") else
                   "blocked_v2_analysis_gate" if not v2_dependency_complete else
                   "blocked_external_api_approval_required" if not run_agents else "not_reached",
                   "repair_events": candidate.get("runtime_constraint_repairs", []) if candidate else []})

    context_for_corpus = load_project_context(project, [target_id])
    candidate_context = {"property_id": target_id,
                         "candidate_id": candidate.get("candidate_id") if candidate else "phase29-fixed-raw",
                         "property": property_context.get("property"),
                         "steps": candidate.get("plan", []) if candidate else [],
                         "context": context_for_corpus}
    corpora: dict[str, Path] = {}
    for arm, replay, seed in (
        ("G1", raw_replay, raw_seed),
        ("G2", final_replay, candidate.get("concrete_seed") if candidate else None),
    ):
        if not (replay and replay.get("replay_status") == "executable" and seed):
            continue
        corpus_root = output_root / "seed-corpora" / arm
        corpus_root.mkdir(parents=True, exist_ok=True)
        seed_id = new_seed_id()
        path = write_corpus(project, candidate_context, replay["resolved_transactions"],
                            context_for_corpus, corpus_root,
                            replay=replay, seed_id=seed_id)
        corpora[arm] = path
    stages.append({"stage": 7, "name": "Echidna 原生语料回放资格", "status":
                   "passed" if corpora else
                   "blocked_v2_analysis_gate" if not v2_dependency_complete else
                   "blocked_external_api_approval_required" if not run_agents else "failed_no_valid_seed",
                   "G1_seed": str(corpora["G1"].relative_to(ROOT)) if "G1" in corpora else None,
                   "G2_seed": str(corpora["G2"].relative_to(ROOT)) if "G2" in corpora else None})

    corpus_seed_paths = {arm: path for arm, path in corpora.items()}
    no_seed_status = ("blocked_v2_analysis_gate" if not v2_dependency_complete else
                      "blocked_external_api_approval_required" if not run_agents else
                      "not_run_no_valid_replay")
    if collect_existing:
        fuzz = _collect_existing_native_groups(
            project, config, property_context, output_root, repeats=repeats,
            timeout=timeout, test_limit=test_limit, python_seed=python_seed,
            no_seed_status=no_seed_status)
    else:
        fuzz = _run_native_groups(project, config, context, property_context, output_root,
                                  corpus_seed_paths, repeats=repeats, timeout=timeout,
                                  test_limit=test_limit, python_seed=python_seed,
                                  no_seed_status=no_seed_status)
    _write_json(output_root / "echidna-comparison.json", fuzz)
    stages.append({"stage": 8, "name": "G0/G1/G2 轻量对照", "status":
                   "completed_with_missing_seed_arms" if not corpora else "completed",
                   "group_counts": {arm: sum(row.get("arm") == arm and "repeat" in row
                                              for row in fuzz["runs"])
                                    for arm in ("G0", "G1", "G2")}})

    property_source_path = ROOT / property_context["property_source"].split("#", 1)[0]
    if not property_source_path.is_file():
        property_source_path = ROOT / raw["source"]["root"] / property_context[
            "property_source"].split("#", 1)[0]
    freeze = {
        "upstream_repository": raw["source"]["repository"],
        "upstream_commit": raw["source"]["commit"],
        "benchmark_commit": json.loads((ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目版本冻结.json").read_text(encoding="utf-8"))["official_benchmark"]["commit"],
        "source_tree_sha256": _source_tree_hash(ROOT / raw["source"]["root"]),
        "harness_sha256": _sha256(ROOT / raw["source"]["root"] / raw["harness"]["source"]),
        "property_source_sha256": _sha256(property_source_path),
        "profile_sha256": _sha256(config_path(project)),
        "artifact_sha256": _sha256(ROOT / config["artifact"]),
        "analysis_sha256": _sha256(ROOT / config["report"]),
        "target_property_id": target_id,
        "target_property": property_context.get("property"),
    }
    _write_json(output_root / "01-input-freeze.json", freeze)
    record = {"schema_version": 1, "project": project, "target_property_id": target_id,
              "target_property": property_context.get("property"),
              "stages": stages, "agent": agent, "agent_error": agent_error,
              "echidna_comparison": fuzz, "input_freeze": freeze,
              "overall_status": ("native_baseline_only_v2_analysis_incomplete"
                                 if not v2_dependency_complete else
                                 "native_baseline_only_external_api_blocked" if not run_agents else
                                 "full_seeded_experiment" if corpora else "native_only_seed_path_blocked"),
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    _write_json(output_root / "phase29-result.json", record)
    return record


def config_path(project: str) -> Path:
    return ROOT / PROJECTS[project]["profile_path"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=sorted(PROJECTS))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--test-limit", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261129)
    parser.add_argument("--token-budget", type=int, default=400000)
    parser.add_argument("--wall-budget", type=int, default=600)
    parser.add_argument("--skip-agent-api", action="store_true",
                        help="不调用外部 Agent API，仅执行本地编译、分析、部署探针及 G0")
    parser.add_argument("--collect-existing", action="store_true",
                        help="复用已存在的 G0 原始日志，不重新运行 Echidna")
    args = parser.parse_args()
    result = run_one(args.project, repeats=args.repeats, timeout=args.timeout,
                     test_limit=args.test_limit, python_seed=args.seed,
                     token_budget=args.token_budget, wall_budget=args.wall_budget,
                     run_agents=not args.skip_agent_api,
                     collect_existing=args.collect_existing)
    print(json.dumps({"project": result["project"],
                      "overall_status": result["overall_status"],
                      "stages": result["stages"]}, ensure_ascii=False, indent=2))
    return 0 if result["overall_status"] in {
        "full_seeded_experiment", "native_only_seed_path_blocked",
        "native_baseline_only_external_api_blocked",
        "native_baseline_only_v2_analysis_incomplete"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
