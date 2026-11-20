# Adopting the pipeline in a contract repo

Six steps. Nothing here is copy-pasted: the gate logic lives in this repo and is
consumed, so a fix lands once and every repo gets it.

## 1. Vendor the pipeline as a submodule

```bash
git submodule add https://github.com/pigfox/solidity-pipeline lib/solidity-pipeline
```

HTTPS, not SSH, so CI can clone it without a deploy key.

The submodule gives you three things at a pinned commit: the shared Solidity
base, the gate scripts, and `slither.config.json`. It also means you run
**byte-identical gates locally** — the same `coverage.sh` CI runs.

## 2. Remap the shared base

In `foundry.toml`:

```toml
remappings = [
    "pipeline/=lib/solidity-pipeline/src/",
    # ... your existing remappings
]
```

## 3. Write `test/Properties.sol`

See [PROPERTIES.md](PROPERTIES.md). The contract extends `PigfoxProperties` and
declares its own property count and description.

## 4. Copy the two fuzzer configs

```bash
cp lib/solidity-pipeline/config/echidna.yaml .
cp lib/solidity-pipeline/config/medusa.json .
```

These are the one deliberate copy, and the header of each says why: both tools
resolve corpus and target paths relative to the working directory, so a config
living under `lib/` would write corpora into the submodule. Only the values
marked tunable may differ between repos.

`foundry.toml` needs its invariant `depth` to match `seqLen` in `echidna.yaml`
and `callSequenceLength` in `medusa.json`.

## 5. Call the reusable workflow

`.github/workflows/ci.yml`:

```yaml
name: CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  pipeline:
    uses: pigfox/solidity-pipeline/.github/workflows/solidity.yml@v1
    with:
      expected-properties: 4
```

Add any repo-specific jobs — a Go agent, a circuit build — as siblings in the
same file. The pipeline covers Solidity; it does not try to be everything.

Inputs worth knowing:

| Input | Use it when |
| --- | --- |
| `expected-properties` | Always. Required. |
| `coverage-exclusions` | A src/ file is genuinely untestable — see below. |
| `fmt-paths` | The tree has pre-existing formatting violations you are not fixing yet. Narrow it and say so in the README. |
| `properties-source` | The harness is not at `test/Properties.sol`. |
| `pipeline-ref` | You call the workflow at something other than `@v1`. Keep it equal to the ref in your `uses:` line — it is the fallback source for a gate script your submodule pin is too old to carry. |
| the version pins | A repo needs to move a tool ahead of the estate. Prefer moving the estate. |

### When a stage lands, bump your submodule

The `uses:` ref pins the orchestration; the submodule pins the gate SCRIPTS. When
a new stage lands in the pipeline those two move at different times, and the
window between them is real: the tag moves for every consumer at once, while each
repo bumps its own pin when it next gets touched.

A stage must not turn every consumer red in that window, and it must not be
skipped either — a gate that did not run may not report green. So a job whose
script the submodule does not yet carry takes it from `pipeline-ref` instead and
prints a `::warning::` naming the stale pin. That is a nag, not a resting place:

```bash
git submodule update --remote lib/solidity-pipeline
git add lib/solidity-pipeline && git commit -m "chore(pipeline): bump the submodule"
```

Until you do, CI is running a gate whose bytes are not the ones you run locally —
which is the one property this whole arrangement exists to give you.

## 6. Delete what the pipeline replaced

Once the shared path is green in that repo, remove the local `slither.config.json`
and any local copy of `coverage.sh` / `no-chain-copy-gate.sh`. **Not before.** A
repo with both is a repo where nobody can tell which one ran.

---

## Coverage exclusions

`coverage-exclusions` takes a comma-separated list of `src/` paths. Two rules:

1. **Named, never hidden inside a percentage.** The gate prints `SKIP` for each
   one, so a reader of the CI log sees exactly what was not covered.
2. **A stale exclusion fails the build.** An exclusion matching no row in the
   report is an error, not a no-op — otherwise a renamed file leaves a hole that
   still reads as a documented decision.

Every exclusion is also justified in prose in the consuming repo's docs. The
estate currently has exactly two — the same generated file in each of the two zk
repos, and nothing else:

