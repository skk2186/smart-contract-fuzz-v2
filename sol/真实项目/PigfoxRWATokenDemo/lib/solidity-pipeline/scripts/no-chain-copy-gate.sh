#!/usr/bin/env bash
#
# no-chain-copy-gate.sh — mechanical enforcement of the DIRECT-CHAIN DOCTRINE.
#
# Everything in this estate talks to Base Sepolia (84532) directly, or runs in a
# pure in-process EVM it builds itself from source. Nothing points the EVM at a
# copy of a remote chain's state. This gate is what makes that a fact rather than
# a habit: it greps every TRACKED file for the banned tokens and fails on a hit.
#
# NOTE ON SCOPE — the doctrine bans copying a remote chain's state. It does NOT
# ban the in-memory local EVM that `forge test`, Echidna and Medusa construct:
# those build fresh contracts from source in-process, reach no network, and stand
# in for nothing. Without them the property fuzzing this pipeline is built around
# could not exist. Only the copy-a-live-chain tokens are banned, and this gate
# bans them LITERALLY — including inside a negation. Write the doctrine as an
# absence, not as a disclaimer that names what it forbids.
#
# It also SELF-TESTS. A grep gate that has silently stopped matching — a bad
# path, a changed grep, a quoting slip — reports the same green as a clean tree,
# which is the failure mode this whole exercise exists to prevent. So before
# trusting a pass, the gate plants a token in a temporary tracked-path file,
# re-runs its own scan, and refuses to pass unless it catches the plant.
#
# Usage:
#   no-chain-copy-gate.sh [--root DIR] [--exclude PATH]... [scan|selftest|all]
#
# stderr is never suppressed: a grep that cannot read the tree must be loud.
set -uo pipefail

ROOT="$PWD"
MODE="all"
EXTRA_EXCLUDES=()

while [ "$#" -gt 0 ]; do
	case "$1" in
	--root)
		ROOT="$2"
		shift 2
		;;
	--exclude)
		EXTRA_EXCLUDES+=("$2")
		shift 2
		;;
	scan | selftest | all)
		MODE="$1"
		shift
		;;
	-h | --help)
		sed -n '2,26p' "$0"
		exit 0
		;;
	*)
		echo "no-chain-copy-gate.sh: unknown argument '$1'" >&2
		exit 2
		;;
	esac
done

cd "$ROOT" || {
	echo "FAIL: cannot enter $ROOT" >&2
	exit 2
}

# The banned tokens, one -e per token. Matching is case-insensitive, so a single
# token covers its capitalised spellings.
TOKENS=(fork forking fork-url fork_url --fork-url ForkRotation)

# This file necessarily contains every token it bans. When the pipeline is
# consumed as a submodule its contents are not tracked by the consuming repo and
# git grep never sees it — but when the gate is pointed at a repo that DOES track
# a copy, that copy excludes itself and nothing else.
SELF_PATHS=("scripts/no-chain-copy-gate.sh" "lib/solidity-pipeline/scripts/no-chain-copy-gate.sh")

# scan prints every offending "path:line:text" and returns 1 if there were any.
scan() {
	local args=() t p
	for t in "${TOKENS[@]}"; do args+=(-e "$t"); done

	local excludes=()
	for p in "${SELF_PATHS[@]}" ${EXTRA_EXCLUDES[@]+"${EXTRA_EXCLUDES[@]}"}; do
		excludes+=(":(exclude)$p")
	done

	# git grep over tracked files only — untracked and gitignored paths are out
	# of scope by design. -I skips binaries; -n gives a reviewable location.
	git grep -I -n -i "${args[@]}" -- . "${excludes[@]}"
}

run_scan() {
	local hits
	hits="$(scan)"
	if [ -n "$hits" ]; then
		echo "FAIL: chain-copy tokens present in tracked files:" >&2
		printf '%s\n' "$hits" >&2
		return 1
	fi
	echo "  ok   scan: no chain-copy tokens in tracked files"
	return 0
}

# selftest proves the scan can still catch what it claims to catch.
run_selftest() {
	local planted=".no-chain-copy-gate-selftest.md"

	if [ -e "$planted" ]; then
		echo "FAIL: self-test scratch path $planted already exists — refusing to clobber it" >&2
		return 1
	fi

	# Assemble the token so this line is not itself a hit in the source.
	printf 'planted by the gate self-test: --%s-url\n' "fork" >"$planted"
	git add -N -- "$planted" || {
		echo "FAIL: could not stage the planted file for git grep" >&2
		rm -f -- "$planted"
		return 1
	}

	# Capture, then match in-shell. Piping scan into `grep -q` looks equivalent
	# and is not: grep exits on the first match, git grep takes SIGPIPE writing
	# the rest, and `pipefail` reports that as failure — so the self-test would
	# report "not caught" whenever the tree ALSO had real hits, i.e. exactly when
	# it matters.
	local out caught=0
	out="$(scan)"
	case "$out" in
	*"$planted"*) caught=1 ;;
	esac

	git rm --cached --quiet -- "$planted" >/dev/null
	rm -f -- "$planted"

	if [ "$caught" != "1" ]; then
		echo "FAIL: self-test — the gate did NOT catch a planted token. The scan is broken and its pass means nothing." >&2
		return 1
	fi
	echo "  ok   self-test: a planted token was caught"
	return 0
}

case "$MODE" in
scan) run_scan ;;
selftest) run_selftest ;;
all)
	rc=0
	run_selftest || rc=1
	run_scan || rc=1
	if [ "$rc" = "0" ]; then
		echo "NO-CHAIN-COPY GATE: PASS"
	else
		echo "NO-CHAIN-COPY GATE: FAIL" >&2
	fi
	exit "$rc"
	;;
esac
