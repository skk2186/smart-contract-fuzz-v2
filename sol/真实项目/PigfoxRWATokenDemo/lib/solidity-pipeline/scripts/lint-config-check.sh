#!/usr/bin/env bash
#
# lint-config-check.sh — a consuming repo's [lint] block must agree with the
# canonical one in config/lint.toml.
#
# WHY THIS EXISTS. Slither and Solhint are consumed from this submodule by flag, so
# they exist in exactly one place and cannot drift. `forge lint` has no
# --config-file: it reads the [lint] table of the tree it is linting. So the config
# is copied into each repo, and a copy nobody checks is a copy that drifts — which
# is the failure mode docs/slither-exclusions.md was written to prevent.
#
# WHAT IT CHECKS
#   - exclude_lints matches the canonical set EXACTLY, in any order. An extra
#     exclusion is a suppression nobody reviewed; a missing one means the repo is
#     failing on something the estate decided to allow.
#   - ignore contains both canonical entries. A repo with a snarkjs-generated
#     verifier may ALSO list src/Verifier.sol; nothing else is permitted.
#
# It SELF-TESTS. A checker that has silently stopped matching reports the same
# green as a correct tree.
#
# Usage:
#   lint-config-check.sh [--root DIR] [--canonical FILE] [check|selftest|all]
#
# stderr is never suppressed.
set -uo pipefail

# GLOBBING OFF, and this is load-bearing rather than tidiness. The values this
# script compares ARE globs — "test/**/*.sol" — and they are word-split out of a
# comma-joined list. An unquoted expansion in a `for` or a `case` undergoes
# pathname expansion, so when the script ran with a consuming repo as its working
# directory, "test/**/*.sol" silently became the list of files it matched
# (test/mocks/MockAggregator.sol) and the comparison failed against itself. It
# passed in repos with no test/ subdirectory, which is the worst kind of bug:
# green on five trees and red on the sixth for a reason that has nothing to do
# with their configs. CI caught it; the self-test reproduced it immediately.
set -f

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$PWD"
CANONICAL="$HERE/../config/lint.toml"
MODE="all"

while [ "$#" -gt 0 ]; do
	case "$1" in
	--root)
		ROOT="$2"
		shift 2
		;;
	--canonical)
		CANONICAL="$2"
		shift 2
		;;
	check | selftest | all)
		MODE="$1"
		shift
		;;
	-h | --help)
		sed -n '2,25p' "$0"
		exit 0
		;;
	*)
		echo "lint-config-check.sh: unknown argument '$1'" >&2
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

# Parse the [lint] table of a foundry.toml and print two sorted, comma-joined
# lists: "ignore=<...>" then "exclude=<...>". Comments and ordering are ignored.
parse_lint() {
	python3 - "$1" <<'PY'
import re, sys

try:
    text = open(sys.argv[1]).read()
except OSError:
    print("ERR: cannot read"); raise SystemExit(0)

m = re.search(r'^\[lint\]\s*$(.*?)(?=^\[|\Z)', text, re.M | re.S)
if not m:
    print("ERR: no [lint] table"); raise SystemExit(0)
body = re.sub(r'#.*', '', m.group(1))

def arr(name):
    a = re.search(name + r'\s*=\s*\[(.*?)\]', body, re.S)
    if not a:
        return None
    return sorted(x for x in re.findall(r'"([^"]+)"', a.group(1)))

ig, ex = arr('ignore'), arr('exclude_lints')
if ig is None or ex is None:
    print("ERR: [lint] is missing ignore or exclude_lints"); raise SystemExit(0)
print("ignore=" + ",".join(ig))
print("exclude=" + ",".join(ex))
PY
}

