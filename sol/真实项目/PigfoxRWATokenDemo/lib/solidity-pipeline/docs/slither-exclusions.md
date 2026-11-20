# Slither exclusions — every one of them, and why

`slither.config.json` at the root of this repo is the **only** Slither
configuration any pigfox contract repo uses. Consuming repos do not carry their
own copy and do not add their own exclusions: an exclusion that is not written
down here does not exist.

The gate is `fail_on: low`. Anything Slither reports at **low severity or above**
fails the build. Informational and optimization findings are still printed —
`exclude_informational` is deliberately `false` — they just do not fail the job.

## Path filters

| Filter | Reason |
| --- | --- |
| `lib/` | Third-party code we do not own: OpenZeppelin, forge-std, and this pipeline itself when vendored as a submodule. Findings here are upstream's to fix, and failing on them would make an unrelated dependency bump turn an unchanged tree red. |
| `test/` | Test and fuzz harnesses are not the artifact under test. They deliberately do things production code must not — unchecked transfers, hardcoded actors, permissive access — because that is how they reach the states a property needs. |
| `script/` | Deployment and drill scripts are operator tooling, run by a human with a key, never by an untrusted caller. They are covered by review and by the live-chain rehearsal, not by static analysis aimed at attacker-reachable code. |

`exclude_dependencies: true` is the same argument as `lib/`, applied to whatever
crytic-compile classifies as a dependency rather than to a literal path.

## Detector exclusions

Each of these is excluded for the whole estate. If one of them ever needs to be
re-enabled, it is re-enabled here, once, for everybody.

| Detector | Reason |
| --- | --- |
| `naming-convention` | Style, not safety, and twice unactionable. `src/Verifier.sol` in the zk repos is generated verbatim by snarkjs; its identifiers are not ours to rename and the next circuit build would undo the edit. In `rwa-tokenization-demo` it fires on `RWAToken.decimals`/`name`/`symbol` — names **ERC-20 fixes in lower case**, so "fixing" them would break every ERC-20 consumer — and on immutable registry handles that read most naturally in `mixedCase` and mirror the ERC-3643 naming. Enabling it would mean permanently excluding whole files instead, which hides more than it shows. |
| `too-many-digits` | Fires on the large literals that are unavoidable in this estate: BN254 field moduli, `1e18`-scale amounts, and verification-key constants. All of them are either generated or checked by a test that computes the same value independently. |
| `solc-version` | Every repo pins an exact `solc` in `foundry.toml` (`0.8.28`). Slither's preference for a version range is the opposite of what a reproducible build wants. The pin is the control; this detector argues against it. |
| `assembly` | Groth16 verification is inline assembly by construction — snarkjs emits it and the BN254 precompile calls have no Solidity-level equivalent. Reporting the presence of assembly says nothing about whether it is correct; the property fuzzers and the real-proof tests are what establish that. |
| `incorrect-return-in-assembly` | Same generated verifier. The pattern Slither objects to is snarkjs's `return`-from-assembly idiom, which is correct in context and byte-identical to what the circuit build produces. |
| `missing-inheritance` | Fires when a contract's surface happens to match an interface it does not declare. In this estate the interfaces are declared where they are load-bearing (`IGasDemo`, `IVerifier`) and the remaining matches are coincidence. |
| `low-level-calls` | The escrow settles by `call{value:}` deliberately: `transfer` and `send` carry a 2300-gas stipend that breaks payouts to contract recipients. The return value is checked at every site, which is the actual safety requirement. |
| `reentrancy-events` | See below — this one is worth reading before you trust it. |
| `timestamp` | Fires on any comparison involving `block.timestamp`. Every use in the estate is a **freshness window measured in days**, not an edge a validator's few seconds of skew can cross: `PriceOracle`'s staleness check (`block.timestamp - updatedAt > maxAge`), and `ZKComplianceRegistry`'s credential expiry (`expiry <= block.timestamp` on redemption, `verifiedUntil[account] > block.timestamp` on verification). In the KYC registry that comparison **is the product** — a credential lapses when its expiry passes — and the semantics are specified in that repo's `SECURITY.md`. A detector that cannot distinguish "this turns on a 15-second edge" from "this asks whether a credential expired last month" reports the second as if it were the first. |
| `incorrect-equality` | See below. This one is **Medium**, so excluding it is the largest concession in this file and it is scoped by argument, not by convenience. |

