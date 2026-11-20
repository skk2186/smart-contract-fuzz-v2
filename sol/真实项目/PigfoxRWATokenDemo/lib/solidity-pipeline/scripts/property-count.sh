#!/usr/bin/env bash
#
# property-count.sh — proves the fuzzers tested as much as you think they did.
#
# The dangerous failure in property fuzzing is not a property that fails. It is a
# property that stops being REGISTERED: a rename, a stale `crytic-export/`,
# coverage-instrumented artifacts left in `out/` by `forge coverage`, or a
# `testPrefixes` mismatch. Any of those makes the engine walk a smaller set and
# report a green run. It has happened in this estate — a stale artifact shrank a
# five-property set to four and the job passed.
#
# So the count is asserted from three independent directions and they must agree:
#
#   --source   the static count of `function echidna_` declarations in the
#              harness source, cross-checked against the `pigfoxPropertyCount()`
#              literal the harness declares.
#   --engine   what Echidna or Medusa actually registered at runtime.
#
# Any mismatch is a hard failure. So is an output this script cannot parse: an
# engine whose output format changed must not read as "found zero, expected zero".
#
# Usage:
#   property-count.sh --source FILE --expected N
#   property-count.sh --engine echidna|medusa --output FILE --expected N
set -euo pipefail

MODE=""
SOURCE=""
ENGINE=""
OUTPUT=""
EXPECTED=""

while [ "$#" -gt 0 ]; do
	case "$1" in
	--source)
		MODE="source"
		SOURCE="$2"
		shift 2
		;;
	--engine)
		MODE="engine"
		ENGINE="$2"
		shift 2
		;;
	--output)
		OUTPUT="$2"
		shift 2
		;;
	--expected)
		EXPECTED="$2"
		shift 2
		;;
	-h | --help)
		sed -n '2,28p' "$0"
		exit 0
		;;
	*)
		echo "property-count.sh: unknown argument '$1'" >&2
		exit 2
		;;
	esac
done

if [ -z "$MODE" ]; then
	echo "property-count.sh: one of --source or --engine is required" >&2
	exit 2
fi
if ! printf '%s' "$EXPECTED" | grep -qE '^[1-9][0-9]*$'; then
	echo "property-count.sh: --expected must be a positive integer, got '${EXPECTED}'" >&2
	echo "Zero is not a valid expectation: a harness with no properties is not a green run." >&2
	exit 2
fi

fail() {
	echo "PROPERTY COUNT GATE: FAIL" >&2
	printf '%s\n' "$@" >&2
	exit 1
}

# extract_return_value FILE FUNCTION
#
# Prints the `return <value>` of FUNCTION's body, as one line, or nothing.
#
# The block is FLATTENED to a single line before matching. Solidity source is not
# line-oriented and `forge fmt` will wrap a long return value onto the line after
# the `return` keyword, which a line-based grep cannot match — the declaration is
# valid, the parser just cannot see it. That is not hypothetical: it is how this
# gate reported a false failure on zk-escrow, whose harness description was the
# only one in the estate long enough to get wrapped.
#
# Never fails. A function that is absent, or that returns something this does not
# recognise, yields empty output so the CALLER can report it properly. Letting a
# no-match grep exit non-zero under `set -e` is what turned a diagnosable
# condition into a silent exit 1 with no output at all.
extract_return_value() {
	local file="$1" fn="$2"
	sed -n "/function[[:space:]]*${fn}/,/}/p" "$file" |
		tr '\n' ' ' |
		grep -oE 'return[[:space:]]+("[^"]*"|[0-9]+)' |
		head -1 || true
}

