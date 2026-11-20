#!/usr/bin/env bash
#
# sizes.sh — the pigfox deployable-bytecode size gate.
#
# EIP-170 bounds the RUNTIME bytecode a chain will accept for a deployed contract
# (24,576 bytes); EIP-3860 bounds its INITCODE (49,152). Both are limits on
# DEPLOYMENT. This gate therefore applies them to exactly the tree whose contents
# are deployed — src/ — and to nothing else. Both limits are enforced in full on
# everything in that tree, with no exclusion flag: a src/ contract over the limit
# is undeployable, which is a fact about the code rather than a policy to opt out
# of.
#
# WHY THIS EXISTS, instead of `forge build --sizes`. That command decides what
# counts as a test by FILENAME — contracts compiled from *.t.sol and *.s.sol are
# left out of the table. This pipeline's own convention names the property harness
# `test/Properties.sol`, which is not *.t.sol, so the harness was measured against
# a limit that cannot apply to it: it is constructed in process by Echidna, by
# Medusa and by `forge test`, and is deployed nowhere. deposit-dispute's harness
# reached 25,044 bytes and turned the stage red with nothing wrong.
#
# The filename heuristic is not merely too strict. It is also too LOOSE, and that
# is the more serious half:
#
#   - test/DepositDispute.t.sol in that same repo compiles to 53,113 bytes of
#     runtime and 53,170 of initcode — over BOTH limits, by more than twice — and
#     `forge build --sizes` says nothing about it, because of the suffix. A gate
#     that ignores a 53KB contract while failing the build on a 25KB one is not
#     enforcing a size policy; it is enforcing a naming convention.
#   - `--sizes` reports whatever is sitting in out/, so `--skip` cannot scope it:
#     a stale artifact left by an earlier build is reported again. Scoping by
#     argument list is therefore not available even in principle.
#
# So scope is taken from each artifact's own
# metadata.settings.compilationTarget. A contract's SOURCE PATH decides whether it
# is in scope — not its filename, not the argument list, and not what a previous
# build happened to leave behind.
#
# WHAT IT SKIPS, printed by name with its measured size so a reader sees exactly
# what was not checked: every contract compiled from outside src/. Harnesses,
# deploy scripts and library code are not deployed by this estate. Sizes are never
# folded into a total or a percentage.
#
# It refuses to pass VACUOUSLY. No artifacts at all, or no src/ contract carrying
# any runtime bytecode, is the shape of a build that did not happen or a matcher
# that has stopped matching — and it is indistinguishable from a clean tree.
#
# It SELF-TESTS. A gate that has quietly stopped working reports the same green as
# a clean tree.
#
# Usage:
#   sizes.sh [--root DIR] [--out DIR] [check|selftest|all]
#
#   --root DIR   repo to gate (default: $PWD)
#   --out DIR    artifact directory, relative to --root (default: out)
#
# stderr is never suppressed.
set -uo pipefail

ROOT="$PWD"
OUT="out"
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
	check | selftest | all)
		MODE="$1"
		shift
		;;
	-h | --help)
		sed -n '2,57p' "$0"
		exit 0
		;;
	*)
		echo "sizes.sh: unknown argument '$1'" >&2
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

