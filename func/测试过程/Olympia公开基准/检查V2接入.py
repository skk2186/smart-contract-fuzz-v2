#!/usr/bin/env python3
"""不调用模型 API，检查 V2 当前参数编码器和项目注册表能否接入 Olympia。"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = ROOT / "func/测试过程/Olympia公开基准/结果/ASE2024-20261116"
DEFAULT_DATASET = ROOT / "sol/单合约测试/OlympiaASE2024"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run-id", default="native-echidna-60s")
    args = parser.parse_args()
    results = args.results_dir.resolve()
    dataset = args.dataset_dir.resolve()
    if args.run_id in {"", ".", ".."} or "/" in args.run_id or "\\" in args.run_id:
        parser.error("run-id 必须是单个目录名")
    baseline = results / args.run_id / "原生基线汇总.json"
    if not baseline.is_file():
        parser.error("先完成原生 Echidna 基线，再执行此 V2 接入检查")
    plan = json.loads((results / "实验方案.json").read_text(encoding="utf-8"))
    if not plan.get("samples"):
        parser.error("找不到已归档的 Olympia 样本清单")

    sys.path.insert(0, str(ROOT / "deepseek"))
    sys.path.insert(0, str(ROOT / "func/功能"))
    sys.path.insert(0, str(ROOT / ".tools/python"))
    from AgentB import normalize_argument
    from 属性种子上下文 import PROJECTS

    accepted_scalar = normalize_argument("int8", -1)
    try:
        normalize_argument("int8[]", [-1])
        dynamic_array_supported = True
        dynamic_array_error = None
    except (TypeError, ValueError) as exc:
        dynamic_array_supported = False
        dynamic_array_error = f"{type(exc).__name__}: {exc}"

    sample_rows = []
    for sample in plan["samples"]:
        source = dataset / sample["split"] / sample["sample_id"] / sample["source"]
        content = source.read_text(encoding="utf-8")
        step_signatures = sorted(set(re.findall(
            r"\bfunction\s+step\s*\(\s*(int8\[\])\s+(?:memory|calldata)\s+\w+\s*\)",
            content,
        )))
        sample_rows.append({
            "sample_id": sample["sample_id"],
            "split": sample["split"],
            "target_property": "echidna_noBug",
            "transaction_signatures": [f"step({value})" for value in step_signatures],
            "has_dynamic_int8_array_entrypoint": "int8[]" in step_signatures,
        })

    has_expected_entry = len(sample_rows) == 12 and all(
        row["has_dynamic_int8_array_entrypoint"] for row in sample_rows
    )
    registered_project = "Olympia" in PROJECTS
    report = {
        "check_type": "offline static integration check; no model/API invocation",
        "baseline_completed_first": True,
        "samples": len(sample_rows),
        "all_samples_share_echidna_no_bug_target": all(
            row["target_property"] == "echidna_noBug" for row in sample_rows
        ),
        "all_samples_expose_step_int8_array": has_expected_entry,
        "agent_b_scalar_int8_supported": accepted_scalar == -1,
        "agent_b_dynamic_int8_array_supported": dynamic_array_supported,
        "agent_b_dynamic_array_error": dynamic_array_error,
        "olympia_registered_in_v2_context_projects": registered_project,
        "v2_context_registered_projects": sorted(PROJECTS),
        "v2_end_to_end_ready": False,
        "blocking_reason": [
            "Olympia step(int8[]) 的动态数组参数不在 Agent B 当前 ABI 参数编码器支持的类型中。",
            "V2 属性上下文的 PROJECTS 注册表仅配置既有真实项目，没有 Olympia 任意源码入口。",
            "因此无法在不修改 V2 接入/编码逻辑的情况下生成可供同一 Echidna 预算回放的 V2 语料。",
        ],
        "agent_algorithms_modified": False,
        "known_solution_provided_to_agent": False,
        "api_called": False,
        "sample_checks": sample_rows,
    }
    output = results / "v2-compatibility.json"
    write_json(output, report)
    print(json.dumps({
        "samples": len(sample_rows),
        "dynamic_int8_array_supported": dynamic_array_supported,
        "registered_project": registered_project,
        "v2_end_to_end_ready": report["v2_end_to_end_ready"],
        "report": str(output),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
