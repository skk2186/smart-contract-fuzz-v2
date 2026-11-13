#!/usr/bin/env python3
"""核对 Agent A 响应的属性覆盖、候选函数归属与实际模型用量。"""

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".tools/results/AgentA对照输入.json"
LOG = ROOT / ".tools/results/AgentA调用记录.jsonl"
OUT = ROOT / ".tools/results/AgentA对照评价.json"


def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    logs = [json.loads(line) for line in LOG.read_text(encoding="utf-8").splitlines()]
    by_case = defaultdict(lambda: defaultdict(list))
    for item in logs:
        by_case[item["case"]][item["layout"]].append(item)
    result = {}
    for case, case_data in data["cases"].items():
        property_ids = set(case_data["property_ids"])
        result[case] = {}
        for layout, payloads in case_data["layouts"].items():
            if layout == "global_shared":
                continue  # 当前代表集合仅一个原组，与 grouped 输入完全相同
            rows = by_case[case][layout]
            expected = []
            allowed = {}
            for payload in payloads:
                if layout == "independent":
                    props = [payload["property"]]
                else:
                    blocks = payload["context_blocks"]
                    props = []
                    for record in payload["properties"]:
                        prop = dict(record["core"])
                        for path, ids in record["refs"].items():
                            target = prop
                            keys = path.split(".")
                            for key in keys[:-1]:
                                target = target[key]
                            target[keys[-1]] = [blocks[key] for key in ids]
                        props.append(prop)
                for prop in props:
                    pid = prop["property_id"]
                    expected.append(pid)
                    allowed[pid] = {x["function"] for x in prop.get("candidate_actions", [])}
                    allowed[pid].update(x["function"] for x in
                                        prop.get("cross_contract", {}).get("candidate_actions", []))
            found = []
            invalid = []
            nonempty = 0
            repeated_internal = 0
            json_errors = 0
            reason_without_evidence = 0
            no_uncertainty = 0
            for row in rows:
                if row.get("exit_code") != 0 or not row.get("response"):
                    continue
                try:
                    answer = json.loads(row["response"])
                except json.JSONDecodeError:
                    json_errors += 1
                    continue
                for p in answer.get("properties", []):
                    pid = p.get("property_id")
                    found.append(pid)
                    calls = p.get("calls", [])
                    if calls:
                        nonempty += 1
                    names = [call.get("function") for call in calls]
                    repeated_internal += len(names) - len(set(names))
                    for name in names:
                        if name not in allowed.get(pid, set()):
                            invalid.append({"property_id": pid, "function": name})
                    if not p.get("uncertainties"):
                        no_uncertainty += 1
                    if not p.get("reason"):
                        reason_without_evidence += 1
            totals = {key: sum((row.get("usage") or {}).get(key, 0) for row in rows)
                      for key in ("input_tokens", "cached_input_tokens", "output_tokens")}
            result[case][layout] = {
                "expected_properties": len(expected), "model_calls": len(rows),
                "successful_calls": sum(row.get("exit_code") == 0 for row in rows),
                "failed_calls": [row["index"] for row in rows if row.get("exit_code") != 0],
                "response_properties": len(found),
                "missing_properties": sorted(set(expected) - set(found)),
                "unexpected_properties": sorted(set(found) - property_ids),
                "duplicate_property_ids": len(found) - len(set(found)),
                "nonempty_candidate_sequences": nonempty,
                "confirmed_executable_sequences": None,
                "execution_validation": "未提供具体参数且未进行确定性回放，不能给出可执行数量",
                "candidate_function_mismatches": invalid,
                "repeated_function_within_sequences": repeated_internal,
                "responses_without_uncertainties": no_uncertainty,
                "responses_without_reason": reason_without_evidence,
                "invalid_json_responses": json_errors,
                "actual_model_tokens": totals,
                "total_wall_seconds": round(sum(row.get("elapsed_seconds", 0) for row in rows), 2),
            }
            print(case, layout, result[case][layout])
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
