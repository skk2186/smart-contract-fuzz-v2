#!/usr/bin/env python3
"""从同一 Agent A 信息投影无损构造三种上下文布局并计数。"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from pathlib import Path


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def effect_ids(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"effect_ids", "evidence_ids"} and isinstance(item, list):
                yield from (x for x in item if isinstance(x, str))
            else:
                yield from effect_ids(item)
    elif isinstance(value, list):
        for item in value:
            yield from effect_ids(item)


def guard_view(guard):
    return {key: guard[key] for key in (
        "kind", "function", "expression", "branch", "source", "state_reads",
        "variables_read", "data_dependencies", "predicate_calls", "predicate_logic",
        "predicate_returns", "external_calls")
        if key in guard}


def effect_view(effect):
    """Agent A 所需投影：保留全部守卫表达式、分支路径、调用绑定和源码位置。"""
    result = {key: effect[key] for key in (
        "state", "receiver", "receiver_scope", "receiver_path", "writer", "expression",
        "index_accesses", "source_index_accesses", "source", "call_path",
        "expression_call_constraints", "resolution") if key in effect}
    guards = {}

    def ref(guard):
        item = guard_view(guard)
        key = hashlib.sha256(compact(item).encode()).hexdigest()[:16]
        guards[key] = item
        return key

    result["guards"] = [ref(g) for g in effect.get("guards", [])]
    result["cfg_guard_alternatives"] = [
        {"function": alt.get("function"), "truncated": alt.get("truncated"),
         "paths": [[ref(g) for g in path] for path in alt.get("paths", [])]}
        for alt in effect.get("cfg_guard_alternatives", [])]
    result["guard_catalog"] = guards
    return result


def project_property(prop, catalog, blocks):
    """保留所有原属性字段，仅把列表项变为可重建的内容地址引用。"""
    core = copy.deepcopy(prop)
    refs = {}
    for field in ("read_sites", "candidate_actions", "prerequisite_state_closure", "unknowns"):
        if isinstance(core.get(field), list):
            refs[field] = []
            for item in core.pop(field):
                key = hashlib.sha256(compact([field, item]).encode()).hexdigest()[:20]
                blocks[key] = item
                refs[field].append(key)
    if isinstance(core.get("cross_contract"), dict):
        for field in list(core["cross_contract"]):
            if isinstance(core["cross_contract"][field], list):
                path = "cross_contract." + field
                refs[path] = []
                for item in core["cross_contract"].pop(field):
                    key = hashlib.sha256(compact([path, item]).encode()).hexdigest()[:20]
                    blocks[key] = item
                    refs[path].append(key)
    ids = sorted(set(effect_ids(prop)))
    missing = set(ids) - set(catalog)
    if missing:
        raise ValueError(f"{prop['property_id']} 缺失效果证据: {sorted(missing)}")
    return {"core": core, "refs": refs, "effect_ids": ids}


def recover(record, blocks):
    prop = copy.deepcopy(record["core"])
    for path, ids in record["refs"].items():
        target = prop
        keys = path.split(".")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = [blocks[key] for key in ids]
    return prop


def selected_blocks(records, blocks):
    keys = sorted({key for record in records for ids in record["refs"].values() for key in ids})
    return {key: blocks[key] for key in keys}


def selected_effects(records, catalog):
    keys = sorted({key for record in records for key in record["effect_ids"]})
    return {key: catalog[key] for key in keys}


def build(report, grouping, timings=None):
    tick = time.perf_counter_ns()
    originals = {p["property_id"]: p for p in report["properties"]}
    if len(originals) != len(report["properties"]):
        raise ValueError("原报告存在重复 property_id")
    # 同一任务投影同时供三种布局使用；比较的是布局，不把原报告中不进入 Agent A 的辅助字段计入。
    keep = {"property", "source", "property_id", "analysis_contract", "analysis_contract_source",
            "read_states", "property_write_states", "environment_reads", "balance_observations",
            "read_sites", "candidate_actions", "cross_contract", "evidence_ids", "analysis_status",
            "context_status", "dependency_status", "unresolved_effect_actions",
            "prerequisite_state_closure", "unknowns"}
    projected = {pid: {key: value for key, value in prop.items() if key in keep}
                 for pid, prop in originals.items()}
    catalog = {key: effect_view(value) for key, value in report["effect_catalog"].items()}
    for effect_id, original in report["effect_catalog"].items():
        view = catalog[effect_id]
        if any(view.get(key) != original.get(key) for key in
               ("state", "writer", "expression", "source", "call_path") if key in original):
            raise AssertionError(f"效果来源或调用路径丢失: {effect_id}")
        restored = [view["guard_catalog"][key] for key in view["guards"]]
        if restored != [guard_view(g) for g in original.get("guards", [])]:
            raise AssertionError(f"守卫丢失: {effect_id}")
        restored_paths = [[[view["guard_catalog"][key] for key in path]
                           for path in alt["paths"]]
                          for alt in view["cfg_guard_alternatives"]]
        original_paths = [[[guard_view(g) for g in path] for path in alt.get("paths", [])]
                          for alt in original.get("cfg_guard_alternatives", [])]
        if restored_paths != original_paths:
            raise AssertionError(f"控制流守卫路径丢失: {effect_id}")
    if timings is not None:
        timings["context_projection_ms"] = (time.perf_counter_ns() - tick) / 1_000_000
    tick = time.perf_counter_ns()
    blocks = {}
    records = {pid: project_property(prop, catalog, blocks)
               for pid, prop in projected.items()}
    members = [[item["property_id"] for item in group["members"]]
               for group in grouping["groups"]]
    found = [pid for group in members for pid in group]
    if len(found) != len(set(found)) or set(found) != set(originals):
        raise ValueError("分组未恰好保留全部属性")
    for pid, record in records.items():
        if recover(record, blocks) != projected[pid]:
            raise AssertionError(f"属性上下文重建失败: {pid}")
    # ① 独立请求：属性自身全部上下文和关联效果证据在本次请求中展开。
    independent = []
    for pid, record in records.items():
        independent.append({"property": recover(record, blocks),
                            "effect_catalog": selected_effects([record], catalog)})
    # ② 一个项目级共享目录，属性仍保持逐条记录。
    all_records = [records[pid] for pid in originals]
    global_shared = {"context_blocks": selected_blocks(all_records, blocks),
                     "effect_catalog": selected_effects(all_records, catalog),
                     "properties": all_records}
    # ③ 同一分组只出现一次上下文；跨组重复不隐式共享。
    grouped = []
    for group in members:
        subset = [records[pid] for pid in group]
        grouped.append({"context_blocks": selected_blocks(subset, blocks),
                        "effect_catalog": selected_effects(subset, catalog),
                        "properties": subset})
    if timings is not None:
        timings["context_dedup_ms"] = (time.perf_counter_ns() - tick) / 1_000_000
    return {"independent": independent, "global_shared": global_shared,
            "grouped": grouped, "member_groups": members,
            "audit": {"properties": len(projected),
                      "candidate_actions": sum(len(p.get("candidate_actions", [])) +
                                               len(p.get("cross_contract", {}).get("candidate_actions", []))
                                               for p in projected.values()),
                      "unknown_items": sum(len(p.get("unknowns", [])) for p in projected.values()),
                      "referenced_effects": len(selected_effects(all_records, catalog)),
                      "guard_occurrences": sum(len(e.get("guards", [])) +
                                               sum(len(path) for alt in e.get("cfg_guard_alternatives", [])
                                                   for path in alt.get("paths", []))
                                               for e in selected_effects(all_records, catalog).values()),
                      "same_projection_rebuilt": True}}


def token_count(payload, encoder):
    return len(encoder.encode(compact(payload)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grouping", default=".tools/results/属性关联分组.json")
    parser.add_argument("--output", default=".tools/results/属性上下文压缩结果.json")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".tools/tokenizer"))
    import tiktoken

    enc = tiktoken.get_encoding("o200k_base")
    grouping = json.loads(Path(args.grouping).read_text(encoding="utf-8"))
    result = {"tokenizer": "tiktoken 0.14.0 / o200k_base", "projects": {}}
    for name, group_data in grouping["projects"].items():
        source = json.loads(Path(group_data["input_file"]).read_text(encoding="utf-8"))
        layouts = build(source, group_data)
        counts = {"independent": sum(map(lambda x: token_count(x, enc), layouts["independent"])),
                  "global_shared": token_count(layouts["global_shared"], enc),
                  "grouped": sum(map(lambda x: token_count(x, enc), layouts["grouped"]))}
        maxima = {"independent": max(token_count(x, enc) for x in layouts["independent"]),
                  "global_shared": counts["global_shared"],
                  "grouped": max(token_count(x, enc) for x in layouts["grouped"])}
        result["projects"][name] = {"properties": len(layouts["independent"]),
                                    "groups": len(layouts["grouped"]),
                                    "payload_tokens": counts,
                                    "largest_payload_tokens": maxima,
                                    "retention_audit": layouts["audit"]}
        print(name, counts)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
