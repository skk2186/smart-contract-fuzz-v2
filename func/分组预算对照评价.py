#!/usr/bin/env python3
"""按完整重复运行汇总预算、模型成本和结构化响应质量。"""

import json
import statistics
from collections import Counter
from pathlib import Path

from 属性上下文压缩 import recover


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / ".tools/results/分组预算对照输入.json"
LOG = ROOT / ".tools/results/分组预算对照调用.jsonl"
OUT = ROOT / ".tools/results/分组预算对照评价.json"
BUDGET = {"Request": 380_000, "Immutable": 600_000}
METHODS = ("cache", "random", "controlled", "current_group")


def properties_from_payload(payload):
    parts = payload.get("requests", [payload])
    for part in parts:
        blocks = dict(payload.get("context_blocks", {}))
        blocks.update(part.get("context_blocks", {}))
        for record in part["properties"]:
            yield recover(record, blocks)


def evaluate_run(payloads, rows, expected):
    expected_by_index = []
    allowed = {}
    for payload in payloads:
        ids = []
        for prop in properties_from_payload(payload):
            pid = prop["property_id"]
            ids.append(pid)
            allowed[pid] = {x["function"] for x in prop.get("candidate_actions", [])}
            allowed[pid].update(x["function"] for x in
                                prop.get("cross_contract", {}).get("candidate_actions", []))
        expected_by_index.append(ids)
    used = [row for row in rows if row.get("usage")]
    answered = []
    json_failures = 0
    wrong_functions = []
    overlong_sequences = 0
    no_uncertainty = 0
    nonempty = 0
    repeated_functions = 0
    prefix_ids = Counter()
    for row in rows:
        if row.get("exit_code") != 0 or not row.get("response"):
            continue
        try:
            result = json.loads(row["response"])
        except json.JSONDecodeError:
            json_failures += 1
            continue
        for item in result.get("properties", []):
            pid = item.get("property_id")
            answered.append(pid)
            calls = item.get("calls", [])
            nonempty += bool(calls)
            overlong_sequences += len(calls) > 4
            no_uncertainty += not bool(item.get("uncertainties"))
            names = [x.get("function") for x in calls]
            repeated_functions += len(names) - len(set(names))
            wrong_functions.extend((pid, name) for name in names
                                   if name not in allowed.get(pid, set()))
            prefix = item.get("shared_prefix_id")
            if prefix:
                prefix_ids[prefix] += 1
    usage = {key: sum((row["usage"] or {}).get(key, 0) for row in used)
             for key in ("input_tokens", "cached_input_tokens", "output_tokens")}
    complete = (len(rows) == len(payloads) and all(row.get("exit_code") == 0 for row in rows)
                and len(answered) == len(expected) and set(answered) == set(expected)
                and len(set(answered)) == len(answered))
    return {
        "complete": complete, "expected_properties": len(expected),
        "attempted_calls": len(rows), "planned_calls": len(payloads),
        "successful_calls": len(used), "response_properties": len(answered),
        "missing_properties": sorted(set(expected) - set(answered)),
        "nonempty_templates": nonempty,
        "confirmed_executable_sequences": None,
        "wrong_candidate_functions": wrong_functions,
        "overlong_sequences": overlong_sequences,
        "responses_without_uncertainty": no_uncertainty,
        "invalid_json_responses": json_failures,
        "repeated_functions_within_sequences": repeated_functions,
        "shared_prefix_ids_used_by_multiple_properties": sum(v > 1 for v in prefix_ids.values()),
        "usage": usage,
        "input_plus_output_tokens": usage["input_tokens"] + usage["output_tokens"],
        "total_wall_seconds": round(sum(row.get("elapsed_seconds", 0) for row in rows), 2),
        "failures": [row.get("errors", []) for row in rows if row.get("exit_code") != 0],
    }


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    rows = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()]
    indexed = {(row["case"], row["run_key"], row["index"]): row for row in rows}
    result = {"model": data["model"], "budget_input_plus_output_tokens": BUDGET,
              "projects": {}}
    for case, case_data in data["cases"].items():
        expected = case_data["property_ids"]
        project = {"repetitions": {}, "method_summary_complete_runs_only": {}}
        for rep in range(1, data["repetitions"][case] + 1):
            trial = {}
            for method in METHODS:
                key = f"r{rep}_{method}"
                payloads = case_data["runs"][key]
                found = [indexed[(case, key, i)] for i in range(len(payloads))
                         if (case, key, i) in indexed]
                trial[method] = evaluate_run(payloads, found, expected)
            project["repetitions"][str(rep)] = trial
        for method in METHODS:
            complete = [r[method] for r in project["repetitions"].values()
                        if r[method]["complete"]]
            if complete:
                project["method_summary_complete_runs_only"][method] = {
                    "complete_repetitions": len(complete),
                    "input_tokens_median": statistics.median(r["usage"]["input_tokens"] for r in complete),
                    "input_tokens_range": [min(r["usage"]["input_tokens"] for r in complete),
                                           max(r["usage"]["input_tokens"] for r in complete)],
                    "nonempty_templates_median": statistics.median(r["nonempty_templates"] for r in complete),
                    "wall_seconds_median": statistics.median(r["total_wall_seconds"] for r in complete),
                }
        paired = [rep for rep, trial in project["repetitions"].items()
                  if all(trial[method]["complete"] for method in METHODS)]
        project["paired_repetitions"] = paired
        project["paired_summary"] = {}
        for method in METHODS:
            values = [project["repetitions"][rep][method] for rep in paired]
            if not values:
                continue
            project["paired_summary"][method] = {
                "runs": len(values),
                "model_calls": values[0]["planned_calls"],
                "input_tokens_median": statistics.median(v["usage"]["input_tokens"] for v in values),
                "input_tokens_range": [min(v["usage"]["input_tokens"] for v in values),
                                       max(v["usage"]["input_tokens"] for v in values)],
                "cached_input_tokens_median": statistics.median(v["usage"]["cached_input_tokens"]
                                                                  for v in values),
                "output_tokens_median": statistics.median(v["usage"]["output_tokens"] for v in values),
                "wall_seconds_median": statistics.median(v["total_wall_seconds"] for v in values),
                "wall_seconds_range": [min(v["total_wall_seconds"] for v in values),
                                       max(v["total_wall_seconds"] for v in values)],
                "nonempty_templates": [v["nonempty_templates"] for v in values],
                "all_structural_checks_passed": all(not v["missing_properties"] and
                                                      not v["wrong_candidate_functions"] and
                                                      not v["invalid_json_responses"] and
                                                      not v["overlong_sequences"] for v in values),
            }
        failures = [row for row in rows if row["case"] == case and row.get("exit_code") != 0]
        project["service_failures"] = {
            "attempts": len(failures),
            "elapsed_seconds": round(sum(row.get("elapsed_seconds", 0) for row in failures), 2),
            "quota": sum("usage limit" in json.dumps(row.get("errors", [])).lower()
                         for row in failures),
            "cybersecurity_review": sum("cybersecurity risk" in json.dumps(row.get("errors", [])).lower()
                                        for row in failures),
        }
        result["projects"][case] = project
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for case, project in result["projects"].items():
        print(case, {method: item["complete_repetitions"] for method, item in
                     project["method_summary_complete_runs_only"].items()})


if __name__ == "__main__":
    main()
