#!/usr/bin/env bash
#
# coverage.sh — the pigfox Solidity coverage gate.
#
# Requires 100% LINE, STATEMENT, BRANCH and FUNCTION coverage on every file under
# src/, with only NAMED, DOCUMENTED exclusions.
#
# This is a gate, not a report. Three things fail it:
#
#   1. Any non-excluded src/ file below 100% on any of the four metrics.
#   2. A report it cannot parse. A `forge coverage` output-format change must
#      never pass by default — "I found no rows, so nothing was under 100%" is
#      the exact shape of a gate that has silently stopped working.
#   3. A declared exclusion that matched no row. A stale or misspelled exclusion
#      is a hole in the gate that reads as a documented decision.
#
# Usage:
#   coverage.sh [--root DIR] [--exclude PATH]... [--report FILE] [--skip-run]
#               [--no-match-contract REGEX]
#
#   --root DIR      repo to gate (default: $PWD)
#   --exclude PATH  a src/-relative-to-repo-root path to skip, e.g. src/Verifier.sol.
#                   Repeatable. Every exclusion must be justified in the consuming
#                   repo's docs; see docs/ADOPTING.md.
#   --report FILE   where to write/read the summary (default: coverage-summary.txt)
#   --skip-run      re-check an existing report instead of re-running the suite.
#                   Used by the pipeline's own self-test to exercise the gate.
#   --no-match-contract REGEX
#                   TEST CONTRACTS whose coverage run is skipped. This does NOT
#                   exclude any src/ file and does NOT lower the threshold — see
#                   the block below, which is the whole justification.
#
# Environment: COVERAGE_EXCLUDE may carry a comma-separated exclusion list, which
# is how the reusable workflow passes its `coverage-exclusions` input through.
# It is merged with any --exclude flags. COVERAGE_NO_MATCH_CONTRACT carries the
# `--no-match-contract` value the same way.
#
# --- WHY --no-match-contract IS NOT A WEAKENED GATE ------------------------
#
# It drops a test contract from INSTRUMENTATION, never from RUNNING. The suite it
# names still executes in full at the `forge test` stage, and under both fuzzers.
# What changes is only which tests are used to MEASURE coverage, and the threshold
# they are measured against does not move: every src/ row must still be 100% on
# all four metrics, and this script still refuses an unparseable report and a
# vacuous pass.
#
# THE CASE IT WAS ADDED FOR, with numbers. deposit-dispute's invariant harness
# builds merkle proofs in Solidity, so every call does real hashing. Under
# instrumentation (which disables the optimizer) its coverage run peaks at
# 33.8 GiB — measured, `Maximum resident set size: 35421688 kB` — against a
# standard GitHub runner's 16 GB, so the runner died rather than the gate failing.
# The split: 67 unit tests cost 0.37 CPU-seconds, 20 invariant tests cost 2,473.
# And the invariant suite covers NOTHING the unit suite misses — with it excluded
# the report is byte-identical at 100% on all four metrics (151/151 lines,
# 184/184 statements, 40/40 branches, 26/26 functions) in 5.6s at 433 MiB.
#
# SO THE EXCLUSION IS SAFE ONLY WHILE THAT IDENTITY HOLDS, and nothing here
# assumes it keeps holding. If the unit suite ever stops reaching a line, a
# statement, a branch or a function, that row drops below 100% and THIS GATE FAILS
# — the same enforcement that has always been here, now doing double duty as the
# guard on the exclusion. The exclusion cannot start hiding something silently,
# because the only way it could hide anything is by producing a sub-100% row, and
# a sub-100% row is a failure. That is why this is a `--no-match-contract` on the
# INSTRUMENTATION and not an `--exclude` of a src/ file: an --exclude removes a
# row from the check, and this does not remove any row at all.
set -euo pipefail

ROOT="$PWD"
REPORT="coverage-summary.txt"
SKIP_RUN=0
EXCLUDES=()
NO_MATCH_CONTRACT=""

while [ "$#" -gt 0 ]; do
	case "$1" in
	--root)
		ROOT="$2"
		shift 2
		;;
	--exclude)
		EXCLUDES+=("$2")
		shift 2
		;;
	--report)
		REPORT="$2"
		shift 2
		;;
	--no-match-contract)
		# Explicit arity check. Without it `set -u` turns a missing value into an
		# "unbound variable" crash that exits 1 — indistinguishable from a gate
		# REJECTION, which is the one thing an exit code here must never be
		# ambiguous about. A usage error is 2.
		if [ "$#" -lt 2 ]; then
			echo "coverage.sh: --no-match-contract requires a value" >&2
			exit 2
		fi
		NO_MATCH_CONTRACT="$2"
		shift 2
		;;
	--skip-run)
		SKIP_RUN=1
		shift
		;;
	-h | --help)
		sed -n '2,65p' "$0"
		exit 0
		;;
	*)
		echo "coverage.sh: unknown argument '$1'" >&2
		exit 2
		;;
	esac
done

# Merge the environment-provided list. Empty entries are dropped rather than
# turned into an exclusion that matches nothing and then fails rule 3.
if [ -n "${COVERAGE_EXCLUDE:-}" ]; then
	IFS=',' read -r -a _env_excludes <<<"$COVERAGE_EXCLUDE"
	for e in "${_env_excludes[@]}"; do
		e="$(printf '%s' "$e" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
		[ -n "$e" ] && EXCLUDES+=("$e")
	done
