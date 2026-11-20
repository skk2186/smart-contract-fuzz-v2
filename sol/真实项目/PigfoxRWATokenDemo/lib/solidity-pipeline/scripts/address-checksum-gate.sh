#!/usr/bin/env bash
#
# address-checksum-gate.sh — mechanical enforcement of EIP-55 address casing.
#
# WHY THIS EXISTS. A pinned contract address is not decoration. It is the `to` of
# a real transaction, and viem — the signer behind every wallet flow in this
# estate — validates EIP-55 BEFORE it estimates gas. It refuses an address whose
# capitalisation does not match its checksum:
#
#   EstimateGasExecutionError: Address "0xd6F7…19b" is invalid.
#   - Address must match its checksum counterpart.
#
# Three gas-demo addresses were mis-cased from the day they were pinned. They were
# imported that way from a deployments/base-sepolia.json in this very estate, and
# nothing noticed until two live wallet takes died on them, sixty seconds at a
# time, with the page reporting a nonce problem it did not have. The consuming
# site now guards its own copies. This gate guards the ORIGIN, where the bytes are
# written down first — and it lives HERE, in the shared pipeline, because a copy
# of it in one contract repo is the exact failure this pipeline exists to prevent.
#
# THE ORACLE IS THE TOOLCHAIN'S OWN. The correct casing comes from
# `cast to-check-sum-address` — the same implementation forge, cast and every
# Foundry script in the estate already use — so this gate cannot drift from the
# thing it protects by re-deriving EIP-55 here. `cast` is called with exactly ONE
# argument on purpose: a second argument is a chain id and selects EIP-1191, which
# is a DIFFERENT checksum from the one a wallet applies.
#
# WHAT COUNTS AS A HIT. Exactly what viem's `isAddress(a, { strict: true })`
# rejects, and nothing more:
#
#   * an all-lower-case address asserts no checksum at all and PASSES, because
#     viem accepts it (`address.toLowerCase() === address` returns early);
#   * anything carrying an upper-case hex letter asserts a checksum, and that
#     assertion has to be true.
#
# THE SCAN SET IS BUILT BY CONSTRUCTION — every 20-byte hex literal in every
# TRACKED file, never a list of files somebody remembered to name. A named target
# is a hypothesis: the incident above was found in four places and the repo held
# addresses in three more. Longer hex runs — a 32-byte hash, a keccak topic, a
# bytecode blob — are matched WHOLE and then discarded, so nothing bites the first
# forty characters of something that is not an address.
#
# It also SELF-TESTS, and the self-test cannot pass vacuously. It plants a
# mis-cased address alongside its correct form, its lower-case form and a 32-byte
# topic, then requires the scan to have SEEN the three address literals and to
# have rejected exactly the one that is wrong, on the right line, with the right
# correction. A scanner that has silently stopped matching reports the same green
# as a clean tree; an empty scan set is what that looks like, so it fails.
#
# Usage:
#   address-checksum-gate.sh [--root DIR] [--exclude PATH]... [--allow-empty]
#                            [scan|selftest|all]
#
# stderr is never suppressed: a scan that cannot read the tree must be loud.
set -uo pipefail

ROOT="$PWD"
MODE="all"
ALLOW_EMPTY=0
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
	--allow-empty)
		ALLOW_EMPTY=1
		shift
		;;
	scan | selftest | all)
		MODE="$1"
		shift
		;;
	-h | --help)
		sed -n '2,54p' "$0"
		exit 0
		;;
	*)
		echo "address-checksum-gate.sh: unknown argument '$1'" >&2
		exit 2
		;;
	esac
done

cd "$ROOT" || {
	echo "FAIL: cannot enter $ROOT" >&2
	exit 2
}

# A 20-byte hex literal, plus any hex that FOLLOWS it. Matching the tail is what
# lets the filter discard a longer run whole: a 32-byte topic matches as all
# sixty-four of its characters and then fails the exact-length test, instead of
# matching its own first forty and being reported as a mis-cased address.
ADDR_RE='0x[0-9a-fA-F]{40}[0-9a-fA-F]*'
EXACT_RE=':0x[0-9a-fA-F]{40}$'

# This file necessarily contains the mis-cased address its self-test plants. When
# the pipeline is consumed as a submodule its contents are not tracked by the
# consuming repo and git grep never sees it — but when the gate is pointed at a
# repo that DOES track a copy, that copy excludes itself and nothing else.
SELF_PATHS=("scripts/address-checksum-gate.sh" "lib/solidity-pipeline/scripts/address-checksum-gate.sh")

