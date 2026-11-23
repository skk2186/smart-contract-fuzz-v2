#!/usr/bin/env python3
"""Replay the frozen Phase41 Drips output through the Phase42 E2/E3 fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "deepseek/实验过程"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入")]

import 真实合约统一执行适配器 as adapter
import Phase41Drips端到端实验 as phase41
from AgentB import to_echidna_sequence
from 属性种子上下文 import compact_for_agent


FROZEN = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase41-20261123/Drips"
OUTPUT = ROOT / "func/测试过程/SCFuzzBench公开项目接入/结果/Phase42-20261123/Drips/automatic"
MANIFEST_PATH = ROOT / "func/测试过程/SCFuzzBench公开项目接入/项目配置/Drips.json"


def write_json(path: Path, value: Any) -> None:
    adapter.write_json(path, value)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=False)
    manifest = adapter.read_json(MANIFEST_PATH)
    frozen_agent = adapter.read_json(FROZEN / "agent/agent-run.json")
    frozen_sequence = frozen_agent["concrete_output"]["transactions"]
    backend, _, _, tools = phase41._foundry(manifest, OUTPUT / "tooling")
    target = phase41.PROPERTY_SIGNATURE

    # Preserve an after-change E1 replay from the exact frozen Agent B sequence.
    raw_e1, feedback_e1 = phase41._replay(
        backend, manifest, frozen_sequence, "E1-frozen-agent-output",
        OUTPUT / "E1", target)
    write_json(OUTPUT / "E1.raw.json", raw_e1)
    write_json(OUTPUT / "E1.v2-feedback.json", feedback_e1)

    context, prop = phase41._context_for_agent(
        manifest, {"status": "success", "contract_address":
                   feedback_e1.get("deployment", {}).get("target_address"),
                   "observed_state": feedback_e1.get("state_before", []),
                   "role_addresses": [{"role": row.get("role"),
                                       "address": row["address"]}
                                      for row in manifest.get("accounts", [])],
                   "observation_completeness": feedback_e1.get("capabilities", {}).get(
                       "state_observation")})
    compact_context = compact_for_agent(context)
    write_json(OUTPUT / "agent-context-focused.json", compact_context)
    focused_prop = compact_context["properties"][0]
    context_metrics = {
        "agent_was_not_called": True,
        "frozen_agent_output_sha256": adapter.sha256_file(FROZEN / "agent/agent-run.json"),
        "original_candidate_action_count": len(prop.get("candidate_actions", [])),
        "focused_candidate_action_count": len(focused_prop.get("candidate_actions", [])),
        "context_focus": focused_prop.get("context_focus"),
        "direct_internal_helpers": [row.get("function") for row in
                                     focused_prop.get("direct_internal_helper_contexts", [])],
        "runtime_numeric_observations": [
            {"name": row.get("name"), "value": row.get("value"), "status": row.get("status")}
            for row in feedback_e1.get("state_before", [])
            if row.get("name") in {"minAmtPerSec", "cycleSecs"}],
        "source_guard_evidence_for_target_action": next((
            action.get("numeric_guard_evidence", []) for action in prop.get("candidate_actions", [])
            if action.get("abi_signature") == "setStreams(uint8,uint8,uint160,uint32,uint32,int128)"), []),
    }
    write_json(OUTPUT / "context-audit.json", context_metrics)

    e2 = phase41._e2_repair(context, frozen_sequence, feedback_e1)
    write_json(OUTPUT / "E2-proposal.json", e2)
    if e2.get("applied"):
        raw_e2, feedback_e2 = phase41._replay(
            backend, manifest, e2["sequence"], "E2-source-getter-repair",
            OUTPUT / "E2", target)
        write_json(OUTPUT / "E2.raw.json", raw_e2)
        write_json(OUTPUT / "E2.v2-feedback.json", feedback_e2)
    else:
        raw_e2, feedback_e2 = raw_e1, feedback_e1

    echidna_seed_only = None
    echidna_seed_path = None
    if e2.get("applied") and feedback_e2.get("replay_status") == "executable":
        seed_candidate = {"property_id": phase41.PROPERTY_ID,
                          "assertion_trigger": prop.get("assertion_trigger")}
        seed_contents = to_echidna_sequence(
            seed_candidate, e2["sequence"], context,
            contract_address="0xa647ff3c36cfab592509e13860ab8c4f28781a66")
        seed_root = OUTPUT / "echidna-seed-only"
        seed_root.mkdir(parents=True, exist_ok=False)
        echidna_seed_path = seed_root / "automatic-e2-seed.txt"
        echidna_seed_path.write_text(json.dumps(seed_contents, ensure_ascii=False, indent=2) + "\n",
                                     encoding="utf-8")
        prep = adapter.read_json(FROZEN / "准备/01-source-dependency-preparation.json")
        corpus = seed_root / "corpus" / "automatic-e2"
        echidna_seed_only = phase41._run_fuzz_campaign(
            corpus, seed=phase41.PAIRED_SEEDS[0], test_limit=0,
            seed_file=echidna_seed_path, workspace=Path(prep["cache"]["workspace"]),
            senders=[row["address"] for row in manifest.get("accounts", [])])
        write_json(seed_root / "echidna-seed-only-result.json", echidna_seed_only)

    report = adapter.read_json(ROOT / phase41.PROJECTS["Drips"]["report"])
    groups = {}
    for group, bind in (("G1", False), ("G2", True)):
        result = phase41._run_e3_group(
            group, e2["sequence"], feedback_e2, context, manifest, backend,
            OUTPUT, bind_phase37=bind)
        groups[group] = result
        write_json(OUTPUT / (group + "-result.json"), result)

    summary = {
        "schema_version": 1,
        "project": "Drips",
        "classification": "engineering_integration_and_regression_only",
        "baseline_head": "328530091fb85c864eeff8cae81e2d6273d1eada",
        "property_id": phase41.PROPERTY_ID,
        "property_signature": target,
        "agent_output_sha256": adapter.sha256_file(FROZEN / "agent/agent-run.json"),
        "tool_versions": tools.get("versions", {}),
        "before_change": adapter.read_json(FROZEN / "comparison/G0-E1-G1-G2-summary.json"),
        "after_change": {
            "E1": {"backend_status": raw_e1.get("status"),
                   "replay_status": feedback_e1.get("replay_status"),
                   "sequence": frozen_sequence,
                   "failed_transactions": feedback_e1.get("failure_evidence", []),
                   "target_property_state": feedback_e1.get("target_property_state"),
                   "properties": feedback_e1.get("properties", [])},
            "E2": {"status": "repair_applied_and_replayed" if e2.get("applied")
                    else "no_evidence_based_parameter_repair",
                   "proposal": e2,
                   "backend_status": raw_e2.get("status"),
                   "replay_status": feedback_e2.get("replay_status"),
                   "target_property_state": feedback_e2.get("target_property_state"),
                   "properties": feedback_e2.get("properties", []),
                   "echidna_seed_file": str(echidna_seed_path) if echidna_seed_path else None,
                   "echidna_seed_only": echidna_seed_only},
            "G1": groups["G1"],
            "G2": groups["G2"],
        },
        "context_audit": context_metrics,
        "interpretation": {
            "assertion_pass_is_not_counterexample": True,
            "automatically_discovered_counterexample": False,
            "manual_diagnostic_oracle_counted_as_discovery": False,
            "G1_G2_same_starting_sequence": groups["G1"].get(
                "starting_sequence_fingerprint") == groups["G2"].get(
                "starting_sequence_fingerprint"),
            "G1_G2_same_candidate_budget": groups["G1"].get("candidate_budget") ==
                groups["G2"].get("candidate_budget"),
        },
    }
    write_json(OUTPUT / "Phase42-automatic-summary.json", summary)
    print(json.dumps({
        "status": "complete",
        "output": str(OUTPUT),
        "E1": {"backend": raw_e1.get("status"), "replay": feedback_e1.get("replay_status")},
        "E2": {"applied": e2.get("applied"),
               "replay": feedback_e2.get("replay_status"),
               "proposal": next((row.get("proposal") for row in e2.get("proposals", [])
                                 if row.get("proposal")), None),
               "propagated": e2.get("propagated_argument_updates", [])},
        "G1": {"status": groups["G1"].get("status"),
               "candidates": groups["G1"].get("candidate_count"),
               "valid_sequences": groups["G1"].get("valid_sequence_count")},
        "G2": {"status": groups["G2"].get("status"),
               "candidates": groups["G2"].get("candidate_count"),
               "valid_sequences": groups["G2"].get("valid_sequence_count"),
               "binding_statuses": sorted({row.get("phase37_binding_status")
                                             for row in groups["G2"].get("candidates", [])})},
        "focused_context": {"actions": context_metrics["original_candidate_action_count"],
                            "retained": context_metrics["focused_candidate_action_count"],
                            "helpers": context_metrics["direct_internal_helpers"]},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