# run_check <artifact-dir> [quiet]
#
# Exits 1 on a gate rejection, 0 on a pass. The whole verdict lives in python3 so
# that the size arithmetic and the scope decision are in one place and are read
# from the artifacts rather than from a formatted table.
run_check() {
	python3 - "$1" "${2:-loud}" <<'PY'
import glob
import json
import os
import sys

RUNTIME_LIMIT = 24576   # EIP-170
INITCODE_LIMIT = 49152  # EIP-3860

outdir, verbosity = sys.argv[1], sys.argv[2]
quiet = verbosity == "quiet"


def emit(msg):
    if not quiet:
        print(msg)


def size_of(section):
    """Bytes in an artifact bytecode section. Absent or unlinked reads as zero."""
    obj = section.get("object", "") if isinstance(section, dict) else ""
    if not isinstance(obj, str):
        return 0
    if obj.startswith("0x"):
        obj = obj[2:]
    return len(obj) // 2


found = []
pattern = os.path.join(outdir, "**", "*.json")
for path in sorted(glob.glob(pattern, recursive=True)):
    # build-info blobs are whole-compilation inputs and outputs, not per-contract
    # artifacts. They are large and carry no compilationTarget of their own.
    if os.sep + "build-info" + os.sep in path:
        continue
    try:
        with open(path) as handle:
            art = json.load(handle)
    except (OSError, ValueError):
        continue
    if not isinstance(art, dict):
        continue
    metadata = art.get("metadata")
    if not isinstance(metadata, dict):
        continue
    settings = metadata.get("settings")
    if not isinstance(settings, dict):
        continue
    target = settings.get("compilationTarget")
    if not isinstance(target, dict) or not target:
        continue
    source, name = sorted(target.items())[0]
    found.append(
        (source, name, size_of(art.get("deployedBytecode")), size_of(art.get("bytecode")))
    )

if not found:
    print(
        "FAIL: no compiled artifacts with a compilationTarget under %s." % outdir,
        file=sys.stderr,
    )
    print(
        "      Run `forge build` before this gate. Refusing to pass vacuously.",
        file=sys.stderr,
    )
    sys.exit(1)

checked = sorted(a for a in found if a[0].startswith("src/"))
skipped = sorted(a for a in found if not a[0].startswith("src/"))

failures = 0
for source, name, runtime, initcode in checked:
    over = []
    if runtime > RUNTIME_LIMIT:
        over.append(
            "runtime %d exceeds EIP-170's %d by %d"
            % (runtime, RUNTIME_LIMIT, runtime - RUNTIME_LIMIT)
        )
    if initcode > INITCODE_LIMIT:
        over.append(
            "initcode %d exceeds EIP-3860's %d by %d"
            % (initcode, INITCODE_LIMIT, initcode - INITCODE_LIMIT)
        )
    if over:
        failures += 1
        emit("  FAIL  %s:%s" % (source, name))
        for reason in over:
            emit("        %s" % reason)
    else:
        emit(
            "  OK    %s:%s  runtime %d (margin %d), initcode %d (margin %d)"
            % (
                source,
                name,
                runtime,
                RUNTIME_LIMIT - runtime,
                initcode,
                INITCODE_LIMIT - initcode,
            )
        )

# Skips are printed, never folded into a total. Library artifacts are counted
# rather than listed one by one: they are dependencies, not this repo's decisions.
own = [a for a in skipped if not a[0].startswith("lib/")]
libs = [a for a in skipped if a[0].startswith("lib/")]
for source, name, runtime, initcode in own:
    emit(
        "  SKIP  %s:%s  runtime %d, initcode %d — outside src/, never deployed"
        % (source, name, runtime, initcode)
    )
if libs:
    emit(
        "  SKIP  %d library contract(s) under lib/ — dependencies, never deployed from here"
        % len(libs)
    )

concrete = [a for a in checked if a[2] > 0]
if not concrete:
    print(
        "\nFAIL: %d src/ artifact(s) found, none carrying any runtime bytecode."
        % len(checked),
        file=sys.stderr,
    )
    print(
        "      That is an interface-only scan set, or a matcher that has stopped",
        file=sys.stderr,
    )
    print("      matching. Refusing to pass vacuously.", file=sys.stderr)
    sys.exit(1)

if failures:
    print(
        "\nFAILED: %d src/ contract(s) exceed a deployment limit." % failures,
        file=sys.stderr,
    )
    sys.exit(1)

emit(
    "\nPASSED: %d deployable src/ contract(s) within EIP-170 and EIP-3860 "
    "(%d contract(s) skipped as never-deployed)." % (len(concrete), len(skipped))
)
sys.exit(0)
PY
}

# plant <artifact-dir> <source-path> <contract> <runtime-bytes> <initcode-bytes>
#
# Writes a minimal artifact of the shape this gate reads. Self-test only.
plant() {
	python3 - "$@" <<'PY'
import json
import os
import sys

outdir, source, name, runtime, initcode = (
    sys.argv[1],
    sys.argv[2],
    sys.argv[3],
    int(sys.argv[4]),
    int(sys.argv[5]),
)
directory = os.path.join(outdir, os.path.basename(source))
os.makedirs(directory, exist_ok=True)
artifact = {
    "bytecode": {"object": "0x" + "00" * initcode},
    "deployedBytecode": {"object": "0x" + "00" * runtime},
    "metadata": {"settings": {"compilationTarget": {source: name}}},
}
with open(os.path.join(directory, name + ".json"), "w") as handle:
    json.dump(artifact, handle)
PY
}

