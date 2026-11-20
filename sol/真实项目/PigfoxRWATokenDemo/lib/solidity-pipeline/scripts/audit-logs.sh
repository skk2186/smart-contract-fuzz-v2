#!/usr/bin/env bash
#
# audit-logs.sh — capture every gate's FULL output as committed, plain-text logs.
#
# WHY. Everything this pipeline measures currently lives for the length of a CI
# log and then expires, and reading it needs a GitHub account and a login. The
# figures in pipeline-summary.json say what the tools concluded; they do not let a
# stranger read what the tools actually SAID. These logs do. They are committed,
# so they survive; plain text, so GitHub renders them in-browser with line numbers
# and permalinks; and public, so no login stands between a reader and the evidence.
#
# PLAIN TEXT, NEVER COMPRESSED. A .gz forces a download and defeats the entire
# point — permalinking to a line inside a gzip is not possible.
#
# NON-TTY CAPTURE. Both fuzzers change format when they detect a terminal:
# Echidna draws an ncurses dashboard and Medusa emits ANSI colour. Piping to a
# file already denies them a TTY, which is why every capture here redirects rather
# than using `script` or a pty. What lands in the file is what a machine sees.
#
# SECRETS ARE A STOP, NOT A REDACTION. The scan below runs BEFORE anything is
# considered committable. A hit means a tool printed something it should not have,
# and quietly masking it would hide that fact while leaving the underlying leak in
# place. So it fails loudly and commits nothing.
#
# Usage:
#   audit-logs.sh [--root DIR] [--out DIR] [--exclusions LIST]
#                 [capture|scan|selftest|all]
#
# stderr is never suppressed.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$PWD"
OUT="audit"
EXCLUSIONS=""
MODE="all"

while [ "$#" -gt 0 ]; do
	case "$1" in
	--root)
		ROOT="$2"
		shift 2
		;;
	--out)
		OUT="$2"
		shift 2
		;;
	--exclusions)
		EXCLUSIONS="$2"
		shift 2
		;;
	capture | scan | selftest | all)
		MODE="$1"
		shift
		;;
	-h | --help)
		sed -n '2,30p' "$0"
		exit 0
		;;
	*)
		echo "audit-logs.sh: unknown argument '$1'" >&2
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

