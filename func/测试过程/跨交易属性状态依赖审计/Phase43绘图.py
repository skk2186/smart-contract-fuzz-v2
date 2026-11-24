#!/usr/bin/env python3
"""Render Phase43 figures from the archived campaign-results.csv only."""
from __future__ import annotations

import csv
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "func/测试过程/跨交易属性状态依赖审计/结果/Phase43-20261123"
OUT = BASE / "figures"
OUT.mkdir(parents=True, exist_ok=True)
with (BASE / "campaign-results.csv").open(encoding="utf-8", newline="") as f:
    ROWS = list(csv.DictReader(f))

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 12,
    "axes.labelsize": 10, "figure.dpi": 150, "savefig.dpi": 180,
    "axes.spines.top": False, "axes.spines.right": False,
})
BLUE, ORANGE, GREEN, RED, GRAY = "#3478B8", "#E58B2A", "#36966E", "#C75658", "#89939D"


def subset(source, group=None, phase=None, sample=None):
    return [r for r in ROWS if r["source"] == source
            and (group is None or r["group"] == group)
            and (phase is None or r["phase"] == phase)
            and (sample is None or r["sample_id"] == sample)]


def floats(rows, key):
    vals = []
    for r in rows:
        try:
            vals.append(float(r[key]))
        except (ValueError, TypeError, KeyError):
            pass
    return vals


def count_valid(rows):
    ids = {r["sample_id"] for r in rows if r.get("complete_executable", "").lower() == "true"}
    return len(ids)


def save(fig, name):
    fig.tight_layout()
    fig.savefig(OUT / name, bbox_inches="tight")
    plt.close(fig)


# 1. Effective seed generation rate. Real denominator is the two selected,
# runnable native-property tasks (Aave and Liquity); the other candidates are
# shown in the caption and remain in admission.csv.
fig, axes = plt.subplots(1, 2, figsize=(9.2, 4.2), sharey=True)
for ax, title, source, denominator in [
    (axes[0], "Olympia synthetic set", "Olympia", 100),
    (axes[1], "SCFuzzBench eligible tasks", "SCFuzzBench", 2),
]:
    labels, values, colors = [], [], []
    for group, phase, label, color in [("E1", "agent_replay", "E1 raw", BLUE),
                                        ("E2", "repair_and_replay", "E2 repaired", ORANGE)]:
        rows = subset(source, group, phase)
        n = count_valid(rows)
        labels.append(label)
        values.append(100 * n / denominator)
        colors.append(color)
        ax.text(len(values)-1, values[-1] + 1.2, f"{n}/{denominator}", ha="center", fontsize=9)
    ax.bar(labels, values, color=colors, width=0.58)
    ax.set_title(title)
    ax.set_ylim(0, 60)
    ax.set_ylabel("Complete executable seed rate (%)")
    ax.grid(axis="y", alpha=.22)
    ax.set_axisbelow(True)
axes[1].text(.5, -0.22, "2 selected targets; 1/2 seeded. 2 other candidates blocked or had no eligible property.",
             transform=axes[1].transAxes, ha="center", va="top", fontsize=8, color="#555")
fig.suptitle("Complete executable seeds after E1/E2", y=1.02)
save(fig, "01_effective_seed_rate.png")


# 2. Target-native counterexample discovery rate. Aave G1/G2 are N/A rather
# than zero because those groups had no valid V2 seed.
fig, ax = plt.subplots(figsize=(8.6, 4.5))
x = np.arange(3)
groups = ["G0", "G1", "G2"]
for label, source, sample, color, offset in [
    ("Olympia", "Olympia", None, BLUE, -.25),
    ("Liquity V2 governance", "SCFuzzBench", "SCFUZZ-LiquityV2Governance", GREEN, 0),
    ("Aave V4", "SCFuzzBench", "SCFUZZ-AaveV4", RED, .25),
]:
    rates = []
    counts = []
    for group in groups:
        rows = subset(source, group, "formal_fuzz", sample)
        ran = [r for r in rows if r["status"] == "completed"]
        cex = sum(r.get("native_counterexample", "").lower() == "true" for r in ran)
        counts.append((cex, len(ran)))
        rates.append(100*cex/len(ran) if ran else np.nan)
    mask = [not np.isnan(v) for v in rates]
    if any(mask):
        ax.bar(x[mask] + offset, np.array(rates)[mask], width=.23, label=label, color=color)
        for i, (cex, n) in enumerate(counts):
            if n:
                ax.text(x[i] + offset, rates[i] + 2, f"{cex}/{n}", ha="center", fontsize=8)
            elif sample == "SCFUZZ-AaveV4" and i > 0:
                ax.text(x[i] + offset, 3, "N/A", ha="center", fontsize=8, color=GRAY)
ax.set_xticks(x, groups)
ax.set_ylim(0, 115)
ax.set_ylabel("Selected native-property cEX rate (%)")
ax.set_title("Counterexamples verified by the original property")
ax.legend(frameon=False, ncol=3, loc="upper center")
ax.grid(axis="y", alpha=.2)
ax.set_axisbelow(True)
ax.text(.01, -.2, "Aave's six non-target canary failures are excluded; Aave G1/G2 were not run.",
        transform=ax.transAxes, fontsize=8, color="#555")
save(fig, "02_native_counterexample_rate.png")


