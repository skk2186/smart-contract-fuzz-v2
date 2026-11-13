#!/usr/bin/env python3
"""运行 Agent A/B → ABI 校验 → Anvil 回放 → Echidna 原生语料闭环。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from AgentA import generate_candidates
from AgentB import instantiate_candidate
from deepseek接口 import DeepSeekCallError
from 属性种子上下文 import PROJECTS, find_property, load_project_context, read_json
from 种子验证 import AnvilSession, new_seed_id, replay_seed, run_echidna, write_corpus


ROOT = Path(__file__).resolve().parents[2]
GROUPS = ROOT / ".tools/results/属性关联分组.json"
DEFAULT_PROPERTIES = {
    "Hokusai": "echidna_investor_cap",
    "Request": "echidna_token_conservation",
    "Immutable": "echidna_group_occupancy",
}


def _group_property_ids(project: str, group_index: int) -> list[str]:
    groups = read_json(GROUPS)
    values = groups["projects"][project]["groups"]
    if group_index < 0 or group_index >= len(values):
        raise ValueError(f"{project} 分组索引 {group_index} 超出范围")
    return [member["property_id"] for member in values[group_index].get("members", [])]


def _load_ids(project: str, property_ids: list[str], contains: list[str],
              group_index: int | None) -> list[str]:
    if group_index is not None:
        return _group_property_ids(project, group_index)
    ids = list(property_ids)
    for query in contains:
        ids.append(find_property(project, query))
    if not ids:
        ids.append(find_property(project, DEFAULT_PROPERTIES[project]))
    return list(dict.fromkeys(ids))


def _candidate_context(candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    return {**candidate, "project": context["project"], "context": context,
            "property": next(p["property"] for p in context["properties"]
                             if p["property_id"] == candidate["property_id"])}


def _attempt_agent_b(context: dict[str, Any], candidate: dict[str, Any], max_repairs: int):
    feedback = None
    events = []
    for attempt in range(1, max_repairs + 2):
        try:
            data, event = instantiate_candidate(context, candidate, feedback=feedback, attempt=attempt)
            events.append(event)
            return data, events
        except DeepSeekCallError as exc:
            if exc.event:
                events.append(exc.event)
            else:
                events.append({"ok": False, "error_kind": exc.kind, "error": str(exc)})
            feedback = ("上次响应未通过本地 ABI/交易结构校验。请按同一计划修正。错误：" + str(exc))[:1200]
            if attempt > max_repairs:
                raise
    raise AssertionError("unreachable")


def run_project(project: str, property_ids: list[str], *, max_candidates: int,
                max_steps: int, repairs: int, echidna_limit: int,
                echidna_timeout: int, run_fuzzer: bool) -> dict[str, Any]:
    started = time.monotonic()
    context = load_project_context(project, property_ids)
    missing_predicates = [p["property_id"] for p in context["properties"]
                          if not p.get("property_predicate")]
    if missing_predicates:
        raise ValueError(f"缺少可定位的属性谓词源码：{missing_predicates}")
    actions = {p["property_id"]: sum(bool(a.get("seed_compatible"))
                                      for a in p["candidate_actions"])
               for p in context["properties"]}
    if not any(actions.values()):
        raise ValueError(f"所选属性均没有匹配 Harness ABI 的可序列化状态入口：{actions}")

    plan, agent_a_event = generate_candidates(
        context, max_candidates=max_candidates, max_steps=max_steps,
        tag=f"AgentA_{project}_{'_'.join(property_ids)}")
    candidates = plan.get("property_sequences", [])
    results = []
    experiment_id = uuid.uuid4().hex
    run_root = ROOT / f"deepseek/结果/Agent种子语料/{project}/{experiment_id}"
    corpus_root = run_root / "种子包"
    corpus_root.mkdir(parents=True, exist_ok=True)
    (corpus_root / "coverage").mkdir(exist_ok=True)

    if candidates:
        with AnvilSession() as session:
            for candidate in candidates:
                candidate = _candidate_context(candidate, context)
                try:
                    concrete, agent_b_events = _attempt_agent_b(context, candidate, repairs)
                    replay = replay_seed(project, candidate, concrete["transactions"], session=session)
                    corpus_file = None
                    seed_id = None
                    if replay["replay_status"] == "executable":
                        seed_id = new_seed_id()
                        corpus_file = write_corpus(project, candidate, concrete["transactions"],
                                                   context, corpus_root, replay=replay,
                                                   seed_id=seed_id)
                    results.append({"candidate_id": candidate["candidate_id"],
                                    "property_id": candidate["property_id"],
                                    "seed_id": seed_id,
                                    "plan": candidate["steps"], "seed": concrete,
                                    "agent_b_calls": agent_b_events, "replay": replay,
                                    "corpus_file": str(corpus_file.relative_to(ROOT)) if corpus_file else None,
                                    "status": "abi_encoded_and_replayed" if corpus_file else "replay_failed"})
                except Exception as exc:
                    results.append({"candidate_id": candidate.get("candidate_id"),
                                    "property_id": candidate.get("property_id"),
                                    "plan": candidate.get("steps"),
                                    "status": "candidate_error",
                                    "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
    echidna = []
    if run_fuzzer and results:
        properties_by_id = {p["property_id"]: p["property"].rsplit(".", 1)[-1].split("(", 1)[0]
                            for p in context["properties"]}
        for property_id, property_name in properties_by_id.items():
            campaign_root = run_root / "Echidna" / property_id
            coverage = campaign_root / "coverage"
            coverage.mkdir(parents=True, exist_ok=True)
            for row in results:
                if row.get("property_id") == property_id and row.get("corpus_file"):
                    source = ROOT / row["corpus_file"]
                    shutil.copy2(source, coverage / source.name)
            echidna.append(run_echidna(project, campaign_root, property_name=property_name,
                                       test_limit=echidna_limit,
                                       timeout=echidna_timeout, seed=20261113))
    return {"project": project, "property_ids": property_ids,
            "property_count": len(context["properties"]), "action_counts": actions,
            "agent_a": agent_a_event, "agent_a_output": plan,
            "candidates": results, "echidna": echidna,
            "experiment_id": experiment_id,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=list(PROJECTS))
    parser.add_argument("--property-id", action="append", default=[])
    parser.add_argument("--property-contains", action="append", default=[])
    parser.add_argument("--group-index", type=int)
    parser.add_argument("--max-candidates", type=int, default=2)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--repairs", type=int, default=1)
    parser.add_argument("--echidna-limit", type=int, default=80)
    parser.add_argument("--echidna-timeout", type=int, default=45)
    parser.add_argument("--skip-echidna", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_candidates <= 4 or not 1 <= args.max_steps <= 12:
        parser.error("候选数应为 1–4，序列长度应为 1–12")
    property_ids = _load_ids(args.project, args.property_id,
                             args.property_contains, args.group_index)
    result = run_project(args.project, property_ids,
                         max_candidates=args.max_candidates,
                         max_steps=args.max_steps, repairs=args.repairs,
                         echidna_limit=args.echidna_limit,
                         echidna_timeout=args.echidna_timeout,
                         run_fuzzer=not args.skip_echidna)
    output = ROOT / f"deepseek/结果/{args.project}-Agent种子闭环.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"project": args.project, "properties": len(property_ids),
                      "candidates": len(result["candidates"]),
                      "status": [item["status"] for item in result["candidates"]],
                      "echidna_exit": [item.get("exit_code") for item in result["echidna"]],
                      "output": str(output)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

