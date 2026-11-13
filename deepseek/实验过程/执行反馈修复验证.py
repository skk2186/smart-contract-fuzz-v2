#!/usr/bin/env python3
"""单属性受控故障注入：验证真实回放反馈能否修复被吞掉的内部回滚。"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "deepseek"), str(ROOT / "func/功能"),
               str(ROOT / "deepseek/实验过程")]

from AgentB import instantiate_candidate  # noqa: E402
from deepseek接口 import CallBudget  # noqa: E402
from 分组可信度修复实验 import (CAPTURE_FUNCTION, CAPTURE_PROPERTY_ID, PROJECT,
                              PREFIX_FUNCTION, _execution_feedback, _sample_constraints)  # noqa: E402
from 属性种子上下文 import load_project_context  # noqa: E402
from 种子验证 import AnvilSession, replay_seed  # noqa: E402


def main() -> None:
    run_id = uuid.uuid4().hex
    output_dir = ROOT / "deepseek/结果/执行反馈修复验证" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    deadline = time.monotonic() + 180
    budget = CallBudget(200_000, deadline_monotonic=deadline)
    call_options = {"budget": budget, "log_path": output_dir / "api调用.jsonl",
                    "timeout": 120, "max_retries": 1}
    context = load_project_context(PROJECT, [CAPTURE_PROPERTY_ID])
    prop = context["properties"][0]
    candidate = {
        "candidate_id": f"fault-injection-{run_id[:12]}",
        "property_id": CAPTURE_PROPERTY_ID,
        "project": PROJECT,
        "property": prop["property"],
        "context": context,
        "steps": [{"function": PREFIX_FUNCTION,
                    "rationale": "创建授权记录并使 paymentRefCounter 大于零"},
                   {"function": CAPTURE_FUNCTION,
                    "rationale": "使用授权额度内的金额执行 capture"}],
        "execution_constraints": _sample_constraints(CAPTURE_PROPERTY_ID),
    }
    result = {"run_id": run_id, "kind": "controlled_fault_injection",
              "fault_injection": "将 captureAmount 改为授权金额 + 1；不作为候选种子或主实验结果。"}

    with AnvilSession() as session:
        first, first_event = instantiate_candidate(context, candidate,
                                                   attempt=1, call_options=call_options)
        bad_transactions = json.loads(json.dumps(first["transactions"]))
        authorized_amount = int(bad_transactions[0]["arguments"][0])
        bad_transactions[1]["arguments"][1] = authorized_amount + 1
        failed_replay = replay_seed(PROJECT, candidate, bad_transactions, session=session)
        feedback = _execution_feedback(failed_replay)

        fixed_prefix = [json.loads(json.dumps(bad_transactions[0]))]
        repaired, repair_event = instantiate_candidate(
            context, candidate, feedback=feedback, attempt=2,
            fixed_prefix_transactions=fixed_prefix, call_options=call_options)
        repaired_replay = replay_seed(PROJECT, candidate, repaired["transactions"],
                                      session=session)

    failed_capture = next((tx for tx in failed_replay.get("transactions", [])
                           if tx.get("function") == CAPTURE_FUNCTION), {})
    repaired_capture = next((tx for tx in repaired_replay.get("transactions", [])
                             if tx.get("function") == CAPTURE_FUNCTION), {})
    passed = (
        failed_replay.get("replay_status") == "replay_failed" and
        failed_capture.get("status") == "success" and
        failed_capture.get("observed_effect_status") == "not_observed" and
        repaired_replay.get("replay_status") == "executable" and
        repaired_capture.get("observed_effect_status") == "changed"
    )
    report = {
        **result,
        "status": "passed" if passed else "failed",
        "property_id": CAPTURE_PROPERTY_ID,
        "candidate_id": candidate["candidate_id"],
        "fixed_prefix": fixed_prefix,
        "injected_failure_replay": failed_replay,
        "agent_b_repair_feedback": feedback,
        "agent_b_repaired_transactions": repaired["transactions"],
        "repair_replay": repaired_replay,
        "api_events": [first_event, repair_event],
        "api_usage": {"calls": budget.calls, "preflight_charged_tokens": budget.spent_tokens,
                      "actual_tokens": sum(int((event.get("usage") or {}).get("total_tokens", 0))
                                           for event in (first_event, repair_event))},
    }
    output = output_dir / "执行反馈修复验证.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(output),
                      "failed_replay_status": failed_replay.get("replay_status"),
                      "injected_capture_effect": failed_capture.get("observed_effect_status"),
                      "repair_replay_status": repaired_replay.get("replay_status"),
                      "repair_capture_effect": repaired_capture.get("observed_effect_status"),
                      "actual_tokens": report["api_usage"]["actual_tokens"]}, ensure_ascii=False),
          flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