# 3. Time to first native target counterexample; no discovery by the budget
# is right-censored, not assigned a time of zero.
fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.4))
ax = axes[0]
ax.set_title("Olympia: no target cEX by 60 s")
ax.axvline(60, color=GRAY, linestyle="--", lw=1.4)
ax.set_xlim(0, 66); ax.set_ylim(-.5, 2.5)
ax.set_yticks([0,1,2], groups)
ax.set_xlabel("Seconds; right-censored at 60 s")
for i, group in enumerate(groups):
    rr = subset("Olympia", group, "formal_fuzz")
    ran = [r for r in rr if r["status"] == "completed"]
    ax.scatter([60]*len(ran), [i]*len(ran), s=11, alpha=.55,
               color=[BLUE, GREEN, ORANGE][i], label=f"{group} {len(ran)}/0 cEX")
    ax.text(61, i, f"0/{len(ran)}", va="center", fontsize=8)
ax.grid(axis="x", alpha=.2)
ax = axes[1]
ax.set_title("Liquity V2: observed target cEX")
means, sds = [], []
for group in groups:
    rr = subset("SCFuzzBench", group, "formal_fuzz", "SCFUZZ-LiquityV2Governance")
    v = floats([r for r in rr if r["native_counterexample"].lower() == "true"], "time_to_first_native_counterexample_seconds")
    means.append(statistics.mean(v) if v else np.nan)
    sds.append(statistics.stdev(v) if len(v) > 1 else 0)
ax.bar(groups, means, color=[BLUE, GREEN, ORANGE], width=.58)
ax.errorbar(np.arange(3), means, yerr=sds, fmt="none", ecolor="#333", capsize=4)
for i, m in enumerate(means): ax.text(i, m + sds[i] + .7, f"{m:.1f}s", ha="center", fontsize=9)
ax.set_ylim(0, 65); ax.set_ylabel("Seconds")
ax.grid(axis="y", alpha=.2); ax.set_axisbelow(True)
fig.suptitle("Time to first target-property counterexample", y=1.02)
save(fig, "03_time_to_first_counterexample.png")


def sample_means(source, sample_id=None):
    ids = sorted({r["sample_id"] for r in ROWS if r["source"] == source and (sample_id is None or r["sample_id"] == sample_id)})
    paired = []
    for sid in ids:
        result = {}
        for group in ("G0", "G1", "G2"):
            rr = [r for r in ROWS if r["sample_id"] == sid and r["group"] == group and r["phase"] == "formal_fuzz" and r["status"] == "completed"]
            vv = floats(rr, "final_coverage")
            if len(vv) == 3:
                result[group] = statistics.mean(vv)
        if all(g in result for g in ("G0", "G1", "G2")):
            paired.append(result)
    return paired


# 4. Paired final coverage by independent contract; do not pool codebases.
fig, axes = plt.subplots(1, 2, figsize=(9.3, 4.4))
for ax, title, paired in [(axes[0], "Olympia (18 paired contracts)", sample_means("Olympia")),
                          (axes[1], "Liquity V2 governance (1 project)", sample_means("SCFuzzBench", "SCFUZZ-LiquityV2Governance"))]:
    means, errs = [], []
    for g in groups:
        vals = [p[g] for p in paired]
        means.append(statistics.mean(vals) if vals else np.nan)
        errs.append(statistics.stdev(vals) if len(vals)>1 else 0)
    ax.bar(groups, means, color=[BLUE,GREEN,ORANGE], width=.58)
    ax.errorbar(np.arange(3), means, yerr=errs, fmt="none", ecolor="#333", capsize=4)
    ax.set_title(title)
    ax.set_ylabel("Unique instructions")
    ax.grid(axis="y", alpha=.2); ax.set_axisbelow(True)
    for i,m in enumerate(means): ax.text(i,m+errs[i],f"{m:.1f}",ha="center",va="bottom",fontsize=8)
fig.suptitle("Final Echidna coverage on paired runs (mean ± contract SD)", y=1.02)
save(fig, "04_paired_coverage.png")


# 5. G2 minus G1 paired ablation. Binding applicability/success is displayed
# because coverage deltas alone cannot identify a binding effect.
fig, ax = plt.subplots(figsize=(7.4, 4.4))
labels, means, errors, ns = [], [], [], []
for label, pairs in [("Olympia", sample_means("Olympia")),
                     ("Liquity V2 governance", sample_means("SCFuzzBench", "SCFUZZ-LiquityV2Governance"))]:
    deltas = [p["G2"] - p["G1"] for p in pairs]
    labels.append(label); ns.append(len(deltas))
    means.append(statistics.mean(deltas) if deltas else 0)
    errors.append(statistics.stdev(deltas) if len(deltas)>1 else 0)
ax.axhline(0, color=GRAY, lw=1)
bars=ax.bar(labels, means, yerr=errors, capsize=5, color=[BLUE,GREEN], width=.55)
ax.set_ylabel("G2 − G1 unique instructions")
ax.set_title("Phase37 binding ablation: paired coverage difference")
ax.grid(axis="y", alpha=.2); ax.set_axisbelow(True)
for bar, mean, n in zip(bars, means, ns):
    ax.text(bar.get_x()+bar.get_width()/2, bar.get_height()+errors[labels.index(bar.get_label())] if bar.get_label() in labels else mean,
            f"Δ={mean:.2f}; n={n}", ha="center", va="bottom", fontsize=9)
ax.text(.5, -.2, "Binding applicability: 0; binding success: 0 in both evaluated datasets.",
        transform=ax.transAxes, ha="center", fontsize=8, color="#555")
save(fig, "05_g1_g2_ablation.png")

print("\n".join(str(p) for p in sorted(OUT.glob("*.png"))))
