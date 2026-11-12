#!/usr/bin/env python3
"""从属性分析 JSON 构建可解释的共享依赖图，并保守地划分属性组。"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from itertools import combinations
from pathlib import Path


def features(prop: dict, mutable: set[str]) -> dict[str, set[str]]:
    states = {"self:" + state for state in prop["read_states"] if state in mutable}
    for observation in prop["cross_contract"]["observations"]:
        path = observation.get("receiver_path")
        if path:
            states.update("external:" + "/".join(path) + ":" + state
                          for state in observation["read_states"] if state in mutable)
    actions = {item["function"] for item in prop["candidate_actions"]
               if item.get("effect_ids")}
    actions.update(item["function"] for item in prop["cross_contract"]["candidate_actions"]
                   if item.get("effect_ids") and
                   item["status"] == "confirmed_static_path_candidate")
    setup = {item["function"] for state in prop["prerequisite_state_closure"]
             for item in state["possible_setup_actions"]}
    return {"states": states, "actions": actions, "setup": setup}


def pair_evidence(left: dict, right: dict) -> dict:
    shared = {kind: sorted(left[kind] & right[kind])
              for kind in ("states", "actions", "setup")}
    shared["supported"] = bool(shared["states"] and shared["actions"] or
                               len(shared["states"]) >= 2)
    shared["score"] = 2 * len(shared["states"]) + len(shared["actions"])
    return shared


def group_pairs(groups: list[list[str]]):
    return [tuple(sorted(pair)) for group in groups for pair in combinations(group, 2)]


def quality(groups: list[list[str]], edges: dict[tuple[str, str], dict],
            feats: dict[str, dict]) -> dict:
    pairs = group_pairs(groups)
    return {
        "within_pairs": len(pairs),
        "supported_pairs": sum(edges[pair]["supported"] for pair in pairs),
        "pairs_with_shared_setup": sum(bool(edges[pair]["setup"]) for pair in pairs),
        "shared_setup_pair_total": sum(len(edges[pair]["setup"]) for pair in pairs),
        "reused_state_features": sum(
            sum(len(feats[pid]["states"]) for pid in group)
            - len(set().union(*(feats[pid]["states"] for pid in group)))
            for group in groups),
        "reused_candidate_features": sum(
            sum(len(feats[pid]["actions"]) for pid in group)
            - len(set().union(*(feats[pid]["actions"] for pid in group)))
            for group in groups),
    }


def analyze(report: dict, trials: int, seed: int) -> dict:
    properties = report["properties"]
    by_id = {prop["property_id"]: prop for prop in properties}
    if len(by_id) != len(properties):
        raise ValueError("property_id 不唯一，无法安全分组")
    mutable = {effect["state"] for effect in report["effect_catalog"].values()}
    feats = {pid: features(prop, mutable) for pid, prop in by_id.items()}
    contexts: dict[tuple[str, str], list[str]] = defaultdict(list)
    for pid, prop in by_id.items():
        contexts[(prop["analysis_contract"], prop["analysis_contract_source"])].append(pid)
    edges: dict[tuple[str, str], dict] = {}
    for members in contexts.values():
        for left, right in combinations(sorted(members), 2):
            edges[(left, right)] = pair_evidence(feats[left], feats[right])
    groups = [{pid} for pid in by_id]
    for pair, evidence in sorted(edges.items(),
                                 key=lambda item: (-item[1]["score"], item[0])):
        if not evidence["supported"]:
            continue
        left_group = next(group for group in groups if pair[0] in group)
        right_group = next(group for group in groups if pair[1] in group)
        if left_group is right_group:
            continue
        common_states = set.intersection(*(feats[pid]["states"]
                                           for pid in left_group | right_group))
        if common_states and all(edges[tuple(sorted((a, b)))]["supported"]
                                 for a in left_group for b in right_group):
            left_group.update(right_group)
            groups.remove(right_group)
    grouped = sorted((sorted(group) for group in groups),
                     key=lambda group: (by_id[group[0]]["analysis_contract_source"],
                                        by_id[group[0]]["analysis_contract"], group))
    singleton = [[pid] for pid in by_id]
    rng = random.Random(seed)
    random_metrics = []
    for _ in range(trials):
        random_groups = []
        for context, members in contexts.items():
            sizes = [len(group) for group in grouped
                     if (by_id[group[0]]["analysis_contract"],
                         by_id[group[0]]["analysis_contract_source"]) == context]
            shuffled = sorted(members)
            rng.shuffle(shuffled)
            offset = 0
            for size in sizes:
                random_groups.append(shuffled[offset:offset + size])
                offset += size
        random_metrics.append(quality(random_groups, edges, feats))
    selected = quality(grouped, edges, feats)
    return {
        "input_properties": len(properties),
        "group_count": len(grouped),
        "grouped_properties": sum(len(group) for group in grouped if len(group) > 1),
        "groups": [{"members": [{"property_id": pid,
                                  "property": by_id[pid]["property"],
                                  "analysis_contract": by_id[pid]["analysis_contract"],
                                  "analysis_contract_source": by_id[pid]["analysis_contract_source"]}
                                 for pid in group],
                    "shared_core": {
                        kind: sorted(set.intersection(*(feats[pid][kind] for pid in group)))
                        for kind in ("states", "actions", "setup")
                    },
                    "pair_evidence": [{"left": pair[0], "right": pair[1],
                                       **edges[pair]}
                                      for pair in group_pairs([group])]}
                   for group in grouped],
        "graph": [{"left": pair[0], "right": pair[1], **evidence}
                  for pair, evidence in edges.items() if evidence["supported"]],
        "evaluation": {
            "independent": quality(singleton, edges, feats),
            "grouped": selected,
            "matched_random": {"trials": trials,
                               "mean": {key: sum(item[key] for item in random_metrics) / trials
                                        for key in selected},
                               "max": {key: max(item[key] for item in random_metrics)
                                       for key in selected}},
        },
        "method": "同一分析合约内：共享可写状态和有写入证据的候选函数，或共享至少两个可写状态；完全连接合并，且全组至少共享一个状态；可能实例别名只保留在原报告，不作为分组证据。前置操作仅用于独立评价。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True,
                        help="项目名=属性分析 JSON 路径，可重复")
    parser.add_argument("--output", required=True)
    parser.add_argument("--random-trials", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if args.random_trials < 1:
        parser.error("--random-trials 必须大于零")
    result = {"schema_version": "1.0", "random_seed": args.seed, "projects": {}}
    for item in args.input:
        name, separator, path = item.partition("=")
        if not separator or not name or not path:
            parser.error("--input 应为 项目名=JSON路径")
        report = json.loads(Path(path).read_text(encoding="utf-8"))
        result["projects"][name] = {"input_file": path,
                                    **analyze(report, args.random_trials, args.seed)}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    for name, project in result["projects"].items():
        print(f"{name}: 属性 {project['input_properties']}，组 {project['group_count']}，"
              f"参与共享组 {project['grouped_properties']}")


if __name__ == "__main__":
    main()