fi

# Same channel for the instrumentation exclusion. A whitespace-only value is
# treated as unset rather than as a regex that matches everything.
if [ -z "$NO_MATCH_CONTRACT" ] && [ -n "${COVERAGE_NO_MATCH_CONTRACT:-}" ]; then
	NO_MATCH_CONTRACT="$(printf '%s' "$COVERAGE_NO_MATCH_CONTRACT" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
fi

cd "$ROOT"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }

if [ "$SKIP_RUN" = "1" ]; then
	log "Reusing existing report at $REPORT"
	if [ ! -f "$REPORT" ]; then
		echo "FAIL: --skip-run given but $REPORT does not exist." >&2
		exit 1
	fi
else
	log "Running forge coverage in $ROOT"
	# Test and script sources are excluded from the report: they are the
	# instrument, not the artifact under test.
	#
	# --no-match-contract, when set, drops a TEST CONTRACT from instrumentation.
	# It is announced rather than applied quietly, because a reader of this log
	# must be able to see that a suite did not contribute to the figures below —
	# and must be able to see that it is a suite, not a src/ file. The threshold
	# is unchanged either way, which is what makes it safe; see the header.
	if [ -n "$NO_MATCH_CONTRACT" ]; then
		forge coverage \
			--no-match-coverage '(script|test)/' \
			--no-match-contract "$NO_MATCH_CONTRACT" \
			--report summary |
			tee "$REPORT"
	else
		forge coverage \
			--no-match-coverage '(script|test)/' \
			--report summary |
			tee "$REPORT"
	fi
fi

echo
if [ "${#EXCLUDES[@]}" -eq 0 ]; then
	log "Enforcing 100% coverage on src/ (no exclusions)"
else
	log "Enforcing 100% coverage on src/ (excluding: ${EXCLUDES[*]})"
fi
# Announced HERE rather than beside the forge invocation, so it is stated whenever
# the exclusion is in force — including under --skip-run, where no run happens but
# the report being checked was still produced with a suite left out. A reader of
# this log must be able to see that, and an earlier draft of this script printed it
# only on the run path, where --skip-run silently omitted it.
if [ -n "$NO_MATCH_CONTRACT" ]; then
	log "Instrumentation excluded test contracts matching: $NO_MATCH_CONTRACT"
	log "  those tests STILL RUN at the forge test stage and under both fuzzers —"
	log "  this drops them from measurement, not from execution."
	log "  And this is the guard on that exclusion: if the remaining tests stop"
	log "  reaching any line, statement, branch or function, the row drops below"
	log "  100% and this gate fails. The exclusion cannot hide a gap silently."
fi

# The exclusion list crosses into awk as a newline-delimited blob rather than as
# a shell-expanded pattern, so a path containing a regex metacharacter is matched
# literally.
printf '%s\n' "${EXCLUDES[@]+"${EXCLUDES[@]}"}" | awk '
    NR == FNR {
        if ($0 != "") { excluded[$0] = 1; declared[$0] = 1 }
        next
    }

    # Summary table rows for source files, e.g.
    # | src/Escrow.sol | 100.00% (92/92) | 100.00% (61/61) | ... |
    /^\| *src\// {
        n = split($0, cells, "|")
        if (n < 6) {
            printf "  MALFORMED ROW: %s\n", $0
            malformed++
            next
        }
        file = cells[2]
        gsub(/^[ \t]+|[ \t]+$/, "", file)

        if (file in excluded) {
            printf "  SKIP  %-40s (documented exclusion)\n", file
            delete declared[file]
            skipped++
            next
        }

        seen++
        bad = 0
        for (i = 3; i <= 6; i++) {
            pct = cells[i]
            gsub(/^[ \t]+/, "", pct)
            if (pct !~ /^[0-9]+(\.[0-9]+)?%/) { malformed++; bad = 1; continue }
            sub(/%.*/, "", pct)
            if (pct + 0 < 100) bad = 1
        }

        if (bad) {
            printf "  FAIL  %-40s %s\n", file, $0
            failures++
        } else {
            printf "  OK    %-40s 100%% lines / statements / branches / functions\n", file
        }
    }

    END {
        rc = 0
        if (seen == 0 && skipped == 0) {
            print "\nERROR: no src/ rows found in the coverage summary."
            print "The report format may have changed, or the run produced nothing."
            print "Refusing to pass by default."
            rc = 1
        }
        if (malformed > 0) {
            printf "\nERROR: %d coverage row(s) did not parse as expected.\n", malformed
            print "Refusing to pass by default; a format change is a gate failure, not a pass."
            rc = 1
        }
        for (f in declared) {
            printf "\nERROR: declared exclusion %s matched no row in the report.\n", f
            print "A stale exclusion is a hole in the gate that reads as a decision."
            rc = 1
        }
        if (failures > 0) {
            printf "\nFAILED: %d file(s) under 100%% coverage.\n", failures
            rc = 1
        }
        if (rc != 0) exit rc
        printf "\nPASSED: %d file(s) at 100%% on all four metrics", seen
        if (skipped > 0) printf " (%d documented exclusion(s))", skipped
        printf ".\n"
    }
' - "$REPORT"
