#!/usr/bin/env bash
#
# selftest.sh — proves the pipeline's own gates still fail what they claim to fail.
#
# A gate that has quietly stopped working reports the same green as a clean tree.
# Every script in this repo is therefore driven here against synthetic inputs
# whose correct verdict is known, including the ones that MUST be rejected. A
# passing run of this file means the gates can still say no.
#
# Usage: scripts/selftest.sh
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
WORK="$ROOT/tmp-selftest"

rm -rf "$WORK"
mkdir -p "$WORK"
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0

# expect <want-rc> <name> -- <command...>
#
# The wanted code is matched EXACTLY. "any non-zero" would let a usage error
# (rc=2) stand in for a gate rejection (rc=1) — which is how a gate that has
# stopped running at all reads as a gate that is still saying no.
expect() {
	local want="$1" name="$2"
	shift 3 # drop want, name, and the literal --
	local out rc
	out="$("$@" 2>&1)"
	rc=$?
	if [ "$rc" = "$want" ]; then
		printf '  \033[32mok\033[0m   %s (rc=%s)\n' "$name" "$rc"
		pass=$((pass + 1))
	else
		printf '  \033[31mFAIL\033[0m %s — wanted rc %s, got %s\n' "$name" "$want" "$rc"
		printf '%s\n' "$out" | sed 's/^/         /'
		fail=$((fail + 1))
	fi
}

# expect_fail_with <substring> <name> -- <command...>
#
# Like `expect 1`, but ALSO requires the failure to explain itself.
#
# Checking only the exit code is how this suite passed over a real defect: a
# `set -e` crash and a deliberate rejection both exit 1, so a case asserting
# "rc=1" went green while the script was actually dying mid-parse with no output
# at all — and CI inherited the same silence. A gate that cannot say why it
# failed is barely better than one that does not fail, so the tests that matter
# assert the sentence, not the number.
expect_fail_with() {
	local want="$1" name="$2"
	shift 3
	local out rc
	out="$("$@" 2>&1)"
	rc=$?
	if [ "$rc" = "0" ]; then
		printf '  \033[31mFAIL\033[0m %s — expected a rejection, got success\n' "$name"
		fail=$((fail + 1))
		return
	fi
	case "$out" in
	*"$want"*)
		printf '  \033[32mok\033[0m   %s (rc=%s, explained)\n' "$name" "$rc"
		pass=$((pass + 1))
		;;
	*)
		printf '  \033[31mFAIL\033[0m %s — rejected (rc=%s) but never said %q\n' "$name" "$rc" "$want"
		printf '%s\n' "${out:-<no output at all — this is the silent-crash failure mode>}" | sed 's/^/         /'
		fail=$((fail + 1))
		;;
	esac
}

section() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
section "coverage.sh"

cat >"$WORK/clean.txt" <<'EOF'
| File          | % Lines        | % Statements   | % Branches   | % Funcs      |
|---------------|----------------|----------------|--------------|--------------|
| src/A.sol     | 100.00% (10/10)| 100.00% (8/8)  | 100.00% (2/2)| 100.00% (3/3)|
| src/B.sol     | 100.00% (5/5)  | 100.00% (4/4)  | 100.00% (1/1)| 100.00% (2/2)|
| Total         | 100.00% (15/15)| 100.00% (12/12)| 100.00% (3/3)| 100.00% (5/5)|
EOF

cat >"$WORK/short.txt" <<'EOF'
| File          | % Lines        | % Statements   | % Branches   | % Funcs      |
|---------------|----------------|----------------|--------------|--------------|
| src/A.sol     | 100.00% (10/10)| 100.00% (8/8)  | 100.00% (2/2)| 100.00% (3/3)|
| src/B.sol     | 80.00% (4/5)   | 100.00% (4/4)  | 100.00% (1/1)| 100.00% (2/2)|
EOF

cat >"$WORK/branchshort.txt" <<'EOF'
| File          | % Lines        | % Statements   | % Branches   | % Funcs      |
|---------------|----------------|----------------|--------------|--------------|
| src/A.sol     | 100.00% (10/10)| 100.00% (8/8)  | 50.00% (1/2) | 100.00% (3/3)|
EOF

cat >"$WORK/norows.txt" <<'EOF'
Compiling 12 files with Solc 0.8.28
Nothing to compile.
EOF

