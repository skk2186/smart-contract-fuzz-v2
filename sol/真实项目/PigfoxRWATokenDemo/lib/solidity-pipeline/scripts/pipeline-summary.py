#!/usr/bin/env python3
"""pipeline-summary.py — emit a committed, machine-readable record of what the
pipeline measured, pegged to the source it measured.

WHY THIS EXISTS. The figures a pipeline produces live for the length of a CI log
and then vanish. Anything that wants to display them — a page, a README, a
report — has to copy them by hand, and a hand-copied figure rots silently. It
already did: pigfox.com's testing page went on stating four repositories and
twenty-two properties long after both were wrong, on a page about not trusting
unverified numbers.

So the figures are written down beside the code they describe, in a form a
machine can read, and pegged so that "describes the current source" is checkable
rather than assumed.

THE PEG IS A PAIR OF TREE SHAS, NOT A COMMIT SHA, and that is not a preference.
A file cannot carry the hash of the commit that contains it: writing the file
changes its blob, which changes the tree, which changes the commit sha. The
constraint is circular and unsatisfiable. What IS satisfiable is recording
`git rev-parse HEAD:src` and `HEAD:test` — the content hashes of the inputs the
pipeline actually verified. A later check recomputes both and compares. That is
self-consistent, survives a rebase or a force-push, and correctly does NOT
invalidate the figures when only a README changed.

WHAT THIS FILE DOES NOT CLAIM. It does not say CI passed, and it cannot. The
workflow runs with `permissions: contents: read`, so CI cannot commit this file
back; a human generates it locally and commits it. With no branch protection, a
locally-green summary can land in the same push as a change that goes red in CI.
Therefore ANY consumer that displays these figures MUST gate them on the
repository's CI badge — a different source, which the generating machine does not
control. See docs/PIPELINE-SUMMARY.md. There is deliberately no `passed` field
here for a consumer to mistake for that guarantee.

FAILS LOUDLY, NEVER QUIETLY. Every input is required and every parse is checked.
A missing echidna transcript must not become "0 calls" — a zero that means "not
measured" is the exact shape of the stale-artifact bug the property-count gate
exists to catch.

Usage:
  scripts/pipeline-summary.py \
      --coverage coverage-summary.txt \
      --echidna  echidna-output.txt \
      --medusa   medusa-output.txt \
      --out      pipeline-summary.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "pigfox-pipeline-summary/v1"


class Failure(Exception):
    """A measurement that could not be taken. Never downgraded to a default."""


def run(cmd: list[str], cwd: Path | None = None) -> str:
    """Run a command and return stdout, or raise with enough detail to act on."""
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise Failure(
            f"{' '.join(cmd)} exited {proc.returncode}\n"
            f"stderr: {proc.stderr.strip()[:400]}"
        )
    return proc.stdout


# --------------------------------------------------------------------------
# The peg
# --------------------------------------------------------------------------

def tree_shas(repo: Path) -> dict[str, str]:
    """The content hashes of the directories the pipeline verifies.

    Both must exist. A repo with no test/ has nothing to summarise, and silently
    omitting a peg would make the eventual verification check vacuous for it.
    """
    peg = {}
    for name in ("src", "test"):
        sha = run(["git", "rev-parse", f"HEAD:{name}"], cwd=repo).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise Failure(f"git rev-parse HEAD:{name} returned {sha!r}, not a tree sha")
        peg[f"{name}Tree"] = sha
    return peg


# --------------------------------------------------------------------------
# Tests — machine-readable, straight from forge
# --------------------------------------------------------------------------

def forge_tests(repo: Path) -> dict[str, int]:
    """Suite and test counts from `forge test --json`.

    Parsed from JSON rather than from the console summary because the console
    line is a human artefact that has changed shape between forge releases,
    and a count read from prose is a count that breaks on an upgrade.
    """
    raw = run(["forge", "test", "--json"], cwd=repo)
    start = raw.find("{")
    if start < 0:
        raise Failure("forge test --json produced no JSON object")
    try:
        suites = json.loads(raw[start:])
    except json.JSONDecodeError as exc:
        raise Failure(f"forge test --json output did not parse: {exc}") from exc
    if not isinstance(suites, dict) or not suites:
        raise Failure("forge test --json returned no suites")

    passed = failed = skipped = 0
    for suite in suites.values():
        for result in (suite.get("test_results") or {}).values():
            status = result.get("status")
            if status == "Success":
                passed += 1
            elif status == "Skipped":
                skipped += 1
            else:
                failed += 1

    total = passed + failed + skipped
    if total == 0:
        raise Failure("forge test --json reported zero tests")
    return {"suites": len(suites), "passed": passed, "failed": failed, "skipped": skipped}


# --------------------------------------------------------------------------
# Coverage — parsed from the artefact coverage.sh already produces
# --------------------------------------------------------------------------

COVERAGE_ROW = re.compile(
    r"^\|\s*(?P<file>src/[^|]+?)\s*\|"
    r"\s*(?P<lines>[\d.]+)%[^|]*\|"
    r"\s*(?P<statements>[\d.]+)%[^|]*\|"
    r"\s*(?P<branches>[\d.]+)%[^|]*\|"
    r"\s*(?P<functions>[\d.]+)%[^|]*\|",
    re.MULTILINE,
)


def coverage(path: Path, exclusions: list[str]) -> dict:
    """Per-file coverage from the summary the gate already reads.

    Reuses coverage.sh's artefact rather than re-running an expensive pass, and
    reports PER FILE. A single estate percentage is the shape that rots; a list
    of files with their own numbers can be checked against the tree.
    """
    if not path.is_file():
        raise Failure(f"coverage summary {path} does not exist — run the coverage gate first")
    text = path.read_text(encoding="utf-8", errors="replace")

    files = []
    for m in COVERAGE_ROW.finditer(text):
        files.append({
            "file": m.group("file"),
            "lines": float(m.group("lines")),
            "statements": float(m.group("statements")),
            "branches": float(m.group("branches")),
            "functions": float(m.group("functions")),
        })
    if not files:
        raise Failure(
            f"no src/ rows parsed from {path} — the report format may have changed, "
            "and an unparsed report must not read as full coverage"
        )

    return {
        "files": files,
        "namedExclusions": exclusions,
        "allFilesAtHundred": all(
            f["lines"] == 100.0 and f["statements"] == 100.0
            and f["branches"] == 100.0 and f["functions"] == 100.0
            for f in files
        ),
    }


# --------------------------------------------------------------------------
# Fuzzers
# --------------------------------------------------------------------------

ANSI = re.compile(r"\x1b\[[0-9;]*m")

ECHIDNA_PASSING = re.compile(r"^echidna_[A-Za-z0-9_]+:\s+(?:passing|passed)", re.MULTILINE)
ECHIDNA_FAILING = re.compile(r"^echidna_[A-Za-z0-9_]+:\s+(?:failed|FAILED)", re.MULTILINE)
ECHIDNA_CALLS = re.compile(r"^Total calls:\s*(\d+)", re.MULTILINE)

MEDUSA_PASSED = re.compile(r"\[PASSED\]\s+Property Test:")
MEDUSA_FAILED = re.compile(r"\[FAILED\]\s+Property Test:")
MEDUSA_CALLS = re.compile(r"calls:\s*(\d+)")


def fuzzer(path: Path, engine: str) -> dict[str, int]:
    """Registered property counts and total calls, from an engine transcript.

    BOTH ENGINES ARE TEXT-PARSED, and the asymmetry behind that is worth stating.
    Echidna does support `--format json`; Medusa supports nothing but
    `--no-color`. Reading Echidna's transcript rather than running a second
    JSON-format campaign is a deliberate trade: the numbers are already in the
    file the gate just produced, and a second hundred-thousand-call run to
    re-learn them would cost minutes for nothing. The regexes below are the same
    shapes scripts/property-count.sh already asserts against, so a format change
    fails the GATE loudly before it can quietly mislead this generator.
    """
    if not path.is_file():
        raise Failure(f"{engine} transcript {path} does not exist — run {engine} first")
    text = ANSI.sub("", path.read_text(encoding="utf-8", errors="replace"))

    if engine == "echidna":
        passing = len(ECHIDNA_PASSING.findall(text))
        failing = len(ECHIDNA_FAILING.findall(text))
        calls_match = ECHIDNA_CALLS.search(text)
    else:
        passing = len(MEDUSA_PASSED.findall(text))
        failing = len(MEDUSA_FAILED.findall(text))
        # Medusa prints a running fuzz line; the last one carries the final total.
        found = MEDUSA_CALLS.findall(text)
        calls_match = found[-1] if found else None

    if passing == 0 and failing == 0:
        raise Failure(
            f"parsed no registered properties from {path} — an unparsed transcript "
            "must not read as a zero-property run"
        )
    if calls_match is None:
        raise Failure(f"no call total found in {path}")

    calls = int(calls_match if isinstance(calls_match, str) else calls_match.group(1))
    return {"registeredPassing": passing, "registeredFailing": failing, "calls": calls}


# --------------------------------------------------------------------------
# Slither
# --------------------------------------------------------------------------

FAIL_ON_LOW = {"Low", "Medium", "High"}


def slither(repo: Path, config: Path) -> dict:
    """Findings by impact, from `slither --json -`.

    Slither exits non-zero when it has findings at the fail-on threshold, so the
    exit code is not an error here — only unparsable output is.
    """
    proc = subprocess.run(
        ["slither", ".", "--config-file", str(config), "--ignore-compile", "--json", "-"],
        cwd=repo, capture_output=True, text=True, check=False,
    )
    start = proc.stdout.find("{")
    if start < 0:
        raise Failure(f"slither produced no JSON (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    try:
        report = json.loads(proc.stdout[start:])
    except json.JSONDecodeError as exc:
        raise Failure(f"slither JSON did not parse: {exc}") from exc

    detectors = ((report.get("results") or {}).get("detectors")) or []
    by_impact: dict[str, int] = {}
    for d in detectors:
        by_impact[d.get("impact", "Unknown")] = by_impact.get(d.get("impact", "Unknown"), 0) + 1

    return {
        "failOn": "low",
        "findingsAtFailOnLow": sum(n for i, n in by_impact.items() if i in FAIL_ON_LOW),
        "byImpact": by_impact,
    }


# --------------------------------------------------------------------------
# Toolchain
# --------------------------------------------------------------------------

def toolchain() -> dict[str, str]:
    """The versions that produced these figures.

    Recorded because a figure is only reproducible against the toolchain that
    produced it: forge's formatter and coverage instrumentation both change
    between releases, which is why the pipeline pins them in the first place.
    """
    def first_line(cmd: list[str]) -> str:
        try:
            return run(cmd).strip().splitlines()[0].strip()
        except (Failure, IndexError) as exc:
            raise Failure(f"could not read version via {' '.join(cmd)}: {exc}") from exc

    return {
        "forge": first_line(["forge", "--version"]),
        "slither": first_line(["slither", "--version"]),
        "echidna": first_line(["echidna", "--version"]),
        "medusa": first_line(["medusa", "--version"]),
    }


# --------------------------------------------------------------------------

def audit_logs(repo: Path, rel: str) -> list:
    """Index the committed audit/ logs: name, byte size, SHA-256.

    WHY A HASH AND NOT JUST A SIZE. The point of these logs is that a stranger can
    read what the tools said without a GitHub account. A consumer that DISPLAYS a
    figure from this summary should be able to prove the log it links has not been
    edited since the summary was generated — a size alone would not survive a
    same-length edit, and a hash makes the claim checkable rather than trusted.

    Returns [] when there is no audit/ directory, so a repo that has not adopted
    the logs yet still generates a valid summary rather than failing. An EMPTY
    audit/ directory is a different thing and is reported as an error, because it
    means capture ran and produced nothing.
    """
    d = repo / rel
    if not d.is_dir():
        return []
    logs = sorted(p for p in d.glob("*.log") if p.is_file())
    if not logs:
        raise Failure(f"{rel}/ exists but holds no .log files — capture produced nothing")
    out = []
    for p in logs:
        data = p.read_bytes()
        out.append(
            {
                "file": f"{rel}/{p.name}",
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="repository root (default: cwd)")
    ap.add_argument("--coverage", default="coverage-summary.txt")
    ap.add_argument("--echidna", default="echidna-output.txt")
    ap.add_argument("--medusa", default="medusa-output.txt")
    ap.add_argument("--slither-config", default="lib/solidity-pipeline/slither.config.json")
    ap.add_argument("--out", default="pipeline-summary.json")
    ap.add_argument("--audit", default="audit", help="directory of committed audit logs")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()

    try:
        summary = {
            "schema": SCHEMA,
            "//": (
                "Generated by scripts/pipeline-summary.py. Figures describe the source pegged "
                "below. This file does NOT and CANNOT attest that CI passed — see "
                "docs/PIPELINE-SUMMARY.md; a consumer displaying these figures must gate them "
                "on the repository's CI badge."
            ),
            "generatedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            "peg": tree_shas(repo),
            "tests": forge_tests(repo),
            "coverage": coverage(repo / args.coverage, exclusions=[]),
            "slither": slither(repo, repo / args.slither_config),
            "echidna": fuzzer(repo / args.echidna, "echidna"),
            "medusa": fuzzer(repo / args.medusa, "medusa"),
            "toolchain": toolchain(),
            "audit": audit_logs(repo, args.audit),
        }
    except Failure as exc:
        print(f"pipeline-summary: FAILED — {exc}", file=sys.stderr)
        print("Nothing written. A summary with a guessed figure is worse than none.", file=sys.stderr)
        return 1

    out = repo / args.out
    out.write_text(json.dumps(summary, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(f"pipeline-summary: wrote {out}")
    print(f"  peg      src {summary['peg']['srcTree'][:12]}  test {summary['peg']['testTree'][:12]}")
    print(f"  tests    {summary['tests']['passed']} passed in {summary['tests']['suites']} suites")
    print(f"  echidna  {summary['echidna']['registeredPassing']} properties, {summary['echidna']['calls']} calls")
    print(f"  medusa   {summary['medusa']['registeredPassing']} properties, {summary['medusa']['calls']} calls")
    print(f"  slither  {summary['slither']['findingsAtFailOnLow']} findings at fail-on low")
    return 0


if __name__ == "__main__":
    sys.exit(main())
