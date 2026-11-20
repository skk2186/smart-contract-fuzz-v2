#!/usr/bin/env bash
#
# stages-check.sh — the stage table in README.md must agree with the stages the
# reusable workflow actually defines.
#
# WHY THIS EXISTS. When `lint` landed as step 1 of the pipeline, the workflow
# gained a stage and this repo's README gained a row — but every CONSUMING repo's
# README, and pigfox.com's page about the pipeline, went on describing a pipeline
# without its first step. One of them even printed a stage COUNT, so it was not
# merely incomplete, it was arithmetic that had quietly become false.
#
# Those downstream surfaces are not reachable from here (a fix for that is
# discussed below). What IS reachable is the canonical description — this repo's
# own README — and that is worth gating, because every other surface is written by
# reading it. A stale enumeration reads as a decision: it says "these are the
# stages" with the same confidence whether or not it is true.
#
# WHAT IT CHECKS. The workflow's job `name:` values, in declaration order, must
# equal the README stage tokens, in table order. The comparison is on the part of
# the job name BEFORE any parenthesis — `slither (static analysis, fail on low and
# up)` matches a README row of `slither` — so a job may explain itself in CI
# without that prose having to be duplicated in the table. Order is part of the
# check, not incidental to it: the table's order IS the claim about what runs
# first, and "lint is step 1" is a claim this pipeline makes out loud.
#
# WHAT IT CANNOT CHECK, deliberately. It cannot see a consuming repo's README, or
# pigfox.com. Reaching those needs network and cross-repo reads, with a failure
# mode where somebody else's outage turns this tree red — the same trade
# docs/CONSUMERS.md already argues for the consumer list. A deterministic offline
# gate on the canonical list is worth more than a flaky complete one. It also
# cannot check that a row's DESCRIPTION is true; it checks that the set of stages,
# and their order, cannot drift.
#
# It SELF-TESTS. A checker that has silently stopped matching reports the same
# green as a correct tree.
#
# Usage:
#   stages-check.sh [--root DIR] [check|selftest|all]
#
# stderr is never suppressed.
set -uo pipefail

ROOT="$PWD"
MODE="all"

while [ "$#" -gt 0 ]; do
	case "$1" in
	--root)
		ROOT="$2"
		shift 2
		;;
	check | selftest | all)
		MODE="$1"
		shift
		;;
	-h | --help)
		sed -n '2,41p' "$0"
		exit 0
		;;
	*)
		echo "stages-check.sh: unknown argument '$1'" >&2
		exit 2
		;;
	esac
done

fail=0

note_ok() { printf '  ok   %s\n' "$1"; }
note_bad() {
	printf '  FAIL %s\n' "$1" >&2
	fail=1
}

# Stage names from the workflow, in declaration order: each job's `name:` value
# truncated at the first parenthesis. Parsed positionally rather than with a YAML
# library so this gate needs nothing installed that the others do not.
workflow_stages() {
	python3 - "$1" <<'PY'
import re,sys
out=[]
in_jobs=False
for line in open(sys.argv[1]):
    if re.match(r'^jobs:\s*$', line):
        in_jobs=True
        continue
    if in_jobs and re.match(r'^\S', line):
        break
    if in_jobs:
        m=re.match(r'^    name:\s*(.+?)\s*$', line)
        if m:
            out.append(m.group(1).split('(')[0].strip())
for s in out:
    print(s)
PY
}

# Stage tokens from the README's stage table, in table order.
readme_stages() {
	python3 - "$1" <<'PY'
import re,sys
rows=[]
inside=False
for line in open(sys.argv[1]):
    if line.startswith('## What it runs'):
        inside=True; continue
    if inside and line.startswith('## '):
        break
    if inside and line.startswith('|'):
        m=re.match(r'\|\s*`([^`]+)`\s*\|', line)
        if m:
            rows.append(m.group(1).strip())
for r in rows:
    print(r)
PY
}

run_check() {
	local root="$1" quiet="${2:-}"
	local wf="$root/.github/workflows/solidity.yml"
	local readme="$root/README.md"

	if [ ! -f "$wf" ]; then
		echo "FAIL: no reusable workflow at $wf" >&2
		return 1
	fi
	if [ ! -f "$readme" ]; then
		echo "FAIL: no README.md at $readme" >&2
		return 1
	fi

	local want got
	want="$(workflow_stages "$wf")" || {
		echo "FAIL: could not parse the workflow's jobs" >&2
		return 1
	}
	got="$(readme_stages "$readme")" || {
		echo "FAIL: could not parse the README stage table" >&2
		return 1
	}

	# Refuse to pass vacuously: an empty side means the parser stopped matching,
	# which is exactly the failure this gate is supposed to be immune to.
	if [ -z "$want" ]; then
		echo "FAIL: no jobs found in the workflow — refusing to pass vacuously" >&2
		return 1
	fi
	if [ -z "$got" ]; then
		echo "FAIL: no rows found in the README stage table — refusing to pass vacuously" >&2
		return 1
	fi

	local rc=0
	local diff_out
	# Order matters, so this is a plain diff, NOT a sorted one.
	diff_out="$(diff <(printf '%s\n' "$want") <(printf '%s\n' "$got"))"
	if [ -n "$diff_out" ]; then
		rc=1
		if [ -z "$quiet" ]; then
			echo "FAIL: README stage table disagrees with the workflow" >&2
			echo "  '<' = in the workflow only, '>' = in the README only" >&2
			printf '%s\n' "$diff_out" >&2
		fi
	fi
	return "$rc"
}