cat >"$WORK/reformatted.txt" <<'EOF'
File,Lines,Statements,Branches,Funcs
src/A.sol,100%,100%,100%,100%
EOF

cov() {
	COVERAGE_EXCLUDE="" "$HERE/coverage.sh" --root "$WORK" --skip-run --report "$1" "${@:2}"
}

expect 0 "a clean 100% report passes" -- cov clean.txt
expect 1 "a line shortfall fails" -- cov short.txt
expect 1 "a BRANCH shortfall fails (not just lines)" -- cov branchshort.txt
expect 1 "a report with no src/ rows fails rather than passing vacuously" -- cov norows.txt
expect 1 "an unparseable report format fails rather than passing by default" -- cov reformatted.txt
expect 0 "a documented exclusion skips its row" -- cov short.txt --exclude src/B.sol
expect 1 "a STALE exclusion (matches no row) fails" -- cov clean.txt --exclude src/Ghost.sol
expect 1 "a missing report under --skip-run fails" -- cov nosuchfile.txt

# The environment channel the reusable workflow uses must behave like --exclude.
out_env="$(COVERAGE_EXCLUDE="src/B.sol" "$HERE/coverage.sh" --root "$WORK" --skip-run --report short.txt 2>&1)"
rc_env=$?
if [ "$rc_env" = "0" ] && printf '%s' "$out_env" | grep -q "SKIP"; then
	printf '  \033[32mok\033[0m   COVERAGE_EXCLUDE is honoured like --exclude\n'
	pass=$((pass + 1))
else
	printf '  \033[31mFAIL\033[0m COVERAGE_EXCLUDE was not honoured\n'
	printf '%s\n' "$out_env" | sed 's/^/         /'
	fail=$((fail + 1))
fi

# --- --no-match-contract: the instrumentation exclusion ---------------------
#
# THE PROPERTY THAT MATTERS is that it changes what is MEASURED and not what is
# REQUIRED. So the cases below are mostly about the threshold surviving it: a
# shortfall must still fail while the exclusion is in force, because that is the
# only guard standing between this option and a silently hidden gap.
expect 1 "a shortfall still fails WITH --no-match-contract set (the guard on the exclusion)" \
	-- cov short.txt --no-match-contract InvariantsTest
expect 1 "a BRANCH shortfall still fails WITH --no-match-contract set" \
	-- cov branchshort.txt --no-match-contract InvariantsTest
expect 1 "a vacuous report still fails WITH --no-match-contract set" \
	-- cov norows.txt --no-match-contract InvariantsTest
expect 0 "a clean report passes with --no-match-contract set" \
	-- cov clean.txt --no-match-contract InvariantsTest
expect 2 "--no-match-contract with no value is a usage error, not a silent empty" \
	-- "$HERE/coverage.sh" --root "$WORK" --skip-run --report clean.txt --no-match-contract

# It must ANNOUNCE itself. An instrumentation exclusion nobody can see in the log
# is the shape of a gate quietly measuring less than a reader believes.
out_nmc="$(COVERAGE_NO_MATCH_CONTRACT="InvariantsTest" COVERAGE_EXCLUDE="" \
	"$HERE/coverage.sh" --root "$WORK" --skip-run --report clean.txt 2>&1)"
rc_nmc=$?
if [ "$rc_nmc" = "0" ] && printf '%s' "$out_nmc" | grep -q "STILL RUN"; then
	printf '  \033[32mok\033[0m   COVERAGE_NO_MATCH_CONTRACT is honoured and says the tests still run\n'
	pass=$((pass + 1))
else
	printf '  \033[31mFAIL\033[0m COVERAGE_NO_MATCH_CONTRACT was not honoured or did not announce itself\n'
	printf '%s\n' "$out_nmc" | sed 's/^/         /'
	fail=$((fail + 1))
fi

# A whitespace-only environment value must read as UNSET. Passing it through to
# forge as a regex would match every contract and instrument nothing, which would
# report a vacuous pass rather than an error.
out_ws="$(COVERAGE_NO_MATCH_CONTRACT="   " COVERAGE_EXCLUDE="" \
	"$HERE/coverage.sh" --root "$WORK" --skip-run --report clean.txt 2>&1)"
rc_ws=$?
if [ "$rc_ws" = "0" ] && ! printf '%s' "$out_ws" | grep -q "Instrumentation excludes"; then
	printf '  \033[32mok\033[0m   a whitespace-only COVERAGE_NO_MATCH_CONTRACT reads as unset\n'
	pass=$((pass + 1))
