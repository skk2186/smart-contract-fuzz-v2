# Solhint rules — every suppression, and why

`.solhint.json` at the root of this repo is the **only** Solhint configuration any
pigfox contract repo uses. Consuming repos do not carry their own copy and do not
add their own rule exclusions: a rule turned off that is not written down here
does not exist.

Same discipline as [slither-exclusions.md](slither-exclusions.md), for the same
reason. A silent config edit is the failure mode both documents exist to prevent.

> **Status: adopted, not gated.** This config is inert data today. No workflow
> runs Solhint and no repo fails because of it. See [Rollout](#rollout) — gating
> before every repo is clean would fail all six at once, which is how a new gate
> gets disabled instead of obeyed.

## What Solhint is for here, and what it is not

Solhint is a **style and consistency** linter. It is not a second opinion on
security, and it is not treated as one.

Security in this estate is owned by Slither at `fail-on: low`, by Echidna and
Medusa against a declared property set, and by a 100% coverage gate on `src/`.
Those look at reachability, state and value flow. Solhint parses a single file
and matches patterns in its syntax tree; it has no cross-contract model and no
notion of what an attacker can reach.

That distinction is not theoretical. Measured against this estate, on the
`solhint:recommended` ruleset, Solhint's incremental find rate on top of what
already runs was **zero**: 3,006 findings across the six repos, of which the
number that indicated a defect Slither and the fuzzers had missed was none. The
breakdown of that measurement is in [What the measurement found](#what-the-measurement-found).

So Solhint earns its place on documentation and consistency — a public function
whose parameters are undocumented, a state variable with implicit visibility, a
pragma that has drifted off the pinned compiler. Those are real and worth
catching. Expecting more than that from it would be miscalibrated.

## Scope: `src/` only

Solhint runs against `src/`, never `test/` or `script/`. This mirrors
`filter_paths` in `slither.config.json` exactly, and for the same reason: the
deployed artifact is what the gate is about. Test and fuzz harnesses deliberately
do things production code must not, because that is how they reach the states a
property needs.

For Solhint the argument is stronger still, because a naming linter and Foundry
disagree by construction:

- Foundry discovers tests by the `test`, `testFuzz` and `invariant_` prefixes.
- The pipeline's standing law requires property predicates to be named
  `echidna_*`, and forbids `echidna_revert_*`.

Both are snake_case by mandate, and `func-name-mixedcase` flags every one of
them. Pointing Solhint at `test/` produced **471** naming findings that could
only be resolved by breaking test discovery. Scoping to `src/` removes all 471
without a single suppression — which is why none of the naming rules that fire
only in `test/` appear in the table below.

The scope is expressed by the paths passed on the command line, the same way
`fmt-paths` scopes `forge fmt --check`. It is not encoded in this file, because
Solhint has no `filter_paths` equivalent in config.

## Rule exclusions

Each of these is off for the whole estate. If one ever needs to come back, it
comes back here, once, for everybody.

| Rule | Reason |
| --- | --- |
| the `gas-*` family | The seven `solhint:recommended` enables: `gas-calldata-parameters`, `gas-custom-errors`, `gas-increment-by-one`, `gas-indexed-events`, `gas-small-strings`, `gas-strict-inequalities`, `gas-struct-packing`. (Solhint ships three more — `gas-length-in-loops`, `gas-multitoken1155`, `gas-named-return-values` — which `recommended` does not enable, so this file does not name them: turning off a rule that is already off is a no-op that reads as a decision. The pinned version is what makes that safe to rely on.) Off for two independent reasons, either of which suffices. **First**, `gas-optimization/src/GasNaive.sol` is deliberately unoptimized — it is the control in a measured comparison, and the differential *is* the product. A linter demanding it be optimized is asking for the demo to be deleted. **Second**, per the failure taxonomy, a gas or style finding is not grounds to redeploy a contract that behaves correctly, so on every already-deployed contract these findings are unactionable by rule. Gas in this estate is measured, not asserted: `foundry.toml` sets `gas_reports`, `.gas-snapshot` is committed, and CI turns on `gas_snapshot_check` so a regression is a reviewable diff. That is a number from the EVM, not a linter's opinion. |
| `gas-indexed-events` in particular | Included above, but it is worth naming why it is not merely noisy. It fires on `Transfer(address indexed from, address indexed to, uint256 value)` asking that `value` be indexed. **ERC-20 fixes that event signature.** Indexing `value` changes the topic layout and breaks every indexer and consumer that reads the standard event. Same class of finding as Slither's `naming-convention` on `decimals` — the rule is right in general and wrong about a signature the standard nails down. |
| `const-name-snakecase` | Fires on `uint8 public constant decimals = 18;` in `RWAToken` and `KYCToken`. **ERC-20 fixes `decimals` in lower case**; renaming it to `DECIMALS` changes the public getter and breaks every ERC-20 consumer. This is the identical argument already recorded for Slither's `naming-convention`, and it is off for identical reasons. |
| `immutable-vars-naming` | Wants `SCREAMING_SNAKE_CASE` for immutables, which would rename the registry handles — `token`, `identityRegistry`, `assetRegistry`. Those read most naturally in mixedCase and mirror the ERC-3643 naming the RWA repo follows deliberately. Already recorded under Slither's `naming-convention` for the same code. |
| `no-empty-blocks` | Fires on `try target.writeRecord(...) {} catch { reverted = true; }` in `GasRace._measure`. The empty block is the try's success branch: the contract measures gas around a call and records whether it reverted, so there is by construction nothing to do on success — and Solidity requires the block to be there. Unactionable by construction, the same test Slither's `reentrancy-events` had to pass. |
| `import-path-check` | Cannot resolve Foundry remappings. It reports `@openzeppelin/contracts-upgradeable/...` as a path that "doesn't exist" because it resolves against `node_modules`, not against `remappings` in `foundry.toml`. Every one of the 67 findings it produced was a false positive on an import that compiles. A rule that is wrong about every input it sees in this estate is not a rule. |
| `avoid-low-level-calls` | The escrow settles by `call{value:}` deliberately: `transfer` and `send` carry a 2300-gas stipend that breaks payouts to contract recipients. The return value is checked at every site, which is the actual safety requirement. Identical to Slither's `low-level-calls` entry, off for the identical reason. |
| `use-natspec` → `author` only | The `@author` sub-check is off; `title`, `notice`, `param` and `return` stay **on**. An `@author` tag on every contract is ceremony that restates what `git log` records precisely and the tag records approximately — and unlike the other four it tells a reader nothing about what the code does. The rest of the rule is the single most valuable thing Solhint contributes here and is deliberately left at full strength. |

### Configured, not excluded

Two rules are tuned rather than turned off, because their default configuration
is wrong for Solidity 0.8 or for this estate:

| Rule | Setting | Reason |
| --- | --- | --- |
| `func-visibility` | `ignoreConstructors: true` | All 26 findings it produced were constructors, and Solhint's own message says to set this flag. Constructor visibility has been meaningless since 0.7 and specifying it is an error in 0.8. The rule still catches a genuine missing visibility on any other function. |
| `compiler-version` | `0.8.28` | Every `src/` file pins `pragma solidity 0.8.28;` exactly, matching `solc` in each `foundry.toml`. The recommended default is a `^0.8.24` range, which is the opposite of what a reproducible build wants — the exact pin is the control. Set to the exact version so a drifted pragma fails rather than passes. Bump this and the `foundry.toml` pins together, never separately. |

## What is NOT excluded

Everything else in `solhint:recommended` runs at full strength on `src/`:
`state-visibility`, `explicit-types`, `no-console`, `func-name-mixedcase`,
`contract-name-capwords`, `event-name-capwords`, `no-unused-import`,
`no-unused-vars`, `no-global-import`, `imports-on-top`, `duplicated-imports`,
`visibility-modifier-order`, `quotes`, `one-contract-per-file`,
`interface-starts-with-i`, `max-states-count`, `function-max-lines`,
`reason-string`, `constructor-syntax`, `use-forbidden-name`, `avoid-tx-origin`,
`avoid-sha3`, `avoid-suicide`, `avoid-throw`, `avoid-call-value`,
`check-send-result`, `multiple-sends`, `not-rely-on-block-hash`, `reentrancy`,
`no-inline-assembly`, `no-complex-fallback`, `no-unchecked-calls`,
`no-immutable-before-declaration`.

`no-console` is worth calling out: scoping to `src/` is what makes it useful. In
`script/` a `console2` import is the point; in a deployed contract it is a
defect, and the rule now says so without a single false positive.

## Generated verifiers

`src/Verifier.sol` in `zk-escrow` and `zk-kyc-pass` is generated verbatim by
snarkjs from the proving key. Its identifiers, visibility keywords and inline
assembly are not ours to change, and the next circuit build would undo any edit.
It is already excluded from `forge fmt` and `forge lint` (`ignore` in
`foundry.toml`) and from the coverage gate (`coverage-exclusions`).

Solhint gets the same treatment, and for the same reason — but **per repo**, via a
`.solhintignore` in the repo that has the file:

```
src/Verifier.sol
```

Not in this shared config. A shared config that names a path existing in only two
of six repos is a rule about somebody else's tree; the estate keeps
generated-file carve-outs at the site, next to the `foundry.toml` ignores that
already state the reason.

The effect is measured, not assumed: excluding it removes **68 findings** —
56 `state-visibility`, 8 `explicit-types`, 2 `function-max-lines`, 2
`no-inline-assembly` — and those are the *only* findings of those rules anywhere
in the estate. Outside the generated verifiers, `src/` is already clean on all
four.

## What the measurement found

Measured on Solhint **6.2.3**, the pinned version, across all six repos.

The `solhint:recommended` ruleset pointed at `src/`, `test/` and `script/`
reported **3,006** findings. The table below is where they went.

| Step | Findings | What it removed |
| --- | --- | --- |
| `solhint:recommended`, all paths | 3,006 | — |
| scope to `src/` | 542 | test/fuzz harness noise, all 471 Foundry naming findings, `no-console` on scripts |
| exclude generated verifiers | 474 | 68 findings in snarkjs output |
| apply this config | 192 | the gas family, the two ERC-20 naming rules, constructor visibility, unresolvable imports, `@author` |

Everything that survives is `use-natspec` — **192 messages** over **104 distinct
sites** (Solhint reports a missing `@param` twice, once as missing and once as a
name mismatch against the empty set). Per repo:

| Repo | Messages | Distinct sites |
| --- | --- | --- |
| `interest-rate-model` | 0 | 0 |
| `oracle-health-explorer` | 18 | 10 |
| `zk-escrow` | 20 | 11 |
| `gas-optimization` | 25 | 14 |
| `zk-kyc-pass` | 41 | 22 |
| `rwa-tokenization-demo` | 88 | 47 |

Without the per-repo `.solhintignore`, `zk-kyc-pass` is 81 and `zk-escrow` 58.

**Every remaining finding is a missing comment.** Fixing them changes no
statement, no storage layout and no behaviour. What it does change is measured in
[the drift note below](#does-adding-natspec-cause-drift).

## Does adding natspec cause drift?

Measured, not reasoned about. No repo sets `bytecode_hash`, so all six take
Foundry's default (`ipfs`) and a CBOR metadata trailer **is** appended.

A comment-only edit was compiled twice under the estate's exact settings (solc
0.8.28, optimizer on at 200 runs). Result: the runtime object stayed the same
length, and **exactly 32 bytes changed** — the IPFS digest at bytes 200–231 of
243. The executable prefix and the trailing solc-version bytes were
byte-identical. So natspec changes the metadata digest and nothing else.

Then the deployed estate was checked against a fresh build of current source, for
all 15 deployed contracts. Thirteen already differ from what is on chain, in
exactly the same way: 32 bytes, all inside the CBOR trailer, executable code
identical. The two that match byte-for-byte are the two most recently deployed.

That difference is **not** source drift. The verified source Basescan holds was
pulled for three contracts spanning both groups and matches the repo file
byte-for-byte in every case, with identical compiler, optimizer and EVM version.
The cause is the `remappings` list, which feeds the metadata JSON: adopting the
pipeline added `pipeline/=lib/solidity-pipeline/src/`, and in `gas-optimization`
that commit lands *after* the deploy commit. Repos deployed after adoption match;
repos deployed before it do not.

Two things follow, and they point in opposite directions:

- A 32-byte metadata-only difference between repo and chain is already the normal
  state of this estate, has been since the pipeline was adopted, and has caused
  no problem. Basescan verification is a stored record and is unaffected.
- But the **verified source still matches the repo exactly today**, and adding
  natspec is what would end that. The real cost is not bytecode; it is that a
  reader comparing Basescan's source against the repo would find them different.

Which is a decision about provenance, not about safety, and it is recorded here
so the next person does not have to re-measure it.

### Findings that were real, and what happened to them

Three deserve recording rather than silent suppression:

- **`gas-struct-packing` on `rwa-tokenization-demo/src/Redemption.sol:44`** —
  correct. `Request { address holder; uint256 assetId; uint256 amount; bool
  settled; bool exists; }` occupies four slots; moving the two bools up beside
  the address would fit it in three. It is a genuine saving and it is
  **deliberately not actioned**: it is a storage-layout change to a deployed
  contract, and the failure taxonomy is explicit that a gas finding is not
  grounds to redeploy. Recorded here so turning the rule off does not erase the
  knowledge.
- **`reentrancy` ×3 in `zk-kyc-pass/test/Properties.sol:188-190`** — ghost-variable
  bookkeeping after an actor's `exec` call, inside the fuzz harness. Not deployed
  code. Slither already filters `test/` for exactly this reason.
- **`max-states-count` in two `test/Properties.sol`** — harnesses carrying 16 and
  19 ghost variables against a limit of 15. That is what a property harness is.

None of the three is a defect in a deployed contract. That is the measured
version of the claim at the top of this file.

## Rollout

Mirrors the pipeline-summary rollout, and the order is not optional.

1. **Shared config lands, ungated.** ← where the estate is now. `.solhint.json`
   and this document exist; nothing runs them.
2. **Each repo adopts and goes clean.** Add the `.solhintignore` where there is a
   generated verifier, fix the `use-natspec` sites, run
   `solhint -c lib/solidity-pipeline/.solhint.json 'src/**/*.sol'` until it is
   silent. Cheapest first: `interest-rate-model` (already clean),
   `oracle-health-explorer`, `zk-escrow`, `gas-optimization`, `zk-kyc-pass`,
   `rwa-tokenization-demo`.
3. **Only then the gate lands and `v1` moves.** A `solhint` job in
   `solidity.yml`, with the version pinned like every other tool, and a
   `solhint-paths` input defaulting to `src/` for the same reason `fmt-paths`
   exists.

Gating before step 2 finishes fails all six repos at once. A gate that is red on
arrival gets routed around, and then the estate has a rule nobody obeys — which
is worse than not having the rule.

## Adding an exclusion

1. Add the row above with a reason that would convince a reviewer who did not
   write the code. "It is noisy" is not a reason; "it is wrong about this code,
   and here is the code" is.
2. Turn the rule off in `.solhint.json`.
3. Say so in the pull request.

Per-file suppressions are not used. `// solhint-disable-next-line` scattered
through the source is the same "silently configured away" pattern
`slither-exclusions.md` forbids: invisible from the config, invisible from CI
output, and it outlives the reason for it.