### `incorrect-equality` in particular

Slither's "dangerous strict equality" detector exists for a real bug: comparing a
balance or a timestamp with `==` when an attacker can push the value *past* the
target so the equality never holds. Excluding a **Medium** detector estate-wide
therefore needs an argument, not a preference.

The argument is that every occurrence in this estate is a **sentinel** check, not
an economic one:

```solidity
// src/PriceOracle.sol
function latestPrice() external view returns (uint256 currentPrice, uint256 at) {
    if (updatedAt == 0) revert NoPrice();   // "no price has ever been pushed"
    return (price, updatedAt);
}
```

`updatedAt` is zero in exactly one circumstance — `setPrice` has never run — and
it is assigned `block.timestamp`, which is never zero on a live chain. There is
no value to skip past: the comparison is "initialised or not", spelled with the
zero value because Solidity has no null.

The alternative in source is a separate `bool initialised`, which is a storage
change and therefore a redeploy — and per the pipeline's failure taxonomy a
static-analysis finding is not a reason to redeploy a contract that behaves
correctly.

What is given up: if a future contract compares a balance with `==` in economic
logic, this detector will not catch it. That is a real gap and it is the reason
this entry names the exact code it was granted for. A new `==` on a mutable
economic quantity is a review question, and this file is where the fact that the
detector is off must be rediscovered.

**This exclusion replaces a silent one.** `rwa-tokenization-demo` carried
`timestamp,incorrect-equality` in its own `slither.config.json` with no reason
recorded anywhere — which is exactly the failure mode this document exists to
prevent. Adopting the pipeline moved it here, in the open.

### `reentrancy-events` in particular

This detector reports one thing only: an event was emitted **after** an external
call. Its consequence is that an off-chain observer could, under reentrancy, see
events in an unexpected order. It says nothing about whether funds or state are
safe.

Slither grades the reentrancy family separately, and the three that *are* about
state remain on at full strength:

| Detector | Severity | Status |
| --- | --- | --- |
| `reentrancy-eth` | High | **enabled** |
| `reentrancy-no-eth` | Medium | **enabled** |
| `reentrancy-benign` | Low | **enabled** |
| `reentrancy-events` | Low | excluded |

It is excluded because it is unactionable by construction for a whole class of
contract in this estate. `GasRace.race` measures two contracts and then emits the
figures; the figures do not exist until those calls return, so the event
*cannot* precede them. Any measure-then-report contract has the same shape. The
alternative to excluding it is a per-file `slither-disable-next-line`, which this
document forbids for good reason, or leaving a permanent known-failing finding,
which trains everyone to ignore the output.

Excluded on the strength of the table above. If a future contract emits an event
after a call to an **untrusted** address and the ordering matters to a consumer,
that is a design review question, not something this detector would have caught
in a useful way.

## What is NOT excluded

Nothing else. In particular state-affecting reentrancy, uninitialized state,
arbitrary-send, unchecked transfers, shadowing, and the whole high/medium tier
run at full strength on `src/`. A finding there is a finding, and the build
stops.

`cyclomatic-complexity` is left ON deliberately even though it currently fires on
`GasRace._measure` (12). It is Informational, so it prints without failing the
build — which is exactly the policy: informational findings are visible, not
fatal. Silencing it would remove a signal that costs nothing to carry.

## Adding an exclusion

1. Add the row above with a reason that would convince a reviewer who did not
   write the code.
2. Add the detector to `detectors_to_exclude` in `slither.config.json`.
3. Say so in the pull request. A silent config edit is the failure mode this
   file exists to prevent.

Per-file suppressions are not used. `// slither-disable-next-line` scattered
through the source is exactly the "silently configured away" pattern this
document forbids: it is invisible from the config, invisible from CI output, and
survives long after the reason for it has gone.
