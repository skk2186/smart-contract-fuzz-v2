#!/usr/bin/env python3
"""按固定项目 manifest 完成真实合约统一执行准入与阶段日志保存。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "func/功能"))

import 真实合约统一执行适配器 as adapter  # noqa: E402


ALLOWED_STATUSES = {
    "ready", "ready_with_verified_adapter", "unsupported_semantics",
    "dependency_blocked", "execution_failed", "unknown",
}


def _relative(path: str | Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def _build(manifest: dict[str, Any], workspace: Path, output: Path,
           env: dict[str, str], forge: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    build_out = output / "build-out"
    build_cache = output / "build-cache"
    command = [forge, "build", "--root", str(workspace), "--offline", "--force",
               "--out", str(build_out), "--cache-path", str(build_cache)]
    log = output / "02-forge-build.log"
    try:
        completed = adapter._run(command, workspace, env, timeout=900, log_path=log)
        artifact_relative = Path(manifest["build"].get("artifact", ""))
        if artifact_relative.parts and artifact_relative.parts[0] == "out":
            artifact_relative = Path(*artifact_relative.parts[1:])
        artifact = build_out / artifact_relative if artifact_relative.parts else None
        passed = completed.returncode == 0 and artifact is not None and artifact.is_file()
        result = {
            "status": "passed" if passed else "execution_failed",
            "command": command,
            "returncode": completed.returncode,
            "log": _relative(log),
            "artifact": _relative(artifact) if artifact else None,
            "artifact_sha256": adapter.sha256_file(artifact) if artifact and artifact.is_file() else None,
            "error": None if passed else completed.stdout[-3000:],
        }
    except Exception as exc:
        result = {"status": "execution_failed", "command": command,
                  "log": _relative(log), "error": "%s: %s" % (type(exc).__name__, exc)}
    adapter.write_json(output / "02-forge-build.json", result)
    return result


def _semantic_checks(manifest: dict[str, Any], sequence: dict[str, Any],
                     feedback: dict[str, Any], echidna: dict[str, Any] | None) -> dict[str, Any]:
    txs = feedback.get("transactions", [])
    expected_txs = sequence.get("transactions", [])
    checks: list[dict[str, Any]] = []
    checks.append({
        "kind": "transaction_count",
        "expected": len(expected_txs),
        "actual": len(txs),
        "passed": len(txs) == len(expected_txs),
    })
    sender_ok = len(txs) == len(expected_txs) and all(
        str(actual.get("sender", "")).lower() == str(expected.get("sender", "")).lower()
        for actual, expected in zip(txs, expected_txs)
    )
    checks.append({"kind": "sender_preservation", "passed": sender_ok,
                   "senders": [row.get("sender") for row in txs]})
    checks.append({"kind": "transaction_success", "passed": bool(txs) and all(
        row.get("status") == "success" for row in txs)})
    checks.append({"kind": "configured_properties_foundry", "passed": bool(feedback.get(
        "property_checks_passed"))})

    for expectation in manifest.get("semantic_checks", []):
        kind = expectation.get("kind")
        index = int(expectation.get("transaction_index", 0)) - 1
        row = txs[index] if 0 <= index < len(txs) else None
        if kind == "timestamp_delta" and row:
            actual = row.get("timestamp_after") - row.get("timestamp_at_call")
            expected = int(expectation["expected_delta_seconds"])
            checks.append({**expectation, "actual_delta_seconds": actual, "passed": actual == expected})
        elif kind == "state_increase" and row:
            before = next((item.get("value") for item in row.get("observations_before", [])
                           if item.get("name") == expectation["observer"] and item.get("success")), None)
            after = next((item.get("value") for item in row.get("observations_after", [])
                          if item.get("name") == expectation["observer"] and item.get("success")), None)
            try:
                old, new = int(before), int(after)
                passed = new > old
            except (TypeError, ValueError):
                old, new, passed = before, after, False
            checks.append({**expectation, "before": old, "after": new, "passed": passed})
        else:
            checks.append({**expectation, "passed": False,
                           "error": "unknown semantic check kind or missing transaction/observer"})

    native_required = manifest.get("native_assertions", [])
    native_properties = {row.get("name"): row.get("status")
                         for row in (echidna or {}).get("properties", [])}
    for signature in native_required:
        checks.append({"kind": "native_assertion", "signature": signature,
                       "status": native_properties.get(signature),
                       "passed": native_properties.get(signature) == "passing"})
    native_replay_ok = bool(echidna and echidna.get("status") == "passed"
                            and echidna.get("seed_replay_observed")
                            and echidna.get("loaded_sequences", 0) >= 1
                            and not echidna.get("property_failure_observed"))
    checks.append({"kind": "native_fixed_sequence_replay", "passed": native_replay_ok,
                   "loaded_sequences": (echidna or {}).get("loaded_sequences"),
                   "seed_replay_observed": (echidna or {}).get("seed_replay_observed")})
    return {"status": "passed" if checks and all(row.get("passed") for row in checks) else "failed",
            "checks": checks,
            "e2_feedback": "transaction arguments, sender, value, outcome, revert bytes, and configured state observations are present",
            "e3_feedback": "generic per-step getter deltas and per-step property results are present; predicate-specific getter mapping remains manifest-dependent",
            "e3_predicate_getter_trajectory_complete": any(
                observer.get("semantic_role") == "target_property_operand"
                for observer in manifest.get("observers", []))}


def _cleanup_generated(output: Path, keep: bool) -> list[str]:
    if keep:
        return []
    root = output.resolve()
    removed = []
    for name in ("out", "cache", "build-out", "build-cache", "tool-shim"):
        target = (root / name).resolve()
        if root in target.parents and target.is_dir():
            shutil.rmtree(target)
            removed.append(_relative(target))
    for path in root.rglob("covered.*"):
        if path.is_file() and root in path.resolve().parents:
            path.unlink()
            removed.append(_relative(path))
    return removed


def run(manifest_path: Path, output: Path, retry_failed_archives: bool,
        keep_build_artifacts: bool, retry_missing_submodules: bool = False) -> dict[str, Any]:
    manifest_path = manifest_path if manifest_path.is_absolute() else ROOT / manifest_path
    output = output if output.is_absolute() else ROOT / output
    manifest_path, output = manifest_path.resolve(), output.resolve()
    manifest = adapter.read_json(manifest_path)
    output.mkdir(parents=True, exist_ok=True)
    result: dict[str, Any] = {
        "schema_version": 1,
        "phase": "40",
        "project_id": manifest["project"]["id"],
        "manifest": _relative(manifest_path),
        "source_commit": manifest["project"]["commit"],
        "source_tree_sha256_expected": manifest["project"].get("source_tree_sha256"),
        "status": "unknown",
        "stages": {},
        "sequences": [],
    }
    prep = adapter.prepare_project(manifest_path, output,
                                   retry_failed_archives=retry_failed_archives,
                                   retry_missing_submodules=retry_missing_submodules)
    result["stages"]["source_and_dependencies"] = prep
    if prep.get("status") != "ready":
        result["status"] = prep.get("status") if prep.get("status") in ALLOWED_STATUSES else "unknown"
        result["reason"] = "source/dependency preparation did not complete"
        adapter.write_json(output / "admission-result.json", result)
        result["cleanup"] = _cleanup_generated(output, keep_build_artifacts)
        adapter.write_json(output / "admission-result.json", result)
        return result

    env, tools = adapter.tool_environment(manifest, output)
    result["tools"] = tools
    workspace = Path(prep["cache"]["workspace"])
    build = _build(manifest, workspace, output, env, tools["forge"])
    result["stages"]["forge_build"] = build
    if build.get("status") != "passed":
        result["status"] = "execution_failed"
        result["reason"] = "offline Forge build failed or the configured artifact was not produced"
    else:
        sequence_results = []
        foundry = adapter.FoundryCheatcodeBackend(manifest, workspace, output, env, tools["forge"])
        for sequence in manifest.get("sequences", []):
            request = adapter.execution_request(sequence)
            raw = foundry.execute_sequence(request)
            feedback = foundry.to_v2_feedback(raw)
            adapter.write_json(output / (sequence["id"] + ".v2-feedback.json"), feedback)
            row: dict[str, Any] = {"sequence_id": sequence["id"],
                                   "foundry": raw, "v2_feedback": feedback}
            deployment = feedback.get("deployment", {}).get("target_address")
            native = None
            if raw.get("status") == "passed" and deployment:
                native = adapter.run_echidna_sequence(manifest, workspace, sequence,
                                                       deployment, output, env, tools["echidna"])
            row["echidna_native"] = native
            row["semantic_validation"] = _semantic_checks(manifest, sequence, feedback, native)
            if raw.get("status") == "unsupported_semantics":
                row["status"] = "unsupported_semantics"
            elif raw.get("status") != "passed":
                row["status"] = "execution_failed"
            elif native is None:
                row["status"] = "unknown"
            elif any(check.get("passed") is False and check.get("kind") == "sender_preservation"
                     for check in row["semantic_validation"]["checks"]):
                row["status"] = "unsupported_semantics"
            elif row["semantic_validation"]["status"] != "passed":
                row["status"] = "execution_failed"
            else:
                row["status"] = "ready_with_verified_adapter"
            sequence_results.append(row)
        result["sequences"] = sequence_results
        if not sequence_results:
            result["status"] = "unknown"
            result["reason"] = "manifest contains no replayable sequence"
        elif all(row["status"] == "ready_with_verified_adapter" for row in sequence_results):
            result["status"] = "ready_with_verified_adapter"
            result["reason"] = "fixed source, offline build, cheatcode execution, native replay, configured state, and property checks passed"
        elif any(row["status"] == "unsupported_semantics" for row in sequence_results):
            result["status"] = "unsupported_semantics"
        elif any(row["status"] == "execution_failed" for row in sequence_results):
            result["status"] = "execution_failed"
        else:
            result["status"] = "unknown"
    if result["status"] not in ALLOWED_STATUSES:
        result["status"] = "unknown"
    adapter.write_json(output / "admission-result.json", result)
    result["cleanup"] = _cleanup_generated(output, keep_build_artifacts)
    adapter.write_json(output / "admission-result.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--retry-failed-archives", action="store_true",
                        help="Explicitly retry previously failed immutable package archives.")
    parser.add_argument("--retry-missing-submodules", action="store_true",
                        help="Explicitly retry previously failed pinned gitlink restoration.")
    parser.add_argument("--keep-build-artifacts", action="store_true")
    args = parser.parse_args()
    result = run(args.manifest, args.output, args.retry_failed_archives,
                 args.keep_build_artifacts, args.retry_missing_submodules)
    print(json.dumps({"project_id": result.get("project_id"), "status": result.get("status"),
                      "result": _relative(args.output / "admission-result.json")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