# ---------------------------------------------------------------------------
# --source: static agreement between the predicates and the declared literal.
# ---------------------------------------------------------------------------
if [ "$MODE" = "source" ]; then
	[ -f "$SOURCE" ] || fail "harness source not found: $SOURCE"

	# Count declarations, not call sites: the `function` keyword must be present.
	declared_predicates="$(grep -cE '^[[:space:]]*function[[:space:]]+echidna_[A-Za-z0-9_]*[[:space:]]*\(' "$SOURCE" || true)"

	# The literal the harness itself declares.
	#
	# FLATTENED before matching, and the `|| true` is load-bearing. Both details
	# are here because this gate broke on zk-escrow in exactly this spot:
	#
	#   * `forge fmt` wraps a long return onto the line AFTER the `return`
	#     keyword. A line-based grep then matches nothing — the declaration is
	#     perfectly valid, the parser just cannot see it. Piping through `tr`
	#     first makes the block one line, so the wrap is invisible to the regex.
	#
	#   * Without `|| true`, a grep that matches nothing exits 1, `pipefail`
	#     propagates it, and `set -e` kills the script THERE — exit 1, no stdout,
	#     no stderr, and the diagnostic below never runs. CI reported a bare
	#     "Process completed with exit code 1" with zero output. A gate that
	#     cannot say why it failed is barely better than one that does not fail.
	literal="$(extract_return_value "$SOURCE" pigfoxPropertyCount | grep -oE '[0-9]+' | head -1 || true)"

	if [ -z "$literal" ]; then
		fail "$SOURCE does not override pigfoxPropertyCount() with a plain integer literal." \
			"The harness must state its own property count as an independent literal;" \
			"a computed expression would agree with a broken harness automatically."
	fi

	# The harness's own one-line statement of what it proves. Printed so a CI log
	# says what was covered, not only how much. An unoverridden default reads as
	# an unfinished harness and fails. Same flattening and same guard as above.
	description="$(extract_return_value "$SOURCE" pigfoxHarnessDescription |
		sed 's/^return[[:space:]]*"//; s/"[[:space:]]*$//' | head -1 || true)"

	echo "  source predicates      : $declared_predicates"
	echo "  declared literal       : $literal"
	echo "  expected (CI input)    : $EXPECTED"
	echo "  harness proves         : ${description:-<none>}"

	if [ -z "$description" ] || [ "$description" = "UNDESCRIBED HARNESS" ]; then
		fail "$SOURCE does not override pigfoxHarnessDescription() with a real string." \
			"A harness that will not say what it proves is not finished."
	fi

	# RESERVED PREFIX. Echidna gives `echidna_revert_*` the OPPOSITE meaning to
	# every other predicate: such a property passes only when the call REVERTS.
	# A normal boolean predicate with that name is therefore falsified precisely
	# because it returns true — and Echidna reports it with an EMPTY call
	# sequence, then its shrinker crashes trying to minimise a counterexample
	# that does not exist. That reads exactly like a real invariant violation and
	# is not one. It cost a debugging session in gas-optimization; it costs a
	# one-line error now.
	reserved="$(grep -oE '^[[:space:]]*function[[:space:]]+echidna_revert_[A-Za-z0-9_]*' "$SOURCE" |
		grep -oE 'echidna_revert_[A-Za-z0-9_]*' || true)"
	if [ -n "$reserved" ]; then
		fail "$SOURCE declares a predicate using Echidna's RESERVED echidna_revert_ prefix:" \
			"$reserved" \
			"Echidna reads that prefix as 'this call must revert', so a predicate that" \
			"returns true is reported FALSIFIED with an empty call sequence — which looks" \
			"identical to a genuine invariant violation. Rename it; 'failure_conditions'" \
			"reads the same and collides with nothing."
	fi

	if [ "$declared_predicates" != "$EXPECTED" ]; then
		fail "$SOURCE declares $declared_predicates echidna_* predicates, expected $EXPECTED." \
			"If a predicate was added or removed on purpose, bump the workflow's" \
			"expected-properties input and pigfoxPropertyCount() together."
	fi
	if [ "$literal" != "$EXPECTED" ]; then
		fail "pigfoxPropertyCount() returns $literal, expected $EXPECTED." \
			"The harness's own declaration disagrees with CI. One of them is stale."
	fi

	echo "PROPERTY COUNT GATE (source): PASS — $EXPECTED predicates, declaration agrees"
	exit 0
fi

# ---------------------------------------------------------------------------
# --engine: what the fuzzer actually registered.
# ---------------------------------------------------------------------------
[ -f "$OUTPUT" ] || fail "engine output not found: $OUTPUT"

# Strip ANSI colour before matching. Medusa colours its status lines and the
# escape sequences sit between the bracket and the word.
plain="$(sed -r 's/\x1b\[[0-9;]*[mK]//g' "$OUTPUT")"

case "$ENGINE" in
echidna)
	# Echidna prints one line per property: "echidna_foo: passing" (or "passed",
	# depending on version). A failing property prints "failed!" and is not
	# counted here — the engine's own exit code fails the job for that.
	found="$(printf '%s\n' "$plain" | grep -cE '^echidna_[A-Za-z0-9_]+:[[:space:]]+(passing|passed)' || true)"
	failed="$(printf '%s\n' "$plain" | grep -cE '^echidna_[A-Za-z0-9_]+:[[:space:]]+(failed|FAILED)' || true)"
	;;
medusa)
	found="$(printf '%s\n' "$plain" | grep -cE '\[PASSED\][[:space:]]+Property Test:' || true)"
	failed="$(printf '%s\n' "$plain" | grep -cE '\[FAILED\][[:space:]]+Property Test:' || true)"
	;;
*)
	echo "property-count.sh: --engine must be 'echidna' or 'medusa', got '$ENGINE'" >&2
	exit 2
	;;
esac

echo "  engine                 : $ENGINE"
echo "  registered passing     : $found"
echo "  registered failing     : $failed"
echo "  expected               : $EXPECTED"

if [ "$failed" != "0" ]; then
	fail "$ENGINE reported $failed FAILING propert(ies). An invariant was violated." \
		"Per the pipeline's failure taxonomy this is a SOURCE defect, not a tooling one:" \
		"fix the contract, then redeploy (or upgrade, behind a proxy) before it is demoed."
fi

if [ "$found" != "$EXPECTED" ]; then
	fail "$ENGINE registered $found properties, expected $EXPECTED." \
		"A property stopped being picked up. Check for: a rename; a stale" \
		"crytic-export/; coverage-instrumented artifacts left in out/ by a" \
		"'forge coverage' run that preceded this one; a testPrefixes mismatch." \
		"If a predicate was added or removed on purpose, bump expected-properties" \
		"and pigfoxPropertyCount() together."
fi

echo "PROPERTY COUNT GATE ($ENGINE): PASS — $EXPECTED properties registered and passing"