- **`zk-escrow/src/Verifier.sol`** — generated verbatim by snarkjs from the
  proving key. Its residual uncovered lines are the inline-assembly early exits
  taken when the BN254 `ecAdd` / `ecMul` / pairing precompiles themselves report
  failure. Those cannot be made to fail from a test: inputs that are merely wrong
  are rejected by the reachable `checkField` branch, which *is* covered. Reaching
  the rest would need a broken EVM, not a broken proof. The verifier is still
  exercised end-to-end by real Groth16 proofs in `test/ZkRelease.t.sol`.
- **`zk-kyc-pass/src/Verifier.sol`** — the same generated artifact, from that
  repo's own proving key, excluded for the same reason and unreachable for the
  same reason. Its verifier is exercised end-to-end by real Groth16 proofs in
  `test/RealProof.t.sol`.

The two zk repos are the only ones that declare an exclusion. Every other
consuming repo's gate runs with `no exclusions` and every `src/` file is at 100%
on all four metrics. `consumers.json` at the repo root is the canonical list of
which repos are on the pipeline and what each one excludes.

## Formatting exceptions

**There are none.** Every consuming repo takes the `fmt-paths` default of
`src test script`, and none passes the input at all.

This section used to carry a table with one row: `zk-escrow` narrowed `fmt-paths`
to `test` because `src/EscrowUpgradeable.sol`, `script/Deploy.s.sol` and
`script/RecoveryDrill.s.sol` held pre-existing line-wrapping violations. PF-S123
formatted those three files and removed the input, so the carve-out is gone rather
than merely documented.

The row is deleted rather than kept "for history" on purpose. A table listing an
exception that no longer exists reads as a live decision, and a stale enumeration
carries the same authority as a true one — the rot class this pipeline already
fails the build over for coverage exclusions. If an exception ever returns it gets
a row again, and `consumers.json` carries the same fact in machine-readable form.

## Running the gates locally

```bash
lib/solidity-pipeline/scripts/coverage.sh
lib/solidity-pipeline/scripts/property-count.sh --source test/Properties.sol --expected 4
lib/solidity-pipeline/scripts/no-chain-copy-gate.sh all
lib/solidity-pipeline/scripts/address-checksum-gate.sh all

rm -rf crytic-export && forge build --force
echidna . --contract Properties --config echidna.yaml | tee echidna-output.txt
lib/solidity-pipeline/scripts/property-count.sh --engine echidna --output echidna-output.txt --expected 4

rm -rf crytic-export && forge build --force
medusa fuzz --config medusa.json 2>&1 | tee medusa-output.txt
lib/solidity-pipeline/scripts/property-count.sh --engine medusa --output medusa-output.txt --expected 4
```

The `rm -rf crytic-export && forge build --force` before each fuzz run is not
optional. `forge coverage` leaves instrumented artifacts in `out/` that
crytic-compile will consume without complaint, registering a property set that
does not match your source.

### Slither is in this scope too, and it fails differently

**Slither goes through crytic-compile exactly as the fuzzers do**, so it needs the
same clean rebuild. This was left implicit and cost a real failure: running
Slither straight after a coverage run in zk-escrow produced

```
AssertionError: Contract Script not found
```

and exit 1 — while CI read green, because CI builds cleanly before its Slither
job. That is worse than a wrong finding. It is a **parse failure wearing the same
exit code as a finding**, so anything reading only the status concludes Slither
disagrees with CI about the contracts rather than that it never analysed them.

So the rule is not "before each fuzz run" but **before anything that reads
`out/` through crytic-compile** — Slither, Echidna and Medusa alike:

```bash
rm -rf crytic-export && forge build --force
slither . --ignore-compile --config-file lib/solidity-pipeline/slither.config.json
```

### The same stale artifacts break `forge script`, and say nothing useful

The fuzzers are not the only consumer that trusts `out/`. A deploy can fail the
same way, and its error names nothing:

```
Error: No contract bytecode
```

That is the whole message. No file, no contract, no hint that artifacts are
involved. It happened in PF-S124 deploying `rwa-tokenization-demo` — the script
compiled fine, `out/Deploy.s.sol/Deploy.json` existed, and `forge script` still
refused, both in simulation and with `--broadcast`.

The fix is `forge clean && forge build`, after which the identical command
succeeded. Worth reaching for early, because the error invites you to go looking
at the script, the RPC or the key instead — none of which are the problem.

**Run `forge clean` before any deploy that follows a coverage or lint run in the
same working tree.** It costs one rebuild and removes a whole class of confusing
failure. The rule generalises past the two cases now recorded here: anything that
reads `out/` can be poisoned by artifacts a different command left there, and the
symptom never mentions `out/`.
