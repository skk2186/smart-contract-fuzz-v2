#!/usr/bin/env python3
"""Phase31 bounded sequence expansion and paired Wallet mechanism experiment."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func" / "功能"))
sys.path.insert(0, str(ROOT / "deepseek"))

from 属性种子上下文 import PROJECTS, load_project_context, read_json
from 种子验证 import (AnvilSession, replay_seed, run_echidna, to_echidna_sequence,
                     write_corpus)
from 状态反馈序列扩展 import (build_action_templates, feedback_vector,
                         propose_extensions, retain_diverse_prefixes,
                         sequence_fingerprint, transaction_fingerprint)


RESULT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase31-20261119"
WALLET_RESULT = RESULT / "Wallet机制回归"
RUN_ROOT = WALLET_RESULT
EXPANSION_ROOT = WALLET_RESULT
CONFIG_PATH = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置/Wallet02Refund.json"
P1_PATH = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Wallet02Refund/Phase30B-20261119/03-P0-P1配对验证结果.json"
PROPERTY_ID = "8e75f62866f6d582a033"
MAX_LENGTH = 8
RETAINED_PREFIXES = 4
MAX_EXECUTIONS = 24
SEEDS = [20261125, 20261135, 20261145]
EXTENSION_MODES = {"random": "A_random", "static": "A_static",
                   "state_feedback": "E3"}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def _profile_wallet() -> dict[str, Any]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    profile = {
        "report": config["paths"]["analysis_report"],
        "artifact": config["paths"]["compiled_artifact"],
        "source_root": config["source"]["root"],
        "contract": config["harness"]["contract"],
        "deployment": config["deployment"],
        "execution": config["execution"],
        "property": config["property"],
        "senders": config["actions"]["senders"],
        "fuzzer_target": str(ROOT / config["compiler"]["target"]),
        "solc": config["compiler"]["solc"],
        "solc_version": config["compiler"]["version"],
        "echidna": {"prefix": config["echidna"]["prefix"],
                    "workers": config["echidna"]["workers"],
                    "call_sequence_length": config["echidna"]["call_sequence_length"],
                    "stop_on_fail": config["echidna"]["stop_on_fail"],
                    "disable_slither": config["echidna"]["disable_slither"]},
    }
    PROJECTS["Wallet02Refund"] = profile
    return config


def _artifact_abi(project: str) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    artifact = read_json(PROJECTS[project]["artifact"])
    abi = {entry["name"] + "(" + ",".join(x["type"] for x in entry.get("inputs", [])) + ")": entry
           for entry in artifact.get("abi", []) if entry.get("type") == "function"}
    return abi, artifact


def _load_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    config = _profile_wallet()
    context = load_project_context("Wallet02Refund", [PROPERTY_ID])
    prop = context["properties"][0]
    abi_by_signature, artifact = _artifact_abi("Wallet02Refund")
    prior = read_json(P1_PATH)
    candidate_row = next(item for item in prior["candidates"]
                         if item["name"] == "P1-source-context-planner")
    transactions = []
    for item in candidate_row["resolved_transactions"]:
        transactions.append({key: copy.deepcopy(item[key]) for key in (
            "function", "arguments", "sender", "value_wei", "delay_seconds",
            "delay_blocks", "expected_outcome", "data_dependencies") if key in item})
    candidate = {"project": "Wallet02Refund", "property_id": PROPERTY_ID,
                 "candidate_id": "phase30b-p1-raw-agent-ab-candidate",
                 "property": prop["property"], "context": context,
                 "assumptions": [], "transactions": transactions}
    source_ref = str(prop.get("property_source", "")).split("#", 1)[0]
    property_source = ((ROOT / source_ref).read_text(encoding="utf-8", errors="replace")
                       if source_ref and (ROOT / source_ref).is_file() else "")
    return config, context, abi_by_signature, {"candidate": candidate,
                                               "property": prop,
                                               "artifact": artifact,
                                               "property_source": property_source,
                                               "comparison": candidate_row}


def _execution_tx(tx: dict[str, Any]) -> dict[str, Any]:
    return {key: copy.deepcopy(value) for key, value in tx.items()
            if key in {"function", "arguments", "sender", "value_wei", "delay_seconds",
                       "delay_blocks", "expected_outcome", "data_dependencies"}}


def _execute(project: str, candidate: dict[str, Any], sequence: list[dict[str, Any]], *,
             runtime_constraints: bool = True) -> dict[str, Any]:
    return replay_seed(project, candidate, [_execution_tx(tx) for tx in sequence],
                       runtime_constraints=runtime_constraints)


def _apply_one_parameter_repair(project: str, candidate: dict[str, Any],
                                sequence: list[dict[str, Any]], replay: dict[str, Any]
                                ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any] | None]:
    for index, row in enumerate(replay.get("transactions", [])):
        proposal = row.get("constraint_repair_proposal")
        if not proposal:
            continue
        repaired = copy.deepcopy(sequence)
        tx_index = int(proposal.get("transaction_index", index + 1)) - 1
        if not 0 <= tx_index < len(repaired):
            continue
        tx = repaired[tx_index]
        old_args = list(tx.get("arguments", []))
        updates = proposal.get("argument_updates") or [{
            "argument_index": proposal["argument_index"],
            "repaired_value": proposal["repaired_value"]}]
        applied = []
        for update in updates:
            arg = int(update["argument_index"])
            if 0 <= arg < len(old_args):
                applied.append({"argument_index": arg, "before": old_args[arg],
                                "after": update["repaired_value"]})
                old_args[arg] = update["repaired_value"]
        if not applied:
            continue
        tx["arguments"] = old_args
        repaired_replay = _execute(project, candidate, repaired, runtime_constraints=False)
        return repaired, repaired_replay, {"transaction_index": tx_index + 1,
                                           "updates": applied, "proposal": proposal}
    return sequence, replay, None


def _valid_action_sequence(sequence: list[dict[str, Any]],
                           abi_by_signature: dict[str, dict[str, Any]]) -> tuple[bool, str | None]:
    if not sequence or len(sequence) > MAX_LENGTH:
        return False, "sequence length outside the frozen bound"
    for tx in sequence:
        abi = abi_by_signature.get(str(tx.get("function", "")))
        if abi is None or len(abi.get("inputs", [])) != len(tx.get("arguments", [])):
            return False, "function signature or argument count does not match ABI"
        if not isinstance(tx.get("sender"), str) or not str(tx["sender"]).startswith("0x"):
            return False, "missing sender address"
    return True, None


def _score_node(node: dict[str, Any], seen_states: set[str], property_source: str) -> dict[str, Any]:
    feedback = feedback_vector(node["replay"], property_source=property_source,
                               seen_states=seen_states)
    node["feedback"] = feedback
    node["sequence"] = node["sequence"]
    return node


def _run_extension(mode: str, base_sequence: list[dict[str, Any]],
                   action_templates: list[dict[str, Any]], action_evidence: dict[str, dict[str, Any]],
                   abi_by_signature: dict[str, dict[str, Any]], candidate: dict[str, Any],
                   target_states: set[str], senders: list[str], property_source: str,
                   *, random_seed: int = 20261119) -> dict[str, Any]:
    started = time.monotonic()
    base_replay = _execute("Wallet02Refund", candidate, base_sequence, runtime_constraints=True)
    base_sequence, base_replay, base_repair = _apply_one_parameter_repair(
        "Wallet02Refund", candidate, base_sequence, base_replay)
    executions = 1  # fresh baseline replay; extension decisions below are separately counted
    records: list[dict[str, Any]] = [{"candidate_no": 0, "origin": "frozen_base_replay",
                                     "sequence": base_sequence, "replay": base_replay,
                                     "parameter_repair": base_repair,
                                     "feedback": feedback_vector(base_replay,
                                                                 property_source=property_source)}]
    frontier = [{"sequence": base_sequence, "replay": base_replay, "depth": 0}]
    seen_sequences = {sequence_fingerprint(base_sequence)}
    seen_states: set[str] = set()
    decisions: list[dict[str, Any]] = []
    target_candidate: dict[str, Any] | None = None
    budget_executions = 0
    iteration = 0
    while frontier and budget_executions < MAX_EXECUTIONS and target_candidate is None:
        iteration += 1
        pool: list[dict[str, Any]] = []
        for parent in frontier:
            proposals = propose_extensions(
                parent["sequence"], action_templates, action_evidence,
                abi_by_signature, mode=mode, replay=parent["replay"],
                target_states=target_states, senders=senders,
                max_sequence_length=MAX_LENGTH,
                max_proposals=MAX_EXECUTIONS - budget_executions,
                random_seed=random_seed + iteration + parent["depth"])
            for proposal in proposals:
                sequence = proposal["sequence"]
                fingerprint = proposal["fingerprint"]
                if fingerprint in seen_sequences:
                    decisions.append({"iteration": iteration, "operator": proposal["operator"],
                                      "sequence_fingerprint": fingerprint,
                                      "decision": "discarded", "reason": "semantic duplicate"})
                    continue
                valid, reason = _valid_action_sequence(sequence, abi_by_signature)
                if not valid:
                    decisions.append({"iteration": iteration, "operator": proposal["operator"],
                                      "sequence_fingerprint": fingerprint,
                                      "decision": "discarded", "reason": reason})
                    continue
                # Each candidate is replayed from a fresh deployment and receives at
                # most one existing local parameter repair; no Agent is called.
                run_started = time.monotonic()
                replay = _execute("Wallet02Refund", candidate, sequence, runtime_constraints=True)
                sequence, replay, repair = _apply_one_parameter_repair(
                    "Wallet02Refund", candidate, sequence, replay)
                elapsed = time.monotonic() - run_started
                seen_sequences.add(fingerprint)
                budget_executions += 1
                executions += 1
                vector = feedback_vector(replay, property_source=property_source,
                                         seen_states=seen_states)
                new_states = set(vector["getter_state_fingerprints"])
                seen_states |= new_states
                record = {"candidate_no": budget_executions,
                          "iteration": iteration,
                          "origin": proposal["operator"],
                          "proposal_reason": proposal["proposal_reason"],
                          "proposal_evidence": proposal.get("evidence"),
                          "sequence_fingerprint": fingerprint,
                          "sequence": sequence, "replay": replay,
                          "parameter_repair": repair,
                          "elapsed_seconds": round(elapsed, 6),
                          "feedback": vector,
                          "retention_decision": "pending"}
                records.append(record)
                decisions.append({"iteration": iteration,
                                  "sequence_fingerprint": fingerprint,
                                  "operator": proposal["operator"],
                                  "decision": "executed",
                                  "reason": proposal["proposal_reason"]})
                if vector["counterexample_reached"] and replay.get("replay_status") == "executable":
                    target_candidate = record
                    break
                if (replay.get("transactions") and
                        (vector["property_related_state_changed"] or
                         any(row.get("status") == "success" for row in replay["transactions"]))):
                    pool.append({"sequence": sequence, "replay": replay,
                                 "depth": parent["depth"] + 1,
                                 "feedback": vector, "record": record})
                if budget_executions >= MAX_EXECUTIONS:
                    break
            if target_candidate or budget_executions >= MAX_EXECUTIONS:
                break
        if target_candidate:
            target_candidate["retention_decision"] = "target_reached_stop"
            break
        retained = retain_diverse_prefixes(pool, RETAINED_PREFIXES)
        for node in pool:
            node["record"]["retention_decision"] = node.get(
                "retention_decision", "discarded_budget_or_lower_feedback_and_lower_diversity")
            if node in retained:
                node["record"]["retention_decision"] = "retained_diverse_prefix"
        frontier = retained
    eligible = [row for row in records
                if row.get("replay", {}).get("replay_status") == "executable" and
                row.get("feedback", {}).get("property_related_state_changed")]
    return {"mode": mode, "status": "target_reached" if target_candidate else
            "valid_related_state_candidate" if eligible else "no_valid_related_state_candidate",
            "base_candidate_fingerprint": sequence_fingerprint(base_sequence),
            "base_parameter_repair": base_repair,
            "candidate_execution_budget": MAX_EXECUTIONS,
            "candidate_executions": budget_executions,
            "base_replay_executions": 1,
            "total_anvil_replays": executions,
            "elapsed_seconds": round(time.monotonic() - started, 6),
            "api_calls": 0, "api_tokens": 0, "api_cost_usd": 0,
            "records": records, "decisions": decisions,
            "target_candidate": target_candidate,
            "eligible_candidates": eligible}


def _write_seed(project: str, candidate: dict[str, Any], sequence: list[dict[str, Any]],
                context: dict[str, Any], group: str) -> Path:
    root = RUN_ROOT / "seed-pack" / group
    root.mkdir(parents=True, exist_ok=True)
    seed_id = "seed-" + uuid.uuid4().hex
    replay = {"replay_status": "executable"}
    return write_corpus(project, candidate, sequence, context, root,
                        replay=replay, seed_id=seed_id)


def _lcov_lines(root: Path) -> set[tuple[str, int]]:
    result: set[tuple[str, int]] = set()
    for path in root.rglob("*.lcov"):
        current = ""
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("SF:"):
                current = line[3:]
            elif line.startswith("DA:"):
                fields = line[3:].split(",")
                if len(fields) >= 2 and fields[0].isdigit() and int(fields[1]) > 0:
                    result.add((current, int(fields[0])))
    return result


def _copy_seed_file(source: Path | None, corpus: Path) -> None:
    if source is None:
        return
    target = corpus / "coverage" / source.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def run_wallet_echidna(groups: dict[str, dict[str, Any]], candidate: dict[str, Any],
                       context: dict[str, Any], seeds: list[int] = SEEDS) -> dict[str, Any]:
    results = []
    skipped = []
    for group, payload in groups.items():
        if payload.get("skip_reason"):
            skipped.append({"group": group, "reason": payload["skip_reason"]})
            continue
        sequence = payload.get("sequence")
        valid_seed = payload.get("valid_seed", False)
        seed_path = (_write_seed("Wallet02Refund", candidate, sequence, context, group)
                     if valid_seed and sequence else None)
        preparation_seconds = float(payload.get("preparation_seconds", 0))
        for seed in seeds:
            for stage, limit in (("seed_only", 0), ("fuzz_500", 500)):
                corpus = RUN_ROOT / "echidna" / group / f"seed-{seed}" / stage
                corpus.mkdir(parents=True, exist_ok=True)
                _copy_seed_file(seed_path, corpus)
                result = run_echidna(
                    "Wallet02Refund", corpus,
                    property_name="echidna_wallet_accounting_respected()",
                    test_limit=limit, timeout=60, seed=seed,
                    seq_len=MAX_LENGTH, shrink_limit=1, stop_on_fail=False,
                    disable_slither=True, sender_pool=PROJECTS["Wallet02Refund"]["senders"],
                    working_directory=ROOT)
                result["end_to_end_elapsed_seconds"] = None
                result["end_to_end_cost_scope"] = (
                    "seed preparation is a one-time group cost; report it separately from each Echidna repeat")
                result["seed_preparation_seconds"] = preparation_seconds
                result["group"] = group
                result["stage"] = stage
                result["external_seed_used"] = seed_path is not None
                result["seed_path"] = str(seed_path.relative_to(ROOT)) if seed_path else None
                _write_json(corpus / "summary.json", result)
                results.append(result)
    coverage = {}
    for result in results:
        key = (result["group"], result["seed"])
        if result["stage"] == "seed_only":
            coverage[key] = {"seed_only_lines": _lcov_lines(Path(result["full_log_path"]).parent)}
        else:
            final_lines = _lcov_lines(Path(result["full_log_path"]).parent)
            seed_lines = coverage.get(key, {}).get("seed_only_lines", set())
            coverage[key]["final_lines"] = final_lines
            coverage[key]["mutation_added_lines"] = final_lines - seed_lines
    compact_coverage = [{"group": group, "seed": seed,
                         "seed_only_line_count": len(item.get("seed_only_lines", set())),
                         "mutation_added_line_count": len(item.get("mutation_added_lines", set())),
                         "final_line_count": len(item.get("final_lines", set())),
                         "seed_only_lines": sorted(item.get("seed_only_lines", set())),
                         "mutation_added_lines": sorted(item.get("mutation_added_lines", set()))}
                        for (group, seed), item in sorted(coverage.items())]
    return {"groups": results, "skipped_groups": skipped, "coverage": compact_coverage,
            "coverage_interpretation": "LCOV line sets are compared within the same group/seed between testLimit=0 replay-only and testLimit=500 campaigns; no counter-based mutation inference is used."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["wallet-extension", "wallet-fuzz"],
                        default="wallet-extension")
    parser.add_argument("--max-executions", type=int, default=MAX_EXECUTIONS)
    parser.add_argument("--mode", choices=["random", "static", "state_feedback", "all"],
                        default="all")
    parser.add_argument("--run-tag", default="attempt-02-feedback-priority")
    parser.add_argument("--expansion-tag", default=None,
                        help="wallet-fuzz 使用指定目录中的已冻结扩展结果")
    parser.add_argument("--groups", nargs="+",
                        choices=["E0", "E1", "E2", "E3", "A_random", "A_static"],
                        default=None, help="wallet-fuzz 仅运行指定对照组")
    args = parser.parse_args()
    if args.max_executions != MAX_EXECUTIONS:
        raise ValueError("Phase31冻结候选执行上限为24，不接受扩大预算")
    global RUN_ROOT, EXPANSION_ROOT
    RUN_ROOT = WALLET_RESULT / args.run_tag
    EXPANSION_ROOT = WALLET_RESULT / (args.expansion_tag or args.run_tag)
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    config, context, abi_by_signature, loaded = _load_context()
    candidate = loaded["candidate"]
    prop = loaded["property"]
    base = candidate["transactions"]
    action_templates, template_decisions = build_action_templates(
        prop["candidate_actions"], abi_by_signature, base, config["actions"]["senders"])
    action_evidence = {str(row.get("abi_signature")): row
                       for row in prop["candidate_actions"] if row.get("abi_signature")}
    target_states = set(prop.get("read_states", [])) | set(prop.get("property_write_states", []))
    if args.phase == "wallet-extension":
        modes = list(EXTENSION_MODES) if args.mode == "all" else [args.mode]
        results = {}
        for mode in modes:
            result = _run_extension(mode, base, action_templates, action_evidence,
                                    abi_by_signature, candidate, target_states,
                                    config["actions"]["senders"], loaded["property_source"])
            result["candidate_template_decisions"] = template_decisions
            results[mode] = result
            _write_json(RUN_ROOT / f"{EXTENSION_MODES[mode]}-扩展回放.json", result)
        _write_json(RUN_ROOT / "01-扩展方法汇总.json", {
            "phase": 31, "input": "Phase30B P1 exact Agent A/B transaction candidate",
            "manual_oracle_read": False, "manual_oracle_used": False,
            "base_sequence": base, "action_templates": action_templates,
            "target_states": sorted(target_states), "max_sequence_length": MAX_LENGTH,
            "retained_prefixes": RETAINED_PREFIXES,
            "candidate_execution_limit_per_mode": MAX_EXECUTIONS,
            "results": results})
        return

    group_sources = {}
    base_replay = _execute("Wallet02Refund", candidate, base, runtime_constraints=True)
    base_replay = _apply_one_parameter_repair("Wallet02Refund", candidate, base, base_replay)[1]
    group_sources["E1"] = {"sequence": base, "valid_seed": base_replay.get("replay_status") == "executable",
                            "preparation_seconds": 0, "replay": base_replay}
    # The frozen Phase30B E1 candidate did not trigger a runtime repair. E2 is therefore
    # the same paired plan and same concrete arguments; this is explicitly recorded.
    group_sources["E2"] = {**group_sources["E1"], "parameter_repair": "no repair proposal; identical to E1"}
    group_sources["E0"] = {"sequence": None, "valid_seed": False, "preparation_seconds": 0}
    for mode, group in EXTENSION_MODES.items():
        result_path = EXPANSION_ROOT / f"{group}-扩展回放.json"
        expansion = read_json(result_path)
        choice = expansion.get("target_candidate")
        if choice is None:
            choice = next((row for row in expansion.get("eligible_candidates", [])
                           if row.get("origin") != "frozen_base_replay"), None)
        group_sources[group] = {
            "sequence": choice.get("sequence") if choice else None,
            "valid_seed": bool(choice and choice.get("replay", {}).get("replay_status") == "executable" and
                                choice.get("feedback", {}).get("property_related_state_changed")),
            "preparation_seconds": expansion.get("elapsed_seconds", 0),
            "replay": choice.get("replay") if choice else None,
            "candidate_execution_count": expansion.get("candidate_executions", 0),
            "automatic_target_reached": bool(expansion.get("target_candidate")),
            "skip_reason": None if choice else
                "extension mode produced no Anvil-executable, property-related candidate; retain failure without substituting the base sequence",
        }
    if args.groups:
        requested_groups = set(args.groups)
        missing_groups = requested_groups - set(group_sources)
        if missing_groups:
            raise ValueError(f"requested groups unavailable: {sorted(missing_groups)}")
        group_sources = {key: value for key, value in group_sources.items()
                         if key in requested_groups}
    if not any(payload.get("valid_seed") for group, payload in group_sources.items()
               if group in {"E1", "E2", "E3", "A_random", "A_static"}):
        raise RuntimeError("没有合法且产生属性相关状态变化的种子，不启动种子效用组")
    echidna = run_wallet_echidna(group_sources, candidate, context)
    _write_json(RUN_ROOT / "02-E0-E3-Echidna对照.json", echidna)


if __name__ == "__main__":
    main()