else
	printf '  \033[31mFAIL\033[0m a whitespace-only COVERAGE_NO_MATCH_CONTRACT was treated as a pattern\n'
	printf '%s\n' "$out_ws" | sed 's/^/         /'
	fail=$((fail + 1))
fi

# ---------------------------------------------------------------------------
section "property-count.sh"

cat >"$WORK/Properties.sol" <<'EOF'
// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {PigfoxProperties} from "pipeline/PigfoxProperties.sol";

contract Properties is PigfoxProperties {
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 3;
    }

    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return "a synthetic harness used by the pipeline self-test";
    }

    function echidna_one() public pure returns (bool) { return true; }
    function echidna_two() public pure returns (bool) { return true; }
    function echidna_three() public pure returns (bool) { return true; }
}
EOF

cat >"$WORK/PropertiesStaleLiteral.sol" <<'EOF'
contract Properties is PigfoxProperties {
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 5;
    }
    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return "a synthetic harness whose declared count is stale";
    }
    function echidna_one() public pure returns (bool) { return true; }
    function echidna_two() public pure returns (bool) { return true; }
    function echidna_three() public pure returns (bool) { return true; }
}
EOF

# EXACTLY what `forge fmt` produces for a description too long to fit on one
# line: the string moves to the line AFTER `return`. This is the shape that broke
# zk-escrow's CI — a valid declaration the parser could not see, because the old
# regex was line-based. Byte-for-byte the formatter's output, not a paraphrase.
cat >"$WORK/PropertiesWrappedReturn.sol" <<'EOF'
contract Properties is PigfoxProperties {
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 6;
    }

    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return
            "escrowed ETH always equals what is owed, an arbiter never profits, and a nullifier spends once";
    }

    function echidna_one() public pure returns (bool) { return true; }
    function echidna_two() public pure returns (bool) { return true; }
    function echidna_three() public pure returns (bool) { return true; }
    function echidna_four() public pure returns (bool) { return true; }
    function echidna_five() public pure returns (bool) { return true; }
    function echidna_six() public pure returns (bool) { return true; }
}
EOF

# The same wrap applied to the COUNT. forge fmt would not produce this for a
# one-digit literal, but the parser must not depend on that to be correct.
cat >"$WORK/PropertiesWrappedCount.sol" <<'EOF'
contract Properties is PigfoxProperties {
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return
            2;
    }
    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return "a harness whose count literal is wrapped";
    }
    function echidna_one() public pure returns (bool) { return true; }
    function echidna_two() public pure returns (bool) { return true; }
}
EOF

cat >"$WORK/PropertiesUndescribed.sol" <<'EOF'
contract Properties is PigfoxProperties {
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 1;
    }
    function echidna_one() public pure returns (bool) { return true; }
}
EOF

cat >"$WORK/PropertiesReservedPrefix.sol" <<'EOF'
contract Properties is PigfoxProperties {
    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 2;
    }
    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return "a harness that walked into Echidna's reserved prefix";
    }
    function echidna_one() public pure returns (bool) { return true; }
    function echidna_revert_conditions_identical() public pure returns (bool) { return true; }
}
EOF

cat >"$WORK/PropertiesNoLiteral.sol" <<'EOF'
contract Properties {
    function echidna_one() public pure returns (bool) { return true; }
}
EOF

pc() { "$HERE/property-count.sh" "$@"; }

expect 0 "source: 3 predicates, literal 3, expected 3" -- pc --source "$WORK/Properties.sol" --expected 3

# THE REGRESSION. A forge-fmt-wrapped return is a valid declaration and must
# PASS. It did not, and because the parser died rather than reporting, CI showed
# exit 1 with no output whatsoever.
expect 0 "source: a forge-fmt-WRAPPED description still parses (zk-escrow regression)" \
	-- pc --source "$WORK/PropertiesWrappedReturn.sol" --expected 6
expect 0 "source: a wrapped count literal still parses" \
	-- pc --source "$WORK/PropertiesWrappedCount.sol" --expected 2

# Every rejection below must EXPLAIN itself. Asserting only rc=1 is what let a
# silent crash sit here looking like a working gate.
expect_fail_with "declares 3 echidna_* predicates, expected 4" \
	"source: expected 4 but only 3 predicates exist" -- pc --source "$WORK/Properties.sol" --expected 4
