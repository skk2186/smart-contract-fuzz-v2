#!/usr/bin/env python3
"""为缓存、随机批处理、受控规模和当前分组生成同属性集合的输入。"""

import json
import random
import sys
from pathlib import Path

from AgentA对照准备 import INSTRUCTION, split_six
from 属性上下文压缩 import build, compact


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".tools/results/分组预算对照输入.json"


def split_limit(props, limit):
    if limit == 6:
        return split_six(props)
    features = {p["property_id"]: (
        {"s:" + state for state in p.get("read_states", [])} |
        {"a:" + action["function"] for action in p.get("candidate_actions", [])})
        for p in props}
    common = set.intersection(*features.values())
    for key in features:
        features[key] -= common
    remaining = set(features)
    groups = []
    while remaining:
        seed = max(sorted(remaining), key=lambda x: (len(features[x]), x))
        group = [seed]
        remaining.remove(seed)
        while remaining and len(group) < limit:
            next_id = max(sorted(remaining), key=lambda x: (
                sum(len(features[x] & features[y]) for y in group), x))
            group.append(next_id)
            remaining.remove(next_id)
        groups.append(group)
    return groups


def cache_requests(global_shared):
    records = global_shared["properties"]
    block_sets = [{x for ids in record["refs"].values() for x in ids} for record in records]
    effect_sets = [set(record["effect_ids"]) for record in records]
    common_blocks = set.intersection(*block_sets)
    common_effects = set.intersection(*effect_sets)
    shared_blocks = global_shared["context_blocks"]
    shared_effects = global_shared["effect_catalog"]
    result = []
    for record, block_keys, effect_keys in zip(records, block_sets, effect_sets):
        result.append({
            "context_blocks": {key: shared_blocks[key] for key in sorted(common_blocks)},
            "effect_catalog": {key: shared_effects[key] for key in sorted(common_effects)},
            "requests": [{"context_blocks": {key: shared_blocks[key] for key in sorted(block_keys - common_blocks)},
                          "effect_catalog": {key: shared_effects[key] for key in sorted(effect_keys - common_effects)},
                          "properties": [record]}],
        })
    return result


def grouped_payloads(report, groups):
    return build(report, {"groups": [{"members": [{"property_id": pid} for pid in group]}
                                     for group in groups]})["grouped"]


def main():
    sys.path.insert(0, str(ROOT / ".tools/tokenizer"))
    import tiktoken
    encoder = tiktoken.get_encoding("o200k_base")
    original = json.loads((ROOT / ".tools/results/AgentA对照输入.json").read_text(encoding="utf-8"))
    grouping = json.loads((ROOT / ".tools/results/属性关联分组.json").read_text(encoding="utf-8"))
    instruction = INSTRUCTION + " 输入可能有 requests 数组：先合并顶层与每个 request 的 context_blocks、effect_catalog，再逐条处理 properties。"
    out = {"model_task_instruction": instruction, "model": "gpt-6.1-sol",
           "seed": 20261112, "repetitions": {"Request": 3, "Immutable": 3}, "cases": {}}
    for case, limit in (("Request", 3), ("Immutable", 6)):
        ids = original["cases"][case]["property_ids"]
        source = json.loads((ROOT / grouping["projects"][case]["input_file"]).read_text(encoding="utf-8"))
        selected = [p for p in source["properties"] if p["property_id"] in ids]
        report = {"properties": selected, "effect_catalog": source["effect_catalog"]}
        base = build(report, {"groups": [{"members": [{"property_id": pid} for pid in ids]}]})
        controlled = split_limit(selected, limit)
        sizes = [len(group) for group in controlled]
        cache = cache_requests(base["global_shared"])
        case_data = {"property_ids": ids, "controlled_groups": controlled,
                     "random_groups": {}, "runs": {}, "payload_tokens": {}}
        for rep in range(1, out["repetitions"][case] + 1):
            shuffled = ids.copy()
            random.Random(out["seed"] + rep).shuffle(shuffled)
            offset = 0
            random_groups = []
            for size in sizes:
                random_groups.append(shuffled[offset:offset + size])
                offset += size
            case_data["random_groups"][str(rep)] = random_groups
            variants = {
                "cache": cache,
                "random": grouped_payloads(report, random_groups),
                "controlled": grouped_payloads(report, controlled),
                "current_group": base["grouped"],
            }
            for method, payloads in variants.items():
                key = f"r{rep}_{method}"
                case_data["runs"][key] = payloads
                case_data["payload_tokens"][key] = [len(encoder.encode(instruction + "\n" + compact(x)))
                                                    for x in payloads]
                got = []
                for payload in payloads:
                    if "requests" in payload:
                        got.extend(x["core"]["property_id"] for req in payload["requests"]
                                   for x in req["properties"])
                    else:
                        got.extend(x["core"]["property_id"] for x in payload["properties"])
                if len(got) != len(ids) or set(got) != set(ids):
                    raise AssertionError(f"{case} {key} 未恰好保留全部属性")
        out["cases"][case] = case_data
        print(case, "attributes", len(ids), "batch_sizes", sizes,
              "per_rep_calls", {k: len(v) for k, v in variants.items()})
    OUTPUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