# The one address in this file that is deliberately wrong, and its correction.
# Held as constants so the self-test asserts the same bytes it plants.
PLANTED_BAD="0xd6F73E9f845f3c9B059b5EA2e5320cd3E15Ec19b"
PLANTED_GOOD="0xD6f73e9f845F3C9B059B5EA2E5320CD3e15ec19b"

require_cast() {
	if ! command -v cast >/dev/null; then
		echo "FAIL: 'cast' is not on PATH." >&2
		echo "This gate takes its EIP-55 answer from Foundry's own implementation rather than re-deriving the checksum, so it cannot run without it. Install Foundry (foundryup), or run this from a job that sets the toolchain up." >&2
		return 1
	fi
	return 0
}

# scan prints every address literal in the tracked tree as "path:line:0xADDR".
scan() {
	local excludes=() p
	for p in "${SELF_PATHS[@]}" ${EXTRA_EXCLUDES[@]+"${EXTRA_EXCLUDES[@]}"}; do
		excludes+=(":(exclude)$p")
	done

	# git grep over tracked files only — untracked and gitignored paths are out
	# of scope by design. -I skips binaries; -n gives a reviewable location.
	git grep -I -n -o -E "$ADDR_RE" -- . "${excludes[@]}" | grep -E "$EXACT_RE"
}

# report_offenders HITS
#
# Prints one line per OCCURRENCE of every address whose casing asserts a checksum
# it does not have. Returns 0 when there are none, 1 when there are, and 2 when
# the oracle itself could not answer — which must never read as "found none".
#
# The oracle is consulted once per DISTINCT address rather than once per
# occurrence: a tracked fuzzer transcript holds thousands of repeats of a few
# dozen addresses, and that is the difference between seconds and minutes.
report_offenders() {
	local hits="$1"
	local cands a lc want badlist=""

	# Only literals carrying an upper-case hex letter assert a checksum. An
	# all-lower-case address asserts nothing and viem accepts it, so it is not
	# this gate's business.
	cands="$(printf '%s\n' "$hits" | sed 's/.*://' | sort -u | grep -E '[A-F]' || true)"

	while IFS= read -r a; do
		[ -n "$a" ] || continue
		lc="${a,,}"
		want="$(cast to-check-sum-address "$lc" || true)"
		case "$want" in
		0x????????????????????????????????????????) ;;
		*)
			echo "FAIL: the checksum oracle did not answer for $lc — 'cast to-check-sum-address' returned '${want}'." >&2
			echo "A gate that cannot compute its own answer must not report green." >&2
			return 2
			;;
		esac
		[ "$want" != "$a" ] || continue
		badlist="${badlist}${a} ${want}"$'\n'
	done <<<"$cands"

	[ -n "$badlist" ] || return 0

	local occurrences hit
	while IFS=' ' read -r a want; do
		[ -n "$a" ] || continue
		occurrences="$(printf '%s\n' "$hits" | grep -F -- ":$a")"
		while IFS= read -r hit; do
			[ -n "$hit" ] || continue
			printf '%s: %s fails EIP-55 — should be %s\n' "${hit%:*}" "$a" "$want"
		done <<<"$occurrences"
	done <<<"$badlist"

	return 1
}

run_scan() {
	require_cast || return 2

	local hits total distinct report rc
	hits="$(scan)"
	total="$(printf '%s\n' "$hits" | grep -c . || true)"
	distinct="$(printf '%s\n' "$hits" | sed 's/.*://' | sort -u | grep -c . || true)"

	if [ "$total" = "0" ]; then
		if [ "$ALLOW_EMPTY" = "1" ]; then
			echo "  ok   scan: no address literals in tracked files (--allow-empty was passed, so the silence is a decision)"
			return 0
		fi
		echo "FAIL: no 20-byte address literals were found in any tracked file." >&2
		echo "A scan set of zero is not a pass. It is the shape a broken matcher makes, and it is indistinguishable from a clean tree." >&2
		echo "If this repo genuinely pins no addresses, say so with --allow-empty rather than letting the silence stand in for it." >&2
		return 1
	fi

	report="$(report_offenders "$hits")"
	rc=$?
	if [ "$rc" = "2" ]; then
		return 2
	fi
	if [ "$rc" != "0" ]; then
		echo "FAIL: address literals whose casing asserts an EIP-55 checksum they do not have:" >&2
		printf '%s\n' "$report" >&2
		echo >&2
		echo "Fix the CASING, never the bytes: the contract is not wrong, its spelling is." >&2
		echo "An address is not corrected until every reference agrees — deployments/*.json, the repo README, the Basescan links, and every pinned copy in the consuming site's handlers, modules and specs." >&2
		return 1
	fi

	echo "  ok   scan: $total address literals ($distinct distinct) across the tracked tree; every checksum-asserting one is EIP-55 valid"
	return 0
}

