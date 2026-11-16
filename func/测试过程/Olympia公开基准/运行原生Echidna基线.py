#!/usr/bin/env python3
"""对已归档的 Olympia 样本运行同属性、同预算的原生 Echidna 基线。"""

from __future__ import annotations

import csv
from datetime import datetime
from importlib import metadata
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RESULTS = ROOT / "func/测试过程/Olympia公开基准/结果/ASE2024-20261116"
DEFAULT_DATASET = ROOT / "sol/单合约测试/OlympiaASE2024"
TARGET_PROPERTY = "echidna_noBug"
TEST_LIMIT = 1_073_741_823
TIMEOUT_SECONDS = 60
SEQ_LEN = 100
SHRINK_LIMIT = 5_000
SEED_BASE = 20261116
SOLC = ROOT / ".tools/olympia-solc/solc-v0.8.26"
SOLC_ARGS = "--evm-version paris --optimize --optimize-runs 99999"


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


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def parse_time_file(path: Path) -> dict[str, float | int | None]:
    if not path.is_file():
        return {"wall_seconds": None, "user_cpu_seconds": None,
                "system_cpu_seconds": None, "max_rss_kb": None}
    match = re.search(
        r"wall_s=([^\s]+) user_s=([^\s]+) sys_s=([^\s]+) maxrss_kb=(\d+)",
        path.read_text(encoding="utf-8", errors="replace"),
    )
    if not match:
        return {"wall_seconds": None, "user_cpu_seconds": None,
                "system_cpu_seconds": None, "max_rss_kb": None}
    return {
        "wall_seconds": float(match.group(1)),
        "user_cpu_seconds": float(match.group(2)),
        "system_cpu_seconds": float(match.group(3)),
        "max_rss_kb": int(match.group(4)),
    }


def parse_property_status(log: str) -> str:
    if re.search(rf"{re.escape(TARGET_PROPERTY)}[^\n]*(?:falsified|failed)",
                 log, re.IGNORECASE):
        return "falsified"
    if re.search(rf"{re.escape(TARGET_PROPERTY)}[^\n]*(?:passed|passing)",
                 log, re.IGNORECASE):
        return "passing"
    if re.search(r"property\s+failure|falsified!", log, re.IGNORECASE):
        return "falsified"
    return "unknown"


def parse_case_count(log: str) -> int | None:
    matches = re.findall(r"fuzzing\s*:\s*(\d+)\s*/\s*\d+", log, re.IGNORECASE)
    if matches:
        return int(matches[-1])
    matches = re.findall(r"after\s+(\d+)\s+tests?", log, re.IGNORECASE)
    return int(matches[-1]) if matches else None


def parse_first_discovery_time(log: str, wall_seconds: float | int | None) -> float | None:
    if wall_seconds is None:
        return None
    timestamps = re.findall(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]", log)
    failure_statuses = re.findall(
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\]\s+\[status\]"
        r"[^\n]*tests:\s*([1-9]\d*)\s*/\s*\d+",
        log,
        re.IGNORECASE,
    )
    if not timestamps or not failure_statuses:
        return None
    end_time = datetime.fromisoformat(timestamps[-1])
    first_failure_status = datetime.fromisoformat(failure_statuses[0][0])
    elapsed = float(wall_seconds) - (end_time - first_failure_status).total_seconds()
    return round(max(0.0, elapsed), 3)


