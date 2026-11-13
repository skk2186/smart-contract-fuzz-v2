#!/usr/bin/env python3
"""对分组和上下文构造的五段预处理分别计时。"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from 属性关联分组 import analyze
from 属性上下文压缩 import build, compact


ROOT = Path(__file__).resolve().parents[1]


def run(report, encoder):
    group_times = {}
    grouped = analyze(report, trials=1, seed=42, timings=group_times)
    context_times = {}
    layouts = build(report, grouped, timings=context_times)
    tick = time.perf_counter_ns()
    token_counts = {
        "independent": sum(len(encoder.encode(compact(x))) for x in layouts["independent"]),
        "global_shared": len(encoder.encode(compact(layouts["global_shared"]))),
        "grouped": sum(len(encoder.encode(compact(x))) for x in layouts["grouped"]),
    }
    token_ms = (time.perf_counter_ns() - tick) / 1_000_000
    return {**group_times, **context_times, "token_encoding_ms": token_ms}, token_counts, grouped


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=9)
    parser.add_argument("--output", default=".tools/results/分组预处理耗时.json")
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error("--repeats 至少为 3")
    sys.path.insert(0, str(ROOT / ".tools/tokenizer"))
    import tiktoken
    encoder = tiktoken.get_encoding("o200k_base")
    grouping = json.loads((ROOT / ".tools/results/属性关联分组.json").read_text(encoding="utf-8"))
    reports = {name: json.loads((ROOT / meta["input_file"]).read_text(encoding="utf-8"))
               for name, meta in grouping["projects"].items()}
    raw = {name: [] for name in reports}
    # 预热解释器、JSON、tokenizer 和缓存；不计入结果。
    for name, report in reports.items():
        run(report, encoder)
    for rep in range(args.repeats):
        for name in list(reports)[rep % len(reports):] + list(reports)[:rep % len(reports)]:
            times, counts, grouped = run(reports[name], encoder)
            if grouped["input_properties"] != grouping["projects"][name]["input_properties"]:
                raise AssertionError("分组属性数不一致")
            raw[name].append({"times_ms": times, "payload_tokens": counts})
            print(name, rep + 1, {k: round(v, 3) for k, v in times.items()}, flush=True)
    result = {"repeats": args.repeats, "clock": "time.perf_counter_ns",
              "scope": "JSON 已载入内存、tokenizer 已预热；不含 Slither 分析、磁盘读写及模型调用",
              "projects": {}}
    for name, trials in raw.items():
        fields = trials[0]["times_ms"]
        result["projects"][name] = {
            "summary_ms": {key: {"median": statistics.median(t["times_ms"][key] for t in trials),
                                  "min": min(t["times_ms"][key] for t in trials),
                                  "max": max(t["times_ms"][key] for t in trials)}
                           for key in fields},
            "raw_trials": trials,
        }
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
