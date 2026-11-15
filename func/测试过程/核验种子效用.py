#!/usr/bin/env python3
"""离线核验现有 EVM 种子的逐交易状态与 Echidna 纯语料覆盖。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

import 种子验证 as verifier
from 属性种子上下文 import load_project_context


def _view_changes(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    left, right = before.get("view_values", {}), after.get("view_values", {})
    return [{"getter": key, "before": left.get(key), "after": right.get(key)}
            for key in sorted(left.keys() | right.keys()) if left.get(key) != right.get(key)]


def _seeded_replay(project: str, prop: dict[str, Any], candidate: dict[str, Any],
                   context: dict[str, Any]) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []
    original_snapshot = verifier._state_view_snapshot

    def capture(*args: Any, **kwargs: Any) -> dict[str, Any]:
        snapshot = original_snapshot(*args, **kwargs)
        snapshots.append(snapshot)
        return snapshot

    verifier._state_view_snapshot = capture
    try:
        plan = {"candidate_id": candidate["candidate_id"],
                "property_id": prop["property_id"], "property": prop["property"],
                "steps": candidate["plan"], "context": context}
        replay = verifier.replay_seed(
            project, plan, candidate["concrete_seed"]["transactions"])
    finally:
        verifier._state_view_snapshot = original_snapshot
    if len(snapshots) != len(replay.get("transactions", [])) + 1:
        raise RuntimeError("状态快照数量与逐交易记录不一致")
    replay["view_changes_by_transaction"] = [
        _view_changes(snapshots[index], snapshots[index + 1])
        for index in range(len(snapshots) - 1)]
    replay["initial_to_final_view_changes"] = _view_changes(snapshots[0], snapshots[-1])
    return replay


def _seed_from_log(prop: dict[str, Any]) -> int:
    path = ROOT / prop["comparisons"]["same_test_budget"]["baseline"]["echidna_log_path"]
    found = re.search(r"^Seed: (\d+)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    if not found:
        raise ValueError(f"Echidna 日志没有随机种子：{path}")
    return int(found.group(1))


def _echidna_zero(project: str, property_name: str, root: Path,
                  random_seed: int, corpus: list[dict[str, Any]] | None,
                  seed_name: str | None) -> dict[str, Any]:
    if root.exists():
        raise FileExistsError(f"核验目录必须全新：{root}")
    coverage = root / "coverage"
    coverage.mkdir(parents=True)
    if corpus is not None:
        (coverage / seed_name).write_text(
            json.dumps(corpus, ensure_ascii=False), encoding="utf-8")
    result = verifier.run_echidna(
        project, root, property_name=property_name, test_limit=0, timeout=30,
        seed=random_seed, seq_len=8, shrink_limit=1, stop_on_fail=False,
        disable_slither=True)
    return {key: result.get(key) for key in (
        "status", "exit_code", "elapsed_seconds", "unique_instructions",
        "coverage_source", "loaded_seed_count", "replayed_sequence_count",
        "replayed_lines", "fuzzing_cases", "fuzzing_transactions",
        "target_property_results", "property_failures", "full_log_path")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="append", type=Path, required=True,
                        help="可重复指定含有效种子的原始逐属性对照 JSON")
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    if output_root.exists() and any(output_root.iterdir()):
        # 已有探针目录也必须与本次正式核验目录隔离。
        if (output_root / "种子效用核验.json").exists():
            parser.error("输出报告已经存在，请选择新目录")
    output_root.mkdir(parents=True, exist_ok=True)
    records = []
    seen: set[tuple[str, str]] = set()
    for report_path in args.report:
        report = json.loads(report_path.resolve().read_text(encoding="utf-8"))
        for prop in report.get("properties", []):
            key = (prop["project"], prop["property_id"])
            if not prop.get("evm_executable") or key in seen:
                continue
            seen.add(key)
            candidate = next(row for row in prop["seed_generation"]["candidate_results"]
                             if row.get("status") == "executable" and row.get("corpus_file"))
            corpus_path = ROOT / candidate["corpus_file"]
            corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
            context = load_project_context(prop["project"], [prop["property_id"]])
            replay = _seeded_replay(prop["project"], prop, candidate, context)
            property_name = prop["property"].rsplit(".", 1)[-1].split("(", 1)[0]
            random_seed = _seed_from_log(prop)
            destination = output_root / prop["project"] / prop["property_id"]
            native = _echidna_zero(prop["project"], property_name,
                                   destination / "native_zero", random_seed, None, None)
            prefixes = []
            for length in range(1, len(corpus) + 1):
                prefix_name = f"{candidate['seed_id']}-prefix-{length}.txt"
                run = _echidna_zero(
                    prop["project"], property_name, destination / f"prefix_{length}",
                    random_seed, corpus[:length], prefix_name)
                previous = native if length == 1 else prefixes[-1]["echidna"]
                prefixes.append({"transaction_count": length, "echidna": run,
                                 "coverage_over_empty": (
                                     run["unique_instructions"] - native["unique_instructions"]),
                                 "marginal_coverage_over_previous_prefix": (
                                     run["unique_instructions"] - previous["unique_instructions"])})
            records.append({"project": prop["project"], "property_id": prop["property_id"],
                            "property": prop["property"], "seed_id": candidate["seed_id"],
                            "seed_class": candidate["seed_class"],
                            "source_report": str(report_path.resolve().relative_to(ROOT)),
                            "source_corpus": str(corpus_path.relative_to(ROOT)),
                            "source_same_test_coverage_delta": prop["comparisons"][
                                "same_test_budget"]["coverage_delta_unique_instructions"],
                            "source_same_time_coverage_delta": prop["comparisons"][
                                "same_end_to_end_time"]["coverage_delta_unique_instructions"],
                            "anvil_replay": replay, "echidna_zero_native": native,
                            "echidna_zero_prefixes": prefixes})
            print(f"{prop['project']}/{prop['property_id']}: "
                  f"Anvil {replay['replay_status']}; "
                  f"zero-test coverage +{prefixes[-1]['coverage_over_empty']}", flush=True)
    output = output_root / "种子效用核验.json"
    output.write_text(json.dumps({"schema_version": 1, "api_calls": 0,
                                  "coverage_method": "Echidna test_limit=0, fresh isolated corpus, same target and random seed; each prefix replayed without fuzz cases",
                                  "records": records}, ensure_ascii=False, indent=2),
                      encoding="utf-8")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
