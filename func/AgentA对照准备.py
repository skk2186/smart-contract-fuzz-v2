#!/usr/bin/env python3
"""准备相同任务、相同属性集合的 Agent A 对照输入。"""

import json
import sys
from pathlib import Path

from 属性上下文压缩 import build, compact


ROOT = Path(__file__).resolve().parents[1]
INSTRUCTION = """你是智能合约模糊测试的 Agent A。只依据所给 Slither 属性上下文规划原生多交易候选序列，不使用工具或读取文件。输入中的 effect_catalog 和 context_blocks 按 ID 引用；同一组可共享上下文，但每条 property_id 必须独立输出，不能合并属性约束。每条属性最多给一条序列，每条序列最多四次调用。调用函数必须来自该属性的 candidate_actions 或 cross_contract.candidate_actions；只给符号参数条件和发送者角色，不猜测具体值。区分明确证据和 unknown；若证据不足，给空 calls 并说明。严格输出一个 JSON 对象：{"properties":[{"property_id":"...","calls":[{"function":"完整签名","arguments":"符号约束","sender":"角色","value":"符号金额或0"}],"shared_prefix_id":"可空字符串","reason":"一句依据","uncertainties":["..."]}]}。不要宣称已验证可执行性。"""


def split_six(props):
    """去掉大组公共特征后按次级读状态/动作做确定性贪心拆分。"""
    features = {}
    for p in props:
        features[p["property_id"]] = (
            {"s:" + x for x in p.get("read_states", [])} |
            {"a:" + x["function"] for x in p.get("candidate_actions", [])})
    common = set.intersection(*features.values())
    for key in features:
        features[key] -= common
    remaining = set(features)
    groups = []
    while remaining:
        seed = max(sorted(remaining), key=lambda key: (len(features[key]), key))
        group = [seed]
        remaining.remove(seed)
        while remaining and len(group) < 6:
            next_id = max(sorted(remaining), key=lambda key: (
                sum(len(features[key] & features[member]) for member in group), key))
            group.append(next_id)
            remaining.remove(next_id)
        groups.append(group)
    return groups


def main():
    sys.path.insert(0, str(ROOT / ".tools/tokenizer"))
    import tiktoken
    enc = tiktoken.get_encoding("o200k_base")
    grouping = json.loads((ROOT / ".tools/results/属性关联分组.json").read_text(encoding="utf-8"))
    cases = {}
    for name, size, anchor in (
        ("Hokusai", 4, "RewardVestingVault"),
        ("Request", 5, "echidna_token_conservation"),
        ("Immutable", 18, "echidna_group_occupancy"),
    ):
        meta = grouping["projects"][name]
        original_group = next(g for g in meta["groups"] if len(g["members"]) == size and
                              any(anchor in p["property"] for p in g["members"]))
        ids = [p["property_id"] for p in original_group["members"]]
        report = json.loads((ROOT / meta["input_file"]).read_text(encoding="utf-8"))
        selected = [p for p in report["properties"] if p["property_id"] in ids]
        selected_report = {"properties": selected, "effect_catalog": report["effect_catalog"]}
        group_specs = {"grouped": [ids]}
        if name == "Immutable":
            group_specs["split"] = split_six(selected)
        cases[name] = {"property_ids": ids, "property_names": [p["property"] for p in selected],
                       "layouts": {}, "split_members": group_specs.get("split")}
        for label, groups in group_specs.items():
            layout = build(selected_report, {"groups": [
                {"members": [{"property_id": pid} for pid in group]} for group in groups]})
            if label == "grouped":
                cases[name]["layouts"]["independent"] = layout["independent"]
                cases[name]["layouts"]["global_shared"] = [layout["global_shared"]]
            cases[name]["layouts"][label] = layout["grouped"]
        cases[name]["tokens"] = {label: [len(enc.encode(INSTRUCTION + "\n" + compact(p)))
                                         for p in payloads]
                                 for label, payloads in cases[name]["layouts"].items()}
        print(name, {k: (len(v), sum(v), max(v)) for k, v in cases[name]["tokens"].items()})
    out = {"model_task_instruction": INSTRUCTION, "cases": cases}
    (ROOT / ".tools/results/AgentA对照输入.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


if __name__ == "__main__":
    main()
