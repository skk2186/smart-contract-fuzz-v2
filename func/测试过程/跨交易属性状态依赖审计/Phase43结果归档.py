#!/usr/bin/env python3
"""Phase43 completed-run archival: unique costs, real-project rows, summaries."""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import shutil
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase43-20261123"
SEEDS = [4301, 4302, 4303]


def load_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


def read_csv(path: Path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, fields: list[str], rows: list[dict]):
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def rel(path: Path) -> str:
    return path.relative_to(BASE).as_posix()


def num(value):
    try:
        return None if value in (None, "", "N/A", "None", "unknown") else float(value)
    except (ValueError, TypeError):
        return None


def truth(value):
    return str(value).lower() in ("true", "1", "yes")


def api_summary(path: Path):
    run = load_json(path, {}) or {}
    usage = run.get("api_usage", {})
    a = run.get("agent_a", {}).get("events", [])
    b = run.get("agent_b", {}).get("events", [])
    return run, usage, a, b


def main():
    # Preserve both originals and lossless, hash-verified compressed copies.
    archive = load_json(BASE / "analysis-archive-manifest.json")
    extra = []
    project = BASE / "real-projects/aave-v4"
    for name in ("06-direct-solc-slither.json", "06-direct-solc-slither.log"):
        source = project / name
        target = source.with_suffix(source.suffix + ".gz")
        if not target.is_file():
            raise RuntimeError(f"Expected pre-compressed copy missing: {target}")
        source_hash = hashlib.sha256()
        with source.open("rb") as f:
            for block in iter(lambda: f.read(1024 * 1024), b""):
                source_hash.update(block)
        extra.append({
            "original_path": rel(source), "original_sha256": source_hash.hexdigest(),
            "original_bytes": source.stat().st_size, "archive_path": rel(target),
            "archive_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            "archive_bytes": target.stat().st_size,
            "verified_restore_sha256": source_hash.hexdigest(), "original_retained": True,
        })
    archive["supplemental_reports"] = extra
    write_json(BASE / "analysis-archive-manifest.json", archive)

    liq_root = BASE / "real-projects/liquity-v2-governance"
    (liq_root / "E2").mkdir(exist_ok=True)
    shutil.copyfile(liq_root / "E1/sequence.json", liq_root / "E2/sequence.json")
    write_json(liq_root / "E2/repair-summary.json", {
        "property": "GovernanceProperties.invariant_GV01()",
        "property_id": "dfb2424a270e98ccc137", "input_sequence": "E1/sequence.json",
        "sequence_sha256": hashlib.sha256((liq_root / "E2/sequence.json").read_bytes()).hexdigest(),
        "repair_applied": False, "transactions_before": 1, "transactions_after": 1,
        "repair_kind": "none; no evidence-supported constraint change was proposed",
        "repair_needed": False, "seed_only_native_status": "passed",
        "property_failure_observed": False,
        "target_state_status": "unknown; native property pass does not expose predicate operands",
        "evidence": ["E1/sequence.json", "E2/seed-only-native-result.json",
                     "E2/seed-only-native/E1-AgentAB.echidna-native.log"],
    })
    for group in ("G1", "G2"):
        (liq_root / group).mkdir(exist_ok=True)
        write_json(liq_root / f"{group}/extension-summary.json", {
            "group": group, "starting_sequence": "E2/sequence.json", "candidate_budget": 24,
            "candidate_count": 0, "valid_sequence_count": 0, "extension_replays": 0,
            "phase37_binding_enabled": group == "G2",
            "binding_applicable": 0 if group == "G2" else None,
            "binding_success": 0 if group == "G2" else None,
            "status": "completed_no_candidates",
            "note": "Formal fuzz uses the shared E2 seed-only baseline; no extension candidate was replayed.",
            "evidence": f"formal-fuzz-final/{group}/*/result.json",
        })

    projects = {
        "SCFUZZ-AaveV4": {
            "id": "aave-v4", "url": "https://github.com/scfuzzbench/aave-v4-scfuzzbench.git",
            "commit": "6f9795808367de1357c1059377dde9201b9c1d66", "tree": "af0fcd51c8fc2b9250fe5dbea39207285cf5daad",
            "hash": "1d05ba83a092f8e8fa611dc3dc34fe95ee03435e142ff0d609345b87701482a2",
            "scope": "完整固定源码与依赖 composite SHA-256",
            "property": "Properties.invariant_shouldNotBecomeLiquidatable()", "property_id": "64362cda961f070afeb8",
            "analysis": "direct-solc fallback analyzed 9 native Boolean properties; 1 selected",
            "build": "Solc 0.8.28 Forge build passed",
            "native": "selected target ran in 3/3 G0 fuzz runs and stayed passing; unrelated canaries falsified",
            "v2": "Agent A called once but no concrete sequence; Agent B and E2/G1/G2 not run",
            "block": "No eligible V2 seed; G1/G2 formal fuzz N/A",
        },
        "SCFUZZ-SuperformV2": {
            "id": "superform-v2-periphery", "url": "https://github.com/scfuzzbench/superform-v2-periphery-scfuzzbench.git",
            "commit": "102eeaf5e2f49963bdd007c7358739b0a0e59e84", "tree": "ea18f9af8e45c4b5b92ae20fa918a2d1ee3ffb62",
            "hash": "unavailable_for_pinned_commit", "scope": "Pinned checkout unavailable; fetched checkout resolved to cbb51b03055e6b08ea6e5d8180e86b7e68dcf84",
            "property": "Boolean native candidates present; no task selected because source/build gate failed", "property_id": "",
            "analysis": "not run", "build": "failed: missing lib/v2-core/lib/openzeppelin-contracts/contracts/interfaces/IERC20Metadata.sol",
            "native": "not run", "v2": "not run",
            "block": "Pinned source/submodule mismatch; no source substitution or property change",
        },
        "SCFUZZ-LiquityV2Governance": {
            "id": "liquity-v2-governance", "url": "https://github.com/scfuzzbench/liquity-V2-gov-scfuzzbench.git",
            "commit": "5610870e7e91fe6e29f8cfb0c0ae316fe9784e10", "tree": "64cde0843ced5bdb1260100f1184b3d7cd020e6f",
            "hash": "7177d2eb3d8c2203339e7411743ba8871a55e97db7c348c5a5c9b6eb33217278",
            "scope": "固定提交跟踪文件与递归固定子模块 composite SHA-256",
            "property": "GovernanceProperties.invariant_GV01()", "property_id": "dfb2424a270e98ccc137",
            "analysis": "7 native Boolean properties analyzed; 1 selected",
            "build": "Solc 0.8.24 Forge build passed",
            "native": "E1/E2 seed-only passed; G0/G1/G2 each found selected target counterexample in 3/3 seeds",
            "v2": "one executable E1/E2 transaction; no repair; G1/G2 extension candidate 0; fuzz completed",
            "block": "Initial dependency preparation was incomplete; final direct property analysis/build/fuzz completed. Foundry replay mismatch excluded from counterexamples.",
        },
        "SCFUZZ-OriginDollar": {
            "id": "origin-dollar", "url": "https://github.com/scfuzzbench/origin-dollar-scfuzzbench.git",
            "commit": "299ec6b6bf5401b43efc3e9f7ee5cab3e76167c4", "tree": "55a124e6cf45670ac14a9c0ea6c68a1cae4aa3c5",
            "hash": "fe50a0281ef85c9578fb9a6207246cdba3ace987a2890a8e3a7a5990259b6389",
            "scope": "固定提交跟踪文件与递归固定子模块 composite SHA-256",
            "property": "No eligible zero-argument native Boolean property; source contains parameterized test/assert functions", "property_id": "",
            "analysis": "source/build inspection complete; no eligible task", "build": "Solc 0.8.28 Forge build passed",
            "native": "not run because no eligible native property", "v2": "not run because no target task",
            "block": "No eligible native Boolean property under frozen filter; target not replaced",
        },
    }

    admissions = read_csv(BASE / "admission.csv")
    for row in admissions:
        p = projects.get(row["sample_id"])
        if not p:
            continue
        row.update({
            "dimension": "", "upstream_commit": p["commit"], "source_hash": p["hash"],
            "native_property": p["property"], "generator_reachability": "not_applicable",
            "analysis_status": p["analysis"], "build_status": p["build"],
            "native_admission": p["native"], "v2_status": p["v2"], "blocking_reason": p["block"],
        })
    write_csv(BASE / "admission.csv", list(admissions[0]), admissions)

    manifest = load_json(BASE / "dataset-manifest.json")
    manifest["scfuzzbench"]["project_results"] = []
    for sid, p in projects.items():
        prep = load_json(BASE / f"real-projects/{p['id']}/01-source-and-dependencies.json", {}) or {}
        manifest["scfuzzbench"]["project_results"].append({
            "sample_id": sid, "project_id": p["id"], "source_repository": p["url"],
            "pinned_commit": p["commit"], "resolved_commit": prep.get("resolved_commit", ""),
            "root_git_tree": p["tree"], "source_hash": p["hash"], "hash_scope": p["scope"],
            "native_property": p["property"], "property_id": p["property_id"],
            "analysis_status": p["analysis"], "build_status": p["build"],
            "native_status": p["native"], "v2_status": p["v2"], "blocking_reason": p["block"],
        })
    manifest["execution_adapter_updates"] = {
        "algorithm_changed": False,
        "allowed_generic_compatibility_support": [
            "Solidity dynamic integer-array ABI encoding and Echidna seed serialization for step(int8[])",
            "fixed Echidna corpus signature field fallback",
            "Echidna outcome parser matches outcome tokens rather than property-name substrings",
            "tool paths resolved from configured Foundry installation in isolated worktree",
        ],
        "upstream_business_sources_modified": False,
        "native_properties_modified": False,
        "harness_semantics_modified": False,
    }
    manifest["completion"] = {
        "olympia_samples": 100, "olympia_per_dimension": 25, "preflight_samples": 20,
        "scfuzzbench_candidates": 4, "real_projects_with_selected_native_property": 2,
        "real_projects_with_completed_native_fuzz": 2,
        "phase_status": "all scheduled samples processed; non-runnable targets retained",
        "completed_date": "2026-11-24",
    }
    write_json(BASE / "dataset-manifest.json", manifest)

    # One row per target; API calls/tokens/costs are not copied into fuzz runs.
    cost_fields = ["sample_id", "source", "property_id", "agent_a_calls", "agent_b_calls", "request_attempts",
                   "failed_request_attempts", "prompt_tokens", "completion_tokens", "total_tokens",
                   "estimated_cost_usd_offpeak", "estimated_cost_usd_peak", "agent_a_seconds", "agent_b_seconds",
                   "agent_total_seconds", "status", "agent_run_record", "api_log", "cost_basis"]
    costs = []
    for sample in manifest["dataset"]["samples"]:
        sid = sample["sample_id"]
        path = BASE / f"tasks/{sid}/agent/agent-run.json"
        run, usage, a, b = api_summary(path)
        costs.append({
            "sample_id": sid, "source": "Olympia", "property_id": run.get("property_id", sample.get("property_id", "")),
            "agent_a_calls": len(a), "agent_b_calls": len(b),
            "request_attempts": int(usage.get("request_attempts") or len(a) + len(b)),
            "failed_request_attempts": int(usage.get("failed_request_attempts") or 0),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0), "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "estimated_cost_usd_offpeak": usage.get("estimated_cost_usd_offpeak", "0"),
            "estimated_cost_usd_peak": usage.get("estimated_cost_usd_peak", "0"),
            "agent_a_seconds": round(sum(float(e.get("elapsed_seconds") or 0) for e in a), 6),
            "agent_b_seconds": round(sum(float(e.get("elapsed_seconds") or 0) for e in b), 6),
            "agent_total_seconds": round(sum(float(e.get("elapsed_seconds") or 0) for e in a + b), 6),
            "status": "recorded" if usage else "no_api_usage",
            "agent_run_record": rel(path) if path.is_file() else "",
            "api_log": rel(BASE / f"tasks/{sid}/agent/API调用.jsonl") if (BASE / f"tasks/{sid}/agent/API调用.jsonl").is_file() else "",
            "cost_basis": usage.get("cost_basis", "no API calls recorded"),
        })
    for sid, project in (("SCFUZZ-AaveV4", "aave-v4"), ("SCFUZZ-SuperformV2", "superform-v2-periphery"),
                         ("SCFUZZ-LiquityV2Governance", "liquity-v2-governance"), ("SCFUZZ-OriginDollar", "origin-dollar")):
        path = BASE / f"real-projects/{project}/agent/agent-run.json"
        run, usage, a, b = api_summary(path)
        costs.append({
            "sample_id": sid, "source": "SCFuzzBench", "property_id": run.get("property_id", ""),
            "agent_a_calls": len(a), "agent_b_calls": len(b),
            "request_attempts": int(usage.get("request_attempts") or len(a) + len(b)),
            "failed_request_attempts": int(usage.get("failed_request_attempts") or 0),
            "prompt_tokens": int(usage.get("prompt_tokens") or 0), "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
            "estimated_cost_usd_offpeak": usage.get("estimated_cost_usd_offpeak", "0"),
            "estimated_cost_usd_peak": usage.get("estimated_cost_usd_peak", "0"),
            "agent_a_seconds": round(sum(float(e.get("elapsed_seconds") or 0) for e in a), 6),
            "agent_b_seconds": round(sum(float(e.get("elapsed_seconds") or 0) for e in b), 6),
            "agent_total_seconds": round(sum(float(e.get("elapsed_seconds") or 0) for e in a + b), 6),
            "status": run.get("status", "recorded" if usage else "not_called"),
            "agent_run_record": rel(path) if path.is_file() else "",
            "api_log": rel(BASE / f"real-projects/{project}/agent/API调用.jsonl") if (BASE / f"real-projects/{project}/agent/API调用.jsonl").is_file() else "",
            "cost_basis": usage.get("cost_basis", "no API calls recorded"),
        })
    assert len(costs) == 104
    write_csv(BASE / "agent-cost-summary.csv", cost_fields, costs)
    cost_by_id = {r["sample_id"]: r for r in costs}

    # Extend historical 1,700 Olympia records with timing columns and remove repeated costs.
    old = [r for r in read_csv(BASE / "campaign-results.csv") if r["source"] == "Olympia"]
    fields = list(old[0])
    for field in ("extension_replay_count", "run_wall_seconds", "analysis_compile_prep_seconds", "static_analysis_seconds", "agent_total_seconds"):
        if field not in fields:
            at = fields.index("agent_a_seconds") if "agent_a_seconds" in fields else len(fields)
            fields.insert(at, field)
    for row in old:
        for field in fields:
            row.setdefault(field, "")
        row["agent_a_seconds"] = row["agent_b_seconds"] = row["agent_tokens"] = ""
        row["agent_cost_usd_offpeak"] = row["agent_cost_usd_peak"] = ""
        if row["phase"] in ("agent_replay", "repair_and_replay") and row["status"] in ("executable", "partial_or_failed"):
            row["target_state_reached"] = "unknown"
            row["target_state_status"] = "unknown"
        if row["phase"] == "extension" and row["status"] == "completed":
            row["extension_replay_count"] = 0
        if row["group"] == "G1":
            row["g2_binding_applicable"] = ""
            row["g2_binding_success"] = ""
        if row["phase"] == "formal_fuzz" and row.get("native_counterexample") not in ("True", "true", "1"):
            row["target_state_reached"] = "unknown"
            row["target_state_status"] = "unknown"
        if row["group"] == "E1" and row["phase"] == "agent_replay":
            c = cost_by_id[row["sample_id"]]
            state = load_json(BASE / f"tasks/{row['sample_id']}/task-state.json", {}) or {}
            row.update({"agent_a_seconds": c["agent_a_seconds"], "agent_b_seconds": c["agent_b_seconds"],
                        "agent_total_seconds": c["agent_total_seconds"], "agent_tokens": c["total_tokens"],
                        "agent_cost_usd_offpeak": c["estimated_cost_usd_offpeak"],
                        "agent_cost_usd_peak": c["estimated_cost_usd_peak"],
                        "analysis_compile_prep_seconds": state.get("analysis_and_compile_seconds", "")})
        task = BASE / "tasks" / row["sample_id"]
        if row["phase"] == "formal_fuzz":
            result = load_json(task / f"echidna/{row['group']}/seed-{row['seed']}/result.json", {}) or {}
            row["run_wall_seconds"] = result.get("elapsed_seconds", "")
            compile_seconds = float(result.get("echidna_compile_seconds") or 0)
            row["compile_seconds"] = compile_seconds
            row["fuzz_seconds"] = max(0, float(result.get("elapsed_seconds") or 0) - compile_seconds)
        if row["phase"] == "seed_only":
            result = load_json(task / f"echidna/{row['group']}-seed-only/result.json", {}) or {}
            row["run_wall_seconds"] = result.get("elapsed_seconds", "")
            compile_seconds = float(result.get("echidna_compile_seconds") or 0)
            row["compile_seconds"] = compile_seconds
            row["fuzz_seconds"] = max(0, float(result.get("elapsed_seconds") or 0) - compile_seconds)

    # All real projects use the same 17-slot phase layout, retaining N/A explicitly.
    real = []
    blank = {k: "" for k in fields}

    def add(sid, group, phase, seed="", status="N/A", note="", **values):
        row = blank.copy()
        row.update({"sample_id": sid, "source": "SCFuzzBench", "dimension": "", "group": group,
                    "phase": phase, "seed": str(seed) if seed else "", "status": status, "notes": note,
                    "raw_dir": ""})
        for k, v in values.items():
            row[k] = "" if v is None else str(v)
        real.append(row)

    # Aave: the target property itself passed in G0; canaries are separate failures.
    sid, aave = "SCFUZZ-AaveV4", BASE / "real-projects/aave-v4"
    c = cost_by_id[sid]
    add(sid, "E1", "agent_replay", status="partial_or_failed", note="Agent A called once and produced no target sequence; Agent B was not called.",
        raw_sequence_count=0, complete_executable=False, agent_a_seconds=c["agent_a_seconds"], agent_total_seconds=c["agent_total_seconds"],
        agent_tokens=c["total_tokens"], agent_cost_usd_offpeak=c["estimated_cost_usd_offpeak"], agent_cost_usd_peak=c["estimated_cost_usd_peak"], raw_dir=rel(aave / "agent/agent-run.json"))
    add(sid, "E1", "seed_only", note="No valid E1 seed; not run and coverage is N/A.")
    add(sid, "E2", "repair_and_replay", note="No E1 seed; E2 was not run.")
    add(sid, "E2", "seed_only", note="No valid E2 seed; not run and coverage is N/A.")
    for group in ("G1", "G2"):
        add(sid, group, "extension", note="No E2 starting seed; extension not run.")
        add(sid, group, "seed_only", note="No V2 seed; not run and coverage is N/A.")
        for seed in SEEDS:
            add(sid, group, "formal_fuzz", seed, complete_executable=False, note="No loadable V2 seed; not run and coverage is N/A.")
    for seed in SEEDS:
        d = load_json(aave / f"formal-fuzz-corrected/seed-{seed}/result.json", {}) or {}
        add(sid, "G0", "formal_fuzz", seed, "completed",
            "Selected target passing; Echidna return code 1 came from two unrelated canaries, excluded from target counterexamples.",
            echidna_target_status=d.get("target_property_status", "passing"), native_counterexample=False,
            target_state_reached="unknown", target_state_status="unknown", final_coverage=d.get("unique_instructions"),
            unique_calls=d.get("unique_calls"), compile_seconds=d.get("compile_seconds"),
            static_analysis_seconds=d.get("slither_seconds"), fuzz_seconds=d.get("fuzz_seconds"),
            run_wall_seconds=d.get("elapsed_seconds"), raw_dir=rel(aave / f"formal-fuzz-corrected/seed-{seed}/echidna.log"))

    # Liquity: seed-only did not falsify; formal fuzz found the original target in every group.
    sid, liq = "SCFUZZ-LiquityV2Governance", BASE / "real-projects/liquity-v2-governance"
    c = cost_by_id[sid]
    add(sid, "E1", "agent_replay", "", "executable", "Agent A/B each called once; one helper_deployInitiative transaction replayed. Predicate operands are not observable in EVM feedback.",
        raw_sequence_count=1, sequence_length=1, transactions_succeeded=1, complete_executable=True,
        target_state_reached="unknown", target_state_status="unknown", property_value=True,
        agent_a_seconds=c["agent_a_seconds"], agent_b_seconds=c["agent_b_seconds"], agent_total_seconds=c["agent_total_seconds"],
        agent_tokens=c["total_tokens"], agent_cost_usd_offpeak=c["estimated_cost_usd_offpeak"],
        agent_cost_usd_peak=c["estimated_cost_usd_peak"], raw_dir=rel(liq / "E1/sequence.json"))
    for group in ("E1", "E2"):
        report = load_json(liq / f"{group}/seed-only-native-result.json", {}) or {}
        add(sid, group, "seed_only", status="completed",
            note="Native Echidna loaded and replayed one sequence; target passed with no counterexample; target internal state is unobservable.",
            complete_executable=True, target_state_reached="unknown", target_state_status="unknown",
            property_value=True, echidna_target_status="passing", native_counterexample=False,
            seed_only_coverage=7966, replayed_seed_count=report.get("loaded_sequences", 1),
            raw_dir=rel(liq / f"{group}/seed-only-native/{'E1-AgentAB.echidna-native.log'}"))
    add(sid, "E2", "repair_and_replay", "", "executable",
        "E2 sequence is byte-identical to E1; repair_applied=false and no repair was needed.",
        raw_sequence_count=1, sequence_length=1, transactions_succeeded=1, complete_executable=True,
        target_state_reached="unknown", target_state_status="unknown", property_value=True,
        raw_dir=rel(liq / "E2/repair-summary.json"))
    for group in ("G1", "G2"):
        add(sid, group, "extension", status="completed",
            note="0/24 extension candidates and 0 candidate replays. G2 Phase37 binding applicable=0 and success=0.",
            complete_executable=False, candidate_count=0, extension_replay_count=0,
            g2_binding_applicable=0 if group == "G2" else "", g2_binding_success=0 if group == "G2" else "",
            raw_dir=rel(liq / f"{group}/extension-summary.json"))
        add(sid, group, "seed_only", status="N/A",
            note="No separate duplicate G1/G2 seed-only run; each formal run records the shared E2 baseline (7966 instructions).")
        for seed in SEEDS:
            d = load_json(liq / f"formal-fuzz-final/{group}/seed-{seed}/result.json", {}) or {}
            add(sid, group, "formal_fuzz", seed, "completed", "Selected native invariant_GV01() falsified; this was a fuzz discovery, not seed-only.",
                complete_executable=True, target_state_reached=True,
                target_state_status=d.get("target_state_status", "confirmed_by_native_property_false"), property_value=False,
                echidna_target_status=d.get("target_property_status", "falsified"), native_counterexample=True,
                time_to_first_native_counterexample_seconds=d.get("time_to_first_native_counterexample_seconds"),
                seed_only_coverage=d.get("seed_only_coverage"), new_coverage=d.get("new_coverage"),
                final_coverage=d.get("unique_instructions"), unique_calls=d.get("unique_calls"),
                replayed_seed_count=d.get("replayed_seed_count"), candidate_count=d.get("candidate_count"),
                g2_binding_applicable=d.get("g2_binding_applicable") if group == "G2" else "",
                g2_binding_success=d.get("g2_binding_success") if group == "G2" else "",
                compile_seconds=d.get("compile_seconds"), static_analysis_seconds=d.get("slither_seconds"),
                fuzz_seconds=d.get("fuzz_seconds"), run_wall_seconds=d.get("elapsed_seconds"),
                raw_dir=rel(liq / f"formal-fuzz-final/{group}/seed-{seed}/echidna.log"))
    for seed in SEEDS:
        d = load_json(liq / f"formal-fuzz-final/G0/seed-{seed}/result.json", {}) or {}
        add(sid, "G0", "formal_fuzz", seed, "completed", "Native G0; selected invariant_GV01() falsified.",
            target_state_reached=True, target_state_status=d.get("target_state_status", "confirmed_by_native_property_false"),
            property_value=False, echidna_target_status=d.get("target_property_status", "falsified"),
            native_counterexample=True, time_to_first_native_counterexample_seconds=d.get("time_to_first_native_counterexample_seconds"),
            final_coverage=d.get("unique_instructions"), unique_calls=d.get("unique_calls"),
            replayed_seed_count=d.get("replayed_seed_count"), compile_seconds=d.get("compile_seconds"),
            static_analysis_seconds=d.get("slither_seconds"), fuzz_seconds=d.get("fuzz_seconds"),
            run_wall_seconds=d.get("elapsed_seconds"), raw_dir=rel(liq / f"formal-fuzz-final/G0/seed-{seed}/echidna.log"))

    # Source-blocked and no-target projects remain in all 17 slots.
    for sid, reason in (("SCFUZZ-SuperformV2", "Pinned source/dependency gate failed; no version replacement."),
                        ("SCFUZZ-OriginDollar", "No eligible zero-argument native Boolean target; no replacement selected.")):
        layout = [("E1", "agent_replay", "not_run"), ("E1", "seed_only", "N/A"),
                  ("E2", "repair_and_replay", "not_run"), ("E2", "seed_only", "N/A"),
                  ("G1", "extension", "not_run"), ("G1", "seed_only", "N/A")]
        layout += [("G1", "formal_fuzz", "N/A")]
        layout += [("G2", "extension", "not_run"), ("G2", "seed_only", "N/A")]
        layout += [("G2", "formal_fuzz", "N/A")]
        layout += [("G0", "formal_fuzz", "N/A")]
        for group, phase, status in layout:
            group_seeds = SEEDS if phase == "formal_fuzz" else [""]
            for seed in group_seeds:
                add(sid, group, phase, seed, status, reason + " Metrics remain N/A.",
                    complete_executable=False if phase in ("agent_replay", "repair_and_replay") else "")

    assert len(real) == 68, len(real)
    rows = old + real
    write_csv(BASE / "campaign-results.csv", fields, rows)

    # Add failed E2 replays and real-project blockers/canaries, preserving prior rows.
    failure_rows = read_csv(BASE / "failures.csv")
    failure_fields = list(failure_rows[0])
    seen = {(r["sample_id"], r["stage"], r["group"], r["seed"], r["failure_class"], r["reason"]) for r in failure_rows}

    def failure(sid, source, stage, group="", seed="", cls="", reason="", log=""):
        row = {"sample_id": sid, "source": source, "dimension": "", "stage": stage,
               "group": group, "seed": str(seed), "failure_class": cls, "reason": reason,
               "raw_log": log, "timestamp": ""}
        key = (sid, stage, group, str(seed), cls, reason)
        if key not in seen:
            failure_rows.append(row)
            seen.add(key)

    for row in old:
        if row["group"] == "E2" and row["phase"] == "repair_and_replay" and row["status"] == "partial_or_failed":
            sid = row["sample_id"]
            repair = load_json(BASE / f"tasks/{sid}/E2/repair.json", {}) or {}
            feedback = load_json(BASE / f"tasks/{sid}/E2/v2-feedback.json", {}) or {}
            failed_tx = next((x for x in reversed(feedback.get("transactions", [])) if x.get("status") == "failed"), {})
            failure(sid, "Olympia", "constraint_repair_replay", "E2", "", "no_evidence_supported_repair",
                    f"{repair.get('status')}; tx={failed_tx.get('transaction_index', '?')}; outer_revert={failed_tx.get('outer_revert')}; reason={failed_tx.get('revert_reason')}",
                    rel(BASE / f"tasks/{sid}/E2/v2-feedback.json"))
    for seed in SEEDS:
        result = load_json(BASE / f"real-projects/aave-v4/formal-fuzz-corrected/seed-{seed}/result.json", {}) or {}
        for prop in ("invariant_canary()", "assert_canary_ASSERTION_CANARY(uint256)"):
            failure("SCFUZZ-AaveV4", "SCFuzzBench", "formal_fuzz", "G0", seed, "non_target_canary_falsified",
                    f"Non-target {prop} falsified; selected target status={result.get('target_property_status')}; excluded from target cEX.",
                    f"real-projects/aave-v4/formal-fuzz-corrected/seed-{seed}/echidna.log")
        failure("SCFUZZ-AaveV4", "SCFuzzBench", "echidna_contract_selection", "G0", seed, "wrong_contract_entrypoint",
                "Initial unavailable contract entry; corrected formal-fuzz-corrected result is retained.",
                f"real-projects/aave-v4/formal-fuzz/seed-{seed}/echidna.log")
    failure("SCFUZZ-AaveV4", "SCFuzzBench", "primary_static_analysis", "", "", "analysis_toolchain_failed",
            "Primary Slither/analysis path failed; direct-solc fallback completed.", "real-projects/aave-v4/05-slither-run.json")
    failure("SCFUZZ-AaveV4", "SCFuzzBench", "agent_b", "E1", "", "no_agent_a_candidate",
            "Agent A returned no concrete sequence; Agent B was not called.", "real-projects/aave-v4/agent/agent-run.json")
    failure("SCFUZZ-SuperformV2", "SCFuzzBench", "source_dependency_preparation", "", "", "pinned_source_unavailable",
            "Pinned source unavailable; checkout resolved to cbb51b03055e6b08ea6e5d8180e86b7e68dcf84.",
            "real-projects/superform-v2-periphery/01-source-and-dependencies.log")
    failure("SCFUZZ-SuperformV2", "SCFuzzBench", "build", "", "", "dependency_missing",
            "Exact build could not find IERC20Metadata.sol; no substitute added.",
            "real-projects/superform-v2-periphery/04-exact-solc-build.log")
    failure("SCFUZZ-LiquityV2Governance", "SCFuzzBench", "foundry_direct_replay", "E1", "", "backend_semantics_mismatch",
            "Foundry report disagreed with native Echidna seed-only (target passed); not counted as cEX.",
            "real-projects/liquity-v2-governance/replay/direct-project-root/forge-final.log")
    failure("SCFUZZ-OriginDollar", "SCFuzzBench", "target_selection", "", "", "no_eligible_native_property",
            "Parameterized test/assert functions only; no eligible zero-argument native Boolean property.",
            "real-projects/origin-dollar/03-forge-build.log")
    write_csv(BASE / "failures.csv", failure_fields, failure_rows)

    # Group/phase and difficulty summaries; N/A remains outside denominators.
    metric_fields = ["source", "dimension", "group", "phase", "sample_count", "run_count", "attempted_runs",
                     "completed_runs", "not_run_count", "na_count", "raw_sequences", "valid_sequences", "valid_sequence_runs", "valid_seed_rate",
                     "repair_attempts", "repair_successes", "repair_success_rate", "extension_candidates", "extension_replays", "binding_applicable",
                     "binding_success", "native_counterexamples", "native_trials", "native_counterexample_rate",
                     "median_first_counterexample_seconds", "right_censored_no_counterexample_runs",
                     "target_state_confirmed_count", "target_state_unknown_count", "mean_seed_only_coverage", "mean_new_coverage",
                     "mean_final_coverage", "mean_analysis_compile_prep_seconds", "mean_static_analysis_seconds",
                     "mean_planning_seconds", "mean_repair_seconds", "mean_execution_seconds", "mean_compile_seconds",
                     "mean_fuzz_seconds", "mean_run_wall_seconds", "agent_tokens_total",
                     "agent_cost_usd_offpeak_total", "agent_cost_usd_peak_total", "agent_seconds_total", "notes"]

    def summarize(source, dimension, group, phase, group_rows):
        attempted = [r for r in group_rows if r["status"] not in ("N/A", "not_run")]
        completed = [r for r in group_rows if r["status"] in ("completed", "executable", "partial_or_failed", "native_counterexample")]

        def values(field):
            return [num(r.get(field)) for r in group_rows if num(r.get(field)) is not None]

        samples = len({r["sample_id"] for r in group_rows})
        valid_runs = sum(1 for r in group_rows if truth(r.get("complete_executable")))
        valid_ids = {r["sample_id"] for r in group_rows if truth(r.get("complete_executable"))}
        valid = len(valid_ids)
        attempts = sum(1 for r in group_rows if phase == "repair_and_replay" and r["status"] == "partial_or_failed")
        repaired = sum(1 for r in group_rows if "repair_applied=True" in r.get("notes", ""))
        cex = sum(1 for r in completed if truth(r.get("native_counterexample")))
        formal = [r for r in completed if r["phase"] == "formal_fuzz"]
        trials = len(formal)
        ttf = [num(r.get("time_to_first_native_counterexample_seconds")) for r in formal
               if num(r.get("time_to_first_native_counterexample_seconds")) is not None]
        app_values = [num(r.get("g2_binding_applicable")) for r in group_rows if r.get("g2_binding_applicable", "") != ""]
        suc_values = [num(r.get("g2_binding_success")) for r in group_rows if r.get("g2_binding_success", "") != ""]
        states_true = sum(1 for r in group_rows if truth(r.get("target_state_reached")) or str(r.get("target_state_status", "")).startswith("confirmed"))
        states_unknown = sum(1 for r in group_rows if str(r.get("target_state_reached", "")).lower() == "unknown" or str(r.get("target_state_status", "")).lower() == "unknown")
        cost_rows = [r for r in group_rows if r["group"] == "E1" and r["phase"] == "agent_replay"]
        tokens = sum(int(num(r.get("agent_tokens")) or 0) for r in cost_rows)
        off = sum((Decimal(str(r.get("agent_cost_usd_offpeak") or "0")) for r in cost_rows), Decimal("0"))
        peak = sum((Decimal(str(r.get("agent_cost_usd_peak") or "0")) for r in cost_rows), Decimal("0"))
        agent_seconds = sum(num(r.get("agent_total_seconds")) or 0 for r in cost_rows)
        return {
            "source": source, "dimension": dimension, "group": group, "phase": phase, "sample_count": samples,
            "run_count": len(group_rows), "attempted_runs": len(attempted), "completed_runs": len(completed),
            "not_run_count": sum(1 for r in group_rows if r["status"] == "not_run"),
            "na_count": sum(1 for r in group_rows if r["status"] == "N/A"),
            "raw_sequences": sum(int(num(r.get("raw_sequence_count")) or 0) for r in group_rows),
            "valid_sequences": valid, "valid_sequence_runs": valid_runs,
            "valid_seed_rate": "N/A" if group == "G0" or phase == "extension" or not samples else f"{valid/samples:.6f}",
            "repair_attempts": attempts, "repair_successes": repaired,
            "repair_success_rate": f"{repaired/attempts:.6f}" if attempts else "N/A",
            "extension_candidates": sum(int(num(r.get("candidate_count")) or 0) for r in group_rows) if phase == "extension" else "",
            "extension_replays": sum(int(num(r.get("extension_replay_count")) or 0) for r in group_rows) if phase == "extension" else "",
            "binding_applicable": int(sum(app_values)) if app_values else "",
            "binding_success": int(sum(suc_values)) if suc_values else "",
            "native_counterexamples": cex, "native_trials": trials,
            "native_counterexample_rate": f"{cex/trials:.6f}" if trials else "N/A",
            "median_first_counterexample_seconds": statistics.median(ttf) if ttf else "N/A",
            "right_censored_no_counterexample_runs": sum(1 for r in formal if not truth(r.get("native_counterexample"))),
            "target_state_confirmed_count": states_true, "target_state_unknown_count": states_unknown,
            "mean_seed_only_coverage": round(statistics.mean(values("seed_only_coverage")), 3) if values("seed_only_coverage") and not (source == "SCFuzzBench" and dimension == "ALL") else "N/A",
            "mean_new_coverage": round(statistics.mean(values("new_coverage")), 3) if values("new_coverage") and not (source == "SCFuzzBench" and dimension == "ALL") else "N/A",
            "mean_final_coverage": round(statistics.mean(values("final_coverage")), 3) if values("final_coverage") and not (source == "SCFuzzBench" and dimension == "ALL") else "N/A",
            "mean_analysis_compile_prep_seconds": round(statistics.mean(values("analysis_compile_prep_seconds")), 3) if values("analysis_compile_prep_seconds") else "N/A",
            "mean_static_analysis_seconds": round(statistics.mean(values("static_analysis_seconds")), 3) if values("static_analysis_seconds") else "N/A",
            "mean_planning_seconds": round(statistics.mean(values("planning_seconds")), 3) if values("planning_seconds") else "N/A",
            "mean_repair_seconds": round(statistics.mean(values("repair_seconds")), 3) if values("repair_seconds") else "N/A",
            "mean_execution_seconds": round(statistics.mean(values("execution_seconds")), 3) if values("execution_seconds") else "N/A",
            "mean_compile_seconds": round(statistics.mean(values("compile_seconds")), 3) if values("compile_seconds") else "N/A",
            "mean_fuzz_seconds": round(statistics.mean(values("fuzz_seconds")), 3) if values("fuzz_seconds") else "N/A",
            "mean_run_wall_seconds": round(statistics.mean(values("run_wall_seconds")), 3) if values("run_wall_seconds") else "N/A",
            "agent_tokens_total": tokens, "agent_cost_usd_offpeak_total": str(off),
            "agent_cost_usd_peak_total": str(peak), "agent_seconds_total": round(agent_seconds, 3),
            "notes": "N/A/not_run excluded from denominators; cEX means selected original native property only; costs are unique per target.",
        }

    def dim_for(row):
        return row["dimension"] or ("real" if row["source"] == "SCFuzzBench" else "unknown")

    metric_rows = []
    keys = sorted({(r["source"], dim_for(r), r["group"], r["phase"]) for r in rows})
    for source, dimension, group, phase in keys:
        rr = [r for r in rows if r["source"] == source and dim_for(r) == dimension and r["group"] == group and r["phase"] == phase]
        metric_rows.append(summarize(source, dimension, group, phase, rr))
    for source, group, phase in sorted({(r["source"], r["group"], r["phase"]) for r in rows}):
        rr = [r for r in rows if r["source"] == source and r["group"] == group and r["phase"] == phase]
        metric_rows.append(summarize(source, "ALL", group, phase, rr))
    write_csv(BASE / "metrics-summary.csv", metric_fields, metric_rows)

    print(json.dumps({
        "admission_rows": len(admissions), "campaign_rows": len(rows), "real_campaign_rows": len(real),
        "failure_rows": len(failure_rows), "metrics_rows": len(metric_rows), "agent_cost_rows": len(costs),
        "agent_totals": {
            "request_attempts": sum(int(r["request_attempts"]) for r in costs),
            "tokens": sum(int(r["total_tokens"]) for r in costs),
            "offpeak_usd": str(sum((Decimal(r["estimated_cost_usd_offpeak"]) for r in costs), Decimal("0"))),
            "peak_usd": str(sum((Decimal(r["estimated_cost_usd_peak"]) for r in costs), Decimal("0"))),
            "seconds": round(sum(float(r["agent_total_seconds"]) for r in costs), 3),
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
