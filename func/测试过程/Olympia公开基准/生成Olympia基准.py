#!/usr/bin/env python3
"""用固定版本的 Olympia 官方 wrapper 生成并归档不含解答的基准样本。"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
EXPECTED_OLYMPIA_COMMIT = "325b910388416750d3485c7b588aba4411971c2d"
DEFAULT_GENERATOR = ROOT / ".tools/olympia-upstream"
DEFAULT_DATASET = ROOT / "sol/单合约测试/OlympiaASE2024"
DEFAULT_RESULTS = ROOT / "func/测试过程/Olympia公开基准/结果/ASE2024-20261116"
DEFAULT_GENERATOR_OUTPUT = ROOT / ".tools/olympia-generated-ase2024-20261116"
DEFAULT_WORK_DIR = ROOT / ".tools/olympia-work-ase2024-20261116"
DIMENSIONS = [5, 10, 15, 20]
INSTANCES_PER_DIMENSION = 3
ALGORITHMS = ["Backtracking", "Kruskal", "Prims", "Wilsons", "Sidewinder"]
EQUALITY_PERCENTAGES = [25, 50]
CYCLE_PERCENTAGES = [0, 25, 50, 75, 100]
GENERATION_METHODS = ["default", "equality"]
GLOBAL_SEED = 20261116


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def package_version(distribution: str) -> str | None:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return None


def remove_staging_directory(path: Path) -> None:
    tools_root = (ROOT / ".tools").resolve()
    resolved = path.resolve()
    if resolved == tools_root or not resolved.is_relative_to(tools_root):
        raise ValueError(f"暂存目录必须是 .tools 下的独立子目录：{resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def official_wrapper_args(output: Path) -> list[str]:
    return [
        "-o", str(output),
        "-d", *[str(value) for value in DIMENSIONS],
        "-i", str(INSTANCES_PER_DIMENSION),
        "-s", str(GLOBAL_SEED),
        "-a", *ALGORITHMS,
        "-m", *GENERATION_METHODS,
        "-e", *[str(value) for value in EQUALITY_PERCENTAGES],
        "-c", *[str(value) for value in CYCLE_PERCENTAGES],
        "--disable-reachability-check",
    ]


def run_official_wrapper(generator: Path, output: Path, work: Path) -> float:
    wrapper = generator / "olympia/olympia_wrapper.py"
    if not wrapper.is_file():
        raise FileNotFoundError(f"找不到官方 wrapper：{wrapper}")

    # 当前主分支的 wrapper 在 --disable-reachability-check 时仍会导入
    # Web3/solcx。此占位模块只让被禁用的检查保持未调用，不改生成器逻辑。
    sys.path.insert(0, str((generator / "olympia").resolve()))
    disabled_check = ModuleType("utils.reachability_test")

    def forbidden_reachability_check(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("reachability check 已禁用，不应被调用")

    disabled_check.run_test = forbidden_reachability_check  # type: ignore[attr-defined]
    sys.modules["utils.reachability_test"] = disabled_check

    # official scripts/generate.sh 调用 PATH 上的 python3；固定到同一 venv。
    os.environ["PATH"] = str(Path(sys.prefix) / "bin") + os.pathsep + os.environ["PATH"]
    os.chdir(work)
    sys.argv = [str(wrapper), *official_wrapper_args(output)]
    started = time.perf_counter()
    try:
        runpy.run_path(str(wrapper), run_name="__main__")
    except SystemExit as exc:
        if exc.code not in (None, 0):
            raise RuntimeError(f"Olympia wrapper 退出码：{exc.code}") from exc
    return time.perf_counter() - started


def parse_generation_seeds(reproduction: Path) -> list[tuple[int, int]]:
    content = reproduction.read_text(encoding="utf-8")
    records = re.findall(
        r"(?m)^# generation command: .*?--dimension\s+(\d+)\s+--seed\s+(\d+)\s*$",
        content,
    )
    return [(int(dimension), int(seed)) for dimension, seed in records]


def parse_program_entry(line: str) -> dict[str, Any]:
    parts = line.split(",")
    if len(parts) != 7:
        raise ValueError(f"非预期的 Olympia programs.list 行：{line!r}")
    algorithm, width, height, maze_seed, program_count, cycles, method = parts
    if width != height:
        raise ValueError(f"本基准只接收正方形迷宫：{line!r}")
    equality = re.fullmatch(r"equality(\d+)_gen", method)
    if method != "default_gen" and equality is None:
        raise ValueError(f"本基准不接收 CVE 或未知生成方法：{method}")
    return {
        "algorithm": algorithm,
        "width": int(width),
        "height": int(height),
        "dimension": int(width),
        "maze_seed": int(maze_seed),
        "program_count": int(program_count),
        "cycle_percent": int(cycles.removesuffix("percent")),
        "generation_method": "equality" if equality else "default",
        "equality_percent": int(equality.group(1)) if equality else None,
        "method_entry": method,
    }


def collect_outputs(output: Path, dataset: Path, results: Path,
                    generation_seconds: float) -> dict[str, Any]:
    programs = output / "programs.list"
    reproduction = output / "reproducible_generation.sh"
    if not programs.is_file() or not reproduction.is_file():
        raise FileNotFoundError("Olympia 未生成 programs.list 或 reproducible_generation.sh")
    entries = [line.strip() for line in programs.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    seeds = parse_generation_seeds(reproduction)
    expected_count = len(DIMENSIONS) * INSTANCES_PER_DIMENSION
    if len(entries) != expected_count or len(seeds) != expected_count:
        raise ValueError(
            f"样本数不匹配：programs.list={len(entries)}，生成命令={len(seeds)}，"
            f"预期={expected_count}"
        )

    dataset.mkdir(parents=True, exist_ok=False)
    seen_by_dimension: dict[int, int] = {}
    samples: list[dict[str, Any]] = []
    for ordinal, (entry, (seed_dimension, instance_seed)) in enumerate(zip(entries, seeds), 1):
        parameters = parse_program_entry(entry)
        dimension = parameters["dimension"]
        if seed_dimension != dimension:
            raise ValueError(f"wrapper 种子维度与 programs.list 不匹配：{entry}")
        seen_by_dimension[dimension] = seen_by_dimension.get(dimension, 0) + 1
        dimension_index = seen_by_dimension[dimension]
        split = "development" if dimension_index <= 2 else "heldout"

        source_name = (
            f"{parameters['algorithm']}_{parameters['width']}x{parameters['height']}_"
            f"{parameters['maze_seed']}_{parameters['program_count']}_"
            f"{parameters['cycle_percent']}percent_{parameters['method_entry']}.sol"
        )
        source = output / "src" / source_name
        if not source.is_file():
            raise FileNotFoundError(f"官方生成源码缺失：{source}")
        content = source.read_text(encoding="utf-8")
        contract_match = re.search(r"\bcontract\s+([A-Za-z_][A-Za-z0-9_]*)\b", content)
        if not contract_match or "echidna_noBug" not in content:
            raise ValueError(f"源码不含预期合约或属性：{source_name}")

        sample_id = source.stem
        destination = dataset / split / sample_id
        destination.mkdir(parents=True, exist_ok=False)
        archived_source = destination / source_name
        shutil.copy2(source, archived_source)

        metadata = {
            "sample_id": sample_id,
            "split": split,
            "split_rule": "同一维度按 wrapper 输出顺序前 2 个为开发集，第 3 个为独立留出集",
            "ordinal": ordinal,
            "dimension_instance_index": dimension_index,
            "source": source_name,
            "source_sha256": sha256(archived_source),
            "contract": contract_match.group(1),
            "target": {
                "property": "echidna_noBug()",
                "oracle": "bug 标志保持 false；进入终点并在下一次 step 调用后置 true 时该属性应被 falsify",
                "known_solution_provided_to_agent": False,
            },
            "generator": {
                "repository": "https://github.com/Rigorous-Software-Engineering/olympia",
                "commit": EXPECTED_OLYMPIA_COMMIT,
                "global_wrapper_seed": GLOBAL_SEED,
                "wrapper_instance_seed": instance_seed,
                **parameters,
                "official_programs_list_entry": entry,
            },
            "generation_validation": {
                "official_reachability_check": "disabled",
                "reason": "本地运行仅安装生成所需依赖；生成后的源码由 Echidna 2.2.3 使用 solc 0.8.26 及官方优化参数单独编译和执行",
            },
            "excluded_artifacts": [
                "sol_tx/ 中的交易参数解答",
                "sln/ 中的迷宫路径解答",
                "txt/ 中的迷宫矩阵",
                "png/ 中的迷宫图",
                "*.foundry.sol 测试包装器",
            ],
        }
        write_json(destination / "生成参数.json", metadata)
        samples.append(metadata)

    artifact_dir = results / "生成器元数据"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(programs, artifact_dir / "programs.list")
    shutil.copy2(reproduction, artifact_dir / "reproducible_generation.sh")
    plan_path = results / "实验方案.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["generation_completed"] = True
    plan["generation_wall_seconds"] = round(generation_seconds, 3)
    plan["samples"] = samples
    write_json(plan_path, plan)
    return plan


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator-dir", type=Path, default=DEFAULT_GENERATOR)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--generator-output", type=Path, default=DEFAULT_GENERATOR_OUTPUT)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    args = parser.parse_args()

    generator = args.generator_dir.resolve()
    dataset = args.dataset_dir.resolve()
    results = args.results_dir.resolve()
    output = args.generator_output.resolve()
    work = args.work_dir.resolve()
    try:
        commit = subprocess.run(
            ["git", "-C", str(generator), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        parser.error(f"无法核实 Olympia 仓库提交：{exc}")
    if commit != EXPECTED_OLYMPIA_COMMIT:
        parser.error(f"Olympia 提交不匹配：要求 {EXPECTED_OLYMPIA_COMMIT}，实际 {commit}")
    if dataset.exists() or results.exists():
        parser.error("数据集或结果目录已存在；为避免覆盖，请使用新的输出路径")

    tools_root = (ROOT / ".tools").resolve()
    if (output == work or output.is_relative_to(work) or work.is_relative_to(output)
            or output == tools_root or work == tools_root
            or not output.is_relative_to(tools_root) or not work.is_relative_to(tools_root)):
        parser.error("generator-output 与 work-dir 必须是 .tools 下互不嵌套的独立目录")
    if output.exists() or work.exists():
        parser.error("本地 Olympia 暂存目录已存在；请先核对后改用新的目录")
    output.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=False)
    results.mkdir(parents=True, exist_ok=False)

    wrapper_args = official_wrapper_args(output)
    plan = {
        "experiment": "Olympia ASE 2024 小型公开基准复现",
        "registered_date": "2026-11-16",
        "paper_original_dataset": "未在官方仓库 main 分支公开文件中找到论文所用的 200 个生成合约及原始 seed 清单",
        "generator": {
            "repository": "https://github.com/Rigorous-Software-Engineering/olympia",
            "commit": commit,
            "wrapper": "olympia/olympia_wrapper.py",
            "arguments": wrapper_args,
            "random_seed": GLOBAL_SEED,
            "dimensions": DIMENSIONS,
            "instances_per_dimension": INSTANCES_PER_DIMENSION,
            "algorithms": ALGORITHMS,
            "methods": GENERATION_METHODS,
            "equality_percentages": EQUALITY_PERCENTAGES,
            "cycle_percentages": CYCLE_PERCENTAGES,
            "cve_method_included": False,
            "official_reachability_check": "disabled; native Echidna compile/run is the separate source validation",
        },
        "generator_runtime": {
            "python": sys.version.split()[0],
            "dependencies": {
                name: package_version(name)
                for name in ("numpy", "matplotlib", "mazelib")
            },
        },
        "split": {
            "development": 8,
            "heldout": 4,
            "rule": "每个维度生成 3 个样本；按 wrapper 输出顺序前 2 个用于开发，第 3 个作为独立留出集",
            "heldout_dimensions": DIMENSIONS,
            "registered_before_campaigns": True,
        },
        "target": {
            "property": "echidna_noBug()",
            "expected": "触发 bug 标志后属性 falsify",
            "known_solution_given_to_agent": False,
        },
        "native_echidna_budget": {
            "version_expected": "Echidna 2.2.3 (Olympia 官方 Docker 镜像)",
            "timeout_seconds": 60,
            "test_limit_sequences": 1073741823,
            "sequence_length_transactions": 100,
            "workers": 1,
            "repeats_per_sample": 1,
            "stop_on_fail": True,
            "seed_policy": "campaign seed = 20261116 + manifest 序号 - 1",
            "shrink_limit": 5000,
            "solc": "0.8.26 (Olympia 官方 Docker 配置)",
            "solc_args": "--evm-version paris --optimize --optimize-runs 99999",
            "coverage": True,
        },
        "v2": {
            "api_called": False,
            "known_solution_given_to_agent": False,
            "status": "静态接入检查将在原生基线后单独记录",
        },
        "data_policy": {
            "archived": ["官方生成的 Echidna Solidity 源码", "生成参数", "programs.list", "reproducible_generation.sh"],
            "not_archived_or_passed_to_agent": ["sol_tx", "sln", "txt", "png", "*.foundry.sol"],
            "temporary_generator_output": str(output),
            "temporary_generator_output_cleaned_after_archive": False,
        },
    }
    write_json(results / "实验方案.json", plan)

    try:
        elapsed = run_official_wrapper(generator, output, work)
        if not output.is_dir():
            raise RuntimeError("Olympia wrapper 未生成输出目录")
        final_plan = collect_outputs(output, dataset, results, elapsed)
        remove_staging_directory(output)
        remove_staging_directory(work)
        final_plan["data_policy"]["temporary_generator_output_cleaned_after_archive"] = True
        write_json(results / "实验方案.json", final_plan)
    except Exception as exc:
        plan["generation_completed"] = False
        plan["generation_error"] = f"{type(exc).__name__}: {exc}"
        write_json(results / "实验方案.json", plan)
        raise

    print(json.dumps({
        "generator_commit": commit,
        "samples": len(final_plan["samples"]),
        "development": sum(row["split"] == "development" for row in final_plan["samples"]),
        "heldout": sum(row["split"] == "heldout" for row in final_plan["samples"]),
        "generation_wall_seconds": final_plan["generation_wall_seconds"],
        "dataset": str(dataset),
        "results": str(results),
        "solution_files_archived": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