expect_fail_with "pigfoxPropertyCount() returns 5, expected 3" \
	"source: literal disagrees with the predicates" -- pc --source "$WORK/PropertiesStaleLiteral.sol" --expected 3
expect_fail_with "does not override pigfoxPropertyCount()" \
	"source: a harness that never declares its count is rejected" -- pc --source "$WORK/PropertiesNoLiteral.sol" --expected 1
expect_fail_with "does not override pigfoxHarnessDescription()" \
	"source: a harness that will not say what it proves is rejected" -- pc --source "$WORK/PropertiesUndescribed.sol" --expected 1
expect_fail_with "RESERVED echidna_revert_ prefix" \
	"source: Echidna's RESERVED echidna_revert_ prefix is rejected" -- pc --source "$WORK/PropertiesReservedPrefix.sol" --expected 2
expect_fail_with "harness source not found" \
	"source: a missing harness file fails" -- pc --source "$WORK/nope.sol" --expected 3
expect 2 "source: --expected 0 is rejected outright" -- pc --source "$WORK/Properties.sol" --expected 0
expect 2 "source: a non-numeric --expected is rejected" -- pc --source "$WORK/Properties.sol" --expected three

cat >"$WORK/echidna-ok.txt" <<'EOF'
echidna_one: passing
echidna_two: passing
echidna_three: passing
Unique instructions: 1234
EOF

cat >"$WORK/echidna-short.txt" <<'EOF'
echidna_one: passing
echidna_two: passing
EOF

cat >"$WORK/echidna-failed.txt" <<'EOF'
echidna_one: passing
echidna_two: passing
echidna_three: failed!
EOF

cat >"$WORK/medusa-ok.txt" <<'EOF'
[PASSED] Property Test: Properties.echidna_one()
[PASSED] Property Test: Properties.echidna_two()
[PASSED] Property Test: Properties.echidna_three()
EOF

# Same content with ANSI colour, exactly as medusa writes it to a terminal.
printf '\033[32m[PASSED]\033[0m Property Test: Properties.echidna_one()\n\033[32m[PASSED]\033[0m Property Test: Properties.echidna_two()\n\033[32m[PASSED]\033[0m Property Test: Properties.echidna_three()\n' >"$WORK/medusa-colour.txt"

cat >"$WORK/medusa-failed.txt" <<'EOF'
[PASSED] Property Test: Properties.echidna_one()
[FAILED] Property Test: Properties.echidna_two()
[PASSED] Property Test: Properties.echidna_three()
EOF

cat >"$WORK/engine-garbage.txt" <<'EOF'
some completely different output format nobody parsed for
EOF

expect 0 "echidna: 3 registered, 3 expected" -- pc --engine echidna --output "$WORK/echidna-ok.txt" --expected 3
expect 1 "echidna: a property stopped being registered" -- pc --engine echidna --output "$WORK/echidna-short.txt" --expected 3
expect 1 "echidna: a FAILING property fails the gate" -- pc --engine echidna --output "$WORK/echidna-failed.txt" --expected 3
expect 1 "echidna: unrecognised output fails rather than counting zero as fine" -- pc --engine echidna --output "$WORK/engine-garbage.txt" --expected 3
expect 0 "medusa: 3 passed, 3 expected" -- pc --engine medusa --output "$WORK/medusa-ok.txt" --expected 3
expect 0 "medusa: ANSI-coloured output is parsed identically" -- pc --engine medusa --output "$WORK/medusa-colour.txt" --expected 3
expect 1 "medusa: a FAILING property fails the gate" -- pc --engine medusa --output "$WORK/medusa-failed.txt" --expected 3
expect 1 "medusa: unrecognised output fails" -- pc --engine medusa --output "$WORK/engine-garbage.txt" --expected 3
expect 2 "an unknown engine is rejected" -- pc --engine foundry --output "$WORK/medusa-ok.txt" --expected 3

# ---------------------------------------------------------------------------
section "no-chain-copy-gate.sh"

# A throwaway git repo, so the gate's own self-test has a tree to plant into.
GITREPO="$WORK/gitrepo"
mkdir -p "$GITREPO"
git -C "$GITREPO" init -q
git -C "$GITREPO" config user.email selftest@pigfox.local
git -C "$GITREPO" config user.name selftest
printf 'clean tree\n' >"$GITREPO/README.md"
git -C "$GITREPO" add -A
git -C "$GITREPO" commit -qm init