# ---------------------------------------------------------------------------
# SECRET SCAN
#
# Deliberately shape-based rather than name-based: a leak does not announce
# itself with the word "secret". A 64-hex run is a private key or a tx-signing
# nonce; 0x-prefixed 64-hex likewise. Bearer tokens and DSNs carry their own
# unmistakable prefixes.
#
# The 40-hex address case is EXCLUDED on purpose — contract addresses are public,
# appear in every one of these logs by design, and flagging them would make the
# scan cry wolf until somebody turned it off.
#
# THE 64-HEX PATTERN IS ANCHORED ON BOTH SIDES, and that is the difference between
# a working scan and one nobody can leave switched on. The first version anchored
# only the trailing edge, and firing it at a real `forge test -vvvv` log produced
# a page of hits, every one of them harmless:
#
#   · ABI-encoded revert payloads — `expectRevert(custom error 0xf28dceb3: 0000…)`
#     is a 200-plus character hex blob, and an unanchored 64-hex pattern matches a
#     window *inside* it at some arbitrary offset.
#   · Long DECIMAL fuzz inputs. `1266759450417450380370089892014882138640698…`
#     is 70 digits, and every decimal digit is also a valid hex character, so a
#     64-character window inside it matches a "hex" pattern perfectly.
#
# Requiring a non-hex boundary on BOTH sides removes the window-inside-a-blob
# class outright. `x` is excluded from the leading boundary so `0x`-prefixed keys
# are not missed.
#
# That still was not enough, and the second failure is the more interesting one:
# the property fuzzers emit decimal inputs of EXACTLY 64 digits, which are
# boundary-anchored and character-for-character indistinguishable from 64-hex.
# No amount of anchoring separates them.
#
# What does separate them is that hex contains LETTERS. A 64-character run of
# nothing but 0-9 is a decimal integer; a private key that happened to contain no
# a-f at all has probability (10/16)^64, about 1 in 10^14. So the pattern requires
# at least one [a-fA-F] inside the run, which is why this needs grep -P rather
# than -E: POSIX ERE has no lookahead to express "64 hex chars, at least one of
# them a letter".
#
# A FOURTH class survived even that, and it is the subtlest: a 32-byte ABI word.
# `expectRevert(custom error 0xc31eb0e0: 2e70248b0000…0000)` is a 4-byte selector
# zero-padded to 32 bytes — exactly 64 hex characters, boundary-anchored, and it
# contains letters, so every rule above passes it through.
#
# The discriminator is the PADDING. ABI encoding pads with long runs of zeros; a
# private key does not. Requiring the run to contain no 24-or-more consecutive
# zeros removes the whole class while leaving real key material matched. Chosen as
# a shape rule rather than a context rule (such as "ignore lines saying
# expectRevert") on purpose: a context exemption would swallow a key that happened
# to appear on such a line, whereas this one only ever exempts the padding itself.
#
# The honest cost of that: a private key of 64 decimal digits would not be caught.
# That is accepted, because it is a 1-in-10^14 shape AND this scan is a safety
# net rather than the control — keys are never written into these repos by design,
# and every deploy script reads them via vm.envUint precisely so they cannot reach
# a log in the first place.
#
# Transaction hashes and Merkle roots are legitimate STANDALONE 64-hex and do
# still hit. That is correct: a hit is reported for a HUMAN to classify, and it is
# a stop rather than an auto-redaction.
# ---------------------------------------------------------------------------
# THE LIMIT OF SHAPE SCANNING, and why an allow-list exists.
#
# A keccak hash and a private key are both uniform 32-byte values. Nothing about
# their shape separates them, and `forge test -vvvv` traces are full of the former:
# the ERC-1967 implementation slot, event topic hashes, commitments, nullifiers.
# zk-escrow's traces hit twelve of them.
#
# So values that are PUBLIC BY CONSTRUCTION are allow-listed BY VALUE, each with a
# written reason, in the calling repo's audit-allowlist.txt. That keeps the scan
# sharp: anything not explicitly listed still fails. The alternative — exempting
# test.log, or dropping to a weaker pattern — would silence the one file a leaked
# key is most likely to land in.
#
# An allow-list entry is a claim that a specific value is public. It is reviewed
# like any other suppression, and the file states why for each.
allow_filter() { # stdin -> stdout, dropping lines whose only hits are allow-listed
	local allow="$ROOT/audit-allowlist.txt"
	if [ ! -f "$allow" ]; then
		cat
		return
	fi
	local vals
	vals="$(grep -oiE '[0-9a-f]{64}' "$allow" 2>/dev/null)"
	if [ -z "$vals" ]; then
		cat
		return
	fi
	grep -viF "$vals"
}

# RULING 58 — THE 64-HEX RULE IS SCOPED BY TOOL PROVENANCE, NOT BY JUDGEMENT.
#
# Every rule above is a shape rule, and PF-S125 hit the wall shape rules have: a
# keccak hash, an ABI word and a fuzz-generated bytes32 are all uniform 32-byte
# values, indistinguishable from a private key. zk-escrow's three fixed constants
# could be allow-listed by value; gas-optimization's 117 fuzz-generated runIds
# could not, because they change on every capture and the list would be stale the
# moment it was written.
#
# So the 64-hex rule is scoped by a CHECKABLE FACT rather than a judgement call:
# was the tool that produced this log ever supplied a key?
#
#   provenance: key-supplied  -> 64-hex rule ON
#   provenance: no-key        -> 64-hex rule OFF
#   provenance ABSENT         -> 64-hex rule ON. Unknown means strict.
#
# EVERY OTHER PATTERN APPLIES EVERYWHERE, without exception — bearer tokens, DSNs,
# PEM blocks and mnemonics fire regardless of provenance. Only the 64-hex rule is
# scoped, because it is the only one with a false-positive class.
#
# STATE IT PLAINLY: no tool in the current capture set is ever supplied a key, so
# the 64-hex rule is inactive across ALL of today's logs by construction. That is
# the ruling applied, not a hole in it — a key cannot appear in a log produced by a
# tool that was never given one. The moment a key-supplied capture is added (a
# deploy or a verification run), it declares key-supplied and gets the full pattern
# automatically, with no allow-list to maintain and nothing to go stale.
log_provenance() { # $1=path -> prints key-supplied | no-key | unknown
	local p
	p="$(sed -n 's/^=== provenance: \(.*\) ===$/\1/p' "$1" 2>/dev/null | head -1)"
	case "$p" in
	key-supplied | no-key) printf '%s' "$p" ;;
	*) printf 'unknown' ;;
	esac
}

