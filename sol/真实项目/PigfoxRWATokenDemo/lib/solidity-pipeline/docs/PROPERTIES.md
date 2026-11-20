# The Properties.sol convention

Every pigfox contract repo has exactly **one** `test/Properties.sol`. It holds a
contract `Properties` extending [`PigfoxProperties`](../src/PigfoxProperties.sol),
and it is the single source of truth for that repo's invariants.

Three engines drive that same contract:

| Engine | How it reaches the properties |
| --- | --- |
| Foundry | `test/Invariants.t.sol` deploys `Properties` and asserts each `echidna_*` predicate directly, so the invariants run in the normal `forge test` suite too. |
| Echidna | `echidna . --contract Properties --config echidna.yaml`, `testMode: property`. |
| Medusa | `medusa fuzz --config medusa.json`, `targetContracts: ["Properties"]`, `testPrefixes: ["echidna_"]`. |

One property file, three engines. A property cannot hold in one and quietly rot
in another, and a bug found by one is reachable by the rest.

## Why the count is declared

The dangerous failure in property fuzzing is not a property that fails loudly. It
is a property that stops being **registered**, because then the engine walks a
smaller set and reports green. It has happened in this estate: a stale
`crytic-export/` shrank a five-property set to four and the job passed.

So the count is stated as a literal and three independent things must agree with
it before a build passes:

1. `pigfoxPropertyCount()` — the harness's own declaration, in Solidity.
2. The static count of `function echidna_` declarations in the source.
3. What Echidna and Medusa each **actually registered at runtime**.

`scripts/property-count.sh` checks (1) against (2) and the CI input, and (3)
separately for each engine. Any disagreement is a hard failure, and so is an
engine output the script cannot parse — "found zero, expected zero" must never
read as a pass.

Adding or removing a predicate therefore takes three edits in one commit: the
predicate, the literal, and the workflow's `expected-properties`. That is the
point. It cannot drift by accident.

## Shape of a harness

```solidity
// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import {PigfoxProperties} from "pipeline/PigfoxProperties.sol";

contract Properties is PigfoxProperties {
    // --- the system under test, deployed by the harness itself -------------
    // No cheatcodes: Echidna and Medusa have none. Anything the harness needs
    // — distinct senders, funded actors, a mock verifier — it constructs.

    function pigfoxPropertyCount() public pure override returns (uint256) {
        return 4;
    }

    function pigfoxHarnessDescription() public pure override returns (string memory) {
        return "one sentence saying what these invariants prove";
    }

    // --- entry points the fuzzer calls -------------------------------------
    // Public, non-view, taking fuzzed arguments. They bound their inputs and
    // swallow their EXPECTED reverts, so the fuzzer spends its budget on
    // reachable states rather than bouncing off a guard.

    // --- the predicates ----------------------------------------------------
    function echidna_something_always_holds() public view returns (bool) {
        return ...;
    }
}
```

## The reserved `echidna_revert_` prefix

**Never name a predicate `echidna_revert_something`.** Echidna gives that prefix
the opposite meaning to every other predicate: such a property passes only when
the call **reverts**. A normal boolean predicate with that name is therefore
falsified *precisely because it returns true*.

It does not fail in a way that says so. Echidna reports it with an **empty call
sequence**, and its shrinker then crashes trying to minimise a counterexample
that does not exist:

```
[Worker 0] Test echidna_revert_conditions_identical falsified!
  Call sequence:

[Worker 0] Crashed: Prelude.init: empty list ... in Echidna.Shrink
```

That is indistinguishable at a glance from a genuine invariant violation, and it
survives hardcoding the predicate to `return true`. It cost a debugging session
in `gas-optimization`. `scripts/property-count.sh --source` now rejects the
prefix outright, so the next repo gets a one-line error instead.

`failure_conditions` reads the same and collides with nothing.

## Rules the harness follows

- **Predicates are `view` and return `bool`.** No `assert`, no revert. A
  predicate that reverts is indistinguishable from a harness bug.
- **The harness deploys its own world.** Echidna and Medusa have no `vm`. If a
  property needs three distinct senders, the harness builds three forwarder
  contracts and calls through them — it does not `vm.prank`.
- **Entry points bound their inputs.** Fuzzers spend their budget where the
  harness lets them. An unbounded `uint256 amount` mostly tests overflow guards.