expect 0 "gate passes on a clean tracked tree" -- "$HERE/no-chain-copy-gate.sh" --root "$GITREPO" all

# The banned token is assembled from halves so this FILE is not itself a hit.
# no-chain-copy-gate.sh has to exclude itself — it lists what it bans — and one
# self-exclusion is the whole exclusion surface. A second one here would mean two
# files in the estate the doctrine gate cannot see, which is one too many.
printf 'this file names --%s%s-url\n' "fo" "rk" >"$GITREPO/bad.md"
git -C "$GITREPO" add -A
git -C "$GITREPO" commit -qm bad

expect 1 "gate fails on a tracked file carrying a banned token" -- "$HERE/no-chain-copy-gate.sh" --root "$GITREPO" all

# ---------------------------------------------------------------------------
section "address-checksum-gate.sh"

# A SECOND throwaway repo. The doctrine gate's one now carries a banned token on
# purpose, and a tree that fails one gate cannot cleanly demonstrate another.
ADDRREPO="$WORK/addrrepo"
mkdir -p "$ADDRREPO/deployments"
git -C "$ADDRREPO" init -q
git -C "$ADDRREPO" config user.email selftest@pigfox.local
git -C "$ADDRREPO" config user.name selftest

# One correctly checksummed address; the same address in all lower case, which
# asserts no checksum and which viem accepts; and a 32-byte topic whose first
# forty hex characters must not be read as an address.
cat >"$ADDRREPO/deployments/base-sepolia.json" <<'EOF'
{
  "GasRace": "0xD6f73e9f845F3C9B059B5EA2E5320CD3e15ec19b",
  "runner": "0xd6f73e9f845f3c9b059b5ea2e5320cd3e15ec19b",
  "deployTx": "0x90fbe6e87fbfe6ac0f8a2736801fd2df6b346912c4d67348b4b4f948d801727a"
}
EOF
git -C "$ADDRREPO" add -A
git -C "$ADDRREPO" commit -qm init

expect 0 "gate passes on a tree whose casing is right" \
	-- "$HERE/address-checksum-gate.sh" --root "$ADDRREPO" all

# THE INCIDENT. The same twenty bytes, spelled with the wrong capitals. viem
# refuses that before it estimates gas, and the page reports a nonce problem it
# does not have. Three gas-demo addresses shipped this way.
cat >"$ADDRREPO/deployments/base-sepolia.json" <<'EOF'
{
  "GasRace": "0xd6F73E9f845f3c9B059b5EA2e5320cd3E15Ec19b",
  "runner": "0xd6f73e9f845f3c9b059b5ea2e5320cd3e15ec19b",
  "deployTx": "0x90fbe6e87fbfe6ac0f8a2736801fd2df6b346912c4d67348b4b4f948d801727a"
}
EOF
git -C "$ADDRREPO" add -A
git -C "$ADDRREPO" commit -qm miscased

# The rejection must name the file, the LINE and the correct casing. "Something
# is wrong somewhere" is not a fix instruction, and the fix is never the bytes.
expect_fail_with "deployments/base-sepolia.json:2: 0xd6F73E9f845f3c9B059b5EA2e5320cd3E15Ec19b fails EIP-55 — should be 0xD6f73e9f845F3C9B059B5EA2E5320CD3e15ec19b" \
	"a mis-cased address is rejected, naming its file, line and correction" \
	-- "$HERE/address-checksum-gate.sh" --root "$ADDRREPO" scan

# A tracked tree with nothing to check. Zero hits is the shape a broken matcher
# makes and it is indistinguishable from a clean tree, so it fails — and the way
# past it is an explicit flag, never silence.
EMPTYREPO="$WORK/emptyrepo"
mkdir -p "$EMPTYREPO"
git -C "$EMPTYREPO" init -q
git -C "$EMPTYREPO" config user.email selftest@pigfox.local
git -C "$EMPTYREPO" config user.name selftest
printf 'a tracked tree with no address literals in it\n' >"$EMPTYREPO/README.md"
git -C "$EMPTYREPO" add -A
git -C "$EMPTYREPO" commit -qm init