scan_file() { # $1=path -> prints offending lines, returns 1 on any hit
	local f="$1" hits=0 line

	# Patterns that fire on EVERY log regardless of provenance. A credential in any
	# of these forms is a leak wherever it appears, so none of them is ever scoped.
	local always='Bearer [A-Za-z0-9._-]{16,}|postgres(?:ql)?://[^ ]+|mysql://[^ ]+|-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:[a-z]{3,8} ){11,23}[a-z]{3,8}\b'
	# The 64-hex private-key shape — the ONLY scoped pattern (Ruling 58).
	local hex64='(?<![0-9a-fA-Fx])(?:0x)?(?=[0-9a-fA-F]{64}(?![0-9a-fA-F]))(?!.{0,63}0{24})(?=[0-9a-fA-F]*[a-fA-F])[0-9a-fA-F]{64}'

	local pattern="$hex64|$always"
	if [ "$(log_provenance "$f")" = "no-key" ]; then
		pattern="$always"
	fi

	while IFS= read -r line; do
		hits=1
		printf '    %s\n' "$line"
	done < <(grep -nP "$pattern" "$f" 2>/dev/null | allow_filter)
	return $((hits == 0 ? 0 : 1))
}

run_scan() {
	local dir="$ROOT/$OUT" any=0 f
	if [ ! -d "$dir" ]; then
		echo "FAIL: no $dir to scan" >&2
		return 1
	fi
	for f in "$dir"/*.log; do
		[ -e "$f" ] || continue
		if ! scan_file "$f" >/tmp/audit-scan-hits.$$ 2>/dev/null; then
			any=1
			echo "SECRET-SHAPED MATCH in $(basename "$f"):" >&2
			cat /tmp/audit-scan-hits.$$ >&2
		fi
		rm -f /tmp/audit-scan-hits.$$
	done
	if [ "$any" -ne 0 ]; then
		cat >&2 <<'MSG'

STOP. A log contains 64-hex or credential-shaped material.
This is NOT auto-redacted: a quiet mask would hide that a tool printed it while
leaving the leak in place. Classify every hit by hand. Transaction hashes and
Merkle roots are legitimate 64-hex and may be allow-listed by name in the calling
repo's docs; anything else is a leak and the tool that printed it must be fixed.
MSG
		return 1
	fi
	return 0
}

# ---------------------------------------------------------------------------
# CAPTURE
# ---------------------------------------------------------------------------
cap() { # $1=logname  $2=provenance  $3...=command
	local name="$1" prov="$2"
	shift 2
	case "$prov" in
	key-supplied | no-key) ;;
	*)
		echo "cap: provenance must be key-supplied or no-key, got '$prov'" >&2
		return 2
		;;
	esac
	local dest="$ROOT/$OUT/$name.log"
	{
		echo "=== $* ==="
		echo "=== captured by lib/solidity-pipeline/scripts/audit-logs.sh, non-TTY, full verbosity ==="
		echo "=== provenance: $prov ==="
		echo
	} >"$dest"
	(cd "$ROOT" && "$@") >>"$dest" 2>&1
	local rc=$?
	{
		echo
		echo "=== exit status: $rc ==="
	} >>"$dest"
	printf '  %-22s %8s bytes  exit %s\n' "$name.log" "$(wc -c <"$dest")" "$rc"
	return 0 # a non-zero tool is still a log worth keeping; gates judge pass/fail
}

run_capture() {
	mkdir -p "$ROOT/$OUT" || return 1
	rm -f "$ROOT/$OUT"/*.log

	cap fmt no-key forge fmt --check
	cap build no-key forge build
	cap lint no-key forge lint
	cap test no-key forge test -vvvv

	# Captured separately from the build, and mirroring the workflow, because
	# `forge build --sizes` measures every contract in out/ against limits that
	# only bind DEPLOYED bytecode. A committed log showing a repo's harness over
	# EIP-170 would read as a finding about the repo when it is a fact about the
	# tool's filename heuristic. sizes.sh reports what is in scope and prints
	# every skip by name, so the log says what was measured and what was not.
	cap sizes no-key "$HERE/sizes.sh" check

	# coverage.sh RUNS forge coverage and then enforces the gate, so capturing it
	# once yields both the full per-file table and the verdict. A separate
	# `forge coverage` capture would repeat the most expensive step in the suite
	# to produce a subset of the same bytes.
	local cov="$HERE/coverage.sh"
	if [ -n "$EXCLUSIONS" ]; then
		cap coverage no-key "$cov" --exclude "$EXCLUSIONS"
	else
		cap coverage no-key "$cov"
	fi

	# SLITHER NEEDS THE CLEAN REBUILD TOO, and this is not belt-and-braces. It
	# reads the artifacts coverage.sh just instrumented, and in zk-escrow that made
	# it die with `AssertionError: Contract Script not found` — a parse failure, not
	# a finding, exit 1 where CI is green. ADOPTING.md documents this hazard for
	# crytic-compile and the fuzzers; Slither goes through crytic-compile too, so it
	# has always been in scope and the omission here was mine.
	(cd "$ROOT" && rm -rf crytic-export && forge build --force >/dev/null 2>&1)
	cap slither no-key slither . --ignore-compile --config-file "$HERE/../slither.config.json"

	# Same clean rebuild before each fuzzer, for the same reason.
	(cd "$ROOT" && rm -rf crytic-export && forge build --force >/dev/null 2>&1)
	cap echidna no-key echidna . --contract Properties --config echidna.yaml

	(cd "$ROOT" && rm -rf crytic-export && forge build --force >/dev/null 2>&1)
	cap medusa no-key medusa fuzz --config medusa.json

	local total
	total="$(du -sb "$ROOT/$OUT" | cut -f1)"
	printf '  TOTAL %s bytes (%s MB)\n' "$total" "$((total / 1048576))"
	if [ "$total" -gt $((25 * 1024 * 1024)) ]; then
		echo "STOP: audit logs exceed the 25 MB ceiling ($total bytes)." >&2
		echo "Report the per-tool breakdown above. Do NOT reduce verbosity silently." >&2
		return 1
	fi
	return 0
}

# ---------------------------------------------------------------------------
# SELF-TEST — the scan must actually catch what it claims to.
# ---------------------------------------------------------------------------
run_selftest() {
	local tmp
	tmp="$(mktemp -d)" || return 1
	# shellcheck disable=SC2064
	trap "rm -rf '$tmp'" RETURN
	mkdir -p "$tmp/audit"

	printf 'ok: contract at 0xb6c3a56CA2f99e3F5d7d16ad968df9f71cCC184D\n' >"$tmp/audit/clean.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_ok "self-test: a 40-hex ADDRESS does not trip the scan"
	else
		note_bad "self-test: an address tripped the scan (it must not)"
	fi

	# The two false-positive classes that a real `forge test -vvvv` log is full of.
	# Both were found by running the first version of this scan against
	# interest-rate-model, where they produced a page of harmless hits — a scan
	# that fires on every log is a scan somebody switches off.
	printf 'expectRevert(custom error 0xf28dceb3: %0400d)\n' 0 >"$tmp/audit/clean.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_ok "self-test: an ABI-encoded revert blob does not trip the scan"
	else
		note_bad "self-test: an ABI blob tripped the scan (64-hex windows inside a longer run)"
	fi

	printf 'testFuzz_supplyNeverExceedsBorrow(%070d)\n' 7 >"$tmp/audit/clean.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_ok "self-test: a 70-digit DECIMAL fuzz input does not trip the scan"
	else
		note_bad "self-test: a long decimal tripped the scan (every digit is also a hex char)"
	fi

	# EXACTLY 64 digits: boundary-anchored and indistinguishable from 64-hex by
	# shape alone. Only the letter requirement separates it. This is the case the
	# fuzzers actually emit, and the one that broke the second version.
	printf 'Properties::probeRate(4854862, %064d)\n' 3 >"$tmp/audit/clean.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_ok "self-test: an EXACTLY-64-digit decimal does not trip the scan"
	else
		note_bad "self-test: a 64-digit decimal tripped the scan (needs the a-f letter requirement)"
	fi

	# A 32-byte ABI WORD: 64 hex, boundary-anchored, contains letters. Only the
	# zero-padding rule separates it. This is what a revert trace is made of.
	printf 'expectRevert(custom error 0xc31eb0e0: 2e70248b%056d)\n' 0 >"$tmp/audit/clean.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_ok "self-test: a zero-padded 32-byte ABI word does not trip the scan"
	else
		note_bad "self-test: an ABI word tripped the scan (needs the zero-padding rule)"
	fi

	printf 'ok: contract at 0xb6c3a56CA2f99e3F5d7d16ad968df9f71cCC184D\n' >"$tmp/audit/clean.log"

	# A REALISTIC key shape: 64 hex characters INCLUDING letters. The first version
	# of this fixture was `0x` plus 64 digits, which the letter requirement
	# correctly skips — the fixture was unrepresentative, not the scan. A key with
	# no a-f in 64 characters is a 1-in-10^14 event and is not what this must catch.
	printf 'leak 0x4c0883a69102937d6231471b5dbb6204fe512961708279e2fcb9d1a4c0883a6e\n' \
		>"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: a 64-hex secret shape was NOT caught"
	else
		note_ok "self-test: a 64-hex secret shape was caught"
	fi
	rm -f "$tmp/audit/planted.log"

	printf 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345\n' >"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: a bearer token was NOT caught"
	else
		note_ok "self-test: a bearer token was caught"
	fi
	rm -f "$tmp/audit/planted.log"

	printf 'DSN postgresql://user:pw@host:5432/db\n' >"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: a database DSN was NOT caught"
	else
		note_ok "self-test: a database DSN was caught"
	fi
	rm -f "$tmp/audit/planted.log"

	# ---- RULING 58: provenance scoping. Three cases, all required by 58g. ----
	local key='0x4c0883a69102937d6231471b5dbb6204fe512961708279e2fcb9d1a4c0883a6e'

	# 58a — a key in a KEY-SUPPLIED log must fail.
	printf '=== provenance: key-supplied ===\ndeploying with %s\n' "$key" >"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: 58a a key in a key-supplied log was NOT caught"
	else
		note_ok "self-test: 58a a key in a key-supplied log was caught"
	fi

	# 58d — UNKNOWN provenance is strict. Same content, no declaration.
	printf 'deploying with %s\n' "$key" >"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: 58d unknown provenance did NOT get the strict pattern"
	else
		note_ok "self-test: 58d unknown provenance got the strict pattern"
	fi

	# 58b — the SAME key in a no-key log does not fire the 64-hex rule...
	printf '=== provenance: no-key ===\ntrace arg %s\n' "$key" >"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_ok "self-test: 58b 64-hex does not fire on a no-key log"
	else
		note_bad "self-test: 58b 64-hex fired on a no-key log"
	fi

	# 58c — ...but EVERY OTHER pattern still fires on that same no-key log. This is
	# the case that proves the scoping is narrow rather than a blanket exemption.
	printf '=== provenance: no-key ===\nAuthorization: Bearer abcdefghijklmnopqrstuvwxyz012345\n' \
		>"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: 58c a bearer token in a no-key log was NOT caught"
	else
		note_ok "self-test: 58c a bearer token in a no-key log was still caught"
	fi

	printf '=== provenance: no-key ===\nDSN postgresql://user:pw@host:5432/db\n' >"$tmp/audit/planted.log"
	if ROOT="$tmp" OUT=audit run_scan >/dev/null 2>&1; then
		note_bad "self-test: 58c a DSN in a no-key log was NOT caught"
	else
		note_ok "self-test: 58c a DSN in a no-key log was still caught"
	fi
}

case "$MODE" in
selftest) run_selftest ;;
scan)
	if run_scan; then note_ok "scan: no secret-shaped material in $OUT/"; else fail=1; fi
	;;
capture)
	run_capture || fail=1
	;;
all)
	run_selftest
	run_capture || fail=1
	if run_scan; then note_ok "scan: no secret-shaped material in $OUT/"; else fail=1; fi
	;;
esac

if [ "$fail" -ne 0 ]; then
	echo "AUDIT LOGS: FAIL" >&2
	exit 1
fi
echo "AUDIT LOGS: PASS"