# selftest proves the scan can still catch what it claims to catch, and that it
# is still looking at anything at all.
run_selftest() {
	require_cast || return 2

	local planted=".address-checksum-gate-selftest.md"

	if [ -e "$planted" ]; then
		echo "FAIL: self-test scratch path $planted already exists — refusing to clobber it" >&2
		return 1
	fi

	# Four literals on four lines, and only the first one is wrong:
	#   1  a mis-cased address — the casing that broke a live demo
	#   2  the same address, correctly checksummed
	#   3  the same address, all lower case: asserts no checksum, viem accepts it
	#   4  a 32-byte topic, whose first forty hex characters are not an address
	{
		printf 'mis-cased: %s\n' "$PLANTED_BAD"
		printf 'checksummed: %s\n' "$PLANTED_GOOD"
		printf 'lower case: 0xd6f73e9f845f3c9b059b5ea2e5320cd3e15ec19b\n'
		printf 'topic: 0x90fbe6e87fbfe6ac0f8a2736801fd2df6b346912c4d67348b4b4f948d801727a\n'
	} >"$planted"

	git add -N -- "$planted" || {
		echo "FAIL: could not stage the planted file for git grep" >&2
		rm -f -- "$planted"
		return 1
	}

	# Capture, then match in-shell. Piping scan into `grep -q` looks equivalent
	# and is not: grep exits on the first match, git grep takes SIGPIPE writing
	# the rest, and `pipefail` reports that as failure — so the self-test would
	# misreport whenever the tree ALSO had real hits, i.e. exactly when it
	# matters.
	local hits mine seen report rc
	hits="$(scan)"
	mine="$(printf '%s\n' "$hits" | grep -F -- "$planted:" || true)"
	seen="$(printf '%s\n' "$mine" | grep -c . || true)"
	report="$(report_offenders "$mine")"
	rc=$?

	git rm --cached --quiet -- "$planted" >/dev/null
	rm -f -- "$planted"

	if [ "$rc" = "2" ]; then
		return 2
	fi

	# VACUITY FIRST. A matcher that has stopped matching produces an empty scan
	# set, and an empty scan set produces no offenders — which is the same
	# output a clean tree produces. Assert that the gate SAW something before
	# believing anything it says about what it saw.
	if [ "$seen" = "0" ]; then
		echo "FAIL: self-test — the scan matched NOTHING in a file holding three address literals." >&2
		echo "The matcher is broken. An empty scan set is what a broken matcher and a clean tree have in common, so this must never pass." >&2
		return 1
	fi
	if [ "$seen" != "3" ]; then
		echo "FAIL: self-test — expected the scan to see exactly 3 address literals in the planted file (a mis-cased address, its checksummed form and its lower-case form) while skipping the 32-byte topic; it saw $seen." >&2
		printf '%s\n' "$mine" >&2
		return 1
	fi
	if [ "$rc" != "1" ]; then
		echo "FAIL: self-test — a planted mis-cased address was NOT rejected. The gate's pass means nothing." >&2
		return 1
	fi

	local n
	n="$(printf '%s\n' "$report" | grep -c . || true)"
	if [ "$n" != "1" ]; then
		echo "FAIL: self-test — expected exactly one rejection (the mis-cased address on line 1), got $n." >&2
		echo "The checksummed form, the lower-case form and the 32-byte topic must all be left alone." >&2
		printf '%s\n' "$report" >&2
		return 1
	fi
	if [ "$report" != "$planted:1: $PLANTED_BAD fails EIP-55 — should be $PLANTED_GOOD" ]; then
		echo "FAIL: self-test — the rejection did not name the planted file, its line, or the correct casing." >&2
		echo "  wanted: $planted:1: $PLANTED_BAD fails EIP-55 — should be $PLANTED_GOOD" >&2
		echo "  got   : $report" >&2
		return 1
	fi

	echo "  ok   self-test: a planted mis-cased address was caught on the right line with the right correction; its checksummed form, its lower-case form and a 32-byte topic were left alone"
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
		echo "ADDRESS CHECKSUM GATE: PASS"
	else
		echo "ADDRESS CHECKSUM GATE: FAIL" >&2
	fi
	exit "$rc"
	;;
esac