run_selftest() {
	local tmp
	tmp="$(mktemp -d)" || return 1
	# shellcheck disable=SC2064
	trap "rm -rf '$tmp'" RETURN

	mkdir -p "$tmp/.github/workflows"
	cp "$ROOT/.github/workflows/solidity.yml" "$tmp/.github/workflows/solidity.yml"
	cp "$ROOT/README.md" "$tmp/README.md"

	if run_check "$tmp" quiet; then
		note_ok "self-test: the real tree passes"
	else
		note_bad "self-test: the real tree does not pass its own check"
	fi

	# A stage added to the workflow and never written into the README. This is the
	# exact defect that shipped when lint landed, so it is the one that matters.
	python3 - "$tmp/.github/workflows/solidity.yml" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).readlines()
out, planted = [], False
for line in lines:
    out.append(line)
    if not planted and line.startswith('  medusa:'):
        out.append('    name: planted-stage (planted by the self-test)\n')
        planted = True
if not planted:
    raise SystemExit('self-test could not plant a job in the workflow')
open(p, 'w').writelines(out)
PY
	if run_check "$tmp" quiet; then
		note_bad "self-test: a workflow stage missing from the README was NOT caught"
	else
		note_ok "self-test: a workflow stage missing from the README was caught"
	fi

	# The other direction: a README row naming a stage the workflow does not
	# define. Planted INSIDE the table — appending at end-of-file plants nothing,
	# because the parser stops at the next heading.
	cp "$ROOT/.github/workflows/solidity.yml" "$tmp/.github/workflows/solidity.yml"
	cp "$ROOT/README.md" "$tmp/README.md"
	python3 - "$tmp/README.md" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).readlines()
out, inside, planted = [], False, False
for line in lines:
    if line.startswith('## What it runs'):
        inside = True
    elif inside and line.startswith('## '):
        inside = False
    if inside and not planted and line.startswith('| `'):
        out.append(line)
        out.append('| `ghost-stage` | not defined by the workflow |\n')
        planted = True
        continue
    out.append(line)
if not planted:
    raise SystemExit('self-test could not plant a row inside the table')
open(p, 'w').writelines(out)
PY
	if run_check "$tmp" quiet; then
		note_bad "self-test: a README row with no workflow stage was NOT caught"
	else
		note_ok "self-test: a README row with no workflow stage was caught"
	fi

	# ORDER. The table's order is the claim about what runs first — "lint is step
	# 1" is a claim this pipeline makes out loud — so a table holding the right
	# stages in the wrong order must fail. A set comparison would pass this.
	cp "$ROOT/.github/workflows/solidity.yml" "$tmp/.github/workflows/solidity.yml"
	cp "$ROOT/README.md" "$tmp/README.md"
	python3 - "$tmp/README.md" <<'PY'
import re,sys
p = sys.argv[1]
lines = open(p).readlines()
inside = False
idx = []
for i, line in enumerate(lines):
    if line.startswith('## What it runs'):
        inside = True
        continue
    if inside and line.startswith('## '):
        break
    if inside and re.match(r'\|\s*`([^`]+)`\s*\|', line):
        idx.append(i)
if len(idx) < 2:
    raise SystemExit('self-test needs at least two table rows to swap')
a, b = idx[0], idx[1]
lines[a], lines[b] = lines[b], lines[a]
open(p, 'w').writelines(lines)
PY
	if run_check "$tmp" quiet; then
		note_bad "self-test: two stages in the wrong order were NOT caught"
	else
		note_ok "self-test: two stages in the wrong order were caught"
	fi
}

case "$MODE" in
selftest)
	run_selftest
	;;
check)
	if run_check "$ROOT"; then
		note_ok "check: README stage table matches the workflow"
	else
		fail=1
	fi
	;;
all)
	run_selftest
	if run_check "$ROOT"; then
		note_ok "check: README stage table matches the workflow"
	else
		fail=1
	fi
	;;
esac

if [ "$fail" -ne 0 ]; then
	echo "STAGES CHECK: FAIL" >&2
	exit 1
fi
echo "STAGES CHECK: PASS"