- **Expected reverts are swallowed by the entry point, not by the fuzzer.**
  Foundry's `fail_on_revert = true` is then meaningful: a revert reaching the
  invariant runner is a harness bug, not a protocol finding.
- **Sticky flags for flow-level facts.** Some invariants are about a
  *transition*, not a *state* — "no settlement ever credited the arbiter of the
  escrow it settled". Check it in the wrapper, set a sticky `bool`, and have the
  predicate report the flag.
- **Rotate roles.** A fixed party triple can never catch a bug that only appears
  when the same address is buyer in one escrow and arbiter in another.
- **`seqLen` matches Foundry's invariant `depth`.** Set in `echidna.yaml`,
  `medusa.json` and `foundry.toml` to the same number, so all three engines walk
  sequences of the same length.

## The one declared fuzz exclusion: generated Groth16 verifiers

`zk-escrow` and `zk-kyc-pass` both substitute a `test/mocks/MockVerifier.sol`
inside their harness. **The real `src/Verifier.sol` is not driven by either
fuzzer in either repo.** That is deliberate, and this is where it is written
down — an exclusion nobody has argued in writing is indistinguishable from one
nobody noticed. PF-S133 found this one undocumented; PF-S134 records it.

**Why.** A Groth16 proof is not fuzzable input. Valid proofs exist only for
witnesses the prover actually holds, and the search space a fuzzer explores
contains none of them: every random `(pA, pB, pC)` is rejected. Pointing the
engines at the real verifier therefore buys one code path — the rejection — for
the entire campaign budget, while making every settlement path unreachable,
because no proof would ever verify. The mock exists so the engines can reach the
state *behind* verification, which is where the protocol's invariants live.

**What is genuinely exercised, and what is not.** State this precisely; a vague
version of it is how the neighbouring `checkField` claim went stale.

| | real `Verifier.sol` | `MockVerifier` |
| --- | --- | --- |
| Echidna / Medusa | **no** | yes |
| Foundry unit + integration tests | **yes**, with real proofs from a checked-in fixture | yes |
| Slither | **yes** — `filter_paths` covers `lib/`, `test/` and `script/` only, so `src/Verifier.sol` is analysed | n/a |
| `forge lint` | no — the documented `src/Verifier.sol` entry in the repo's `[lint]` `ignore` | n/a |
| 100% coverage gate | no — the one named `--exclude`, printed as `SKIP` | n/a |

So the verifier is not untested; it is *not fuzzed*. `zk-escrow`'s
`ZkRelease.t.sol` and `zk-kyc-pass`'s `RealProof.t.sol` each drive real proofs
through it end to end, including tampered public signals, out-of-range field
elements, off-curve points and zero proofs. Those are the tests that make the
substitution safe to declare, and a repo that adopts the mock without them has
an undefended exclusion rather than a documented one.

**How this differs from the estate's other harness mocks.** It is not the only
mock any predicate depends on — `oracle-health-explorer`'s harness builds
`MockAggregator`, `RevertingAggregator` and `WrongShapeAggregator`, and most of
its verdicts would be unreachable without them. The difference is what is being
stood in for. Those mocks replace **third-party Chainlink aggregators**, which
are not this estate's code and cannot be made stale, empty or misshapen on
demand; nothing in `src/` is hidden by them. `MockVerifier` replaces a contract
that **is** in `src/` and **is** deployed on Base Sepolia, so it is the only
substitution that takes a pigfox contract out of the fuzzers' reach — which is
why it, and not they, needs declaring here.

**What would make this exclusion wrong.** If a harness substituted a mock for a
contract whose own logic the properties are supposed to be about, that is not
this exclusion — that is a hole. The mock here stands in for a *proof system*,
and the invariants are about what happens on either side of verification, not
about the pairing check itself.

## Artifacts: the trap that keeps catching people

`forge coverage` overwrites `out/` with coverage-instrumented artifacts.
crytic-compile consumes them without complaint and registers a property set that
does not match the source. So:

```
rm -rf crytic-export
forge build --force
```

immediately before **every** fuzz run, unconditionally. The reusable workflow
does this in both fuzz jobs even though neither currently runs coverage first,
because a future reorder must not be able to bring the bug back.
