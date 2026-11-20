#!/usr/bin/env python3
"""One-time generic Phase36 corpusDir correction; does not alter the seed or gate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "func/功能"), str(ROOT / "deepseek"),
                str(ROOT / "func/测试过程/跨交易属性状态依赖审计"),
                str(ROOT / "func/测试过程/SCFuzzBench公开项目接入")]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计"
RUN_ROOT = BASE / "结果/Phase36-20261120"
FIRST = RUN_ROOT / "Echidna-seed-only/Wallet02Refund/G2/G2-seed-only-summary.json"
OUT = RUN_ROOT / "Echidna-seed-only/Wallet02Refund/G2-corpusDir-fix"


def _write(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if (OUT / "corpus-input/.echidna-run-started").exists():
        raise RuntimeError("修复后的 corpusDir 已运行过；禁止重复运行")
    first = json.loads(FIRST.read_text(encoding="utf-8"))
    raw = first["raw_run"]
    if raw.get("loaded_seed_count") != 0 or raw.get("replayed_sequence_count") != 0:
        raise RuntimeError("首轮缺少预期的零 seed 加载证据，停止路径修复")
    audit_path = BASE / "运行能力审计.py"
    spec = importlib.util.spec_from_file_location("phase36_echidna_fix_audit", audit_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载既有 Phase35 任务上下文")
    audit = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = audit
    spec.loader.exec_module(audit)
    contexts = None
    phase36_path = BASE / "Phase36自适应扩展.py"
    phase36_spec = importlib.util.spec_from_file_location("phase36_echidna_fix_context", phase36_path)
    if phase36_spec is None or phase36_spec.loader is None:
        raise RuntimeError("无法加载 Phase36 冻结任务上下文")
    phase36 = importlib.util.module_from_spec(phase36_spec)
    sys.modules[phase36_spec.name] = phase36
    phase36_spec.loader.exec_module(phase36)
    _, contexts = phase36._load_contexts()
    row = contexts["A_Wallet02Refund"]
    main_g2 = json.loads((RUN_ROOT / "Main/A_Wallet02Refund/G2/G2-自适应E3.json").read_text(encoding="utf-8"))
    target = main_g2.get("target_candidate")
    if not target:
        raise RuntimeError("冻结 G2 没有 Wallet counterexample，不能执行 Echidna 确认")
    replay, sequence = target["replay"], target["sequence"]
    if hashlib.sha256(json.dumps(sequence, ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode()).hexdigest() != first["sequence_sha256"]:
        raise RuntimeError("修复前后的 Wallet seed 序列不一致")

    from 属性种子上下文 import PROJECTS
    from 种子验证 import new_seed_id, run_echidna, write_corpus
    project, context, prop, candidate = row["project"], row["context"], row["prop"], row["candidate"]
    corpus_dir = OUT / "corpus-input"
    seed_path = write_corpus(project, candidate, replay.get("resolved_transactions") or sequence,
        context, corpus_dir, replay=replay, seed_id=new_seed_id())
    property_name = str(prop.get("property_abi") or prop.get("property", "")).split("(", 1)[0].rsplit(".", 1)[-1]
    action_sigs = [item.get("abi_signature") for item in prop.get("candidate_actions", [])
        if item.get("seed_compatible") and item.get("abi_signature")]
    filters = [f"{PROJECTS[project]['contract']}.{sig}" for sig in action_sigs]
    filters.append(f"{PROJECTS[project]['contract']}.{property_name}()")
    source_root = Path(PROJECTS[project]["source_root"])
    working = source_root if source_root.is_absolute() else ROOT / source_root
    # Generic fix established in Phase35: corpusDir must be the directory containing
    # the seed's `coverage/` subtree. The first failed attempt remains untouched.
    run = run_echidna(project, corpus_dir, property_name=property_name,
        test_limit=0, timeout=180, seed=20261125, test_mode="property",
        property_prefix=property_name, filter_functions=filters, seq_len=8,
        shrink_limit=1, stop_on_fail=False, disable_slither=True,
        sender_pool=context.get("sender_pool"), working_directory=working)
    ok = bool(run.get("loaded_seed_count") == 1 and run.get("replayed_sequence_count") == 1 and
              run.get("replay_evidence") and run.get("property_failure_reported"))
    result = {"schema_version": 1, "status": "seed_replayed_property_violation" if ok else "unverified_after_one_generic_fix",
        "first_attempt": {"path": str(FIRST.relative_to(ROOT)),
            "loaded_seed_count": raw.get("loaded_seed_count"),
            "replayed_sequence_count": raw.get("replayed_sequence_count"),
            "property_failure_reported": raw.get("property_failure_reported"),
            "full_log_path": raw.get("full_log_path"),
            "classification": "invalid_seed_only_run: command exited zero but loaded/replayed no seed"},
        "repair": {"kind": "generic corpusDir path correction", "based_on": "Phase35 14-Echidna路径修复后seed-only汇总.json",
            "changed_algorithm_or_seed": False,
            "corpus_dir_passed_to_run_echidna": str(corpus_dir.relative_to(ROOT))},
        "group": "G2", "candidate_no": target.get("candidate_no"),
        "sequence": sequence, "sequence_sha256": first["sequence_sha256"],
        "seed_path": str(seed_path.relative_to(ROOT)), "test_limit": 0,
        "loaded_seed_count": run.get("loaded_seed_count"),
        "replayed_sequence_count": run.get("replayed_sequence_count"),
        "replay_evidence": run.get("replay_evidence"),
        "replayed_lines": run.get("replayed_lines"),
        "anvil_property_violation": replay.get("target_property_violation"),
        "echidna_property_failure": run.get("property_failure_reported"),
        "target_property_results": run.get("target_property_results"),
        "elapsed_seconds": run.get("elapsed_seconds"), "exit_code": run.get("exit_code"),
        "full_log_path": run.get("full_log_path"), "raw_run": run}
    _write(OUT / "G2-seed-only-summary.json", result)
    fix_record = {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
        "original_freeze_sha256": _sha(RUN_ROOT / "00-Phase36冻结.json"),
        "fix_script_sha256": _sha(Path(__file__)),
        "first_attempt_raw_sha256": _sha(FIRST), "corrected_run_sha256": _sha(OUT / "G2-seed-only-summary.json"),
        "result_status": result["status"], "attempts_after_fix": 1}
    _write(RUN_ROOT / "Echidna-语料目录修复记录.json", fix_record)
    print(json.dumps({"status": result["status"], "loaded": result["loaded_seed_count"],
        "replayed": result["replayed_sequence_count"],
        "property_failure": result["echidna_property_failure"],
        "result": str((OUT / "G2-seed-only-summary.json").relative_to(ROOT))}, ensure_ascii=False))


if __name__ == "__main__":
    main()