run_selftest() {
	local work
	work="$(mktemp -d)" || return 1
	# shellcheck disable=SC2064
	trap "rm -rf '$work'" RETURN

	# Every case below whose verdict is "rejected" prints the gate's own reason on
	# stderr as it runs. That is deliberate and it is the thing being tested: a
	# gate that cannot say why it said no is barely better than one that does not
	# say no. The `ok` line under each is the assertion.
	echo "  (expected rejections print their reasons below — the 'ok' lines are the result)"

	# An empty artifact directory must be refused. This is the shape of a build
	# that never ran, and it is indistinguishable from a clean tree.
	mkdir -p "$work/empty"
	if run_check "$work/empty" quiet; then
		note_bad "self-test: an empty artifact set was NOT refused"
	else
		note_ok "self-test: an empty artifact set was refused"
	fi

	# A src/ contract inside both limits passes.
	mkdir -p "$work/ok"
	plant "$work/ok" "src/Token.sol" "Token" 7000 9000
	if run_check "$work/ok" quiet; then
		note_ok "self-test: a src/ contract inside both limits passed"
	else
		note_bad "self-test: a src/ contract inside both limits was rejected"
	fi

	# A src/ contract over EIP-170 must be caught. This is the gate's whole job.
	mkdir -p "$work/oversize-src"
	plant "$work/oversize-src" "src/Token.sol" "Token" 25000 26000
	if run_check "$work/oversize-src" quiet; then
		note_bad "self-test: an oversized src/ runtime was NOT caught"
	else
		note_ok "self-test: an oversized src/ runtime was caught"
	fi

	# Over EIP-3860 on initcode alone, with a legal runtime. Checking only the
	# runtime limit would let this through, and `forge build --sizes` enforces
	# both — narrowing scope must not quietly drop one of the two limits.
	mkdir -p "$work/oversize-initcode"
	plant "$work/oversize-initcode" "src/Token.sol" "Token" 7000 50000
	if run_check "$work/oversize-initcode" quiet; then
		note_bad "self-test: an oversized src/ initcode was NOT caught"
	else
		note_ok "self-test: an oversized src/ initcode was caught"
	fi

	# THE POINT OF THIS GATE. A harness outside src/ is over both limits by more
	# than twice and must NOT fail the build, while a legal src/ contract sits
	# beside it. If this case ever starts failing, the scope has been lost and
	# every consumer's harness is being measured against a limit for deployment
	# it never undergoes.
	mkdir -p "$work/harness"
	plant "$work/harness" "src/Token.sol" "Token" 7000 9000
	plant "$work/harness" "test/Properties.sol" "Properties" 25044 26084
	plant "$work/harness" "test/DepositDispute.t.sol" "DepositDisputeTest" 53113 53170
	plant "$work/harness" "script/Deploy.s.sol" "Deploy" 14449 14494
	if run_check "$work/harness" quiet; then
		note_ok "self-test: oversized harnesses outside src/ did not fail the build"
	else
		note_bad "self-test: an oversized harness outside src/ failed the build"
	fi

	# Artifacts present, but none of them from src/ — a matcher that has stopped
	# matching looks exactly like this, so it must be refused rather than
	# reported as zero failures.
	mkdir -p "$work/no-src"
	plant "$work/no-src" "test/Properties.sol" "Properties" 25044 26084
	if run_check "$work/no-src" quiet; then
		note_bad "self-test: an artifact set with no src/ contract was NOT refused"
	else
		note_ok "self-test: an artifact set with no src/ contract was refused"
	fi

	# An interface-only src/ scan set carries no runtime bytecode. Passing it
	# would mean reporting "nothing over the limit" about nothing at all.
	mkdir -p "$work/interface-only"
	plant "$work/interface-only" "src/IToken.sol" "IToken" 0 0
	if run_check "$work/interface-only" quiet; then
		note_bad "self-test: an interface-only src/ scan set was NOT refused"
	else
		note_ok "self-test: an interface-only src/ scan set was refused"
	fi
}

case "$MODE" in
selftest)
	run_selftest
	;;
check)
	if run_check "$ROOT/$OUT"; then
		note_ok "check: every deployable src/ contract is within EIP-170 and EIP-3860"
	else
		fail=1
	fi
	;;
all)
	run_selftest
	echo
	if run_check "$ROOT/$OUT"; then
		note_ok "check: every deployable src/ contract is within EIP-170 and EIP-3860"
	else
		fail=1
	fi
	;;
esac

if [ "$fail" -ne 0 ]; then
	echo "SIZES GATE: FAIL" >&2
	exit 1
fi
echo "SIZES GATE: PASS"