expect_fail_with "A scan set of zero is not a pass" \
	"an empty scan set fails rather than passing vacuously" \
	-- "$HERE/address-checksum-gate.sh" --root "$EMPTYREPO" scan
expect 0 "--allow-empty turns that silence into a stated decision" \
	-- "$HERE/address-checksum-gate.sh" --root "$EMPTYREPO" --allow-empty scan
expect 2 "an unknown argument is rejected outright" \
	-- "$HERE/address-checksum-gate.sh" --root "$EMPTYREPO" --nope

# THE SELF-TEST'S OWN SHARPNESS. Every case above would still pass if the gate's
# matcher silently stopped matching — that is the whole failure class this file
# exists to refuse — so one case blunts the matcher on purpose and requires the
# gate's built-in self-test to SAY SO rather than report a clean tree. Both the
# scan pattern and the exact-length filter move together, so the blunted gate is
# internally consistent and simply sees nothing.
sed 's/{40}/{41}/' "$HERE/address-checksum-gate.sh" >"$WORK/blunt-gate.sh"
chmod +x "$WORK/blunt-gate.sh"
expect_fail_with "the scan matched NOTHING" \
	"a blunted matcher fails the gate's own self-test instead of passing it" \
	-- "$WORK/blunt-gate.sh" --root "$ADDRREPO" selftest

# ---------------------------------------------------------------------------
section "sizes.sh"

# sizes.sh — EIP-170 and EIP-3860, on src/ only.
#
# The gate carries its own seven-case self-test (an oversized src/ runtime, an
# oversized src/ initcode, an oversized harness OUTSIDE src/ that must NOT fail
# the build, an empty artifact set, an artifact set with no src/ contract, an
# interface-only src/ set, and a legal contract). Driving it from here is what
# makes those cases run in CI rather than only when somebody remembers to.
expect 0 "sizes: the gate's own self-test passes" \
	-- "$HERE/sizes.sh" selftest

# The scope decision read from a real artifact tree. src/ inside the limits and a
# harness far outside them must be a PASS — that is the whole change, and it is
# asserted against artifacts rather than against the argument list.
SIZEREPO="$WORK/sizerepo"
mkdir -p "$SIZEREPO"
"$HERE/sizes.sh" --root "$SIZEREPO" --out out selftest >/dev/null 2>&1 || true
python3 - "$SIZEREPO/out" <<'PY'
import json
import os
import sys

out = sys.argv[1]
# A legal src/ contract, and two harnesses over both limits by more than twice.
for source, name, runtime, initcode in (
    ("src/Token.sol", "Token", 7000, 9000),
    ("test/Properties.sol", "Properties", 25044, 26084),
    ("test/Token.t.sol", "TokenTest", 53113, 53170),
):
    directory = os.path.join(out, os.path.basename(source))
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, name + ".json"), "w") as handle:
        json.dump(
            {
                "bytecode": {"object": "0x" + "00" * initcode},
                "deployedBytecode": {"object": "0x" + "00" * runtime},
                "metadata": {"settings": {"compilationTarget": {source: name}}},
            },
            handle,
        )
PY

expect 0 "sizes: a legal src/ contract beside oversized harnesses passes" \
	-- "$HERE/sizes.sh" --root "$SIZEREPO" check

# And the gate still says no when the contract that IS deployed is too big.
python3 - "$SIZEREPO/out" <<'PY'
import json
import os
import sys

directory = os.path.join(sys.argv[1], "Token.sol")
os.makedirs(directory, exist_ok=True)
with open(os.path.join(directory, "Token.json"), "w") as handle:
    json.dump(
        {
            "bytecode": {"object": "0x" + "00" * 26000},
            "deployedBytecode": {"object": "0x" + "00" * 25000},
            "metadata": {"settings": {"compilationTarget": {"src/Token.sol": "Token"}}},
        },
        handle,
    )
PY

expect_fail_with "exceeds EIP-170" \
	"sizes: an oversized src/ contract is rejected, and says which limit" \
	-- "$HERE/sizes.sh" --root "$SIZEREPO" check

expect 2 "sizes: an unknown argument is rejected outright" \
	-- "$HERE/sizes.sh" --nope

# ---------------------------------------------------------------------------
printf '\n\033[1;34m==>\033[0m %d passed, %d failed\n' "$pass" "$fail"
[ "$fail" = "0" ] || exit 1
echo "PIPELINE SELF-TEST: PASS"