run_check() {
	local root="$1" canonical="$2" quiet="${3:-}"
	local target="$root/foundry.toml"

	if [ ! -f "$target" ]; then
		[ -z "$quiet" ] && echo "FAIL: no foundry.toml at $target" >&2
		return 1
	fi

	local want got
	want="$(parse_lint "$canonical")"
	got="$(parse_lint "$target")"

	case "$want" in ERR*)
		echo "FAIL: canonical config unreadable: $want" >&2
		return 1
		;;
	esac
	case "$got" in ERR*)
		[ -z "$quiet" ] && echo "FAIL: $target: ${got}" >&2
		return 1
		;;
	esac

	local want_ex got_ex want_ig got_ig
	want_ex="$(printf '%s\n' "$want" | sed -n 's/^exclude=//p')"
	got_ex="$(printf '%s\n' "$got" | sed -n 's/^exclude=//p')"
	want_ig="$(printf '%s\n' "$want" | sed -n 's/^ignore=//p')"
	got_ig="$(printf '%s\n' "$got" | sed -n 's/^ignore=//p')"

	local rc=0

	if [ "$want_ex" != "$got_ex" ]; then
		rc=1
		if [ -z "$quiet" ]; then
			echo "FAIL: exclude_lints disagrees with config/lint.toml" >&2
			echo "  canonical: $want_ex" >&2
			echo "  repo     : $got_ex" >&2
		fi
	fi

	# Every canonical ignore entry must be present; src/Verifier.sol may be added.
	local missing="" extra=""
	local IFS=,
	for e in $want_ig; do
		case ",$got_ig," in *",$e,"*) ;; *) missing="$missing $e" ;; esac
	done
	for e in $got_ig; do
		case ",$want_ig,src/Verifier.sol," in *",$e,"*) ;; *) extra="$extra $e" ;; esac
	done
	unset IFS

	if [ -n "$missing" ] || [ -n "$extra" ]; then
		rc=1
		if [ -z "$quiet" ]; then
			echo "FAIL: ignore disagrees with config/lint.toml" >&2
			[ -n "$missing" ] && echo "  missing canonical entries:$missing" >&2
			[ -n "$extra" ] && echo "  entries not permitted:$extra" >&2
		fi
	fi

	return "$rc"
}

run_selftest() {
	local tmp
	tmp="$(mktemp -d)" || return 1
	# shellcheck disable=SC2064
	trap "rm -rf '$tmp'" RETURN

	# A tree that copies the canonical block verbatim must pass.
	{
		echo '[profile.default]'
		echo 'src = "src"'
		cat "$CANONICAL"
	} >"$tmp/foundry.toml"
	if run_check "$tmp" "$CANONICAL" quiet; then
		note_ok "self-test: a verbatim copy passes"
	else
		note_bad "self-test: a verbatim copy was rejected"
	fi

	# The documented generated-verifier addition must still pass.
	sed -i 's|ignore = \["test/\*\*/\*.sol", "script/\*\*/\*.sol"\]|ignore = ["test/**/*.sol", "script/**/*.sol", "src/Verifier.sol"]|' "$tmp/foundry.toml"
	if run_check "$tmp" "$CANONICAL" quiet; then
		note_ok "self-test: the documented src/Verifier.sol addition passes"
	else
		note_bad "self-test: the documented src/Verifier.sol addition was rejected"
	fi

	# An UNDOCUMENTED extra exclusion must fail — this is the drift being guarded.
	sed -i 's|"unwrapped-modifier-logic",|"unwrapped-modifier-logic",\n    "incorrect-shift",|' "$tmp/foundry.toml"
	if run_check "$tmp" "$CANONICAL" quiet; then
		note_bad "self-test: an undocumented extra exclusion was NOT caught"
	else
		note_ok "self-test: an undocumented extra exclusion was caught"
	fi

	# A missing [lint] table must fail rather than pass vacuously.
	printf '[profile.default]\nsrc = "src"\n' >"$tmp/foundry.toml"
	if run_check "$tmp" "$CANONICAL" quiet; then
		note_bad "self-test: a missing [lint] table was NOT caught"
	else
		note_ok "self-test: a missing [lint] table was caught"
	fi
}

case "$MODE" in
selftest) run_selftest ;;
check)
	if run_check "$ROOT" "$CANONICAL"; then
		note_ok "check: [lint] agrees with config/lint.toml"
	else
		fail=1
	fi
	;;
all)
	run_selftest
	if run_check "$ROOT" "$CANONICAL"; then
		note_ok "check: [lint] agrees with config/lint.toml"
	else
		fail=1
	fi
	;;
esac

if [ "$fail" -ne 0 ]; then
	echo "LINT CONFIG CHECK: FAIL" >&2
	exit 1
fi
echo "LINT CONFIG CHECK: PASS"
