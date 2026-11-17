#!/usr/bin/env python3
"""枚举固定提交的 FMBC 数据集，并按预注册规则冻结动态实验样本。

该脚本不调用模型 API，也不将 ground truth 写入 Agent 输入。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATASET = ROOT / "sol/真实项目/FMBC2024"
DEFAULT_RESULTS = ROOT / "func/测试过程/FMBC公开基准/结果/Phase23-20261117"
UPSTREAM_COMMIT = "01251cc338a6126e8735af87fe3845936150783d"
EXCLUDED_TOOL_DIRS = {"solcmc", "certora", "echidna"}
SOURCE_SKIP_PARTS = EXCLUDED_TOOL_DIRS | {".git", "build", "cache"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file() and ".git" not in item.parts):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def read_ground_truth(path: Path) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        valid = []
        excluded = []
        for line_number, raw in enumerate(csv.DictReader(stream), start=2):
            row = dict(raw)
            property_id = (row.get("property") or "").strip()
            if not property_id or property_id.startswith("#"):
                excluded.append({"line_number": line_number, "row": row,
                                 "reason": "CSV 中的空行/注释行，不是 property × version 任务。"})
            else:
                valid.append(row)
        return valid, excluded


def version_sources(case_dir: Path) -> list[Path]:
    result = []
    for path in sorted(case_dir.rglob("*.sol")):
        parts = path.relative_to(case_dir).parts
        if set(parts) & (SOURCE_SKIP_PARTS | {"old"}) or {"lib", "libs", "vendor"} & set(parts[:-1]):
            continue
        result.append(path)
    return result


def source_matches_version(path: Path, version: str) -> bool:
    return bool(re.search(rf"(?:^|[_-]){re.escape(version.lower())}$", path.stem.lower()))


def source_metadata(path: Path, dataset_dir: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="replace")
    pragmas = sorted(set(re.findall(r"\bpragma\s+solidity\s+([^;]+);", text)))
    imports = re.findall(r"\bimport\s+(?:[^\"']*?from\s+)?[\"']([^\"']+)[\"']\s*;", text)
    resolved = []
    unresolved = []
    for import_name in imports:
        candidates = [path.parent / import_name, dataset_dir / import_name]
        found = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
        try:
            relative = found.relative_to(dataset_dir.resolve()) if found is not None else None
        except ValueError:
            relative = None
        if relative is not None:
            resolved.append(relative.as_posix())
        else:
            unresolved.append(import_name)
    description = re.search(r"@custom:version\s+([^\r\n*]+)", text)
    return {
        "path": path.relative_to(dataset_dir).as_posix(),
        "sha256": sha256(path),
        "solidity_pragmas": pragmas,
        "imports": imports,
        "resolved_dependency_paths": sorted(set(resolved)),
        "unresolved_external_imports": sorted(set(unresolved)),
        "version_description_public_data": description.group(1).strip() if description else None,
    }


def dependency_closure(source_rows: list[dict[str, Any]], dataset_dir: Path) -> list[dict[str, Any]]:
    pending = sorted({dep for row in source_rows for dep in row["resolved_dependency_paths"]})
    visited: dict[str, dict[str, Any]] = {}
    while pending:
        relative = pending.pop(0)
        if relative in visited:
            continue
        dependency = dataset_dir / relative
        if not dependency.is_file():
            continue
        metadata = source_metadata(dependency, dataset_dir)
        visited[relative] = metadata
        pending.extend(dep for dep in metadata["resolved_dependency_paths"] if dep not in visited)
    return [visited[key] for key in sorted(visited)]


def matching_artifacts(case_dir: Path, tool: str, property_id: str,
                       version: str) -> list[str]:
    root = case_dir / tool
    if not root.is_dir():
        return []
    files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    property_id = property_id.lower()
    version = version.lower()
    has_version_specific_files = any(version in path.stem.lower() for path in files)
    result = []
    for path in files:
        stem = path.stem.lower()
        if (stem == property_id or property_id in stem) and (
                version in stem or not has_version_specific_files):
            result.append(path.relative_to(case_dir).as_posix())
    return result


def classify_oracle(case_dir: Path, property_id: str, version: str,
                    source_rows: list[dict[str, Any]], dataset_dir: Path) -> dict[str, Any]:
    source_text = "\n".join(
        (dataset_dir / row["path"]).read_text(encoding="utf-8", errors="replace")
        for row in source_rows
    )
    executable_property = False
    for match in re.finditer(r"\bfunction\s+echidna_[A-Za-z0-9_]*\s*\([^)]*\)", source_text):
        body_start = source_text.find("{", match.end())
        signature = source_text[match.end():body_start if body_start >= 0 else match.end() + 200]
        if re.search(r"\breturns\s*\(\s*bool\s*\)", signature):
            executable_property = True
            break
    solcmc = matching_artifacts(case_dir, "solcmc", property_id, version)
    certora = matching_artifacts(case_dir, "certora", property_id, version)
    if executable_property:
        return {
            "status": "candidate_requires_runtime_validation",
            "reason": "版本合约存在 Echidna 命名前缀属性函数；仍需确认属性语义、初始状态及正反版本一致性。",
            "solcmc_artifacts": solcmc,
            "certora_artifacts": certora,
        }
    if solcmc:
        files = [(case_dir / item).read_text(encoding="utf-8", errors="replace") for item in solcmc]
        markers = sorted({marker for text in files for marker in
                          ("ghost", "preghost", "postghost", "invariant", "assert")
                          if marker in text.lower()})
        return {
            "status": "unsupported_without_oracle_translation",
            "reason": (
                "官方 SolCMC 文件是验证器专用的 ghost/preghost/postghost/invariant 片段，"
                "未发现可直接部署并由有限 ABI 交易序列调用的属性入口；自动移植会改变或补造测试语义。"
            ),
            "solcmc_artifacts": solcmc,
            "solcmc_constructs": markers,
            "certora_artifacts": certora,
        }
    if certora:
        return {
            "status": "unsupported_formal_spec_only",
            "reason": "只有 Certora 形式化规则，没有可直接执行的有限交易属性 Oracle。",
            "solcmc_artifacts": [],
            "certora_artifacts": certora,
        }
    return {
        "status": "unsupported_natural_language_only",
        "reason": "数据集提供自然语言属性，但没有对应的可执行运行时 Oracle 文件。",
        "solcmc_artifacts": [],
        "certora_artifacts": [],
    }


def classify_constraint_type(definition: Any) -> str:
    text = str(definition or "").lower()
    if re.search(r"deadline|time|block|expiry|expire|timeout|vesting", text):
        return "temporal"
    if re.search(r"reentr|callback|reentrant", text):
        return "reentrancy"
    if re.search(r"owner|sender|caller|authoriz|permission|onlyif|only if|guardian", text):
        return "authorization"
    if re.search(r"balance|amount|deposit|withdraw|supply|token|ether|eth|reserve", text):
        return "accounting"
    if re.search(r"revert|call|succeed|failure|return", text):
        return "call_outcome"
    return "generic_state"


def enumerate_tasks(dataset_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    task_rows: list[dict[str, Any]] = []
    scenario_rows: list[dict[str, Any]] = []
    for area in ("contracts", "regression"):
        area_dir = dataset_dir / area
        for case_dir in sorted(path for path in area_dir.iterdir() if path.is_dir()):
            skeleton_path = case_dir / "skeleton.json"
            truth_path = case_dir / "ground-truth.csv"
            if not skeleton_path.is_file() or not truth_path.is_file():
                continue
            skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
            is_template = case_dir.name == "template"
            sources = version_sources(case_dir)
            raw_properties = skeleton.get("properties", {})
            if isinstance(raw_properties, dict):
                properties = raw_properties
            elif isinstance(raw_properties, list):
                properties = {
                    f"p{index}": value for index, value in enumerate(raw_properties, start=1)
                }
            else:
                properties = {}
            specification = skeleton.get("specification")
            if isinstance(specification, str) and specification.startswith("file:"):
                spec_path = case_dir / specification[5:]
                specification_text = (spec_path.read_text(encoding="utf-8", errors="replace")
                                      if spec_path.is_file() else None)
                specification_file = spec_path.relative_to(case_dir).as_posix() if spec_path.is_file() else None
            else:
                specification_text, specification_file = specification, None
            ground_rows, excluded_gt_rows = read_ground_truth(truth_path)
            scenario_rows.append({
                "area": area,
                "scenario_id": case_dir.relative_to(dataset_dir).as_posix(),
                "name": skeleton.get("name", case_dir.name),
                "is_template": is_template,
                "source_file_count": len(sources),
                "property_count": len(properties),
                "property_definitions": [
                    {"property_id": key, "definition": value}
                    for key, value in properties.items()
                ],
                "version_ids_from_ground_truth": sorted({
                    (row.get("version") or "").strip() for row in ground_rows
                }),
                "version_source_files": [path.relative_to(dataset_dir).as_posix() for path in sources],
                "excluded_ground_truth_csv_records": excluded_gt_rows,
            })
            for raw in ground_rows:
                property_id = (raw.get("property") or "").strip()
                version = (raw.get("version") or "").strip()
                truth_value = (raw.get("sat") or raw.get("truth") or "").strip()
                expected_holds = (truth_value == "1") if truth_value in {"0", "1"} else None
                matching = [path for path in sources if source_matches_version(path, version)]
                source_rows = [source_metadata(path, dataset_dir) for path in matching]
                dependencies = dependency_closure(source_rows, dataset_dir)
                oracle = classify_oracle(case_dir, property_id, version, source_rows, dataset_dir)
                task_rows.append({
                    "task_id": f"{case_dir.relative_to(dataset_dir).as_posix()}::{property_id}::{version}",
                    "area": area,
                    "scenario_id": case_dir.relative_to(dataset_dir).as_posix(),
                    "scenario_name": skeleton.get("name", case_dir.name),
                    "is_template": is_template,
                    "property_id": property_id,
                    "property_definition": properties.get(property_id),
                    "property_definition_present": property_id in properties,
                    "specification_file": specification_file,
                    "specification": specification_text,
                    "version_id": version,
                    "expected_holds": expected_holds,
                    "ground_truth_raw": truth_value,
                    "ground_truth_footnote": (raw.get("footnote-md") or raw.get("footnote") or "").strip(),
                    "ground_truth_source": truth_path.relative_to(dataset_dir).as_posix(),
                    "source_candidates": source_rows,
                    "source_mapping_status": "unique" if len(matching) == 1 else "ambiguous" if matching else "unmapped",
                    "compile_versions": sorted({v for source in source_rows for v in source["solidity_pragmas"]}),
                    "dependencies": [item["path"] for item in dependencies],
                    "dependency_metadata": dependencies,
                    "unresolved_imports": sorted({item for source in source_rows + dependencies
                                                   for item in source["unresolved_external_imports"]}),
                    "solcmc_artifacts": oracle.get("solcmc_artifacts", []),
                    "certora_artifacts": oracle.get("certora_artifacts", []),
                    "oracle_status": oracle["status"],
                    "oracle_reason": oracle["reason"],
                    "oracle_constructs": oracle.get("solcmc_constructs", []),
                    "template_excluded_from_benchmark_count": is_template,
                })

    counts = Counter()
    for row in task_rows:
        counts["all_ground_truth_rows"] += 1
        counts["template_rows"] += int(row["is_template"])
        counts["benchmark_tasks_excluding_templates"] += int(not row["is_template"])
        counts[f"oracle:{row['oracle_status']}"] += 1
        counts["missing_property_definitions"] += int(not row["property_definition_present"])
        counts[f"area:{row['area']}"] += 1
        if row["expected_holds"] is not None:
            counts[f"ground_truth_holds_{str(row['expected_holds']).lower()}"] += 1
    counts["distinct_scenario_property_groups"] = len({
        (row["scenario_id"], row["property_id"]) for row in task_rows
    })
    counts["distinct_scenario_versions"] = len({
        (row["scenario_id"], row["version_id"]) for row in task_rows
    })
    mapping_counts = Counter(row["source_mapping_status"] for row in task_rows)
    readme_text = (dataset_dir / "README.md").read_text(encoding="utf-8", errors="replace")
    readme_task_match = re.search(
        r"currently comprises\s+(\d+)\s+verification tasks", readme_text, re.IGNORECASE
    )
    checkmarked_contracts = set(re.findall(
        r"\]\(contracts/([^/]+)/\)\s*:white_check_mark:", readme_text
    ))
    benchmark_rows = [row for row in task_rows if not row["is_template"]]
    benchmark_oracles = Counter(row["oracle_status"] for row in benchmark_rows)
    benchmark_areas = Counter(row["area"] for row in benchmark_rows)
    checkmarked_rows = [row for row in benchmark_rows
                        if row["area"] == "contracts" and row["scenario_id"].split("/", 1)[1] in checkmarked_contracts]
    noncheckmarked_contracts = sorted({
        row["scenario_id"] for row in benchmark_rows
        if row["area"] == "contracts" and row["scenario_id"].split("/", 1)[1] not in checkmarked_contracts
    })
    benchmark_pragmas = Counter(
        pragma for row in benchmark_rows for pragma in row["compile_versions"]
    )
    benchmark_property_groups = {
        (row["scenario_id"], row["property_id"]) for row in benchmark_rows
    }
    benchmark_versions = {
        (row["scenario_id"], row["version_id"]) for row in benchmark_rows
    }
    report = {
        "dataset_name": "FMBC 2024 contracts-verification-benchmark",
        "upstream_repository": "https://github.com/fsainas/contracts-verification-benchmark",
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_readme_claimed_verification_tasks": (
            int(readme_task_match.group(1)) if readme_task_match else None
        ),
        "benchmark_task_unit": "one ground-truth.csv property × version row",
        "scenario_count_including_templates": len(scenario_rows),
        "scenario_count_excluding_templates": sum(not row["is_template"] for row in scenario_rows),
        "excluded_ground_truth_csv_record_count": sum(
            len(row["excluded_ground_truth_csv_records"]) for row in scenario_rows
        ),
        "scenario_version_file_mapping_counts": dict(sorted(mapping_counts.items())),
        "benchmark_task_counts_excluding_templates": {
            "by_area": dict(sorted(benchmark_areas.items())),
            "by_oracle_status": dict(sorted(benchmark_oracles.items())),
            "business_contract_rows": benchmark_areas.get("contracts", 0),
            "regression_rows": benchmark_areas.get("regression", 0),
            "distinct_property_definitions": len(benchmark_property_groups),
            "distinct_scenario_versions": len(benchmark_versions),
            "solidity_pragma_constraints": dict(sorted(benchmark_pragmas.items())),
            "readme_checkmarked_contract_rows": len(checkmarked_rows),
            "readme_claim_delta_for_all_contract_rows": (
                benchmark_areas.get("contracts", 0) - int(readme_task_match.group(1))
                if readme_task_match else None
            ),
            "contract_scenarios_not_marked_up_to_date_in_readme": noncheckmarked_contracts,
        },
        "scenarios": scenario_rows,
        "counts": dict(sorted(counts.items())),
        "tasks": task_rows,
    }
    return task_rows, report


def freeze_selection(tasks: list[dict[str, Any]], manifest_sha: str) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        if not task["is_template"]:
            grouped[(task["scenario_id"], task["property_id"])].append(task)
    eligible = []
    for (scenario_id, property_id), rows in sorted(grouped.items()):
        if {row["expected_holds"] for row in rows} != {True, False}:
            continue
        if not all(row["oracle_status"] == "candidate_requires_runtime_validation" for row in rows):
            continue
        eligible.append({
            "scenario_id": scenario_id,
            "property_id": property_id,
            "constraint_type": classify_constraint_type(rows[0]["property_definition"]),
            "task_ids": sorted(row["task_id"] for row in rows),
            "version_ids": sorted({row["version_id"] for row in rows}),
            "rule_rank": [scenario_id, property_id],
        })
    selected = []
    seen_scenarios: set[str] = set()
    for constraint_type in sorted({group["constraint_type"] for group in eligible}):
        for group in sorted(eligible, key=lambda item: item["rule_rank"]):
            if (group["constraint_type"] == constraint_type and
                    group["scenario_id"] not in seen_scenarios):
                selected.append(group)
                seen_scenarios.add(group["scenario_id"])
                break
        if len(selected) == 3:
            break
    if len(selected) < 3:
        for group in sorted(eligible, key=lambda item: item["rule_rank"]):
            if group["scenario_id"] in seen_scenarios:
                continue
            selected.append(group)
            seen_scenarios.add(group["scenario_id"])
            if len(selected) == 3:
                break
    return {
        "freeze_stage": "before any G0/G2 run",
        "selection_rule": (
            "在全部非模板属性组中，保留 ground-truth 同时含 sat=1 与 sat=0 的属性；"
            "再要求所有相关版本都由数据集中存在的 Echidna 命名运行时属性函数直接定义 Oracle；"
            "从属性描述自动归入 temporal、reentrancy、authorization、accounting、call_outcome、generic_state 类别；"
            "按类别字典序优先选取不同场景，类别不足三种时按场景/属性 ID 顺序补足，同一场景最多一组。"
            "该过滤只用于离线配对选择，Agent 输入不包含 ground-truth、footnote 或版本说明。"
        ),
        "max_groups": 3,
        "fixed_seeds": [20261117, 20261118, 20261119],
        "end_to_end_budget_seconds_per_run": 180,
        "paired_groups_share_contract_oracle_deployment_accounts_and_budget": True,
        "manifest_sha256": manifest_sha,
        "eligible_group_count_before_diversity_cap": len(eligible),
        "selected_groups": selected,
        "selected_task_count": sum(len(group["task_ids"]) for group in selected),
        "selection_frozen": True,
        "no_outcome_based_resampling": True,
    }


def write_manifest_csv(path: Path, tasks: list[dict[str, Any]]) -> None:
    fields = [
        "task_id", "area", "scenario_id", "scenario_name", "is_template",
        "property_id", "property_definition", "property_definition_present",
        "version_id", "expected_holds", "ground_truth_raw", "ground_truth_footnote",
        "source_mapping_status", "compile_versions", "dependencies", "unresolved_imports",
        "solcmc_artifacts", "certora_artifacts", "oracle_status", "oracle_reason",
        "ground_truth_source",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore",
                                lineterminator="\n")
        writer.writeheader()
        for task in tasks:
            row = dict(task)
            row["scenario_name"] = json.dumps(task["scenario_name"], ensure_ascii=False)
            row["property_definition"] = json.dumps(task["property_definition"], ensure_ascii=False)
            for key in ("compile_versions", "dependencies", "unresolved_imports", "solcmc_artifacts", "certora_artifacts"):
                row[key] = json.dumps(row[key], ensure_ascii=False)
            writer.writerow(row)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    args = parser.parse_args()
    dataset_dir = args.dataset_dir.resolve()
    results_dir = args.results_dir.resolve()
    if not (dataset_dir / "README.md").is_file():
        parser.error(f"不是有效的 FMBC 数据集目录：{dataset_dir}")
    tasks, manifest = enumerate_tasks(dataset_dir)
    manifest["upstream_readme_sha256"] = sha256(dataset_dir / "README.md")
    manifest["upstream_archived_tree_sha256"] = tree_sha256(dataset_dir)
    manifest_path = results_dir / "dataset-manifest.json"
    write_json(manifest_path, manifest)
    write_manifest_csv(results_dir / "dataset-manifest.csv", tasks)
    selection = freeze_selection(tasks, sha256(manifest_path))
    write_json(results_dir / "selection-freeze.json", selection)
    print(json.dumps({
        "dataset_dir": str(dataset_dir),
        "manifest": str(manifest_path),
        "all_ground_truth_rows": manifest["counts"].get("all_ground_truth_rows", 0),
        "benchmark_tasks_excluding_templates": manifest["counts"].get("benchmark_tasks_excluding_templates", 0),
        "scenarios_excluding_templates": manifest["scenario_count_excluding_templates"],
        "oracle_status_counts": {key: value for key, value in manifest["counts"].items() if key.startswith("oracle:")},
        "selection": str(results_dir / "selection-freeze.json"),
        "selected_groups": len(selection["selected_groups"]),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
