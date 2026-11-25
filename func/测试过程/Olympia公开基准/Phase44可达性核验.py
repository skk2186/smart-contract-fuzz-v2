#!/usr/bin/env python3
"""Independently audit Olympia path reachability and native property execution.

Official solutions are read only for this diagnostic. This module is not imported
by Agent prompts, parameter generation, or sequence-extension code.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import statistics
import subprocess
from collections import deque
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PHASE43 = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase43-20261123"
MANIFEST = PHASE43 / "dataset-manifest.json"
OUTPUT = ROOT / "func/测试过程/Olympia公开基准/结果/Phase44-20261124"
MAX_SEQUENCE_LENGTH = 64
CONTRACT_ADDRESS = "0x00a329c0648769A73afAc7F9381E08FB43dBEA72"
DEPLOYER = "0x0000000000000000000000000000000000030000"
SENDER = "0x0000000000000000000000000000000000010000"
ZERO_WORD = "0x" + "00" * 32


def read_verified(base: Path, metadata: dict[str, Any]) -> str:
    path = base / metadata["path"]
    content = path.read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != metadata["sha256"]:
        raise ValueError("SHA-256 mismatch for {}".format(path))
    return content.decode("utf-8-sig")


def parse_binary_maze(text: str, dimension: int) -> list[str]:
    rows = [line.strip() for line in text.splitlines()
            if re.fullmatch(r"[01]+", line.strip())]
    expected = 2 * dimension + 1
    if len(rows) != expected or any(len(row) != expected for row in rows):
        raise ValueError("maze matrix is not {} by {}".format(expected, expected))
    return rows


def shortest_cell_moves(rows: list[str], dimension: int) -> int:
    """BFS over cell centers; a zero between centers denotes an open passage."""
    start = (0, 0)
    goal = (dimension - 1, dimension - 1)
    queue = deque([(start, 0)])
    visited = {start}
    while queue:
        (row, col), distance = queue.popleft()
        if (row, col) == goal:
            return distance
        for delta_row, delta_col in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next_row, next_col = row + delta_row, col + delta_col
            if not (0 <= next_row < dimension and 0 <= next_col < dimension):
                continue
            wall_row = 2 * row + 1 + delta_row
            wall_col = 2 * col + 1 + delta_col
            neighbor = (next_row, next_col)
            if rows[wall_row][wall_col] == "0" and neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, distance + 1))
    raise ValueError("maze graph has no path from start to goal")


def parse_official_solution(text: str) -> list[int]:
    values = []
    for line in text.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"-?\d+", stripped):
            values.append(int(stripped))
    return values


def parse_official_transactions(text: str) -> list[list[int]]:
    transactions = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.fullmatch(r"\[\s*(.*?)\s*\]", stripped)
        if not match:
            raise ValueError("unsupported official transaction row: " + stripped)
        values = match.group(1).strip()
        transactions.append([] if not values else [int(item.strip()) for item in values.split(",")])
    return transactions


def validate_solution_path(vertices: list[int], rows: list[str], dimension: int) -> bool:
    if not vertices or vertices[0] != 0 or vertices[-1] != dimension * dimension - 1:
        return False
    for left, right in zip(vertices, vertices[1:]):
        left_row, left_col = divmod(left, dimension)
        right_row, right_col = divmod(right, dimension)
        delta_row, delta_col = right_row - left_row, right_col - left_col
        if abs(delta_row) + abs(delta_col) != 1:
            return False
        wall_row = 2 * left_row + 1 + delta_row
        wall_col = 2 * left_col + 1 + delta_col
        if rows[wall_row][wall_col] != "0":
            return False
    return True


def echidna_seed(transactions: list[list[int]]) -> list[dict[str, Any]]:
    result = []
    for values in transactions:
        elements = [{"tag": "AbiInt", "contents": [8, str(value)]}
                    for value in values]
        argument = {"tag": "AbiArrayDynamic", "contents": [
            {"tag": "AbiIntType", "contents": 8}, elements]}
        result.append({
            "call": {"tag": "SolCall", "contents": ["step", [argument]]},
            "delay": [ZERO_WORD, ZERO_WORD],
            "dst": CONTRACT_ADDRESS,
            "gas": 12500000,
            "gasprice": ZERO_WORD,
            "src": SENDER,
            "value": ZERO_WORD,
        })
    return result


def verify_one_cell_transition_per_step(source_text: str) -> bool:
    """Check one handler per call; array fields are not iterated as extra moves."""

    def body_from(match: re.Match[str]) -> str | None:
        opening = source_text.find("{", match.end() - 1)
        if opening < 0:
            return None
        depth = 0
        for index in range(opening, len(source_text)):
            if source_text[index] == "{":
                depth += 1
            elif source_text[index] == "}":
                depth -= 1
                if depth == 0:
                    return source_text[opening + 1:index]
        return None

    step_match = re.search(
        r"function\s+step\s*\(\s*int8\[\]\s+calldata\s+inp\s*\)\s+external\s*\{",
        source_text)
    if not step_match:
        return False
    step_body = body_from(step_match)
    if step_body is None or re.search(r"\b(?:for|while)\s*\(", step_body):
        return False
    calls = re.findall(r"\bfunc_[A-Za-z0-9_]+\s*\(\s*inp\s*\)\s*;", step_body)
    returned_calls = re.findall(
        r"\bfunc_[A-Za-z0-9_]+\s*\(\s*inp\s*\)\s*;\s*return\s*;", step_body)
    if not calls or len(calls) != len(returned_calls):
        return False

    handlers = list(re.finditer(
        r"function\s+func_[A-Za-z0-9_]+\s*\(\s*int8\[\]\s+memory\s+inp\s*\)[^{]*\{",
        source_text))
    if not handlers:
        return False
    for match in handlers:
        body = body_from(match)
        if body is None or re.search(r"\b(?:for|while)\s*\(", body):
            return False
        indexes = re.findall(r"\binp\s*\[\s*([^\]]+)\s*\]", body)
        if any(not re.fullmatch(r"\d+", index.strip()) for index in indexes):
            return False
    return True


def run_native_oracle(sample: dict[str, Any], transactions: list[list[int]],
                      source: Path, output_dir: Path, echidna: str) -> dict[str, Any]:
    if len(transactions) > MAX_SEQUENCE_LENGTH:
        raise ValueError("official solution exceeds the fixed {} transaction cap".format(
            MAX_SEQUENCE_LENGTH))
    if output_dir.exists():
        existing = output_dir / "result.json"
        if existing.is_file():
            result = json.loads(existing.read_text(encoding="utf-8"))
            if result.get("status") == "native_counterexample":
                return result
            history = output_dir.parent / "prior-attempts"
            history.mkdir(parents=True, exist_ok=True)
            index = 1
            while (history / "{}-attempt-{:02d}".format(sample["sample_id"], index)).exists():
                index += 1
            output_dir.rename(history / "{}-attempt-{:02d}".format(sample["sample_id"], index))
        else:
            raise FileExistsError("refusing to overwrite incomplete native result: {}".format(output_dir))

    corpus = output_dir / "corpus"
    coverage = corpus / "coverage"
    coverage.mkdir(parents=True)
    seed_path = coverage / "official-solution.txt"
    seed_path.write_text(json.dumps(echidna_seed(transactions), ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    command = [echidna, str(source), "--contract", "Maze", "--test-mode", "property",
               "--workers", "1", "--seq-len", str(MAX_SEQUENCE_LENGTH),
               "--test-limit", "0", "--timeout", "60", "--seed", "4401",
               "--shrink-limit", "1", "--contract-addr", CONTRACT_ADDRESS,
               "--deployer", DEPLOYER, "--sender", SENDER,
               "--corpus-dir", str(corpus), "--coverage-dir", str(corpus),
               "--disable-onchain-sources", "--format", "text"]
    run_config = {
        "sample_id": sample["sample_id"],
        "diagnostic_only": True,
        "official_answer_passed_to_agent_or_extensioner": False,
        "sequence_length": MAX_SEQUENCE_LENGTH,
        "test_limit": 0,
        "seed_transaction_count": len(transactions),
        "native_property": "echidna_noBug",
        "command": command,
        "corpus_seed": str(seed_path),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run-config.json").write_text(
        json.dumps(run_config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    env = os.environ.copy()
    phase43_root = Path("/home/skk/smart-contract-fuzz-v2/.tools")
    python_target = phase43_root / "phase43-runtime-py311"
    solc_bin = phase43_root / "olympia-solc"
    solc_path = phase43_root / "phase43-solc-bin"
    env["PYTHONPATH"] = ":".join([
        str(python_target), str(ROOT / "deepseek"), str(ROOT / "func/功能"),
        env.get("PYTHONPATH", "")]).rstrip(":")
    env["SOLCX_BINARY_PATH"] = str(solc_bin)
    env["PATH"] = ":".join([
        str(solc_path), str(phase43_root / "olympia-venv/bin"),
        "/home/skk/.local/bin", str(phase43_root / "phase43-z3-root/usr/bin"),
        "/usr/local/bin", "/usr/bin", env.get("PATH", "")])
    completed = subprocess.run(command, cwd=str(ROOT), env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True,
                               encoding="utf-8", errors="replace", timeout=180,
                               check=False)
    log = completed.stdout or ""
    (output_dir / "echidna.log").write_text(log, encoding="utf-8")
    replayed = len(re.findall(r"Sequence replayed from corpus file", log))
    loaded_match = re.search(r"Loaded\s+(\d+) transaction sequences .*?coverage", log)
    property_line = next((line.strip() for line in log.splitlines()
                          if "echidna_noBug:" in line), None)
    counterexample = bool(re.search(r"echidna_noBug:\s*(?:failed|failure)", log, re.I))
    result = {
        "sample_id": sample["sample_id"],
        "exit_code": completed.returncode,
        "timeout": False,
        "sequence_length": MAX_SEQUENCE_LENGTH,
        "seed_transaction_count": len(transactions),
        "loaded_seed_sequences": int(loaded_match.group(1)) if loaded_match else None,
        "replayed_seed_sequences": replayed,
        "property_line": property_line,
        "native_counterexample": counterexample,
        "status": "native_counterexample" if counterexample and replayed else
                  "replayed_without_counterexample" if replayed else "not_replayed_or_unrecognized",
        "raw_log": str((output_dir / "echidna.log").relative_to(ROOT)),
        "run_config": str((output_dir / "run-config.json").relative_to(ROOT)),
    }
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def audit(native_ids: set[str], echidna: str | None) -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    samples = manifest["dataset"]["samples"]
    rows = []
    native_rows = []
    for sample in samples:
        files = sample["files"]
        dimension = int(sample["dimension"])
        source_text = read_verified(PHASE43, files["source"])
        maze_text = read_verified(PHASE43, files["maze_text"])
        solution_text = read_verified(PHASE43, files["solution"])
        transaction_text = read_verified(PHASE43, files["transactions"])
        maze = parse_binary_maze(maze_text, dimension)
        official_path = parse_official_solution(solution_text)
        official_transactions = parse_official_transactions(transaction_text)
        min_moves = shortest_cell_moves(maze, dimension)
        shortest_transactions = min_moves + 2  # enter terminal state, then execute bug action
        path_valid = validate_solution_path(official_path, maze, dimension)
        official_length_matches = len(official_transactions) == len(official_path) + 1
        source_semantics_checked = (
            "function step(int8[] calldata inp) external" in source_text and
            "function func_bug(int8[] memory inp) internal" in source_text and
            "bug = true;" in source_text and
            "function echidna_noBug() external returns (bool) {return !bug;}" in source_text and
            verify_one_cell_transition_per_step(source_text))
        if not path_valid or not official_length_matches or not source_semantics_checked:
            raise ValueError("official route/source validation failed for " + sample["sample_id"])
        classification = ("已验证8笔内可达" if shortest_transactions <= 8
                          else "已证明8笔内不可达")
        row = {
            "sample_id": sample["sample_id"],
            "dimension": dimension,
            "algorithm": sample["algorithm"],
            "official_answer_transactions": len(official_transactions),
            "official_answer_over_8": len(official_transactions) > 8,
            "shortest_cell_moves": min_moves,
            "shortest_target_transactions": shortest_transactions,
            "within_8_classification": classification,
            "maze_hash_verified": True,
            "official_path_legal": path_valid,
            "official_transaction_length_matches_path": official_length_matches,
            "source_native_property_shape_verified": source_semantics_checked,
            "one_cell_transition_per_step_verified": verify_one_cell_transition_per_step(source_text),
            "agent_sequence_or_extension_input": False,
        }
        rows.append(row)
        if sample["sample_id"] in native_ids:
            if not echidna:
                raise RuntimeError("Echidna binary is required for native oracle replay")
            source_path = PHASE43 / files["source"]["path"]
            native = run_native_oracle(
                sample, official_transactions,
                source_path,
                OUTPUT / "native-official-answer" / sample["sample_id"], echidna)
            native_rows.append(native)

    csv_path = OUTPUT / "可达性清单.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    by_dimension = {}
    for dimension in (5, 10, 15, 20):
        group = [row for row in rows if row["dimension"] == dimension]
        distances = [row["shortest_target_transactions"] for row in group]
        by_dimension[str(dimension)] = {
            "count": len(group),
            "official_answer_over_8": sum(row["official_answer_over_8"] for row in group),
            "verified_reachable_within_8": sum(
                row["shortest_target_transactions"] <= 8 for row in group),
            "proved_unreachable_within_8": sum(
                row["shortest_target_transactions"] > 8 for row in group),
            "undetermined": 0,
            "shortest_target_transactions_min": min(distances),
            "shortest_target_transactions_median": statistics.median(distances),
            "shortest_target_transactions_max": max(distances),
        }
    summary = {
        "phase": "Phase44",
        "baseline_commit": "6cc891129640546e014c84eb11ec84e8c96cf1f7",
        "phase43_manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "analysis": "BFS over frozen official maze graph; official solution used only to validate diagnostic path/length, never passed to sequence algorithms",
        "transaction_count_model": "Verified across all generated sources: step dispatches one state handler and returns; handlers use at most inp[0] and do not loop over the array. One call traverses one cell edge. Add one call to enter terminal state and one call to execute func_bug.",
        "fixed_sequence_limit_for_next_comparisons": MAX_SEQUENCE_LENGTH,
        "dimension_summary": by_dimension,
        "overall": {
            "count": len(rows),
            "official_answer_over_8": sum(row["official_answer_over_8"] for row in rows),
            "verified_reachable_within_8": sum(
                row["shortest_target_transactions"] <= 8 for row in rows),
            "proved_unreachable_within_8": sum(
                row["shortest_target_transactions"] > 8 for row in rows),
            "undetermined": 0,
        },
        "native_official_answer_replay": native_rows,
    }
    (OUTPUT / "可达性汇总.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--native-sample", action="append", default=[],
                        help="run an isolated Echidna testLimit=0 replay for this sample ID; repeatable")
    parser.add_argument("--native-all", action="store_true",
                        help="run the independent official-answer corpus replay for all 100 samples")
    parser.add_argument("--echidna", default=shutil.which("echidna") or "/usr/local/bin/echidna")
    args = parser.parse_args()
    ids = set(args.native_sample)
    if args.native_all:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
        ids.update(sample["sample_id"] for sample in manifest["dataset"]["samples"])
    if ids:
        version = subprocess.run([args.echidna, "--version"], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, check=True)
        (OUTPUT / "echidna-version.txt").parent.mkdir(parents=True, exist_ok=True)
        (OUTPUT / "echidna-version.txt").write_text(version.stdout, encoding="utf-8")
    result = audit(ids, args.echidna if ids else None)
    print(json.dumps(result["overall"], ensure_ascii=False, sort_keys=True))
    for dimension, summary in result["dimension_summary"].items():
        print("D{} {}".format(dimension, json.dumps(summary, ensure_ascii=False, sort_keys=True)))
    if result["native_official_answer_replay"]:
        passed = sum(row["status"] == "native_counterexample"
                     for row in result["native_official_answer_replay"])
        print("native official-answer property failures: {}/{}".format(
            passed, len(result["native_official_answer_replay"])))


if __name__ == "__main__":
    main()
