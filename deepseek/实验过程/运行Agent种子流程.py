#!/usr/bin/env python3
"""逐属性运行 Agent A/B、Anvil 回放与 Echidna 原生语料注入。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能")]

from AgentA import generate_candidates
from AgentB import instantiate_candidate
from deepseek接口 import CallBudget, DeepSeekCallError
from 属性种子上下文 import PROJECTS, find_property, load_project_context
from 种子验证 import AnvilSession, new_seed_id, replay_seed, run_echidna, write_corpus


def _load_ids(project: str, property_ids: list[str], contains: list[str]) -> list[str]:
    ids = list(property_ids)
    ids.extend(find_property(project, query) for query in contains)
    if not ids:
        raise ValueError("请至少用 --property-id 或 --property-contains 指定一条属性")
    return list(dict.fromkeys(ids))


def _property_name(prop: dict[str, Any]) -> str:
    return prop["property"].rsplit(".", 1)[-1].split("(", 1)[0]


def _candidate_context(candidate: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    prop = next(item for item in context["properties"]
                if item["property_id"] == candidate["property_id"])
    return {**candidate, "project": context["project"], "context": context,
            "property": prop["property"]}


def _api_summary(log_path: Path) -> dict[str, Any]:
    rows = []
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    metered = [row.get("usage") for row in rows if isinstance(row.get("usage"), dict)]
    return {
        "request_attempts": len(rows),
        "failed_request_attempts": sum(not row.get("ok", False) for row in rows),
        "unmetered_attempts": sum(not isinstance(row.get("usage"), dict) for row in rows),
        "prompt_tokens": sum(item.get("prompt_tokens", 0) for item in metered),
        "completion_tokens": sum(item.get("completion_tokens", 0) for item in metered),
        "total_tokens": sum(item.get("total_tokens", 0) for item in metered),
        "estimated_cost_usd_offpeak": str(sum(
            (Decimal(item["estimated_cost_usd"]["offpeak"]) for item in metered), Decimal(0))),
        "estimated_cost_usd_peak": str(sum(
            (Decimal(item["estimated_cost_usd"]["peak"]) for item in metered), Decimal(0))),
        "cost_basis": "按 API 返回的实际 Token usage 与接口记录价目估算；供应商未在响应中返回实际账单金额",
        "log_path": str(log_path.relative_to(ROOT)),
    }


def _agent_a_for_property(context: dict[str, Any], property_id: str, *,
                           max_candidates: int, max_steps: int,
                           planning_repairs: int, tag: str,
                           call_options: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    events: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    feedback = None
    for attempt in range(1, planning_repairs + 2):
        try:
            plan, event = generate_candidates(
                context, max_candidates=max_candidates, max_steps=max_steps,
                min_steps=1, use_shared_prefixes=False,
                repair_feedback=feedback,
                tag=f"{tag}_plan{attempt}", call_options=call_options)
            events.append(event)
            plans.append(plan)
            candidates = [row for row in plan.get("property_sequences", [])
                          if row.get("property_id") == property_id]
            if candidates:
                return candidates, events, {"status": "planned", "plans": plans}
            if attempt <= planning_repairs:
                feedback = ("上次没有产生可用候选；请针对当前唯一目标属性重新规划，至少给出一条 1 到 "
                            f"{max_steps} 笔交易的候选。无人工路径和参数模板可用。校验问题："
                            + json.dumps(plan.get("invalid_records", []), ensure_ascii=False)[:1200])
        except DeepSeekCallError as exc:
            events.append(exc.event or {"ok": False, "error_kind": exc.kind,
                                        "error": str(exc), "attempt": attempt})
            return [], events, {"status": "agent_a_error", "error": str(exc)[:1000],
                                "plans": plans}
        except Exception as exc:
            events.append({"ok": False, "error_kind": type(exc).__name__,
                           "error": str(exc)[:1000], "attempt": attempt})
            return [], events, {"status": "agent_a_error", "error": str(exc)[:1000],
                                "plans": plans}
    last = plans[-1] if plans else {}
    return [], events, {"status": "agent_a_no_candidate", "plans": plans,
                        "invalid_records": last.get("invalid_records", [])}


def _agent_b_call(context: dict[str, Any], candidate: dict[str, Any], *,
                  feedback: str | None, first_attempt: int, schema_repairs: int,
                  call_options: dict[str, Any]) -> tuple[dict[str, Any] | None,
                                                        list[dict[str, Any]], str | None]:
    events: list[dict[str, Any]] = []
    repair_feedback = feedback
    for offset in range(schema_repairs + 1):
        attempt = first_attempt + offset
        try:
            concrete, event = instantiate_candidate(
                context, candidate, feedback=repair_feedback, attempt=attempt,
                call_options=call_options)
            events.append(event)
            return concrete, events, None
        except DeepSeekCallError as exc:
            events.append(exc.event or {"ok": False, "error_kind": exc.kind,
                                        "error": str(exc), "attempt": attempt})
            locally_repairable = exc.kind in {
                "ValueError", "invalid_shape", "invalid_json", "empty_json",
                "incomplete_response", "TypeError", "KeyError"}
            if offset >= schema_repairs or not locally_repairable:
                return None, events, str(exc)[:1200]
            repair_feedback = ("上次返回没有通过本地参数/交易结构校验；保持函数顺序，按错误修正："
                               + str(exc))[:1200]
        except Exception as exc:
            events.append({"ok": False, "error_kind": type(exc).__name__,
                           "error": str(exc)[:1000], "attempt": attempt})
            return None, events, f"{type(exc).__name__}: {str(exc)[:1000]}"
    return None, events, "Agent B 修复循环结束但没有可用种子"


def _execution_feedback(replay: dict[str, Any]) -> str:
    failing = [row for row in replay.get("transactions", [])
               if row.get("status") != "success" or
               row.get("observed_effect_status") == "not_observed"]
    evidence = {"replay_status": replay.get("replay_status"),
                "deployment_status": replay.get("deployment_status"),
                "initial_property_violations": replay.get("initial_property_violations", []),
                "failed_transactions": failing[:4],
                "property_errors": [row.get("property_error") for row in failing[:4]]}
    return ("Anvil 逐交易回放失败。仅修正参数、发送者、金额或时间；保持 Agent A 的函数顺序，"
            "并检查相邻交易的身份、对象 ID 与提交/揭示数据一致性。不要声称已验证。证据："
            + json.dumps(evidence, ensure_ascii=False)[:2200])


def _event_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {"logical_calls": len(events),
            "failed_logical_calls": sum(not item.get("ok", False) for item in events),
            "events": [{key: item.get(key) for key in
                        ("tag", "ok", "error_kind", "error", "usage", "elapsed_seconds",
                         "attempt", "prompt_utf8_bytes", "invalid_record_count")}
                       for item in events]}


def run_project(project: str, property_ids: list[str], *, max_candidates: int = 1,
                max_steps: int = 8, repairs: int = 1, planning_repairs: int = 1,
                echidna_limit: int = 80, echidna_timeout: int = 45,
                echidna_seed: int = 20261114, token_budget: int = 400_000,
                wall_budget: int = 600, run_fuzzer: bool = True,
                run_root: Path | None = None, api_log_path: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    experiment_id = uuid.uuid4().hex
    if run_root is None:
        run_root = ROOT / "deepseek/结果/Agent种子语料" / project / experiment_id
    run_root.mkdir(parents=True, exist_ok=True)
    api_log = api_log_path or (run_root / "API调用.jsonl")
    api_log.parent.mkdir(parents=True, exist_ok=True)
    deadline = started + wall_budget
    budget = CallBudget(token_budget, deadline_monotonic=deadline)
    call_options = {"budget": budget, "log_path": api_log}

    full_context = load_project_context(project, property_ids)
    properties = {prop["property_id"]: prop for prop in full_context["properties"]}
    property_rows: list[dict[str, Any]] = []
    all_agent_a_events: list[dict[str, Any]] = []
    all_agent_b_events: list[dict[str, Any]] = []

    try:
        session = AnvilSession()
        session.__enter__()
        anvil_error = None
    except Exception as exc:
        session = None
        anvil_error = f"{type(exc).__name__}: {str(exc)[:1000]}"

    try:
        for property_index, property_id in enumerate(property_ids, start=1):
            prop_started = time.monotonic()
            prop = properties[property_id]
            context = {**full_context, "properties": [prop]}
            actions = [action for action in prop.get("candidate_actions", [])
                       if action.get("seed_compatible") and action.get("abi_signature")]
            property_row: dict[str, Any] = {
                "property_id": property_id, "property": prop.get("property"),
                "dependency_status": prop.get("dependency_status"),
                "seed_compatible_action_count": len(actions),
                "candidate_results": [], "status": "pending",
            }
            if not prop.get("property_predicate"):
                property_row.update({"status": "missing_property_predicate",
                                     "error": "Slither 报告没有可定位的属性谓词源码"})
                property_rows.append(property_row)
                continue
            if not actions:
                property_row.update({"status": "no_seed_compatible_action",
                                     "error": "Slither 没有匹配到可序列化的状态入口"})
                property_rows.append(property_row)
                continue

            candidates, a_events, planning = _agent_a_for_property(
                context, property_id, max_candidates=max_candidates,
                max_steps=max_steps, planning_repairs=planning_repairs,
                tag=f"AgentA_{project}_{property_id}", call_options=call_options)
            all_agent_a_events.extend(a_events)
            property_row["agent_a"] = _event_summary(a_events)
            property_row["planning"] = planning
            if not candidates:
                property_row["status"] = planning.get("status", "agent_a_no_candidate")
                property_row["elapsed_seconds"] = round(time.monotonic() - prop_started, 3)
                property_rows.append(property_row)
                continue

            for candidate_index, raw_candidate in enumerate(candidates, start=1):
                candidate = _candidate_context(raw_candidate, context)
                candidate["candidate_id"] = f"{property_id[:12]}-{candidate_index:02d}-{raw_candidate['candidate_id']}"
                candidate_root = run_root / "种子包" / project / property_id
                candidate_root.mkdir(parents=True, exist_ok=True)
                candidate_started = time.monotonic()
                b_events: list[dict[str, Any]] = []
                replay_attempts: list[dict[str, Any]] = []
                concrete: dict[str, Any] | None = None
                replay: dict[str, Any] | None = None
                error = None

                concrete, events, error = _agent_b_call(
                    context, candidate, feedback=None, first_attempt=1,
                    schema_repairs=1, call_options=call_options)
                b_events.extend(events)
                all_agent_b_events.extend(events)
                if concrete and session is not None:
                    try:
                        for repair_index in range(repairs + 1):
                            replay_started = time.monotonic()
                            replay = replay_seed(project, candidate,
                                                concrete["transactions"], session=session)
                            replay["attempt"] = repair_index + 1
                            replay["elapsed_seconds"] = round(time.monotonic() - replay_started, 3)
                            replay["elapsed_from_run_start_seconds"] = round(time.monotonic() - started, 3)
                            replay_attempts.append(replay)
                            if replay.get("replay_status") == "executable":
                                break
                            if repair_index >= repairs or replay.get("deployment_status") != "success":
                                break
                            repaired, retry_events, error = _agent_b_call(
                                context, candidate,
                                feedback=_execution_feedback(replay),
                                first_attempt=len(b_events) + 1,
                                schema_repairs=0, call_options=call_options)
                            b_events.extend(retry_events)
                            all_agent_b_events.extend(retry_events)
                            if not repaired:
                                break
                            concrete = repaired
                    except Exception as exc:
                        error = f"{type(exc).__name__}: {str(exc)[:1000]}"
                elif concrete:
                    error = anvil_error or "Anvil session is unavailable"

                final_replay = replay_attempts[-1] if replay_attempts else None
                seed_id = None
                corpus_file = None
                if final_replay and final_replay.get("replay_status") == "executable" and concrete:
                    seed_id = new_seed_id()
                    try:
                        path = write_corpus(project, candidate, concrete["transactions"],
                                            context, candidate_root,
                                            replay=final_replay, seed_id=seed_id)
                        corpus_file = str(path.relative_to(ROOT))
                    except Exception as exc:
                        error = f"语料写入失败：{type(exc).__name__}: {str(exc)[:800]}"

                status = ("executable" if corpus_file else
                          "replay_failed" if concrete and final_replay else
                          "agent_b_failed" if not concrete else "anvil_unavailable")
                property_row["candidate_results"].append({
                    "candidate_id": candidate["candidate_id"],
                    "plan": candidate["steps"],
                    "status": status,
                    "seed_class": "evm_valid" if corpus_file else
                                  "echidna_only_diagnostic_candidate" if concrete else "none",
                    "seed_id": seed_id, "corpus_file": corpus_file,
                    "concrete_seed": concrete,
                    "agent_b": _event_summary(b_events),
                    "replay_attempts": replay_attempts,
                    "error": error,
                    "elapsed_seconds": round(time.monotonic() - candidate_started, 3),
                })
            valid = sum(row["status"] == "executable"
                        for row in property_row["candidate_results"])
            property_row["status"] = "seed_generated" if valid else "no_valid_evm_seed"
            property_row["valid_evm_seed_count"] = valid
            property_row["elapsed_seconds"] = round(time.monotonic() - prop_started, 3)
            property_rows.append(property_row)
    finally:
        if session is not None:
            session.__exit__(None, None, None)

    echidna_rows = []
    if run_fuzzer:
        for property_index, property_id in enumerate(property_ids, start=1):
            prop = properties[property_id]
            property_name = _property_name(prop)
            campaign_root = run_root / "Echidna" / property_id
            coverage = campaign_root / "coverage"
            coverage.mkdir(parents=True, exist_ok=True)
            source_ids = []
            for row in next(item for item in property_rows
                            if item["property_id"] == property_id).get("candidate_results", []):
                if row.get("status") == "executable" and row.get("corpus_file"):
                    source = ROOT / row["corpus_file"]
                    shutil.copy2(source, coverage / source.name)
                    source_ids.append(row["seed_id"])
            try:
                result = run_echidna(
                    project, campaign_root, property_name=property_name,
                    test_limit=echidna_limit, timeout=echidna_timeout,
                    seed=echidna_seed + property_index - 1,
                    test_mode="property" if property_name.startswith("echidna_") else "assertion",
                    property_prefix=property_name,
                    seq_len=8, stop_on_fail=False, disable_slither=True)
                result["property_id"] = property_id
                result["input_seed_ids"] = source_ids
                result["input_seed_class"] = "evm_valid" if source_ids else "none"
            except Exception as exc:
                result = {"property_id": property_id, "property_name": property_name,
                          "status": "echidna_error",
                          "error": f"{type(exc).__name__}: {str(exc)[:1200]}",
                          "input_seed_ids": source_ids}
            echidna_rows.append(result)

    api_usage = _api_summary(api_log)
    return {
        "schema_version": 2, "experiment_id": experiment_id,
        "project": project, "property_ids": property_ids,
        "property_count": len(property_ids), "property_results": property_rows,
        "echidna": echidna_rows,
        "method": "independent_property_planning_without_grouping_or_shared_prefixes",
        "prompt_policy": {"agent_a_calls_per_property": True,
                          "shared_prefixes_enabled": False,
                          "manual_paths": False, "manual_parameter_templates": False,
                          "agent_b_responsibilities": ["ABI 参数", "发送者", "跨交易数据依赖"],
                          "planning_repairs_per_property": planning_repairs,
                          "execution_feedback_repairs_per_candidate": repairs},
        "budgets": {"echidna_test_limit_per_property": echidna_limit,
                    "echidna_timeout_seconds": echidna_timeout,
                    "token_budget": token_budget, "wall_budget_seconds": wall_budget},
        "api_usage": api_usage,
        "token_budget_accounting_upper_bound": budget.spent_tokens,
        "total_elapsed_seconds": round(time.monotonic() - started, 3),
        "anvil_start_error": anvil_error,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", choices=list(PROJECTS))
    parser.add_argument("--property-id", action="append", default=[])
    parser.add_argument("--property-contains", action="append", default=[])
    parser.add_argument("--max-candidates", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=8)
    parser.add_argument("--planning-repairs", type=int, default=1)
    parser.add_argument("--repairs", type=int, default=1,
                        help="Anvil 执行失败后的 Agent B 反馈修复次数")
    parser.add_argument("--echidna-limit", type=int, default=80)
    parser.add_argument("--echidna-timeout", type=int, default=45)
    parser.add_argument("--echidna-seed", type=int, default=20261114)
    parser.add_argument("--token-budget", type=int, default=400_000)
    parser.add_argument("--wall-budget", type=int, default=600)
    parser.add_argument("--skip-echidna", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_candidates <= 4 or not 1 <= args.max_steps <= 12:
        parser.error("候选数应为 1–4，序列长度应为 1–12")
    if not 0 <= args.repairs <= 3 or not 0 <= args.planning_repairs <= 2:
        parser.error("Agent B 执行修复应为 0–3 次，Agent A 规划修复应为 0–2 次")
    property_ids = _load_ids(args.project, args.property_id, args.property_contains)
    run_root = ROOT / "deepseek/结果/Agent种子语料" / args.project / uuid.uuid4().hex
    result = run_project(
        args.project, property_ids, max_candidates=args.max_candidates,
        max_steps=args.max_steps, repairs=args.repairs,
        planning_repairs=args.planning_repairs,
        echidna_limit=args.echidna_limit, echidna_timeout=args.echidna_timeout,
        echidna_seed=args.echidna_seed, token_budget=args.token_budget,
        wall_budget=args.wall_budget, run_fuzzer=not args.skip_echidna,
        run_root=run_root)
    output = run_root / "逐属性Agent种子流程.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"project": args.project,
                      "properties": len(property_ids),
                      "status": {row["property_id"]: row["status"]
                                 for row in result["property_results"]},
                      "valid_evm_seeds": sum(row.get("valid_evm_seed_count", 0)
                                              for row in result["property_results"]),
                      "api_tokens": result["api_usage"]["total_tokens"],
                      "estimated_api_cost_usd_offpeak": result["api_usage"]["estimated_cost_usd_offpeak"],
                      "output": str(output.relative_to(ROOT))}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
