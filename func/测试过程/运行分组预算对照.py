#!/usr/bin/env python3
"""按固定模型和每项目统一 Token 上限运行三次分组策略对照。"""

import argparse
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".tools/results/分组预算对照输入.json"
OUTPUT = ROOT / ".tools/results/分组预算对照调用.jsonl"
BUDGET = {"Request": 380_000, "Immutable": 600_000}
MODEL = "gpt-6.1-sol"


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def call_model(case, run_key, index, data):
    prompt = data["model_task_instruction"] + "\n" + compact(data["cases"][case]["runs"][run_key][index])
    executable = shutil.which("codex.exe") or shutil.which("codex.cmd")
    if not executable:
        raise RuntimeError("未找到 Codex 命令行")
    cmd = [executable, "exec", "--json", "--ephemeral", "--ignore-user-config",
           "--skip-git-repo-check", "--sandbox", "read-only", "-m", MODEL,
           "-C", str(ROOT), "-"]
    start = time.monotonic()
    base = {"case": case, "run_key": run_key, "index": index,
            "model": MODEL, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "started_utc": datetime.now(timezone.utc).isoformat()}
    try:
        process = subprocess.run(cmd, input=prompt, text=True, capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=600)
        events = []
        for line in process.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        completed = [event for event in events if event.get("type") == "turn.completed"]
        answers = [event.get("item", {}).get("text", "") for event in events
                   if event.get("type") == "item.completed" and
                   event.get("item", {}).get("type") == "agent_message"]
        base.update({"elapsed_seconds": round(time.monotonic() - start, 2),
                     "exit_code": process.returncode,
                     "usage": completed[-1].get("usage") if completed else None,
                     "response": answers[-1] if answers else "",
                     "tool_items": [event.get("item", {}).get("type") for event in events
                                    if event.get("type") == "item.completed" and
                                    event.get("item", {}).get("type") != "agent_message"],
                     "errors": [event for event in events
                                if event.get("type") in {"error", "turn.failed"}],
                     "stderr_tail": process.stderr[-1000:]})
    except subprocess.TimeoutExpired:
        base.update({"elapsed_seconds": round(time.monotonic() - start, 2),
                     "timeout": True, "exit_code": None, "response": "", "usage": None})
    with OUTPUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(base, ensure_ascii=False) + "\n")
    print(case, run_key, index, "exit", base.get("exit_code"),
          "tokens", base.get("usage"), "seconds", base["elapsed_seconds"], flush=True)
    return base


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["Request", "Immutable"])
    parser.add_argument("--rep", type=int, choices=[1, 2, 3])
    parser.add_argument("--method", choices=["cache", "random", "controlled", "current_group"])
    parser.add_argument("--retry-quota", action="store_true",
                        help="额度恢复后仅重试此前因 usage limit 失败的原样输入")
    args = parser.parse_args()
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    previous = {}
    if OUTPUT.exists():
        for line in OUTPUT.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            previous[(item["case"], item["run_key"], item["index"])] = item
    cases = [args.case] if args.case else ["Request", "Immutable"]
    for case in cases:
        reps = [args.rep] if args.rep else [1, 2, 3]
        for rep in reps:
            order = ["cache", "random", "controlled", "current_group"]
            order = order[(rep - 1) % len(order):] + order[:(rep - 1) % len(order)]
            for method in order:
                if args.method and method != args.method:
                    continue
                run_key = f"r{rep}_{method}"
                spent = sum((item.get("usage") or {}).get("input_tokens", 0) +
                            (item.get("usage") or {}).get("output_tokens", 0)
                            for (c, key, _), item in previous.items() if c == case and key == run_key)
                for index in range(len(data["cases"][case]["runs"][run_key])):
                    task = (case, run_key, index)
                    if task in previous:
                        old = previous[task]
                        quota_failure = any("usage limit" in json.dumps(error, ensure_ascii=False).lower()
                                            for error in old.get("errors", []))
                        if not (args.retry_quota and quota_failure):
                            continue
                    if spent >= BUDGET[case]:
                        print(case, run_key, "BUDGET_STOP", spent, flush=True)
                        break
                    result = call_model(case, run_key, index, data)
                    previous[task] = result  # 拦截和失败也不自动重试
                    if any("usage limit" in json.dumps(error, ensure_ascii=False).lower()
                           for error in result.get("errors", [])):
                        print("MODEL_QUOTA_STOP", case, run_key, index, flush=True)
                        return
                    spent += (result.get("usage") or {}).get("input_tokens", 0)
                    spent += (result.get("usage") or {}).get("output_tokens", 0)


if __name__ == "__main__":
    main()
