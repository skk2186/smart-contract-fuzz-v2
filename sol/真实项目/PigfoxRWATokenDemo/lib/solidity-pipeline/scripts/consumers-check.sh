#!/usr/bin/env bash
#
# consumers-check.sh — the repo list in README.md must agree with consumers.json.
#
# WHY THIS EXISTS. The "Repos on the pipeline" table was hand-maintained prose and
# went stale: it listed four repos when six were on the pipeline, and ADOPTING.md
# repeated a matching wrong count. Nothing failed, because nothing checked. A
# stale enumeration reads as a decision — it says "these are the repos" with the
# same confidence whether or not it is true.
#
# WHAT IT CHECKS, both directions:
#   - every repo in consumers.json has a row in README.md's table
#   - every row in README.md's table is in consumers.json
#   - the "what it is" text matches
#
# WHAT IT CANNOT CHECK, and this is deliberate rather than an oversight: it cannot
# discover a repo that adopted the pipeline and was never added to consumers.json.
# That is the exact rot that happened, and catching it requires enumerating the
# GitHub org and reading each repo's ci.yml — network, a token with cross-repo
# read, and a failure mode where somebody else's outage turns this tree red. A
# deterministic offline gate is worth more here than a flaky complete one, so the
# residual gap is documented in docs/CONSUMERS.md instead of being papered over.
# What this gate does guarantee is that ONE list is canonical and the prose cannot
# drift away from it.
#
# It SELF-TESTS. A checker that has silently stopped matching reports the same
# green as a correct tree.
#
# Usage:
#   consumers-check.sh [--root DIR] [check|selftest|all]
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
		sed -n '2,31p' "$0"
		exit 0
		;;
	*)
		echo "consumers-check.sh: unknown argument '$1'" >&2
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

# Extract "repo|what" pairs from consumers.json, without needing jq.
consumers_pairs() {
	python3 - "$1" <<'PY'
import json,sys
with open(sys.argv[1]) as f:
    data=json.load(f)
for c in data["consumers"]:
    print(f'{c["repo"]}|{c["what"]}')
PY
}

# Extract "repo|what" pairs from the README table.
readme_pairs() {
	python3 - "$1" <<'PY'
import re,sys
rows=[]
inside=False
for line in open(sys.argv[1]):
    if line.startswith('## Repos on the pipeline'):
        inside=True; continue
    if inside and line.startswith('## '):
        break
    if inside and line.startswith('|'):
        m=re.match(r'\|\s*\[([^\]]+)\]\([^)]*\)\s*\|\s*(.*?)\s*\|\s*$', line)
        if m:
            rows.append(f'{m.group(1)}|{m.group(2)}')
for r in rows:
    print(r)
PY
}

run_check() {
	local root="$1" quiet="${2:-}"
	local json="$root/consumers.json"
	local readme="$root/README.md"

	if [ ! -f "$json" ]; then
		echo "FAIL: no consumers.json at $json" >&2
		return 1
	fi
	if [ ! -f "$readme" ]; then
		echo "FAIL: no README.md at $readme" >&2
		return 1
	fi

	local want got
	want="$(consumers_pairs "$json")" || {
		echo "FAIL: could not parse consumers.json" >&2
		return 1
	}
	got="$(readme_pairs "$readme")" || {
		echo "FAIL: could not parse README table" >&2
		return 1
	}

	if [ -z "$want" ]; then
		echo "FAIL: consumers.json lists no repos — refusing to pass vacuously" >&2
		return 1
	fi
	if [ -z "$got" ]; then
		echo "FAIL: no 'Repos on the pipeline' table rows found in README.md" >&2
		return 1
	fi

	local rc=0
	local diff_out
	diff_out="$(diff <(printf '%s\n' "$want" | sort) <(printf '%s\n' "$got" | sort))"
	if [ -n "$diff_out" ]; then
		rc=1
		if [ -z "$quiet" ]; then
			echo "FAIL: README table disagrees with consumers.json" >&2
			echo "  '<' = in consumers.json only, '>' = in README only" >&2
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

	cp "$ROOT/consumers.json" "$tmp/consumers.json"
	cp "$ROOT/README.md" "$tmp/README.md"

	if run_check "$tmp" quiet; then
		note_ok "self-test: the real tree passes"
	else
		note_bad "self-test: the real tree does not pass its own check"
	fi

	# Plant a repo in consumers.json that the README does not list. This is the
	# exact defect that shipped, so it is the one the self-test must catch.
	python3 - "$tmp/consumers.json" <<'PY'
import json,sys
p=sys.argv[1]
with open(p) as f: d=json.load(f)
d["consumers"].append({"repo":"planted-repo","what":"planted by the self-test","coverageExclusions":[],"fmtPaths":"src test script"})
with open(p,"w") as f: json.dump(d,f,indent=2)
PY
	if run_check "$tmp" quiet; then
		note_bad "self-test: a repo missing from the README was NOT caught"
	else
		note_ok "self-test: a repo missing from the README was caught"
	fi

	# And the other direction: a README row with no entry in consumers.json. The
	# row must be planted INSIDE the table section — appending at end-of-file
	# plants nothing, because the parser stops at the next heading. The first
	# version of this self-test made exactly that mistake and reported a false
	# failure, which is the self-test earning its place.
	cp "$ROOT/consumers.json" "$tmp/consumers.json"
	cp "$ROOT/README.md" "$tmp/README.md"
	python3 - "$tmp/README.md" <<'PY'
import sys
p = sys.argv[1]
lines = open(p).readlines()
out, inside, planted = [], False, False
for line in lines:
    if line.startswith('## Repos on the pipeline'):
        inside = True
    elif inside and line.startswith('## '):
        inside = False
    if inside and not planted and line.startswith('| [') and line.rstrip().endswith('|'):
        out.append(line)
        out.append('| [ghost-repo](https://github.com/pigfox/ghost-repo) | not in consumers.json |\n')
        planted = True
        continue
    out.append(line)
if not planted:
    raise SystemExit('self-test could not plant a row inside the table')
open(p, 'w').writelines(out)
PY
	if run_check "$tmp" quiet; then
		note_bad "self-test: a README row with no consumers.json entry was NOT caught"
	else
		note_ok "self-test: a README row with no consumers.json entry was caught"
	fi
}

case "$MODE" in
selftest)
	run_selftest
	;;
check)
	if run_check "$ROOT"; then
		note_ok "check: README table matches consumers.json"
	else
		fail=1
	fi
	;;
all)
	run_selftest
	if run_check "$ROOT"; then
		note_ok "check: README table matches consumers.json"
	else
		fail=1
	fi
	;;
esac

if [ "$fail" -ne 0 ]; then
	echo "CONSUMERS CHECK: FAIL" >&2
	exit 1
fi
echo "CONSUMERS CHECK: PASS"
