#!/usr/bin/env python3
"""Bounded Phase46 paired run over four predeclared regression/development cases."""

from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计"
P43 = BASE / "结果/Phase43-20261123"
P44 = BASE / "结果/Phase44-20261124"
P36 = BASE / "结果/Phase36-20261120"
P37 = BASE / "结果/Phase37-20261121"
OUT = BASE / "结果/Phase46-20261127"
FREEZE = OUT / "phase46-frozen-config.json"
SUMMARY = OUT / "phase46-paired-summary.json"
RUN_LOG = OUT / "phase46-run.log"
START_UTC = "2026-11-27T04:29:20Z"
DEADLINE_UTC = "2026-11-27T05:29:20Z"
MAX_LENGTH = 64
CANDIDATES_PER_ARM = 12
RETAINED_PREFIXES = 4
FUZZ_SECONDS = 30
ALGORITHM_SEED = 4101
ECHIDNA_SEED = 4301
CASE_IDS = ("OLYMPIA-001", "OLYMPIA-076", "DAllowance", "Wallet02Refund")
POSITIVE_PROGRESS = {"directional_progress", "goal_reached"}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def read(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
                    encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seq_digest(sequence: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(sequence, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    line = f"{stamp} {message}\n"
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
    print(line.rstrip(), flush=True)


def freeze() -> dict[str, Any]:
    if FREEZE.exists() or SUMMARY.exists():
        raise FileExistsError(f"Phase46 already frozen or run: {OUT}")
    manifest = read(P43 / "dataset-manifest.json")
    dev_ids = read(P44 / "dev/experiment-config.json")["development_sample_ids"]
    task_rows = {item["sample_id"]: item for item in manifest["dataset"]["samples"]}
    small = next(row["sample_id"] for row in (task_rows[item] for item in dev_ids)
                 if row.get("dimension") == 5)
    deep = next(row["sample_id"] for row in (task_rows[item] for item in dev_ids)
                if row.get("dimension") == 20)
    if (small, deep) != ("OLYMPIA-001", "OLYMPIA-076"):
        raise RuntimeError(f"fixed manifest selection changed: {small}, {deep}")
    p36_freeze_path = P36 / "00-Phase36冻结.json"
    p37_inputs_path = P36 / "00-缺失前置步骤删减输入.json"
    p44_inputs = {sample_id: P44 / "dev/tasks" / sample_id / "inputs.json"
                  for sample_id in (small, deep)}
    olympia_static_files = []
    for sample_id in (small, deep):
        p43_task = P43 / "tasks" / sample_id
        source = P43 / task_rows[sample_id]["files"]["source"]["path"]
        olympia_static_files.extend([source, p43_task / "agent/property-context.json",
            p43_task / "analysis/compiler-artifact.json",
            p43_task / "analysis/property-analysis.json.gz"])
    required = [p36_freeze_path, p37_inputs_path, *p44_inputs.values(),
                *olympia_static_files,
                P44 / "dev/experiment-config.json",
                P43 / "dataset-manifest.json",
                ROOT / "func/功能/状态反馈序列扩展.py",
                ROOT / "func/功能/跨交易状态约束.py",
                ROOT / "func/功能/种子验证.py",
                ROOT / "func/测试过程/跨交易属性状态依赖审计/Phase43批量实验.py",
                ROOT / "func/测试过程/跨交易属性状态依赖审计/Phase36自适应扩展.py",
                ROOT / "func/测试过程/跨交易属性状态依赖审计/Phase36属性状态感知门控.py",
                ROOT / "func/测试过程/跨交易属性状态依赖审计/Phase37前置约束绑定验证.py",
                Path(__file__)]
    p36_freeze = read(p36_freeze_path)
    p37_inputs = read(p37_inputs_path)
    cases = {
        small: {"source": "Phase44 frozen development input; first 5x5 task in manifest order",
                "input_path": str(p44_inputs[small].relative_to(ROOT)),
                "input_sha256": digest(p44_inputs[small]),
                "sequence_sha256": seq_digest(read(p44_inputs[small])["E1_sequence"] or []),
                "input_rule": "reuse frozen E1 exactly; same empty-sequence fallback if absent"},
        deep: {"source": "Phase44 frozen development input; first 20x20 task in manifest order",
               "input_path": str(p44_inputs[deep].relative_to(ROOT)),
               "input_sha256": digest(p44_inputs[deep]),
               "sequence_sha256": seq_digest(read(p44_inputs[deep])["E1_sequence"] or []),
               "input_rule": "reuse frozen E1 exactly; same empty-sequence fallback if absent"},
        "DAllowance": {"source": "existing Phase37 isolated missing-prerequisite input; complete route excluded",
                       "input_path": str(p37_inputs_path.relative_to(ROOT)),
                       "input_sha256": digest(p37_inputs_path),
                       "sequence_sha256": seq_digest(p37_inputs["DAllowance"]["sequence"]),
                       "input_rule": "only frozen incomplete sequence passed; full reference route is not loaded"},
        "Wallet02Refund": {"source": "Phase36 frozen E2 input only; independent Wallet oracle excluded",
                           "input_path": str((P36 / "00-Phase36冻结.json").relative_to(ROOT)),
                           "input_sha256": digest(p36_freeze_path),
                           "sequence_sha256": p36_freeze["tasks"]["A_Wallet02Refund"]["sequence_sha256"],
                           "input_rule": "reuse frozen E2 sequence; known counterexample is not passed to the algorithm"},
    }
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    config = {
        "phase": "Phase46",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase_start_utc": START_UTC, "deadline_utc": DEADLINE_UTC,
        "verified_head": git_head, "branch": branch,
        "case_selection_rule": "two fixed first-per-dimension Phase44 development samples, plus the existing Phase37 DAllowance incomplete input and Phase36 Wallet E2 regression input; no outcome-based selection",
        "cases": cases,
        "arms": {"baseline": "legacy feedback, legacy retention, no repeated prerequisite insertion",
                 "guided": "target-direction scoring, observed precondition transitions, retain executable prefixes, permit statically matched prerequisite repetition"},
        "controls": {"same_initial_sequence": True, "same_action_inventory": True,
            "same_max_sequence_length": MAX_LENGTH,
            "candidate_execution_budget_per_arm_per_case": CANDIDATES_PER_ARM,
            "retained_prefix_limit": RETAINED_PREFIXES,
            "algorithm_seed": ALGORITHM_SEED, "echidna_seed": ECHIDNA_SEED,
            "fuzz_seconds_per_arm_per_case": FUZZ_SECONDS,
            "echidna_configuration_shared": True,
            "phase37_parameter_binding_enabled_in_both_arms": True,
            "parameter_repair_enabled_in_both_arms": True,
            "candidate_templates_shared": True,
            "agent_calls": 0, "official_oracle_or_route_passed_to_algorithm": False},
        "frozen_file_sha256": {str(path.relative_to(ROOT)): digest(path) for path in required},
        "metrics": ["complete_executable_sequences", "reliably_observed_target_or_prerequisite_progress",
                    "target_state_reached", "native_echidna_counterexamples", "time_to_first_counterexample",
                    "seed_only_coverage", "final_fuzz_coverage", "candidate_replays", "execution_seconds",
                    "compile_seconds", "wall_seconds", "failure_reason"],
        "fuzz_gate": "Only run after guided arm yields an independently evidenced target-direction change or a same-consumer state-revert-to-success transition with an observed preceding writer change to the statically read guard state.",
        "fallback": "When no retained candidate is executable, both arms use the same executable frozen starting sequence; if absent, no seed-based fuzz is run.",
    }
    write(FREEZE, config)
    write(OUT / "phase46-clock.json", {"start_utc": START_UTC, "deadline_utc": DEADLINE_UTC,
                                       "freeze_utc": config["frozen_at_utc"]})
    return config


def validate_freeze() -> dict[str, Any]:
    config = read(FREEZE)
    if not config:
        raise FileNotFoundError("run --freeze before --run")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
    if (head, branch) != (config["verified_head"], config["branch"]):
        raise RuntimeError("HEAD or branch changed after Phase46 freeze")
    amendments = [OUT / "phase46-freeze-amendment-01.json",
                  OUT / "phase46-freeze-amendment-02.json"]
    loaded_amendments = [read(path) for path in amendments if path.is_file()]
    for amendment in loaded_amendments:
        if amendment.get("base_freeze_sha256") != digest(FREEZE):
            raise RuntimeError("preflight amendment does not bind to the original frozen config")
        if amendment.get("comparison_data_existed_before_amendment") is not False:
            raise RuntimeError("freeze amendment is only permitted before candidate results")
        config["frozen_file_sha256"][amendment["runner_path"]] = amendment["runner_sha256"]
    for relative, expected in config["frozen_file_sha256"].items():
        path = ROOT / relative
        if digest(path) != expected:
            raise RuntimeError(f"frozen input/code hash changed: {relative}")
    for amendment in loaded_amendments:
        failed_summary = ROOT / amendment["failed_launch_summary_path"]
        if digest(failed_summary) != amendment["failed_launch_summary_sha256"]:
            raise RuntimeError("preserved setup-failure summary hash mismatch")
        for relative, expected in amendment["extra_input_sha256"].items():
            if digest(ROOT / relative) != expected:
                raise RuntimeError(f"amended frozen input hash changed: {relative}")
    return config


def amend_preflight() -> dict[str, Any]:
    failure_summary_path = (OUT / "attempt-01-setup-failure" / SUMMARY.name
                            if (OUT / "attempt-01-setup-failure" / SUMMARY.name).is_file()
                            else SUMMARY)
    if not FREEZE.is_file() or not failure_summary_path.is_file():
        raise RuntimeError("preflight amendment requires the original freeze and failed launch summary")
    old_summary = read(failure_summary_path)
    if any(row.get("status") != "failed_or_blocked" or row.get("arms")
           for row in old_summary.get("cases", {}).values()):
        raise RuntimeError("cannot amend after any candidate comparison result exists")
    base_config = read(FREEZE)
    if (base_config.get("verified_head") != subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()):
        raise RuntimeError("HEAD changed since the original freeze")
    manifest = read(P43 / "dataset-manifest.json")
    sample_ids = [case for case in CASE_IDS if case.startswith("OLYMPIA-")]
    rows = {item["sample_id"]: item for item in manifest["dataset"]["samples"]}
    extra_files = []
    for sample_id in sample_ids:
        task = P43 / "tasks" / sample_id
        extra_files += [P43 / rows[sample_id]["files"]["source"]["path"],
            task / "agent/property-context.json", task / "analysis/compiler-artifact.json",
            task / "analysis/property-analysis.json.gz"]
    runner = Path(__file__).resolve()
    prior_amendment = OUT / "phase46-freeze-amendment-01.json"
    amendment_index = 1 if not prior_amendment.exists() else 2
    amendment = {"amendment": amendment_index,
        "amended_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_freeze_sha256": digest(FREEZE),
        "reason": "First launch failed before candidate generation because the Phase43 static report is gzip-compressed and the Phase37 context helper returns three values; selection, budgets and score rules are unchanged.",
        "comparison_data_existed_before_amendment": False,
        "failed_launch_summary_sha256": digest(failure_summary_path),
        "failed_launch_summary_path": str(failure_summary_path.relative_to(ROOT)),
        "runner_path": str(runner.relative_to(ROOT)), "runner_sha256": digest(runner),
        "extra_input_sha256": {str(path.relative_to(ROOT)): digest(path) for path in extra_files}}
    if amendment_index == 2:
        amendment["previous_amendment_sha256"] = digest(prior_amendment)
        amendment["reason"] = "Post-amendment validation fix: apply the frozen runner-hash override before validating code hashes; no experiment data was produced."
    path = OUT / f"phase46-freeze-amendment-{amendment_index:02d}.json"
    if path.exists():
        raise FileExistsError(path)
    write(path, amendment)
    return amendment


def load_olympia(case_id: str, config: dict[str, Any]):
    phase = load_module("phase46_phase43", ROOT / "func/测试过程/跨交易属性状态依赖审计/Phase43批量实验.py")
    phase.RESULT = P43
    phase.MANIFEST = P43 / "dataset-manifest.json"
    phase.MAX_SEQUENCE_LENGTH = MAX_LENGTH
    phase.E3_CANDIDATE_BUDGET = CANDIDATES_PER_ARM
    sample = next(item for item in read(phase.MANIFEST)["dataset"]["samples"]
                  if item["sample_id"] == case_id)
    p43_task = P43 / "tasks" / case_id
    p44_task = P44 / "dev/tasks" / case_id
    inputs = read(p44_task / "inputs.json")
    context = read(p43_task / "agent/property-context.json")
    artifact = read(p43_task / "analysis/compiler-artifact.json")
    analysis_path = p43_task / "analysis/property-analysis.json.gz"
    with gzip.open(analysis_path, "rt", encoding="utf-8") as handle:
        analysis = json.load(handle)
    source = P43 / sample["files"]["source"]["path"]
    if any(value is None for value in (context, artifact, analysis)) or not source.is_file():
        raise RuntimeError(f"missing frozen Olympia context/artifact: {case_id}")
    start = copy.deepcopy(inputs["E1_sequence"] or [])
    if seq_digest(start) != config["cases"][case_id]["sequence_sha256"]:
        raise RuntimeError(f"frozen E1 sequence hash mismatch: {case_id}")
    return phase, sample, source, start, inputs["E1_feedback"], context, artifact, analysis


def run_olympia_case(case_id: str, config: dict[str, Any]) -> dict[str, Any]:
    phase, sample, source, base, feedback, context, artifact, analysis = load_olympia(case_id, config)
    output = OUT / "Olympia" / case_id
    write(output / "frozen-input.json", {"sequence": base, "sequence_sha256": seq_digest(base),
        "feedback": feedback, "source_sha256": digest(source), "input_sha256": config["cases"][case_id]["input_sha256"]})
    arms = {}
    for arm, target_guided in (("baseline", False), ("guided", True)):
        task_dir = output / arm
        started = time.monotonic()
        result = phase.e3_group(arm, sample, base, feedback, context, artifact, analysis,
                                task_dir, bind=True, target_guided=target_guided)
        result["arm_wall_seconds"] = round(time.monotonic() - started, 6)
        result["start_sequence_sha256"] = seq_digest(base)
        write(task_dir / "arm-summary.json", result)
        arms[arm] = result
        log(f"CANDIDATE {case_id}/{arm} count={result['candidate_count']} executable={result['valid_sequence_count']} replay_s={result['replay_seconds']}")
    return {"case_id": case_id, "input_sequence_sha256": seq_digest(base), "arms": arms,
            "engine": "Phase43 PyEVM property replay; same E3 templates, parameter repair and Phase37 binding"}


def load_phase37_cases():
    phase37 = load_module("phase46_phase37", ROOT / "func/测试过程/跨交易属性状态依赖审计/Phase37前置约束绑定验证.py")
    phase36_freeze = read(P36 / "00-Phase36冻结.json")
    phase36, contexts, _projects = phase37._runtime_contexts(phase36_freeze)
    gate = phase36.load_module("phase46_gate", phase36.GATE_FILE)
    phase36.MAX_LENGTH = MAX_LENGTH
    phase36.MAX_EXECUTIONS = CANDIDATES_PER_ARM
    phase36.RETAINED_PREFIXES = RETAINED_PREFIXES
    phase36.SEED_BASE = ALGORITHM_SEED
    return phase37, phase36, gate, contexts


def run_phase37_case(case_id: str, config: dict[str, Any], runtime) -> dict[str, Any]:
    phase37, phase36, gate, contexts = runtime
    row = contexts[case_id]
    base = copy.deepcopy(row["sequence"])
    expected = config["cases"][case_id]["sequence_sha256"]
    if seq_digest(base) != expected:
        raise RuntimeError(f"Phase37 frozen input mismatch: {case_id}")
    profile = __import__("属性种子上下文").PROJECTS[row["project"]]
    report_path = Path(profile["report"])
    artifact_path = Path(profile["artifact"])
    if not report_path.is_absolute():
        report_path = ROOT / report_path
    if not artifact_path.is_absolute():
        artifact_path = ROOT / artifact_path
    report, artifact = read(report_path), read(artifact_path)
    abi = phase37._abi_map(artifact_path)
    effect_catalog = report.get("effect_catalog", {})
    output = OUT / "RealContract" / case_id
    write(output / "frozen-input.json", {"sequence": base, "sequence_sha256": seq_digest(base),
        "source": config["cases"][case_id]["source"], "profile_report_sha256": digest(report_path),
        "artifact_sha256": digest(artifact_path)})
    arms = {}
    for arm, target_guided in (("baseline", False), ("guided", True)):
        started = time.monotonic()
        result = phase36._run_g2(row["project"], row["candidate"], row["prop"], abi,
            copy.deepcopy(base), row["senders"], output / arm, gate,
            binding_enabled=True, effect_catalog=effect_catalog,
            target_guided=target_guided)
        result["arm_wall_seconds"] = round(time.monotonic() - started, 6)
        result["start_sequence_sha256"] = seq_digest(base)
        write(output / arm / "arm-summary.json", result)
        arms[arm] = result
        log(f"CANDIDATE {case_id}/{arm} executed={result['candidate_executions']} considered={result['candidate_proposals_considered']} replays={result['total_anvil_replays']} elapsed_s={result['elapsed_seconds']}")
    return {"case_id": case_id, "input_sequence_sha256": seq_digest(base), "arms": arms,
            "engine": "Phase36 Anvil replay with shared parameter repair, adaptive gate and Phase37 binding"}


def arm_feedback_rows(result: dict[str, Any], *, guided: bool) -> list[dict[str, Any]]:
    if "candidates" in result:
        return [{"sequence": row["sequence"], "feedback": row.get("feedback", {}),
                 "replay_status": row.get("replay_status"), "replay": row.get("replay_feedback"),
                 "record": row} for row in result.get("candidates", [])]
    return [{"sequence": row["sequence"], "feedback": row.get("feedback", {}),
             "replay_status": (row.get("replay") or {}).get("replay_status"),
             "replay": row.get("replay"), "record": row}
            for row in result.get("records", []) if row.get("candidate_no", 0) > 0]


def choose_seeds(case_id: str, arm: str, arm_result: dict[str, Any]) -> tuple[list[list[dict[str, Any]]], list[dict[str, Any]]]:
    from 状态反馈序列扩展 import retain_diverse_prefixes
    rows = arm_feedback_rows(arm_result, guided=(arm == "guided"))
    score_rows = [{"sequence": row["sequence"], "feedback": row["feedback"], "record": row}
                  for row in rows]
    retained = retain_diverse_prefixes(score_rows, RETAINED_PREFIXES,
                                        target_state_guided=(arm == "guided"))
    selected = [row for row in retained if row["record"].get("replay_status") == "executable"]
    selected_records = [row["record"] for row in selected]
    if not selected_records:
        base_path = (OUT / "Olympia" / case_id / "frozen-input.json" if case_id.startswith("OLYMPIA-")
                     else OUT / "RealContract" / case_id / "frozen-input.json")
        base = read(base_path)["sequence"]
        if base and ((case_id.startswith("OLYMPIA-") and
                      read(OUT / "Olympia" / case_id / "frozen-input.json")["feedback"].get("replay_status") == "executable") or
                     (not case_id.startswith("OLYMPIA-") and
                      (arm_result.get("base_replay") or {}).get("replay_status") == "executable")):
            return [base], [{"sequence": base, "replay_status": "executable",
                             "feedback": arm_result.get("base_feedback", {})}]
        return [], []
    return [row["sequence"] for row in selected_records], selected_records


def echidna_non_olympia(case_id: str, row: dict[str, Any], sequences: list[list[dict[str, Any]]],
                         records: list[dict[str, Any]], run_dir: Path, *, test_limit: int,
                         timeout: int) -> dict[str, Any]:
    from 属性种子上下文 import PROJECTS
    from 种子验证 import new_seed_id, run_echidna, write_corpus
    project, prop = row["project"], row["prop"]
    candidate, context = row["candidate"], row["context"]
    corpus_input = run_dir / "corpus-input"
    for index, (sequence, record) in enumerate(zip(sequences, records), start=1):
        replay = record.get("replay") or {}
        write_corpus(project, candidate, replay.get("resolved_transactions") or sequence,
                     context, corpus_input, replay=replay,
                     seed_id=new_seed_id())
    name = str(prop.get("property_abi") or prop["property"]).split("(", 1)[0].rsplit(".", 1)[-1]
    filter_functions = [f"{PROJECTS[project]['contract']}.{item['abi_signature']}"
        for item in prop.get("candidate_actions", [])
        if item.get("seed_compatible") and item.get("abi_signature")]
    filter_functions.append(f"{PROJECTS[project]['contract']}.{name}()")
    source_root = Path(PROJECTS[project]["source_root"])
    working = source_root if source_root.is_absolute() else ROOT / source_root
    return run_echidna(project, corpus_input, property_name=name, test_limit=test_limit,
        timeout=timeout, seed=ECHIDNA_SEED, test_mode="property", property_prefix=name,
        filter_functions=filter_functions, seq_len=MAX_LENGTH, shrink_limit=1,
        stop_on_fail=False, disable_slither=True, sender_pool=context.get("sender_pool"),
        working_directory=working)


def run_fuzz_for_case(case_id: str, case_result: dict[str, Any], runtime) -> dict[str, Any]:
    results = {}
    for arm in ("baseline", "guided"):
        arm_result = case_result["arms"][arm]
        sequences, records = choose_seeds(case_id, arm, arm_result)
        arm_dir = (OUT / "Olympia" / case_id / arm if case_id.startswith("OLYMPIA-")
                   else OUT / "RealContract" / case_id / arm)
        write(arm_dir / "selected-seeds.json", {"sequences": sequences,
            "sequence_sha256": [seq_digest(item) for item in sequences],
            "selection_feedback": [row.get("feedback", {}) for row in records]})
        if not sequences:
            results[arm] = {"status": "not_run_no_executable_seed", "seed_count": 0}
            continue
        if case_id.startswith("OLYMPIA-"):
            phase, sample, source, _, _, context, _, _ = load_olympia(case_id, {})
            candidate = {"property_id": context["properties"][0]["property_id"]}
            seed_only = phase.run_echidna(sample, source, arm_dir / "echidna-seed-only",
                seed=ECHIDNA_SEED, timeout=10, test_limit=0, seed_sequences=sequences,
                candidate=candidate, context=context,
                working_directory=arm_dir / "echidna-seed-only-cwd")
            fuzz = None
            if seed_only.get("replayed_seed_count", 0) > 0:
                fuzz = phase.run_echidna(sample, source, arm_dir / "echidna-fuzz",
                    seed=ECHIDNA_SEED, timeout=FUZZ_SECONDS, test_limit=1_000_000_000,
                    seed_sequences=sequences, candidate=candidate, context=context,
                    working_directory=arm_dir / "echidna-fuzz-cwd")
        else:
            row = runtime[3][case_id]
            seed_only = echidna_non_olympia(case_id, row, sequences, records,
                arm_dir / "echidna-seed-only", test_limit=0, timeout=10)
            fuzz = None
            ev = seed_only.get("corpus_evidence", {})
            if ev.get("loaded_seed_count", 0) > 0 and ev.get("replayed_sequence_count", 0) > 0:
                fuzz = echidna_non_olympia(case_id, row, sequences, records,
                    arm_dir / "echidna-fuzz", test_limit=1_000_000_000, timeout=FUZZ_SECONDS)
        results[arm] = {"seed_count": len(sequences), "seed_only": seed_only,
                        "fuzz": fuzz,
                        "native_counterexample": bool((fuzz or {}).get("native_counterexample") or
                            (fuzz or {}).get("corpus_evidence", {}).get("property_failure_reported")),
                        "time_to_first_native_counterexample_seconds":
                            (fuzz or {}).get("time_to_first_native_counterexample_seconds")}
        write(arm_dir / "fuzz-summary.json", results[arm])
        log(f"FUZZ {case_id}/{arm} seeds={len(sequences)} loaded={seed_only.get('loaded_seed_sequences', (seed_only.get('corpus_evidence') or {}).get('loaded_seed_count'))} replayed={seed_only.get('replayed_seed_count', (seed_only.get('corpus_evidence') or {}).get('replayed_sequence_count'))} fuzz_status={(fuzz or {}).get('status')}")
    return results


def progress_summary(case_result: dict[str, Any]) -> dict[str, Any]:
    summary = {"case_id": case_result["case_id"], "arms": {}, "guided_independent_progress": False}
    for arm, result in case_result["arms"].items():
        rows = arm_feedback_rows(result, guided=(arm == "guided"))
        directional = [row for row in rows if row["feedback"].get("target_progress", {}).get("status") in POSITIVE_PROGRESS]
        prerequisite = [row for row in rows if row["feedback"].get("precondition_progress")]
        state_changes = [row for row in rows if row["feedback"].get("observed_target_state_changes")]
        summary["arms"][arm] = {
            "candidate_replays": result.get("candidate_count", result.get("candidate_executions", 0)),
            "complete_executable_sequences": sum(row.get("replay_status") == "executable" for row in rows),
            "target_direction_or_goal_sequences": len(directional),
            "confirmed_precondition_progress_sequences": len(prerequisite),
            "observed_target_state_change_sequences_direction_unknown": len(state_changes),
            "target_reached_sequences": sum(bool(row["feedback"].get("counterexample_reached")) for row in rows),
            "state_unknown_sequences": sum(row["feedback"].get("target_progress", {}).get("status") == "unknown" for row in rows),
            "execution_seconds": result.get("replay_seconds", result.get("elapsed_seconds")),
            "total_replays": result.get("candidate_count", result.get("total_anvil_replays")),
            "compile_seconds": None,
            "failure_reasons": [row.get("feedback", {}).get("property_check_status")
                                for row in rows if row.get("replay_status") not in {"executable", None}],
        }
        if arm == "guided":
            summary["guided_independent_progress"] = bool(directional or prerequisite)
    return summary


def run() -> dict[str, Any]:
    config = validate_freeze()
    if SUMMARY.exists():
        raise FileExistsError("Phase46 results already exist; no implicit retry")
    OUT.mkdir(parents=True, exist_ok=True)
    RUN_LOG.write_text("", encoding="utf-8")
    rows: dict[str, Any] = {}
    runtime = None
    stage_start = datetime.fromisoformat(START_UTC.replace("Z", "+00:00"))
    for case_id in config["cases"]:
        if (datetime.now(timezone.utc) - stage_start).total_seconds() >= 55 * 60:
            log(f"STOP new cases at or after 55-minute threshold; next={case_id}")
            break
        try:
            if case_id.startswith("OLYMPIA-"):
                rows[case_id] = run_olympia_case(case_id, config)
            else:
                if runtime is None:
                    runtime = load_phase37_cases()
                rows[case_id] = run_phase37_case(case_id, config, runtime)
        except Exception as exc:
            failure = {"case_id": case_id, "status": "failed_or_blocked",
                       "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
            write(OUT / "failures" / f"{case_id}.json", failure)
            rows[case_id] = failure
            log(f"FAIL {case_id}: {failure['error']}")
    analyses = {case_id: progress_summary(result) for case_id, result in rows.items()
                if result.get("arms")}
    should_fuzz = any(item["guided_independent_progress"] for item in analyses.values())
    fuzz = {}
    if should_fuzz:
        for case_id, result in rows.items():
            if not result.get("arms"):
                continue
            try:
                if case_id.startswith("OLYMPIA-"):
                    fuzz[case_id] = run_fuzz_for_case(case_id, result, runtime)
                else:
                    if runtime is None:
                        runtime = load_phase37_cases()
                    fuzz[case_id] = run_fuzz_for_case(case_id, result, runtime)
            except Exception as exc:
                failure = {"case_id": case_id, "stage": "fuzz", "status": "failed_or_blocked",
                           "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
                write(OUT / "failures" / f"{case_id}-fuzz.json", failure)
                fuzz[case_id] = failure
                log(f"FUZZ_FAIL {case_id}: {failure['error']}")
    ended = datetime.now(timezone.utc)
    summary = {"phase": "Phase46", "started_utc": START_UTC,
        "ended_utc": ended.isoformat(),
        "wall_seconds_since_start": round((ended - stage_start).total_seconds(), 3),
        "frozen_config_sha256": digest(FREEZE), "cases": rows,
        "progress_diagnostics": analyses, "fuzz_gate_opened": should_fuzz,
        "fuzz": fuzz, "agent_calls": 0,
        "deadline_utc": DEADLINE_UTC}
    write(SUMMARY, summary)
    write(OUT / "phase46-clock.json", {"start_utc": START_UTC, "deadline_utc": DEADLINE_UTC,
        "end_utc": summary["ended_utc"], "wall_seconds_since_start": summary["wall_seconds_since_start"]})
    log(f"COMPLETE cases={len(rows)} fuzz_gate={should_fuzz}")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--freeze", action="store_true")
    group.add_argument("--amend-preflight", action="store_true")
    group.add_argument("--run", action="store_true")
    args = parser.parse_args()
    result = freeze() if args.freeze else amend_preflight() if args.amend_preflight else run()
    output_path = (FREEZE if args.freeze else OUT / "phase46-freeze-amendment-01.json"
                   if args.amend_preflight else SUMMARY)
    print(json.dumps({"status": "frozen" if args.freeze else "amended" if args.amend_preflight else "complete",
                      "path": str(output_path.relative_to(ROOT)),
                      "cases": list(result.get("cases", {}))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
