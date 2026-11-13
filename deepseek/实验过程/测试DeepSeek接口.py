#!/usr/bin/env python3
"""用三个固定真实属性测试 DeepSeek JSON、用量和错误记录。"""

import json
from pathlib import Path

from deepseek接口 import DeepSeekCallError, call_json


ROOT = Path(__file__).resolve().parents[2]
INPUTS = (
    ("Hokusai", ".tools/results/hokusai-full-final.json", "echidna_claimable_plus_claimed_eq_vested"),
    ("Request", ".tools/results/request-property.json", "echidna_token_conservation"),
    ("Immutable", ".tools/results/immutable-full-final.json", "echidna_group_occupancy"),
)


def main():
    results = []
    for name, file, anchor in INPUTS:
        report = json.loads((ROOT / file).read_text(encoding="utf-8"))
        prop = next(p for p in report["properties"] if anchor in p["property"])
        summary = {"property_id": prop["property_id"], "property": prop["property"],
                   "source": prop["source"],
                   "candidate_actions": [a["function"] for a in prop["candidate_actions"]] +
                                        [a["function"] for a in prop["cross_contract"]["candidate_actions"]],
                   "unknowns": prop["unknowns"]}

        def validate(data, expected=prop["property_id"]):
            if data.get("property_id") != expected or not isinstance(data.get("candidate_count"), int):
                raise DeepSeekCallError("schema_mismatch", "属性身份或候选计数类型不符")

        data, event = call_json(
            system="只根据输入数据回答。严格输出 JSON 对象，字段为 property_id、candidate_count、unknown_count。",
            user=json.dumps(summary, ensure_ascii=False), tag="smoke_" + name,
            max_tokens=256, validator=validate)
        row = {"project": name, "property_id": prop["property_id"],
               "candidate_count_expected": len(summary["candidate_actions"]),
               "candidate_count_returned": data["candidate_count"],
               "unknown_count_expected": len(summary["unknowns"]),
               "unknown_count_returned": data.get("unknown_count"),
               "usage": event["usage"], "elapsed_seconds": event["elapsed_seconds"]}
        results.append(row)
        print(name, "status=ok", "tokens=", event["usage"]["total_tokens"], flush=True)
    output = ROOT / "deepseek/结果/DeepSeek接口固定属性测试.json"
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
