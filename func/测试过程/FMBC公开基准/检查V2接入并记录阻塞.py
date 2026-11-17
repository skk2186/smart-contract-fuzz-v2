#!/usr/bin/env python3
"""静态核对冻结 V2 的 FMBC 接入条件，并把未运行原因逐任务落盘。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = ROOT / "func/测试过程/FMBC公开基准/结果/Phase23-20261117"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def version_output(path: Path, *args: str) -> str | None:
    if not path.is_file():
        return None
    try:
        result = subprocess.run([str(path), *args], capture_output=True, text=True,
                                timeout=10, check=False)
        return (result.stdout or result.stderr).strip()[:1000]
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"{type(exc).__name__}: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    manifest = json.loads((results_dir / "dataset-manifest.json").read_text(encoding="utf-8"))
    freeze = json.loads((results_dir / "selection-freeze.json").read_text(encoding="utf-8"))
    context_path = ROOT / "func/功能/属性种子上下文.py"
    pipeline_path = ROOT / "deepseek/实验过程/运行Agent种子流程.py"
    replay_path = ROOT / "func/功能/种子验证.py"
    context_source = context_path.read_text(encoding="utf-8")
    pipeline_source = pipeline_path.read_text(encoding="utf-8")
    replay_source = replay_path.read_text(encoding="utf-8")
    registered_projects = re.findall(r'^    "([^"\n]+)": \{', context_source, flags=re.MULTILINE)
    task_rows = [row for row in manifest["tasks"] if not row["is_template"]]
    executable_oracles = [row for row in task_rows
                          if row["oracle_status"] == "candidate_requires_runtime_validation"]
    registered_fmbc = any(name.lower() == "fmbc" for name in registered_projects)
    context_requires_registry = "if project not in PROJECTS" in context_source
    cli_requires_registry = 'choices=list(PROJECTS)' in pipeline_source
    replay_uses_echidna_targets = 'entry["name"].startswith("echidna_")' in replay_source
    replay_reads_fmbc_from_registry = 'PROJECTS[project]["artifact"]' in replay_source
    anvil_candidates = sorted((ROOT / ".tools/foundry/versions").rglob("anvil"))
    runtime_environment = {
        "python3": sys.version.split()[0],
        "echidna": version_output(ROOT / ".tools/olympia-echidna/echidna", "--version"),
        "anvil": version_output(anvil_candidates[-1], "--version") if anvil_candidates else None,
        "slither": version_output(ROOT / ".tools/olympia-venv/bin/slither", "--version"),
        "solc_default": version_output(ROOT / ".tools/olympia-venv/bin/solc", "--version"),
        "solc_select_installed_versions": version_output(
            ROOT / ".tools/olympia-venv/bin/solc-select", "versions"
        ),
        "additional_solc_0_8_26": version_output(ROOT / ".tools/olympia-solc/solc-v0.8.26", "--version"),
        "fuzzing_started": False,
    }
    compatibility = {
        "assessment": "static integration check; no API or fuzzing process started",
        "v2_projects_registered": registered_projects,
        "fmbc_registered": registered_fmbc,
        "project_context_requires_registered_name": context_requires_registry,
        "agent_cli_restricts_project_to_registry": cli_requires_registry,
        "replay_property_evaluator_requires_echidna_named_bool_entry": replay_uses_echidna_targets,
        "replay_loads_compiled_artifact_from_project_registry": replay_reads_fmbc_from_registry,
        "fmbc_tasks_with_direct_runtime_oracle": len(executable_oracles),
        "fmbc_arbitrary_source_end_to_end_ready": False,
        "blocking_reasons": [
            "FMBC 没有可直接部署、以 echidna_ 命名且返回 bool 的属性入口；其 SolCMC 文件依赖验证器 ghost/invariant 语义，Certora 文件也不是交易期 Oracle。",
            "V2 上下文加载和 Agent CLI 都把项目名限制在 PROJECTS 静态注册表；部署使用相应项目的固定 artifact/source_root。",
            "回放属性评估器只读取 echidna_ bool 函数；不能直接消费 FMBC 的 SolCMC/Certora 属性定义。",
            "因此无法在不增加通用 SolCMC 到交易期 Oracle 转换器及任意 FMBC 项目上下文加载器的情况下完成同 Oracle 的 G0/G2 配对。",
        ],
        "agent_algorithms_modified": False,
        "deepseek_api_calls": 0,
        "api_call_time_seconds": 0,
        "fuzzing_runs_started": 0,
        "selection_freeze_sha256_matches_manifest": freeze.get("manifest_sha256") == hashlib.sha256(
            (results_dir / "dataset-manifest.json").read_bytes()).hexdigest(),
        "selected_groups": len(freeze.get("selected_groups", [])),
        "evidence_files": [
            "func/功能/属性种子上下文.py",
            "deepseek/实验过程/运行Agent种子流程.py",
            "func/功能/种子验证.py",
        ],
        "runtime_environment": runtime_environment,
    }
    write_json(results_dir / "v2-compatibility.json", compatibility)
    write_json(results_dir / "runtime-environment.json", runtime_environment)

    status_path = results_dir / "G0-G2逐任务状态.csv"
    fields = [
        "task_id", "area", "scenario_id", "property_id", "version_id",
        "oracle_status", "G0_status", "G2_status", "fixed_seeds",
        "valid_transaction_rate", "target_state_reached", "property_violated",
        "coverage", "runtime_seconds", "deepseek_api_time_seconds", "reason",
    ]
    with status_path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in task_rows:
            writer.writerow({
                "task_id": row["task_id"],
                "area": row["area"],
                "scenario_id": row["scenario_id"],
                "property_id": row["property_id"],
                "version_id": row["version_id"],
                "oracle_status": row["oracle_status"],
                "G0_status": "not_run_unsupported_oracle",
                "G2_status": "not_run_unsupported_oracle",
                "fixed_seeds": json.dumps(freeze["fixed_seeds"]),
                "valid_transaction_rate": "",
                "target_state_reached": "not_observable",
                "property_violated": "not_observable",
                "coverage": "not_collected",
                "runtime_seconds": "",
                "deepseek_api_time_seconds": 0,
                "reason": row["oracle_reason"],
            })
    experiment_blocker = {
        "result": "blocked_before_fuzzing; not a negative or zero-coverage experiment",
        "selection_frozen": freeze["selection_frozen"],
        "selected_groups": len(freeze["selected_groups"]),
        "fuzzing_runs_started": 0,
        "G0_runs_started": 0,
        "G2_runs_started": 0,
        "DeepSeek_calls": 0,
        "reason": "全量数据集中不存在符合冻结规则的直接运行时属性 Oracle，且冻结 V2 不支持任意 FMBC 项目上下文和 SolCMC 属性片段。",
        "per_task_status_csv": status_path.name,
        "per_task_status_rows_excluding_templates": len(task_rows),
    }
    write_json(results_dir / "experiment-blocker.json", experiment_blocker)
    print(json.dumps({
        "compatibility": str(results_dir / "v2-compatibility.json"),
        "status_csv": str(status_path),
        "tasks_recorded_as_unsupported": len(task_rows),
        "selected_groups": compatibility["selected_groups"],
        "fuzzing_runs_started": experiment_blocker["fuzzing_runs_started"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
