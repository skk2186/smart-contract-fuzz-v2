# PIGFOX SOLIDITY PIPELINE v1

[![CI](https://github.com/pigfox/solidity-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/pigfox/solidity-pipeline/actions/workflows/ci.yml)

The single verification standard for every Solidity contract in the pigfox
estate. One definition of "green", consumed by every contract repo, so a passing
build means the same thing everywhere.

**Standing law: no contract is deployed or demoed until it passes this pipeline.**

## What it runs

Every stage, on every push. There is no fast path and no opt-out — a repo that
skips a stage is a repo whose green means less than the next one's.

| Stage | Gate |
| --- | --- |
| `pipeline` | The submodule is present, and the gates self-test — they can still say no. |
| `lint` | `forge lint` (bare, so `ignore` applies) **and** Solhint on a pinned `npx` — no `package.json`, lockfile or `node_modules` in any repo. Also checks each repo's copied `[lint]` block still matches the canonical one. |
| `no-chain-copy` | No tracked file points the EVM at a copy of a remote chain's state. Scans, then **plants a token and re-scans** to prove the scan still matches. |
| `address-checksum` | Every 20-byte address literal in every tracked file is EIP-55 valid, judged by `cast`. Plants a mis-cased address and re-scans, and refuses an empty scan set. |
| `properties` | The harness's declared property count agrees with its source. |
| `fmt` | `forge fmt --check`, on a **pinned** Foundry. |
| `forge` | `forge build` over the whole tree, the **deployable-bytecode size gate** (EIP-170 and EIP-3860, on `src/` only — scope read from each artifact's `compilationTarget`, so a stale `out/` cannot widen it), `forge test -vvv` (unit + fuzz + invariants), then **100% line / statement / branch / function coverage on `src/`**. |
| `slither` | Static analysis, `fail-on: low`. Every exclusion is written down with a reason. |
| `echidna` | Property fuzzing, in-memory EVM, 100k sequences of depth 64. |
| `medusa` | The same property file, a second independent engine. |
| `pipeline green` | One required check for branch protection, so adding a stage never needs a settings change in every consuming repo. |

Both fuzzers additionally assert the **number of properties they registered**.

## Why the property count is a gate

The dangerous failure in property fuzzing is not a property that fails. It is a
property that stops being *registered* — a rename, a stale `crytic-export/`,
coverage-instrumented artifacts left in `out/`, a `testPrefixes` mismatch. The
engine then walks a smaller set and reports green.

That has happened in this estate: a stale artifact shrank a five-property set to
four and the job passed. Green on four is not green.

So the count is declared as a literal in the harness and three independent things
must agree with it: the Solidity declaration, the static count of `echidna_*`
predicates in the source, and what each engine actually registered at runtime.
Adding a property takes three edits in one commit. It cannot drift by accident.

The same principle applies one level up: `scripts/selftest.sh` drives every gate
in this repo against inputs whose correct verdict is known, **including the ones
that must be rejected**. A gate that has quietly stopped working reports the same
green as a clean tree.

### A gate must be able to say why

The self-test asserts the **message**, not just the exit code, and that
distinction is not academic. The first version checked `rc == 1` only, which let
a real defect sit in the suite looking healthy: `property-count.sh` was dying
mid-parse under `set -e` — a no-match `grep` inside a command substitution,
`pipefail`, and the script was gone before it could print anything. A crash and a
deliberate rejection both exit 1, so the test went green.

CI inherited the same silence. zk-escrow's `properties` job reported, in full:

```
##[error]Process completed with exit code 1.
```

No stdout, no stderr, no clue. The underlying cause was that `forge fmt` wraps a
long `return` value onto the following line, and the parser was line-based — a
perfectly valid declaration the gate could not see. It only ever showed up in the
one repo whose harness description was long enough to get wrapped.

Two rules came out of it, and both are enforced here rather than remembered:

1. Any `grep` in a command substitution that is *allowed* to match nothing ends
   in `|| true`, so the caller reports the condition instead of `set -e` killing
   the script silently.
2. Every rejection case in `selftest.sh` asserts the sentence the user will read.
   `expect_fail_with` exists for exactly this, and it prints
   `<no output at all — this is the silent-crash failure mode>` when a command
   fails without explaining itself.

## Direct-chain doctrine

Everything in this estate talks to **Base Sepolia (84532) directly**, or runs in
a pure in-process EVM it builds itself from source. Nothing points the EVM at a
copy of a remote chain's state. `scripts/no-chain-copy-gate.sh` enforces that
mechanically over tracked files, and self-tests before it is believed.

The in-memory local EVM that `forge test`, Echidna and Medusa construct is **in
scope and required**. Those engines build fresh contracts from source
in-process, reach no network, and stand in for nothing — they are not a
substitute for a live deployment, they are how the invariants get proved before
one happens. Deployments, upgrades and end-to-end wallet flows are live 84532,
always.

The gate bans its tokens **literally, including inside a negation**. Write the
doctrine as an absence, not as a disclaimer that names what it forbids.

## Address casing is a runtime failure, not a style question

A pinned address is the `to` of a real transaction. viem — the signer behind every
wallet flow in this estate — validates EIP-55 **before** it estimates gas, and
refuses an address whose capitalisation does not match its checksum:

```
EstimateGasExecutionError: Address "0xd6F7…19b" is invalid.
- Address must match its checksum counterpart.
```

Three gas-demo addresses were mis-cased from the day they were pinned, imported
that way from a `deployments/base-sepolia.json` in this estate. Nothing noticed
until two live wallet takes died on them, sixty seconds at a time, with the page
reporting a nonce problem it did not have.

`scripts/address-checksum-gate.sh` guards the origin, where the bytes are written
down first. Three things about it are the point:

- **The oracle is the toolchain's own.** The correct casing comes from
  `cast to-check-sum-address`, so the gate cannot drift from the thing it
  protects by re-deriving EIP-55 itself. `cast` is called with exactly one
  argument — a second argument is a chain id and selects EIP-1191, a *different*
  checksum from the one a wallet applies.
- **The scan set is built by construction**, not from a list of files somebody
  remembered to name. Every 20-byte hex literal in every tracked file. A named
  target is a hypothesis: the incident was found in four places and the repo held
  addresses in three more. Longer hex runs — a 32-byte hash, a keccak topic, a
  bytecode blob — are matched whole and discarded, so nothing bites the first
  forty characters of something that is not an address.
- **An empty scan set fails.** Zero hits is the shape a broken matcher makes and
  it is indistinguishable from a clean tree. A repo that genuinely pins no
  addresses says so with `--allow-empty`; silence never stands in for a decision.

An all-lower-case address asserts no checksum and passes, because that is exactly
what viem accepts. Anything carrying an upper-case hex letter asserts one, and the
assertion has to be true.

## Coverage: 100%, with named exclusions only

All four metrics, every file under `src/`. The gate fails on a shortfall, on a
report it cannot parse, and on a **stale exclusion** — one that matches no row —
because a hole that reads as a documented decision is worse than an obvious gap.

The estate has exactly two exclusions, and they are the same file in the two zk
repos: `zk-escrow/src/Verifier.sol` and `zk-kyc-pass/src/Verifier.sol`. Both are
generated verbatim by snarkjs from that repo's proving key. Their residual
uncovered lines are the assembly early exits taken when the BN254 precompiles
themselves report failure, which cannot be provoked from a test — inputs that are
merely wrong are rejected by the reachable `checkField` branch, which *is*
covered. Each is excluded **by name**, printed as `SKIP` in the log, and each
verifier is still exercised end-to-end by real Groth16 proofs — `test/ZkRelease.t.sol`
in zk-escrow, `test/RealProof.t.sol` in zk-kyc-pass. See
[docs/ADOPTING.md](docs/ADOPTING.md).

The two zk repos are the only ones that declare an exclusion. Every other
consuming repo runs with `no exclusions`, and every file under its `src/` is at
100% on all four metrics. `consumers.json` records which is which.

## Failure taxonomy

What broke determines what you fix. This is the standing rule, not a suggestion.

| Trigger | Action |
| --- | --- |
| **Coverage shortfall** — the code is correct, a path is untested | Write the missing test. No source change, **no redeploy**. Redeploying identical bytecode fixes nothing. |
| **Tooling or config failure** | Fix the pipeline or the config. **Never edit a contract to satisfy a broken tool.** |
| **Test or property failure** — the contract behaves wrongly, or an invariant is violated | The deployed contract is not demo-worthy. Fix the **source**, then: a non-proxy contract is **redeployed** to 84532 and verified on Basescan; a **UUPS proxy has its implementation upgraded** — never replaced, because the proxy holds the history and upgrading is what it is for. Rehearse an upgrade against throwaway contracts first. Then re-run the entire pipeline. |
| **Any address changed** | It is not done until every reference is updated: `deployments/*.json`, the repo README, Basescan links, and every pinned address in the consuming site's handlers, JS modules and E2E specs. |

## Using it

See [docs/ADOPTING.md](docs/ADOPTING.md). In short:

```bash
git submodule add https://github.com/pigfox/solidity-pipeline lib/solidity-pipeline
```

```yaml
jobs:
  pipeline:
    uses: pigfox/solidity-pipeline/.github/workflows/solidity.yml@v1
    with:
      expected-properties: 4
```

The submodule carries the shared harness base, the gate scripts and the Slither
config at a commit you pin — which also means you run **byte-identical gates
locally**, not an approximation of CI.

## Layout

```
.github/workflows/solidity.yml   the reusable workflow (workflow_call)
.github/workflows/ci.yml         this repo's own build: gate self-test, shellcheck, forge
slither.config.json              the ONE Slither config in the estate
.solhint.json                    the ONE Solhint config in the estate — ungated
consumers.json                   canonical list of repos on the pipeline
src/PigfoxProperties.sol         shared harness base; declares the property count
config/echidna.yaml              template — the two fuzzers resolve paths from CWD
config/medusa.json               template
config/lint.toml                 canonical [lint] block, copied into each repo
scripts/coverage.sh              100% coverage gate, named exclusions, fails on unparseable
scripts/sizes.sh                 EIP-170 + EIP-3860 on src/ only, scope from compilationTarget, with self-test
scripts/property-count.sh        static + runtime property-count agreement
scripts/no-chain-copy-gate.sh    direct-chain doctrine gate, with self-test
scripts/address-checksum-gate.sh EIP-55 casing gate over every tracked address literal, with self-test
scripts/selftest.sh              drives every gate against known-bad inputs
scripts/consumers-check.sh       README repo table vs consumers.json, self-testing
scripts/lint-config-check.sh     each repo's [lint] block vs config/lint.toml, self-testing
scripts/stages-check.sh          the stage table above vs the workflow's jobs, in order, self-testing
docs/PROPERTIES.md               the Properties.sol convention
docs/ADOPTING.md                 how a repo consumes this
docs/slither-exclusions.md       every exclusion, with a reason
docs/solhint-rules.md            every Solhint rule exclusion, with a reason
docs/CONSUMERS.md                the consumer list, and the limits of guarding it
docs/forge-lint-rules.md         every forge lint exclusion, with a reason
```

## Pinned toolchain

Every tool is pinned. An unpinned toolchain turns an unchanged tree red on
somebody else's release day and — worse — can turn a red tree green.

| Tool | Pin |
| --- | --- |
| Foundry | `v1.4.2` |
| Slither | `0.11.3` |
| crytic-compile | `0.3.10` |
| Echidna | `2.2.6` |
| Medusa | `v1.5.1` |
| solc | `0.8.28`, in each repo's `foundry.toml` |

## Repos on the pipeline

| Repo | What it is |
| --- | --- |
| [gas-optimization](https://github.com/pigfox/gas-optimization) | Four gas techniques, naive vs optimized, raced on-chain |
| [rwa-tokenization-demo](https://github.com/pigfox/rwa-tokenization-demo) | Permissioned real-world-asset token with identity gating |
| [zk-kyc-pass](https://github.com/pigfox/zk-kyc-pass) | Groth16 KYC attestation, nullifier-bound |
| [zk-escrow](https://github.com/pigfox/zk-escrow) | UUPS escrow with zk release and arbiter dispute settlement |
| [interest-rate-model](https://github.com/pigfox/interest-rate-model) | Kinked borrow/supply rate curve, continuous at the kink |
| [oracle-health-explorer](https://github.com/pigfox/oracle-health-explorer) | Chainlink feed health verdicts with per-feed max age |
| [ai-parametric-insurance](https://github.com/pigfox/ai-parametric-insurance) | Parametric claims settled by a 2-of-3 multi-model adjudication oracle |
| [deposit-dispute](https://github.com/pigfox/deposit-dispute) | Per-item security-deposit split, adjudicated 2-of-3 by three pinned models that never name an amount |

This table is checked against `consumers.json` by `scripts/consumers-check.sh`,
which CI runs — it went stale once, listing four repos when six were on the
pipeline. [docs/CONSUMERS.md](docs/CONSUMERS.md) records what that guard does and
does not catch.

## Licence

MIT.
