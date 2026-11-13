#!/usr/bin/env python3
"""用同一 Codex 模型逐次运行 Agent A 输入，保存原始用量与响应。"""

import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / ".tools/results/AgentA对照输入.json"
OUTPUT = ROOT / ".tools/results/AgentA调用记录.jsonl"
MODEL = "gpt-6.1-sol"


def compact(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run(case, layout, index, data):
    payload = data["cases"][case]["layouts"][layout][index]
    prompt = data["model_task_instruction"] + "\n" + compact(payload)
    executable = shutil.which("codex.exe") or shutil.which("codex.cmd")
    if not executable:
        raise RuntimeError("未找到 Codex 命令行")
    cmd = [executable, "exec", "--json", "--ephemeral", "--ignore-user-config",
           "--skip-git-repo-check", "--sandbox", "read-only", "-m", MODEL,
           "-C", str(ROOT), "-"]
    start = time.monotonic()
    try:
        process = subprocess.run(cmd, input=prompt, text=True, capture_output=True,
                                 encoding="utf-8", errors="replace", timeout=600)
        events = []
        for line in process.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        usage = [event.get("usage") for event in events
                 if event.get("type") == "turn.completed"]
        answers = [event.get("item", {}).get("text", "") for event in events
                   if event.get("type") == "item.completed" and
                   event.get("item", {}).get("type") == "agent_message"]
        tools = [event.get("item", {}).get("type") for event in events
                 if event.get("type") == "item.completed" and
                 event.get("item", {}).get("type") != "agent_message"]
        record = {"case": case, "layout": layout, "index": index, "model": MODEL,
                  "elapsed_seconds": round(time.monotonic() - start, 2),
                  "exit_code": process.returncode, "usage": usage[-1] if usage else None,
                  "response": answers[-1] if answers else "", "tool_items": tools,
                  "errors": [e for e in events if e.get("type") in {"error", "turn.failed"}],
                  "stderr_tail": process.stderr[-2000:]}
    except subprocess.TimeoutExpired as exc:
        record = {"case": case, "layout": layout, "index": index, "model": MODEL,
                  "elapsed_seconds": round(time.monotonic() - start, 2), "timeout": True,
                  "error": str(exc)}
    with OUTPUT.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(case, layout, index, "exit", record.get("exit_code"),
          "seconds", record["elapsed_seconds"], "usage", record.get("usage"), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=["Hokusai", "Request", "Immutable"])
    parser.add_argument("--layout", choices=["independent", "global_shared", "grouped", "split"])
    parser.add_argument("--index", type=int)
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args()
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    existing = set()
    if OUTPUT.exists():
        for line in OUTPUT.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            if item.get("exit_code") == 0 and item.get("response"):
                existing.add((item["case"], item["layout"], item["index"]))
    if args.all:
        cases = [args.case] if args.case else ["Hokusai", "Request", "Immutable"]
        tasks = [(case, layout, index) for case in cases
                 for layout, payloads in data["cases"][case]["layouts"].items()
                 if layout != "global_shared" and (args.layout is None or args.layout == layout)
                 # 单个代表组与 grouped 字节相同，避免重复调用
                 for index in range(len(payloads))]
    elif args.case is not None and args.layout is not None and args.index is not None:
        tasks = [(args.case, args.layout, args.index)]
    else:
        parser.error("指定 --all，或同时指定 --case、--layout、--index")
    for task in tasks:
        if task not in existing:
            run(*task, data)


if __name__ == "__main__":
    main()