def repair_executed_counts(results_dir: Path, run_id: str) -> int:
    campaign_root = results_dir / run_id
    summary_path = campaign_root / "原生基线汇总.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"找不到完整汇总，无法从日志校正：{summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    rows = summary["rows"]
    for row in rows:
        case_dir = ROOT / row["campaign_dir"]
        log = (case_dir / "echidna.log").read_text(encoding="utf-8", errors="replace")
        status = parse_property_status(log)
        row["property_status"] = status
        row["target_discovered"] = status == "falsified"
        row["executed_test_sequences"] = parse_case_count(log)
        row["first_discovery_time_seconds"] = (
            parse_first_discovery_time(log, row.get("campaign_wall_seconds"))
            if status == "falsified" else None
        )
        row["first_discovery_time_semantics"] = (
            "估算值：取 Echidna 日志首次出现 tests=1/1 的状态时刻，并以外部进程墙钟时长反推相对启动时间；状态约每 3 秒采样，包含编译/启动，非精确 EVM 调用时间"
            if status == "falsified" else "固定预算内未发现目标"
        )
        row.update(parse_coverage(case_dir, log))
        write_json(case_dir / "campaign-result.json", row)
    summary["rows"] = rows
    summary["discovered"] = sum(bool(row["target_discovered"]) for row in rows)
    summary["discovery_rate"] = summary["discovered"] / len(rows) if rows else 0.0
    write_json(summary_path, summary)
    fields = [
        "sample_id", "split", "dimension", "property_status", "target_discovered",
        "first_discovery_time_seconds", "executed_test_sequences", "test_limit_sequences",
        "sequence_length_transactions", "campaign_seed", "campaign_wall_seconds",
        "user_cpu_seconds", "system_cpu_seconds", "max_rss_kb", "unique_instructions",
        "covered_source_lines", "total_annotated_source_lines",
        "source_line_coverage_percent", "exit_code", "campaign_dir",
    ]
    with (campaign_root / "原生基线汇总.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def parse_coverage(campaign_dir: Path, log: str) -> dict[str, int | float | None]:
    unique = re.findall(r"Unique instructions\s*:\s*(\d+)", log, re.IGNORECASE)
    covered_txt = sorted(campaign_dir.glob("corpus/covered.*.txt"))
    total_lines: int | None = None
    covered_lines: int | None = None
    if covered_txt:
        total = 0
        covered = 0
        for line in covered_txt[-1].read_text(encoding="utf-8", errors="replace").splitlines():
            match = re.match(r"^\s*\d+\s*\|\s*([^|]*)\|", line)
            if not match:
                continue
            total += 1
            if match.group(1).strip():
                covered += 1
        total_lines, covered_lines = total, covered
    percentage = (100.0 * covered_lines / total_lines
                  if total_lines and covered_lines is not None else None)
    return {
        "unique_instructions": int(unique[-1]) if unique else None,
        "covered_source_lines": covered_lines,
        "total_annotated_source_lines": total_lines,
        "source_line_coverage_percent": round(percentage, 3) if percentage is not None else None,
    }


def run_campaign(sample: dict[str, Any], ordinal: int, dataset: Path,
                 campaign_root: Path, echidna: str) -> dict[str, Any]:
    sample_id = sample["sample_id"]
    source = dataset / sample["split"] / sample_id / sample["source"]
    if not source.is_file():
        raise FileNotFoundError(f"样本源码不存在：{source}")
    if sha256(source) != sample["source_sha256"]:
        raise ValueError(f"样本源码哈希与清单不一致：{sample_id}")

    campaign_dir = campaign_root / sample["split"] / sample_id
    if campaign_dir.exists():
        raise FileExistsError(f"拒绝覆盖既有 campaign：{campaign_dir}")
    corpus_dir = campaign_dir / "corpus"
    campaign_dir.mkdir(parents=True, exist_ok=False)
    corpus_dir.mkdir()

    solc = Path(os.environ.get("SOLC_BIN", str(SOLC))).resolve()
    if not solc.is_file():
        raise FileNotFoundError(f"找不到固定 solc：{solc}（可通过 SOLC_BIN 覆盖）")
    crytic_config = campaign_dir / "crytic-compile.json"
    write_json(crytic_config, {"solc": str(solc)})
    echidna_config = campaign_dir / "echidna.yaml"
    config = [
        'prefix: "echidna_"',
        'testMode: "property"',
        "workers: 1",
        f"corpusDir: {yaml_string(str(corpus_dir.resolve()))}",
        f"timeout: {TIMEOUT_SECONDS}",
        f"testLimit: {TEST_LIMIT}",
        f"seqLen: {SEQ_LEN}",
        f"shrinkLimit: {SHRINK_LIMIT}",
        f"seed: {SEED_BASE + ordinal - 1}",
        f"solcArgs: {yaml_string(SOLC_ARGS)}",
        "codeSize: 0xc00000",
        "coverage: true",
        "stopOnFail: true",
        "",
    ]
    echidna_config.write_text("\n".join(config), encoding="utf-8")

    seed = SEED_BASE + ordinal - 1
    command = [
        echidna, str(source.resolve()), "--contract", sample["contract"],
        "--config", str(echidna_config.resolve()),
        "--test-limit", str(TEST_LIMIT), "--seq-len", str(SEQ_LEN),
        "--shrink-limit", str(SHRINK_LIMIT), "--seed", str(seed),
        "--workers", "1", "--format", "text",
        "--crytic-args", f"--config-file {crytic_config.resolve()}",
    ]
    write_json(campaign_dir / "command.json", {
        "argv": command,
        "seed": seed,
        "test_limit_sequences": TEST_LIMIT,
        "timeout_seconds": TIMEOUT_SECONDS,
        "sequence_length_transactions": SEQ_LEN,
        "shrink_limit": SHRINK_LIMIT,
        "stop_on_fail": True,
    })

    time_bin = Path("/usr/bin/time")
    measurement = campaign_dir / "resource-usage.txt"
    log_path = campaign_dir / "echidna.log"
    measured_command = command
    if time_bin.is_file():
        measured_command = [
            str(time_bin), "-f",
            "wall_s=%e user_s=%U sys_s=%S maxrss_kb=%M",
            "-o", str(measurement), *command,
        ]
    started = time.perf_counter()
    environment = os.environ.copy()
    environment["PATH"] = (
        str(Path(sys.prefix) / "bin")
        + os.pathsep + environment.get("PATH", "")
    )
    with log_path.open("w", encoding="utf-8") as log_stream:
        completed = subprocess.run(
            measured_command, cwd=campaign_dir, stdout=log_stream,
            stderr=subprocess.STDOUT, text=True, check=False, env=environment,
        )
    elapsed = time.perf_counter() - started
    log = log_path.read_text(encoding="utf-8", errors="replace")
    if "crytic-compile not installed or not found in PATH" in log:
        raise RuntimeError("Echidna 未能启动 crytic-compile，请检查隔离环境 PATH")
    resources = parse_time_file(measurement)
    if resources["wall_seconds"] is None:
        resources["wall_seconds"] = round(elapsed, 3)
    status = parse_property_status(log)
    coverage = parse_coverage(campaign_dir, log)
    row = {
        "sample_id": sample_id,
        "split": sample["split"],
        "dimension": sample["generator"]["dimension"],
        "property": TARGET_PROPERTY,
        "property_status": status,
        "target_discovered": status == "falsified",
        "first_discovery_time_seconds": (
            parse_first_discovery_time(log, resources["wall_seconds"])
            if status == "falsified" else None
        ),
        "first_discovery_time_semantics": (
            "估算值：取 Echidna 日志首次出现 tests=1/1 的状态时刻，并以外部进程墙钟时长反推相对启动时间；状态约每 3 秒采样，包含编译/启动，非精确 EVM 调用时间"
            if status == "falsified" else "not discovered within the fixed test-sequence budget"
        ),
        "executed_test_sequences": parse_case_count(log),
        "test_limit_sequences": TEST_LIMIT,
        "sequence_length_transactions": SEQ_LEN,
        "campaign_seed": seed,
        "exit_code": completed.returncode,
        "campaign_wall_seconds": resources["wall_seconds"],
        "user_cpu_seconds": resources["user_cpu_seconds"],
        "system_cpu_seconds": resources["system_cpu_seconds"],
        "max_rss_kb": resources["max_rss_kb"],
        **coverage,
        "campaign_dir": str(campaign_dir.relative_to(ROOT)).replace(os.sep, "/"),
    }
    write_json(campaign_dir / "campaign-result.json", row)
    print(json.dumps({
        "sample": sample_id,
        "split": sample["split"],
        "property_status": status,
        "test_sequences": row["executed_test_sequences"],
        "wall_seconds": row["campaign_wall_seconds"],
        "unique_instructions": row["unique_instructions"],
        "exit_code": row["exit_code"],
    }, ensure_ascii=False), flush=True)
    return row


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--run-id", default="native-echidna-60s")
    parser.add_argument("--echidna", default=os.environ.get("ECHIDNA_BIN") or shutil.which("echidna"))
    parser.add_argument("--rebuild-summary-from-logs", action="store_true",
                        help="从已完成 campaign 日志重建执行序列数和覆盖率汇总")
    args = parser.parse_args()
    results_dir = args.results_dir.resolve()
    if args.rebuild_summary_from_logs:
        repaired = repair_executed_counts(results_dir, args.run_id)
        print(json.dumps({"repaired_samples": repaired}, ensure_ascii=False))
        return 0
    if not args.echidna:
        parser.error("找不到 echidna；请安装 Echidna 2.2.3 或通过 --echidna 指定")
    echidna = str(Path(args.echidna).resolve())
    version = subprocess.run([echidna, "--version"], capture_output=True,
                             text=True, check=False).stdout.strip()
    if version != "Echidna 2.2.3":
        parser.error(f"Olympia 官方 Docker 固定 Echidna 2.2.3，实际为 {version!r}")

    tool_path = str(Path(sys.prefix) / "bin") + os.pathsep + os.environ.get("PATH", "")
    crytic_compile = shutil.which("crytic-compile", path=tool_path)
    if not crytic_compile:
        parser.error("隔离 Python 环境中找不到 crytic-compile（Olympia 官方 Docker 依赖）")
    compile_version = subprocess.run(
        [crytic_compile, "--version"], capture_output=True, text=True, check=False,
        env={**os.environ, "PATH": tool_path},
    ).stdout.strip()
    try:
        slither_version = metadata.version("slither-analyzer")
    except metadata.PackageNotFoundError:
        parser.error("隔离 Python 环境中找不到 slither-analyzer（Olympia 官方 Docker 依赖）")

    dataset = args.dataset_dir.resolve()
    plan_path = results_dir / "实验方案.json"
    if not plan_path.is_file():
        parser.error(f"找不到生成阶段的实验方案：{plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    if not plan.get("generation_completed") or len(plan.get("samples", [])) != 12:
        parser.error("基准生成未完成或样本数不是预登记的 12 个")
    if args.run_id in {"", ".", ".."} or "/" in args.run_id or "\\" in args.run_id:
        parser.error("run-id 必须是单个目录名")
    campaign_root = results_dir / args.run_id
    if campaign_root.exists():
        parser.error(f"campaign 结果目录已存在，拒绝覆盖：{campaign_root}")
    campaign_root.mkdir(parents=True)

    rows: list[dict[str, Any]] = []
    for ordinal, sample in enumerate(plan["samples"], 1):
        rows.append(run_campaign(sample, ordinal, dataset, campaign_root, echidna))

    found = sum(bool(row["target_discovered"]) for row in rows)
    summary = {
        "echidna_version": version,
        "crytic_compile_version": compile_version,
        "slither_analyzer_version": slither_version,
        "echidna_binary_sha256": sha256(Path(echidna)),
        "echidna_release_asset_sha256": (
            sha256(Path(echidna).with_name("echidna-2.2.3-x86_64-linux.tar.gz"))
            if Path(echidna).with_name("echidna-2.2.3-x86_64-linux.tar.gz").is_file()
            else None
        ),
        "solc_binary_sha256": sha256(SOLC),
        "property": f"{TARGET_PROPERTY}()",
        "samples": len(rows),
        "development_samples": sum(row["split"] == "development" for row in rows),
        "heldout_samples": sum(row["split"] == "heldout" for row in rows),
        "discovered": found,
        "discovery_rate": found / len(rows) if rows else 0.0,
        "budget": {
            "test_limit_sequences": TEST_LIMIT,
            "timeout_seconds": TIMEOUT_SECONDS,
            "sequence_length_transactions": SEQ_LEN,
            "shrink_limit": SHRINK_LIMIT,
            "repeats_per_sample": 1,
            "workers": 1,
            "stop_on_fail": True,
            "timeout": TIMEOUT_SECONDS,
            "seed_base": SEED_BASE,
        },
        "rows": rows,
    }
    write_json(campaign_root / "原生基线汇总.json", summary)
    fields = [
        "sample_id", "split", "dimension", "property_status", "target_discovered",
        "first_discovery_time_seconds", "executed_test_sequences", "test_limit_sequences",
        "sequence_length_transactions", "campaign_seed", "campaign_wall_seconds",
        "user_cpu_seconds", "system_cpu_seconds", "max_rss_kb", "unique_instructions",
        "covered_source_lines", "total_annotated_source_lines",
        "source_line_coverage_percent", "exit_code", "campaign_dir",
    ]
    with (campaign_root / "原生基线汇总.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({
        "samples": len(rows), "discovered": found,
        "discovery_rate": summary["discovery_rate"],
        "summary": str(campaign_root / "原生基线汇总.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
