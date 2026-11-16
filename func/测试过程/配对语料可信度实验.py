#!/usr/bin/env python3
"""用相同 Echidna 配置配对运行空语料与既有 V2 种子。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from 属性种子上下文 import load_project_context
from 种子验证 import AnvilSession, INITIAL_BALANCE, replay_seed, run_echidna


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_input(sample: dict[str, Any]) -> dict[str, Any]:
    result_path = ROOT / sample["agent_result"]
    result = _load_json(result_path)
    property_row = next(row for row in result["property_results"]
                        if row["property_id"] == sample["property_id"])
    candidate_row = next(row for row in property_row.get("candidate_results", [])
                         if row.get("seed_id") == sample["seed_id"])
    if candidate_row.get("status") != "executable":
        raise ValueError(f"登记种子当前不是 Anvil executable：{sample['seed_id']}")
    seed_path = ROOT / candidate_row["corpus_file"]
    if not seed_path.is_file():
        raise FileNotFoundError(f"登记种子语料不存在：{seed_path}")
    context = load_project_context(sample["project"], [sample["property_id"]])
    prop_context = context["properties"][0]
    replay_candidate = dict(candidate_row.get("concrete_seed") or {})
    replay_candidate["candidate_id"] = candidate_row["candidate_id"]
    replay_candidate["property_id"] = sample["property_id"]
    replay_candidate["property"] = prop_context.get("property_abi", "")
    replay_candidate["context"] = context
    return {"property_row": property_row, "candidate_row": candidate_row,
            "seed_path": seed_path, "context": context,
            "property_name": prop_context["property_abi"].split("(", 1)[0],
            "sender_pool": list(property_row.get("sender_pool") or []),
            "replay_candidate": replay_candidate}


def _config_artifacts(arm_root: Path, project: str, corpus_name: str) -> tuple[str, str]:
    yaml_path = arm_root / f"{project}-{corpus_name}-echidna.yaml"
    compiler_path = arm_root / f"{project}-{corpus_name}-crytic-compile.json"
    return (yaml_path.read_text(encoding="utf-8"),
            compiler_path.read_text(encoding="utf-8"))


def _without_corpus_path(yaml_text: str) -> str:
    return "\n".join(line for line in yaml_text.splitlines()
                      if not line.startswith("corpusDir:"))


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _run_arm(project: str, property_name: str, sender_pool: list[str],
             corpus_root: Path, *, seed: int, config: dict[str, Any]) -> dict[str, Any]:
    return run_echidna(
        project, corpus_root, property_name=property_name,
        test_limit=int(config["test_limit"]), timeout=int(config.get("timeout_seconds", 45)),
        seed=seed, test_mode="property", seq_len=int(config["seq_len"]),
        shrink_limit=int(config["shrink_limit"]), stop_on_fail=False,
        disable_slither=True, sender_pool=sender_pool)


def run(manifest_path: Path, output_root: Path, *, anvil_only: bool = False) -> dict[str, Any]:
    manifest = _load_json(manifest_path)
    if output_root.exists():
        raise FileExistsError(f"拒绝覆盖已有实验目录：{output_root}")
    output_root.mkdir(parents=True)
    config = manifest["paired_echidna_configuration"]
    result: dict[str, Any] = {"phase": manifest["phase"],
                              "manifest": str(manifest_path.relative_to(ROOT)),
                              "configuration": config,
                              "samples": []}
    result_path = output_root / "配对运行结果.json"

    def save() -> None:
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    for sample in manifest["samples"]:
        loaded = _sample_input(sample)
        sample_result: dict[str, Any] = {
            "project": sample["project"],
            "property_id": sample["property_id"],
            "property": loaded["property_name"],
            "seed_id": sample["seed_id"],
            "seed_file": str(loaded["seed_path"].relative_to(ROOT)),
            "sender_pool": loaded["sender_pool"],
            "anvil_recheck": None,
            "pairs": []}
        result["samples"].append(sample_result)
        save()

        try:
            with AnvilSession() as session:
                for address in sample_result["sender_pool"]:
                    session.rpc("anvil_setBalance", [address, hex(INITIAL_BALANCE)])
                replay = replay_seed(sample["project"], loaded["replay_candidate"],
                                     loaded["candidate_row"]["concrete_seed"]["transactions"],
                                     session=session)
                sample_result["anvil_recheck"] = replay
        except Exception as exc:
            sample_result["anvil_recheck_error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        save()
        if anvil_only:
            continue

        for echidna_seed in config["repeat_echidna_seeds"]:
            pair_root = output_root / sample["project"] / sample["property_id"] / str(echidna_seed)
            native_root = pair_root / "native" / "corpus"
            v2_root = pair_root / "v2" / "corpus"
            native_root.mkdir(parents=True)
            (v2_root / "coverage").mkdir(parents=True)
            shutil.copy2(loaded["seed_path"], v2_root / "coverage" /
                         f"{sample['seed_id']}.txt")
            pair: dict[str, Any] = {"echidna_seed": echidna_seed,
                                    "native": None, "v2": None,
                                    "config_equal_except_corpus_dir": None,
                                    "errors": []}
            sample_result["pairs"].append(pair)
            save()
            try:
                pair["native"] = _run_arm(sample["project"], loaded["property_name"],
                                           loaded["sender_pool"], native_root,
                                           seed=echidna_seed, config=config)
            except Exception as exc:
                pair["errors"].append({"arm": "native", "error":
                                       f"{type(exc).__name__}: {str(exc)[:500]}"})
            save()
            try:
                pair["v2"] = _run_arm(sample["project"], loaded["property_name"],
                                       loaded["sender_pool"], v2_root,
                                       seed=echidna_seed, config=config)
            except Exception as exc:
                pair["errors"].append({"arm": "v2", "error":
                                       f"{type(exc).__name__}: {str(exc)[:500]}"})
            save()
            if pair["native"] is not None and pair["v2"] is not None:
                native_yaml, native_compiler = _config_artifacts(
                    native_root.parent, sample["project"], native_root.name)
                v2_yaml, v2_compiler = _config_artifacts(
                    v2_root.parent, sample["project"], v2_root.name)
                pair["config_equal_except_corpus_dir"] = (
                    _without_corpus_path(native_yaml) == _without_corpus_path(v2_yaml) and
                    json.loads(native_compiler) == json.loads(v2_compiler))
            save()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "deepseek/结果/Phase21目标状态配对/实验方案.json")
    parser.add_argument("--run-id", default="repeat-1")
    parser.add_argument("--anvil-only", action="store_true",
                        help="仅重放已登记的有效种子，刷新属性状态与 getter 证据，不运行 Echidna campaign")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    output_root = ROOT / "deepseek/结果/Phase21目标状态配对" / args.run_id
    if not _is_under(manifest_path, ROOT) or not _is_under(output_root, ROOT):
        parser.error("manifest 与实验输出必须位于本仓库内")
    result = run(manifest_path, output_root, anvil_only=args.anvil_only)
    summary = []
    for row in result["samples"]:
        replay = row.get("anvil_recheck") or {}
        target = replay.get("target_property_state") or {}
        summary.append({"project": row["project"], "property": row["property"],
                        "anvil_status": replay.get("replay_status"),
                        "target_state": target.get("status"),
                        "target_property_state_established": target.get(
                            "target_property_state_established"),
                        "counterexample_state_established": target.get(
                            "counterexample_state_established"),
                        "property_related_state_changed": target.get(
                            "property_related_state_changed"),
                        "first_established_transaction_index": target.get(
                            "first_established_transaction_index"),
                        "trajectory": [{"transaction_index": step.get("transaction_index"),
                                        "property_value": step.get("value"),
                                        "changed_predicate_getters": step.get(
                                            "changed_predicate_getters", [])}
                                       for step in target.get("trajectory", [])],
                        "pairs": len(row["pairs"]),
                        "pair_config_checks": [pair.get("config_equal_except_corpus_dir")
                                               for pair in row["pairs"]]})
    (output_root / "目标状态汇总.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"run_id": args.run_id, "samples": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
